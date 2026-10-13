"""
End-to-End Closed Loop Pipeline
===============================

Orchestrates the full AutoREST workflow for a single ``CalculationTask``:

1.  **Validate** — electron parity check before any file is written.
2.  **Generate** — produce the REST TOML input card.
3.  **Execute** — run REST, monitor progress.
4.  **Parse** — extract structured observables from output.
5.  **Verify** — run scientific QA checks.
6.  **Diagnose** — on failure, classify and propose recovery.
7.  **Auto-recover** — if enabled, apply constrained recovery and re-execute.
8.  **Provenance** — record a hashable audit trail.
9.  **Report** — produce a human-readable summary.

The pipeline is deterministic, LLM-free, and designed to be called either
from the CLI or from the DSH Skill layer.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .task_ir import CalculationTask, TaskIntent
from .diagnose import Diagnosis, FailureStage, classify
from .provenance import build_provenance, save_provenance
from .report import report as generate_report

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# PipelineResult
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class PipelineResult:
    """Complete result of a single pipeline run.

    Attributes
    ----------
    task : CalculationTask
        The original task (or the recovered task, if auto-recovery was used).
    run_record : RunResult or None
        Execution result from the REST runner.
    parse : ParsedResult or None
        Parsed observables.
    qa : list or None
        Scientific QA results.
    diagnosis : Diagnosis or None
        Failure diagnosis (only populated on failure).
    report_text : str
        Human-readable report.
    provenance_path : str or None
        Path to the saved provenance file.
    recovered : bool
        ``True`` when auto-recovery was attempted.
    recovery_attempts : int
        Number of recovery attempts made.
    success : bool
        ``True`` when the pipeline completed without error-level QA failures.
    """

    task: Optional[CalculationTask] = None
    run_record: Any = None
    parse: Any = None
    qa: Any = None
    diagnosis: Optional[Diagnosis] = None
    report_text: str = ""
    provenance_path: Optional[str] = None
    recovered: bool = False
    recovery_attempts: int = 0

    @property
    def success(self) -> bool:
        """True when the calculation completed and no error-level QA issues remain."""
        if self.run_record is None:
            return False
        status = getattr(self.run_record, "status", "unknown")
        if status != "completed":
            return False
        # Check QA for errors
        if self.qa:
            for q in self.qa:
                passed = getattr(q, "passed", True)
                severity = getattr(q, "severity", "ok")
                if not passed and severity == "error":
                    return False
        return True


# ═══════════════════════════════════════════════════════════════════════════════
# run_pipeline
# ═══════════════════════════════════════════════════════════════════════════════


def run_pipeline(
    task: CalculationTask,
    workdir: str,
    conda_env: str = "rest",
    auto_recover: bool = True,
    keep_inputs: bool = True,
    max_recovery_attempts: int = 3,
    timeout: float = 3600.0,
) -> PipelineResult:
    """Run the full AutoREST closed loop for one task.

    Parameters
    ----------
    task : CalculationTask
        The task to execute.
    workdir : str or Path
        Working directory for the calculation.
    conda_env : str
        Conda environment name where REST is installed.
    auto_recover : bool
        When ``True``, apply constrained auto-recovery on failure and
        re-submit (up to *max_recovery_attempts* times).
    keep_inputs : bool
        When ``True``, keep input cards and output files after the run.
    max_recovery_attempts : int
        Maximum number of automatic recovery attempts.
    timeout : float
        Maximum wall-clock seconds per REST invocation.

    Returns
    -------
    PipelineResult
        Complete pipeline outcome.
    """
    work_path = Path(workdir)
    work_path.mkdir(parents=True, exist_ok=True)

    result = PipelineResult()

    # ────────────────────────────────────────────────────────────────
    # Step 1: Electron parity check
    # ────────────────────────────────────────────────────────────────
    parity_issues = task.validate_electron_parity()
    if parity_issues:
        result.diagnosis = Diagnosis(
            stage=FailureStage.SCF,
            evidence=parity_issues,
            likely_cause=(
                "Charge/multiplicity mismatch: " + "; ".join(parity_issues)
            ),
            do_not_change=["charge", "spin", "geometry"],
            next_step="Fix the charge/spin combination before re-submitting.",
        )
        result.report_text = (
            f"❌ Pre-flight check FAILED:\n"
            + "\n".join(f"  • {p}" for p in parity_issues)
        )
        return result

    # ────────────────────────────────────────────────────────────────
    # Step 2: Generate input card
    # ────────────────────────────────────────────────────────────────
    current_task = task
    input_text = _generate_input_card(current_task)
    if input_text is None:
        result.diagnosis = Diagnosis(
            stage=FailureStage.INPUT_PARSING,
            evidence=["Could not generate input card."],
            likely_cause="Input generation failed — check task parameters.",
            next_step="Verify all required fields in CalculationTask.",
        )
        result.report_text = "❌ Input generation FAILED."
        return result

    # ────────────────────────────────────────────────────────────────
    # Execution loop (with optional auto-recovery)
    # ────────────────────────────────────────────────────────────────
    for attempt in range(max_recovery_attempts + 1):
        if attempt > 0:
            result.recovered = True
            result.recovery_attempts = attempt

        # ── Step 3: Execute ───────────────────────────────────────
        run_record = _execute_rest(
            input_text=input_text,
            workdir=work_path,
            conda_env=conda_env,
            timeout=timeout,
            job_name=f"{current_task.system_name}_{'recovery' if attempt > 0 else 'run'}",
        )
        result.run_record = run_record

        # ── Step 4: Parse ─────────────────────────────────────────
        parse_result = _parse_output(run_record)
        result.parse = parse_result

        # ── Step 5: Verify ────────────────────────────────────────
        qa_results = _verify(current_task, parse_result)
        result.qa = qa_results

        # Check for error-level failures
        error_failures = [
            q for q in qa_results
            if not getattr(q, "passed", True) and getattr(q, "severity", "ok") == "error"
        ]

        if not error_failures:
            # Success — exit the loop
            break

        # ── Step 6: Diagnose ──────────────────────────────────────
        raw_text = getattr(run_record, "stdout", "")
        diagnosis = classify(current_task, run_record, raw_text=raw_text)
        result.diagnosis = diagnosis

        # ── Step 7: Auto-recover (if enabled) ─────────────────────
        if not auto_recover or attempt >= max_recovery_attempts:
            break

        recovery = diagnosis.recovery_task
        if recovery is None:
            logger.info("No auto-recovery task available; stopping.")
            break

        current_task = recovery
        input_text = _generate_input_card(current_task)
        if input_text is None:
            break

        logger.info(
            "Auto-recovery attempt %d/%d: %s",
            attempt + 1, max_recovery_attempts, diagnosis.likely_cause,
        )

    # ────────────────────────────────────────────────────────────────
    # Step 8: Provenance
    # ────────────────────────────────────────────────────────────────
    try:
        record = build_provenance(
            task=current_task,
            run_record=result.run_record,
            parse_result=result.parse,
            qa_report=result.qa,
            input_text=input_text,
        )
        prov_path = save_provenance(
            record,
            directory=str(work_path),
            name=current_task.system_name,
        )
        result.provenance_path = prov_path
    except Exception as exc:
        logger.warning("Provenance recording failed: %s", exc)

    # ────────────────────────────────────────────────────────────────
    # Step 9: Report
    # ────────────────────────────────────────────────────────────────
    try:
        result.report_text = generate_report(
            task=current_task,
            result=result.parse,
            qa=result.qa,
        )
    except Exception as exc:
        logger.warning("Report generation failed: %s", exc)
        result.report_text = f"Report generation error: {exc}"

    # ────────────────────────────────────────────────────────────────
    # Cleanup (if requested)
    # ────────────────────────────────────────────────────────────────
    if not keep_inputs:
        _cleanup_workdir(work_path)

    result.task = current_task
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Internal step implementations
# ═══════════════════════════════════════════════════════════════════════════════


def _generate_input_card(task: CalculationTask) -> Optional[str]:
    """Generate a REST TOML input card from a CalculationTask.

    Delegates to the project's ``InputGenerator`` when available;
    otherwise constructs a minimal card directly.
    """
    try:
        from ..input_generator import InputGenerator

        gen = InputGenerator()

        # Map TaskIntent → InputGenerator method
        method_map = {
            TaskIntent.ENERGY: gen.generate_energy,
            TaskIntent.OPTIMIZATION: gen.generate_optimization,
            TaskIntent.FORCE: gen.generate_force,
            TaskIntent.FREQUENCY: gen.generate_frequency,
            TaskIntent.GW_ONLY: gen.generate_gw,
            TaskIntent.BSE_SINGLET: gen.generate_bse,
            TaskIntent.BSE_TRIPLET: gen.generate_bse,
        }

        fn = method_map.get(task.intent)
        if fn is None:
            logger.error("No input generator for intent: %s", task.intent.value)
            return None

        m = task.method
        common = dict(
            system_name=task.system_name,
            geometry=task.geometry.to_rest_position(),
            geometry_unit=task.geometry.unit,
            functional=m.xc,
            basis=m.basis,
            charge=task.charge,
            spin=task.spin,
            spin_polarization=None,  # auto-detect from spin
            empirical_dispersion=m.empirical_dispersion,
            auxbas_path=m.aux_basis,
            num_threads=task.resources.num_threads,
        )

        if task.intent == TaskIntent.BSE_SINGLET:
            common["bse_spin"] = "singlet"
            common["n_roots"] = m.bse_n_roots
            common["bse_tda"] = m.bse_tda
        elif task.intent == TaskIntent.BSE_TRIPLET:
            common["bse_spin"] = "triplet"
            common["n_roots"] = m.bse_n_roots
            common["bse_tda"] = m.bse_tda
        elif task.intent == TaskIntent.GW_ONLY:
            common["gw_scheme"] = m.gw_scheme
            common["scgw"] = m.scgw
            common["n_roots"] = m.gw_n_roots

        card = fn(**common)
        return card

    except ImportError:
        logger.warning("InputGenerator not available; building minimal card directly.")
        return _build_minimal_card(task)
    except Exception as exc:
        logger.error("Input generation failed: %s", exc)
        return None


def _build_minimal_card(task: CalculationTask) -> str:
    """Build a minimal REST TOML card when InputGenerator is unavailable."""
    import textwrap

    m = task.method
    sp = "true" if task.spin > 1 else "false"

    card = textwrap.dedent(f"""\
        [ctrl]
        num_threads = {task.resources.num_threads}
        print_level = 1
        job_type = "{_job_type(task.intent)}"
        xc = "{m.xc}"
        basis_path = "{m.basis}"
        charge = {task.charge}
        spin = {task.spin}
        spin_polarization = {sp}
        eri_type = "{m.eri_type}"
        use_ri_symm = {str(m.use_ri_symm).lower()}
    """)

    if m.empirical_dispersion and m.xc not in _DOUBLE_HYBRID_RPA:
        card += f'empirical_dispersion = "{m.empirical_dispersion}"\n'
    if m.aux_basis:
        card += f'auxbas_path = "{m.aux_basis}"\n'

    card += textwrap.dedent(f"""\

        [geom]
        name = "{task.system_name}"
        unit = "{task.geometry.unit}"
        position = \"\"\"
    """)

    for line in task.geometry.to_rest_position().splitlines():
        card += "    " + line + "\n"

    card += '"""\n'
    return card


