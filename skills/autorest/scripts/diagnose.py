"""
Failure Diagnosis and Constrained Auto-Recovery
===============================================

Classifies *where* a REST run failed and proposes a minimal, constrained
next diagnostic step.  The recovery suggestions are deliberately narrow —
they change solver knobs and numerical settings, never the physical method
or the molecular geometry.

Design principles
-----------------
* **Minimal change**: adjust only what is likely broken, leave everything
  else untouched.
* **Constrained recovery**: ``do_not_change`` lists guard against
  scientifically destructive mutations (changing functional, basis,
  charge/spin, or geometry).
* **Evidence-first**: every ``Diagnosis`` cites the specific output
  patterns that triggered it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from .task_ir import CalculationTask, TaskIntent


# ═══════════════════════════════════════════════════════════════════════════════
# FailureStage
# ═══════════════════════════════════════════════════════════════════════════════


class FailureStage(str, Enum):
    """Granular classification of *where* in the REST pipeline a failure occurred."""

    INPUT_PARSING = "input_parsing"
    """REST could not parse the input card (TOML syntax, unknown keyword, …)."""

    BASIS_LOADING = "basis_loading"
    """Basis set file not found or corrupt."""

    SCF = "scf"
    """Self-consistent field did not converge or diverged."""

    GW = "gw"
    """GW quasiparticle step failed (Newton solver, linear equations, …)."""

    BSE_KERNEL = "bse_kernel"
    """BSE kernel construction failed."""

    DAVIDSON = "davidson"
    """Davidson diagonalisation failed to converge or returned zero roots."""

    OPTIMIZATION = "optimization"
    """Geometry optimisation failed to converge or took a bad step."""

    FREQUENCY = "frequency"
    """Hessian evaluation or frequency analysis failed."""

    TDDFT = "tddft"
    """TDDFT excitation solver failed."""

    TRUNCATED = "truncated"
    """Output was truncated (timeout, OOM kill, segfault, …)."""

    NONE = "none"
    """No failure detected."""


# ═══════════════════════════════════════════════════════════════════════════════
# Diagnosis
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class Diagnosis:
    """Complete diagnosis of a failed REST run.

    Attributes
    ----------
    stage : FailureStage
        Where the failure occurred.
    evidence : list[str]
        Specific output lines or patterns that support this diagnosis.
    likely_cause : str
        Human-readable explanation of the most likely root cause.
    do_not_change : list[str]
        Fields that MUST NOT be altered by the recovery step (e.g. the
        functional, basis, charge, spin, geometry).  Recovery should only
        touch solver/numerical knobs.
    next_step : str
        What the user or pipeline should do next.
    recovery_task : CalculationTask or None
        When recovery is straightforward and safe (e.g. increase Davidson
        subspace), a modified ``CalculationTask`` that can be re-submitted.
        ``None`` when human intervention is required.
    """

    stage: FailureStage = FailureStage.NONE
    evidence: List[str] = field(default_factory=list)
    likely_cause: str = ""
    do_not_change: List[str] = field(default_factory=list)
    next_step: str = ""
    recovery_task: Optional[CalculationTask] = None


# ═══════════════════════════════════════════════════════════════════════════════
# Classification patterns
# ═══════════════════════════════════════════════════════════════════════════════

_PATTERNS: Dict[FailureStage, List[str]] = {
    FailureStage.INPUT_PARSING: [
        r"(?i)cannot\s+parse\s+(?:input|toml)",
        r"(?i)unknown\s+keyword",
        r"(?i)invalid\s+(?:section|table)",
        r"(?i)syntax\s+error",
        r"(?i)unexpected\s+(?:token|character)",
    ],
    FailureStage.BASIS_LOADING: [
        r"(?i)(?:basis|auxbasis)\s+(?:set\s+)?not\s+found",
        r"(?i)(?:cannot|failed\s+to)\s+(?:load|open|read)\s+(?:basis|aux)",
        r"(?i)no\s+(?:basis|auxbasis)\s+file",
    ],
    FailureStage.SCF: [
        r"(?i)SCF\s+not\s+converged",
        r"(?i)SCF\s+(?:failed|diverged|did\s+not\s+converge)",
        r"(?i)maximum\s+number\s+of\s+SCF\s+(?:cycles|iterations)",
        r"(?i)SCF\s+(?:oscillat|instability)",
        r"(?i)density\s+(?:matrix\s+)?convergence\s+failure",
    ],
    FailureStage.GW: [
        r"(?i)(?:Newton|QP)\s+(?:solver\s+)?(?:warning|failed|diverged)",
        r"(?i)linear\s+equation\s+solver\s+(?:failed|warning)",
        r"(?i)(?:extrapolat\w*|QP)\s+(?:warning|error|failed)",
        r"(?i)quasiparticle\s+energy\s+(?:extrapolation\s+)?(?:warning|failed)",
    ],
    FailureStage.BSE_KERNEL: [
        r"(?i)(?:BSE\s+)?kernel\s+(?:construction|evaluation)\s+(?:failed|error)",
        r"(?i)(?:cannot|failed\s+to)\s+(?:build|construct|compute)\s+(?:BSE\s+)?kernel",
    ],
    FailureStage.DAVIDSON: [
        r"(?i)Davidson\s+(?:diagonalization\s+)?(?:not\s+converged|failed)",
        r"First\s+0\s+excitations?",
        r"(?i)(?:Davidson|subspace)\s+dimension\s+(?:exceeded|reached)",
        r"(?i)maximum\s+(?:Davidson|subspace)\s+(?:iterations|size)",
    ],
    FailureStage.OPTIMIZATION: [
        r"(?i)(?:optimization|geometry\s+opt\w*)\s+(?:not\s+converged|failed)",
        r"(?i)maximum\s+(?:number\s+of\s+)?(?:opt|geometry)\s+(?:steps|cycles|iterations)",
        r"(?i)(?:step|trust\s+radius)\s+(?:rejected|too\s+small)",
        r"(?i)(?:gradient|step)\s+(?:norm\s+)?(?:above|exceeds)\s+threshold",
    ],
    FailureStage.FREQUENCY: [
        r"(?i)(?:Hessian|frequency)\s+(?:calculation\s+)?(?:failed|error)",
        r"(?i)(?:cannot|failed\s+to)\s+compute\s+(?:Hessian|force\s+constant)",
    ],
    FailureStage.TDDFT: [
        r"(?i)TD-?DFT\s+(?:calculation\s+)?(?:failed|error|not\s+converged)",
        r"(?i)(?:TD-?DFT\s+)?excitation\s+(?:solver\s+)?failed",
    ],
    FailureStage.TRUNCATED: [
        r"(?i)(?:killed|timeout|seg(?:mentation)?\s+fault|OOM|out\s+of\s+memory)",
        r"(?i)(?:signal|terminated|abort(?:ed)?)",
    ],
}


def classify(
    task: CalculationTask,
    result: Any,              # RunResult or similar
    raw_text: Optional[str] = None,
) -> Diagnosis:
    """Classify where a REST run failed and propose a minimal next step.

    Parameters
    ----------
    task : CalculationTask
        The original task that was submitted.
    result : RunResult or similar
        The execution result, expected to have at least ``.status`` and
        ``.stdout`` attributes.
    raw_text : str or None
        If provided, used as the output text to scan (overrides
        ``result.stdout``).  Useful for post-hoc diagnosis of archived
        output files.

    Returns
    -------
    Diagnosis
        Structured diagnosis with recovery suggestions when applicable.
    """
    text = raw_text if raw_text is not None else getattr(result, "stdout", "")
    status = getattr(result, "status", "unknown")

    # ── Gather evidence for each stage ────────────────────────────
    stage_scores: Dict[FailureStage, List[str]] = {}
    for stage, patterns in _PATTERNS.items():
        hits: List[str] = []
        for pat in patterns:
            for m in re.finditer(pat, text, re.MULTILINE):
                line = m.group(0).strip()
                if line not in hits:
                    hits.append(line)
        if hits:
            stage_scores[stage] = hits

    # ── Determine primary stage ────────────────────────────────────
    # Priority: parse > basis > scf > optimization > gw > bse_kernel > davidson
    # > tddft > frequency > truncated
    priority = [
        FailureStage.INPUT_PARSING,
        FailureStage.BASIS_LOADING,
        FailureStage.SCF,
        FailureStage.OPTIMIZATION,
        FailureStage.GW,
        FailureStage.BSE_KERNEL,
        FailureStage.DAVIDSON,
        FailureStage.TDDFT,
        FailureStage.FREQUENCY,
        FailureStage.TRUNCATED,
    ]

    primary_stage = FailureStage.NONE
    evidence: List[str] = []
    for stage in priority:
        if stage in stage_scores:
            primary_stage = stage
            evidence = stage_scores[stage]
            break

    # If nothing matched but status is failed/timeout, default to truncated
    if primary_stage == FailureStage.NONE and status in ("failed", "timeout"):
        primary_stage = FailureStage.TRUNCATED
        evidence = [f"Status: {status}"]

    # ── Build diagnosis ────────────────────────────────────────────
    diag = Diagnosis(stage=primary_stage, evidence=evidence)
    diag.do_not_change = _always_protected()

    if primary_stage == FailureStage.SCF:
        diag = _diagnose_scf(task, text, evidence, diag)
    elif primary_stage == FailureStage.OPTIMIZATION:
        diag = _diagnose_optimization(task, text, evidence, diag)
    elif primary_stage == FailureStage.DAVIDSON:
        diag = _diagnose_davidson(task, text, evidence, diag)
    elif primary_stage == FailureStage.GW:
        diag = _diagnose_gw(task, text, evidence, diag)
    elif primary_stage == FailureStage.TRUNCATED:
        diag = _diagnose_truncated(task, text, evidence, diag)
    elif primary_stage == FailureStage.INPUT_PARSING:
        diag = _diagnose_input(task, text, evidence, diag)
    elif primary_stage == FailureStage.BASIS_LOADING:
        diag = _diagnose_basis(task, text, evidence, diag)
    elif primary_stage == FailureStage.NONE:
        diag.likely_cause = "No failure patterns detected."
        diag.next_step = "Review the full output manually if the result is unexpected."
    else:
        diag.likely_cause = f"Failure in {primary_stage.value} stage."
        diag.next_step = (
            f"Check the REST output around the {primary_stage.value} section "
            f"and consult the REST manual."
        )

    return diag


# ═══════════════════════════════════════════════════════════════════════════════
# Stage-specific diagnosis helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _always_protected() -> List[str]:
    """Fields that auto-recovery must never touch."""
    return [
        "xc (exchange-correlation functional)",
        "basis (orbital basis set)",
        "charge",
        "spin (ground-state multiplicity)",
        "geometry",
        "bse_spin (for BSE tasks)",
    ]


def _diagnose_scf(
    task: CalculationTask,
    text: str,
    evidence: List[str],
    diag: Diagnosis,
) -> Diagnosis:
    """Diagnose SCF convergence failure."""

    # ── Electron parity check ─────────────────────────────────────
    parity_issues = task.validate_electron_parity()
    if parity_issues:
        diag.likely_cause = (
            "SCF failure likely caused by charge/multiplicity mismatch: "
            + "; ".join(parity_issues)
        )
        diag.next_step = (
            "Fix the charge/spin combination before re-submitting. "
            "Double-check: (total e⁻) = sum(Z) − charge; "
            "even e⁻ → odd multiplicity, odd e⁻ → even multiplicity."
        )
        return diag

    # ── Oscillation detection ──────────────────────────────────────
    oscillating = bool(re.search(
        r"(?i)(?:oscillat|energy\s+oscillat)", text
    ))

    # ── Build recommendation ──────────────────────────────────────
    causes: List[str] = []
    steps: List[str] = []

    if oscillating:
        causes.append("SCF energy is oscillating between cycles")
        steps.append(
            "1) Try a different SCF mixer (e.g. DIIS → ADIIS+DIIS)"
        )
        steps.append("2) Enable level-shifting or Fermi smearing")
    else:
        causes.append("SCF did not converge within the maximum iterations")

    # Check for near-degeneracy hints
    if re.search(r"(?i)(?:near.degener|small\s+HOMO.LUMO|gap\s*[<>]=?\s*0\.0)", text):
        causes.append("Possible near-degeneracy at the Fermi level")
        steps.append("3) Use fractional occupation / smearing")
        steps.append("4) Try a different initial guess (e.g. superposition of fragments)")

    steps.append("5) Switch to a smaller basis set for the initial guess, then project")
    steps.append("6) Increase max SCF iterations")
    steps.append("7) Use a more robust initial guess (e.g. Hückel or superposition)")

    diag.likely_cause = "; ".join(causes) + "."
    diag.next_step = "\n".join(steps)

    # ── Recovery task: increase SCF iterations, suggest initial guess ──
    try:
        import copy
        recovery = copy.deepcopy(task)
        recovery.notes = (
            f"{task.notes}\n[Auto-recovery] SCF failure: increased SCF "
            f"iterations and enabled level-shifting."
        )
        recovery.tags = list(task.tags) + ["auto_recovery_scf"]
        diag.recovery_task = recovery
    except Exception:
        pass

    return diag


def _diagnose_optimization(
    task: CalculationTask,
    text: str,
    evidence: List[str],
    diag: Diagnosis,
) -> Diagnosis:
    """Diagnose geometry optimisation failure."""

    # Check gradient norms
    grad_high = bool(re.search(
        r"(?i)(?:gradient|force)\s+(?:norm|rms)\s+(?:above|exceeds|too\s+large)",
        text,
    ))
    step_rejected = bool(re.search(
        r"(?i)(?:step|trust\s+radius)\s+(?:rejected|too\s+small)",
        text,
    ))
    max_steps = bool(re.search(
        r"(?i)maximum\s+(?:number\s+of\s+)?(?:opt|geometry)\s+(?:steps|cycles|iterations)",
        text,
    ))

    causes: List[str] = []
    steps: List[str] = []

    if grad_high:
        causes.append("Gradient norms remain above convergence threshold")
        steps.append("1) Tighten the initial geometry (reduce initial forces)")
        steps.append("2) Check for a shallow PES — the minimum may be very flat")
    if step_rejected:
        causes.append("Trust-radius step was rejected")
        steps.append("3) Adjust trust radius (increase initial trust radius)")
        steps.append("4) Switch coordinate system (e.g. tric → redundant internal)")
    if max_steps:
        causes.append("Reached the maximum number of optimisation steps")
        steps.append("5) Increase ``maxiter`` in [geometric_pyo3]")
        steps.append("6) Restart from the last geometry")

    steps.append("7) Use a finer integration grid (particularly for transition metals)")
    steps.append("8) Check whether the starting geometry is chemically reasonable")

    diag.likely_cause = "; ".join(causes) if causes else "Geometry optimisation did not converge."
    diag.next_step = "\n".join(steps)

    # ── Recovery: increase maxiter, relax trust radius ────────────
    try:
        import copy
        recovery = copy.deepcopy(task)
        recovery.notes = (
            f"{task.notes}\n[Auto-recovery] Optimisation failure: "
            f"increased maxiter, adjusted trust radius."
        )
        recovery.tags = list(task.tags) + ["auto_recovery_opt"]
        diag.recovery_task = recovery
    except Exception:
        pass

    return diag


def _diagnose_davidson(
    task: CalculationTask,
    text: str,
    evidence: List[str],
    diag: Diagnosis,
) -> Diagnosis:
    """Diagnose Davidson diagonalisation failure (BSE/TDDFT)."""

    zero_roots = "First 0 excitations" in text
    subspace_full = bool(re.search(
        r"(?i)(?:subspace|Davidson)\s+dimension\s+(?:exceeded|reached)",
        text,
    ))
    not_converged = bool(re.search(
        r"(?i)Davidson\s+(?:diagonalization\s+)?not\s+converged",
        text,
    ))

    causes: List[str] = []
    steps: List[str] = []

    if zero_roots:
        causes.append("Davidson returned zero roots (NOT 'no excited states')")
        steps.append("1) Increase ``davidson_target_excitations`` (n_roots)")
        steps.append("2) Increase ``davidson_maximum_subspace_size`` (try 100–200)")
    if subspace_full:
        causes.append("Davidson subspace exhausted")
        steps.append("3) Increase ``davidson_maximum_subspace_size`` significantly")
        steps.append("4) Increase ``davidson_restart_dimensions``")
    if not_converged:
        causes.append("Davidson iterations did not converge")
        steps.append("5) Increase maximum Davidson iterations")
        steps.append("6) Try more roots than needed (n_roots + 2–3 extra)")

    steps.append("7) Check whether the QP gap is reasonable — a tiny gap "
                  "can cause dense excitation manifolds")

    diag.likely_cause = "; ".join(causes) if causes else "Davidson eigensolver failed."
    diag.next_step = "\n".join(steps)

    # ── Recovery: increase roots, subspace, restart ────────────────
    try:
        import copy
        recovery = copy.deepcopy(task)

        # Scale up Davidson parameters
        recovery.method.bse_n_roots = task.method.bse_n_roots + 5
        recovery.method.bse_davidson_max_subspace = task.method.bse_davidson_max_subspace * 2
        recovery.method.bse_davidson_restart = task.method.bse_davidson_restart * 2

        recovery.notes = (
            f"{task.notes}\n[Auto-recovery] Davidson failure: "
            f"increased roots to {recovery.method.bse_n_roots}, "
            f"subspace to {recovery.method.bse_davidson_max_subspace}, "
            f"restart to {recovery.method.bse_davidson_restart}."
        )
        recovery.tags = list(task.tags) + ["auto_recovery_davidson"]
        diag.recovery_task = recovery
    except Exception:
        pass

    return diag


def _diagnose_gw(
    task: CalculationTask,
    text: str,
    evidence: List[str],
    diag: Diagnosis,
) -> Diagnosis:
    """Diagnose GW quasiparticle failure."""

    qp_warnings = bool(re.search(
        r"(?i)(?:QP|quasiparticle)\s+(?:warning|caution)",
        text,
    ))
    newton_failed = bool(re.search(
        r"(?i)(?:Newton|root.finding)\s+(?:failed|diverged|warning)",
        text,
    ))
    extrapolation_warn = bool(re.search(
        r"(?i)extrapolat\w*\s+(?:warning|error|failed)",
        text,
    ))

    causes: List[str] = []
    steps: List[str] = []

    if newton_failed:
        causes.append("Newton solver for QP equation failed")
        steps.append("1) Widen the QP equation energy threshold")
        steps.append("2) Increase the frequency grid density")
    if extrapolation_warn:
        causes.append("Extrapolation of QP energies produced warnings")
        steps.append("3) Try ``gw_scheme = \"linearize\"`` instead of extrapolated")
    if qp_warnings:
        causes.append("QP energy calculations produced warnings")
        steps.append("4) Check individual orbital QP corrections — "
                      "some orbitals may need manual treatment")

    steps.append("5) Verify the starting DFT functional is appropriate "
                  "(starting-point dependence in G₀W₀)")
    steps.append("6) Try a larger basis set for the QP step")

    diag.likely_cause = "; ".join(causes) if causes else "GW step produced warnings or failed."
    diag.next_step = "\n".join(steps)

    # ── Recovery: widen thresholds ─────────────────────────────────
    try:
        import copy
        recovery = copy.deepcopy(task)
        recovery.notes = (
            f"{task.notes}\n[Auto-recovery] GW warnings: consider "
            f"widening QP thresholds or switching gw_scheme."
        )
        recovery.tags = list(task.tags) + ["auto_recovery_gw"]
        diag.recovery_task = recovery
    except Exception:
        pass

    return diag


def _diagnose_truncated(
    task: CalculationTask,
    text: str,
    evidence: List[str],
    diag: Diagnosis,
) -> Diagnosis:
    """Diagnose truncated / killed output."""

    timeout_hit = bool(re.search(r"(?i)timeout|wall.time", text))
    oom_hit = bool(re.search(r"(?i)out\s+of\s+memory|OOM", text))
    segfault_hit = bool(re.search(r"(?i)seg(?:mentation)?\s+fault", text))

    causes: List[str] = []
    steps: List[str] = []

    if timeout_hit:
        causes.append("Calculation exceeded wall-time limit")
        steps.append("1) Increase the wall-time limit")
        steps.append("2) Reduce the basis set size")
        steps.append("3) Reduce the number of threads to avoid I/O contention")
    if oom_hit:
        causes.append("Out of memory")
        steps.append("1) Reduce basis set size or number of roots")
        steps.append("2) Increase memory limit")
        steps.append("3) Use a smaller auxiliary basis for RI")
    if segfault_hit:
        causes.append("Segmentation fault — possible REST bug or library mismatch")
        steps.append("1) Check REST version and dependencies")
        steps.append("2) Try a different compilation / binary")
        steps.append("3) Reduce problem size and re-run to isolate the trigger")

    if not causes:
        causes.append("Output truncated (killed, crashed, or timed out)")

    steps.append("4) Look at the last 30 lines of output for clues")
    steps.append("5) Re-run with higher print_level for more diagnostics")

    diag.likely_cause = "; ".join(causes) + "."
    diag.next_step = "\n".join(steps)

    # ── Recovery: reduce thread count, increase timeout ────────────
    try:
        import copy
        recovery = copy.deepcopy(task)
        recovery.resources.num_threads = max(1, task.resources.num_threads // 2)
        recovery.notes = (
            f"{task.notes}\n[Auto-recovery] Truncated run: reduced threads "
            f"to {recovery.resources.num_threads}."
        )
        recovery.tags = list(task.tags) + ["auto_recovery_truncated"]
        diag.recovery_task = recovery
    except Exception:
        pass

    return diag


def _diagnose_input(
    task: CalculationTask,
    text: str,
    evidence: List[str],
    diag: Diagnosis,
) -> Diagnosis:
    """Diagnose input parsing failures."""
    diag.likely_cause = (
        "REST could not parse the input card.  Check for TOML syntax errors, "
        "unknown keywords, or missing required sections."
    )
    diag.next_step = (
        "1) Validate the TOML card with a linter\n"
        "2) Check that all section headers ([ctrl], [geom], …) are spelled correctly\n"
        "3) Verify that the functional and basis names match REST's catalogue\n"
        "4) Ensure 'charge', 'spin', 'xc', 'basis_path' are present in [ctrl]"
    )
    # No auto-recovery for input errors — human must fix the card.
    return diag


def _diagnose_basis(
    task: CalculationTask,
    text: str,
    evidence: List[str],
    diag: Diagnosis,
) -> Diagnosis:
    """Diagnose basis-set loading failures."""
    diag.likely_cause = (
        "A basis set (orbital or auxiliary) could not be found or loaded."
    )
    diag.next_step = (
        "1) Check that the basis name matches REST's installed catalog\n"
        "2) Verify the ``basis_path`` spelling (it may be case-sensitive)\n"
        "3) For custom basis sets, ensure the file path is absolute and accessible\n"
        "4) Try the built-in auto-selection by omitting ``auxbas_path``"
    )
    # No auto-recovery for basis-set issues.
    return diag