_DOUBLE_HYBRID_RPA = frozenset({
    "RPA@B3LYP", "RPA@PBE", "scsRPA",
    "R-xDH7", "xDH-PBE0",
    "XYG3", "XYG7", "XYGJOS",
})


def _job_type(intent: TaskIntent) -> str:
    """Map TaskIntent to REST ``job_type`` string."""
    _map = {
        TaskIntent.ENERGY: "energy",
        TaskIntent.OPTIMIZATION: "opt",
        TaskIntent.FORCE: "force",
        TaskIntent.FREQUENCY: "energy",  # Hessian + thermo attached via [ctrl.hessian]
        TaskIntent.GW_ONLY: "energy",
        TaskIntent.BSE_SINGLET: "energy",
        TaskIntent.BSE_TRIPLET: "energy",
        TaskIntent.BSE_BOTH: "energy",
        TaskIntent.TDDFT: "energy",
    }
    return _map.get(intent, "energy")


# ═══════════════════════════════════════════════════════════════════════════════
# Execution
# ═══════════════════════════════════════════════════════════════════════════════


def _execute_rest(
    input_text: str,
    workdir: Path,
    conda_env: str,
    timeout: float,
    job_name: str,
) -> Any:
    """Execute REST with the given input card.

    Returns a ``RunResult`` from ``rest_runner``, or a minimal
    dict-like object if the runner is unavailable.
    """
    try:
        from ..rest_runner import RestRunner

        runner = RestRunner(conda_env=conda_env, work_dir=str(workdir))
        return runner.run(
            input_card=input_text,
            output_dir=workdir,
            timeout=timeout,
            job_name=job_name,
        )
    except ImportError:
        logger.warning("RestRunner not available — skipping execution.")
        return _FakeResult(status="skipped", stdout="", stderr="RestRunner unavailable")
    except FileNotFoundError as exc:
        logger.error("REST executable not found: %s", exc)
        return _FakeResult(status="failed", stdout="", stderr=str(exc))
    except Exception as exc:
        logger.exception("REST execution failed")
        return _FakeResult(status="failed", stdout="", stderr=str(exc))


# ═══════════════════════════════════════════════════════════════════════════════
# Parsing
# ═══════════════════════════════════════════════════════════════════════════════


def _parse_output(run_record: Any) -> Any:
    """Parse REST output and return a ``ParsedResult``."""
    stdout = getattr(run_record, "stdout", "")
    if not stdout:
        return _FakeParsedResult()

    try:
        from ..output_parser import OutputParser

        parser = OutputParser()
        return parser.parse(stdout)
    except ImportError:
        logger.warning("OutputParser not available — returning minimal parse.")
        return _FakeParsedResult()
    except Exception as exc:
        logger.warning("Output parsing failed: %s", exc)
        return _FakeParsedResult()


# ═══════════════════════════════════════════════════════════════════════════════
# Verification
# ═══════════════════════════════════════════════════════════════════════════════


def _verify(task: CalculationTask, parse_result: Any) -> List[Any]:
    """Run scientific validation on parsed results.

    Returns a list of ``ValidationCheck`` namedtuples or dicts.
    """
    try:
        from ..scientific_validator import ScientificValidator

        validator = ScientificValidator()
        return validator.validate(parse_result)
    except ImportError:
        return []
    except Exception as exc:
        logger.warning("Validation failed: %s", exc)
        return []


# ═══════════════════════════════════════════════════════════════════════════════
# Cleanup
# ═══════════════════════════════════════════════════════════════════════════════


def _cleanup_workdir(workdir: Path) -> None:
    """Remove temporary calculation files, keeping provenance only."""
    import re
    for path in workdir.iterdir():
        if path.is_file() and not path.name.endswith(".provenance.json"):
            try:
                path.unlink()
            except OSError:
                pass


# ═══════════════════════════════════════════════════════════════════════════════
# Fallback types (when project modules are unavailable)
# ═══════════════════════════════════════════════════════════════════════════════


class _FakeResult:
    """Minimal RunResult stand-in when rest_runner is unavailable."""

    def __init__(self, status: str = "unknown", stdout: str = "", stderr: str = ""):
        self.status = status
        self.stdout = stdout
        self.stderr = stderr
        self.wall_time = 0.0
        self.return_code = -1
        self.scf_converged = False
        self.scf_cycles = 0
        self.mission_accomplished = False
        self.warnings: List[str] = []


class _FakeParsedResult:
    """Minimal ParsedResult stand-in when output_parser is unavailable."""

    def __init__(self):
        self.scf_energy = None
        self.total_energy = None
        self.scf_converged = False
        self.scf_cycles = 0
        self.optimized_geometry = None
        self.optimization_steps = 0
        self.optimization_converged = False
        self.forces = None
        self.frequencies = []
        self.zpe = None
        self.dipole = None
        self.mp2_correlation = None
        self.wall_time = None
        self.mission_accomplished = False
        self.warnings: List[str] = []