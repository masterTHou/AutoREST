"""
REST Execution and Monitoring Module
====================================

Manages REST calculation execution with real-time SCF convergence
monitoring, timeout handling, and output parsing integration.

Provides:
    - RestRunner: orchestrates REST binary detection, execution, and monitoring
    - RunResult: structured dataclass for calculation outcomes
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# RunResult dataclass
# ---------------------------------------------------------------------------


@dataclass
class RunResult:
    """Structured result of a single REST calculation.

    Attributes
    ----------
    status : str
        One of ``"completed"``, ``"failed"``, ``"timeout"``, ``"running"``.
    scf_energy : float or None
        Final SCF energy in Hartree (from the last cycle).
    scf_converged : bool
        Whether the SCF procedure reached convergence.
    scf_cycles : int
        Number of SCF iterations performed.
    total_energy : float or None
        Total energy reported in the output (may differ from SCF energy for
        post-SCF methods).
    wall_time : float
        Wall-clock duration of the calculation in seconds.
    stdout : str
        Complete standard-output stream from the REST process.
    stderr : str
        Complete standard-error stream from the REST process.
    return_code : int
        Exit code of the REST process.
    warnings : list of str
        Warnings extracted from the output (SCF oscillations, near-linear
        dependence, etc.).
    calculation_type : str
        Detected job type (``"energy"``, ``"opt"``, ``"force"``,
        ``"freq"``, ``"tddft"``, ``"unknown"``).
    mission_accomplished : bool
        ``True`` when the REST output contains the ``"Mission accomplished"``
        sentinel line.
    """

    status: str = "running"
    scf_energy: Optional[float] = None
    scf_converged: bool = False
    scf_cycles: int = 0
    total_energy: Optional[float] = None
    wall_time: float = 0.0
    stdout: str = ""
    stderr: str = ""
    return_code: int = -1
    warnings: List[str] = field(default_factory=list)
    calculation_type: str = "unknown"
    mission_accomplished: bool = False

    # ------------------------------------------------------------------
    # Convenience properties
    # ------------------------------------------------------------------

    @property
    def ok(self) -> bool:
        """``True`` when the calculation completed and SCF converged."""
        return self.status == "completed" and self.scf_converged


# ---------------------------------------------------------------------------
# RestRunner
# ---------------------------------------------------------------------------


class RestRunner:
    """Manage REST calculation execution with live monitoring.

    Parameters
    ----------
    conda_env : str
        Name of the conda environment that provides the ``rest`` binary
        (default ``"rest"``).
    rest_executable : str or Path or None
        Explicit path to the REST executable.  When *None* the runner
        auto-detects via the conda environment.
    work_dir : str or Path or None
        Default parent directory for calculation outputs.  When *None*
        a ``calc`` directory is created under the current working directory.

    Notes
    -----
    On **Windows** the runner prefers calling the REST binary directly.
    If the binary cannot be found it will attempt to resolve it through the
    conda environment's ``Library/bin`` or ``Scripts`` locations.
    """

    # Regex patterns compiled once for performance
    _RE_SCF_CYCLE = re.compile(
        r"^\s*\**\s*SCF\s*(?:Iteration|Cycle|iter|cycle)\s*[:=]?\s*(\d+)",
        re.IGNORECASE,
    )
    _RE_SCF_ENERGY = re.compile(
        r"(?:Total\s+)?(?:SCF\s+)?[Ee]nergy\s*[:=]?\s*(-?\d+\.\d+)",
    )
    _RE_SCF_CONVERGED = re.compile(
        r"SCF\s+(?:has\s+)?converged|Convergence\s+reached|convergence\s+criterion",
        re.IGNORECASE,
    )
    _RE_SCF_NOT_CONVERGED = re.compile(
        r"SCF\s+not\s+converged|Failed\s+to\s+converge",
        re.IGNORECASE,
    )
    _RE_MISSION = re.compile(r"Mission\s+accomplished", re.IGNORECASE)
    _RE_ERROR = re.compile(r"(?i)(?:FATAL|Error|ABORT)\b")
    _RE_WARNING = re.compile(
        r"(?i)(?:WARNING|WARN|CAUTION|oscillat|linear\s+depend|near\s+linear)",
    )
    _RE_CALC_TYPE = re.compile(
        r"(?i)"
        r"\b("
        r"Single\s*Point\s*Energy"
        r"|Geometry\s*Optimization"
        r"|Force\s*Calculation"
        r"|Frequenc(?:y|ies)\s*Calculation"
        r"|TD-?DFT"
        r"|GW"
        r"|BSE"
        r")\b",
    )

    # ------------------------------------------------------------------
    def __init__(
        self,
        conda_env: str = "rest",
        rest_executable: Optional[Union[str, Path]] = None,
        work_dir: Optional[Union[str, Path]] = None,
    ) -> None:
        self._conda_env = conda_env

        if rest_executable is not None:
            self._rest_exe = Path(rest_executable)
        else:
            self._rest_exe = self._detect_rest_executable()

        if work_dir is not None:
            self._work_dir = Path(work_dir)
        else:
            self._work_dir = Path.cwd() / "calc"

        self._work_dir.mkdir(parents=True, exist_ok=True)

        logger.info("RestRunner initialised — REST binary: %s", self._rest_exe)
        logger.info("Default work directory: %s", self._work_dir)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        input_card: Union[str, Path],
        output_dir: Optional[Union[str, Path]] = None,
        timeout: float = 3600.0,
        monitor_interval: float = 10.0,
        job_name: Optional[str] = None,
    ) -> RunResult:
        """Execute a single REST calculation.

        Parameters
        ----------
        input_card : str or Path
            Path to an existing ``.in`` file **or** the raw TOML content
            of the input card.  If the argument is not a path to an
            existing file it is treated as the input-card body.
        output_dir : str or Path or None
            Directory in which the calculation runs.  When *None* a
            timestamped sub-directory of *work_dir* is created.
        timeout : float
            Maximum wall-clock seconds before the process is killed
            (default 1 hour).
        monitor_interval : float
            Seconds between output-file inspection passes.
        job_name : str or None
            Label for the output sub-directory.  When *None* the stem of
            the input file or ``"rest_calc"`` is used.

        Returns
        -------
        RunResult
            Structured outcome of the calculation.
        """
        # -- resolve output directory ----------------------------------------
        if output_dir is not None:
            out_dir = Path(output_dir)
        else:
            stem = job_name or "rest_calc"
            # Ensure a unique directory name per run
            ts = time.strftime("%Y%m%d_%H%M%S")
            out_dir = self._work_dir / f"{stem}_{ts}"
        out_dir.mkdir(parents=True, exist_ok=True)

        # -- resolve input file ----------------------------------------------
        input_path = Path(input_card)
        if not input_path.is_file():
            # Treat *input_card* as TOML body text
            input_path = self._write_input_file(
                str(input_card),
                out_dir,
                job_name or "input",
            )

        logger.info("Running REST in %s with input %s", out_dir, input_path.name)

        # -- prepare output file paths ---------------------------------------
        stdout_path = out_dir / "output.out"

        # -- launch REST process ---------------------------------------------
        result = RunResult()
        t_start = time.perf_counter()

        try:
            # On Windows prefer passing the command as a list to avoid shell
            # escaping issues; REST accepts "-i <input>" natively.
            cmd: List[str] = [
                str(self._rest_exe),
                "-i",
                str(input_path),
            ]

            with open(stdout_path, "w", encoding="utf-8", errors="replace") as fh:
                # Write a header so the monitor can start reading immediately
                fh.write(f"# AutoREST run started at {time.ctime()}\n")
                fh.write(f"# Command: {' '.join(cmd)}\n")
                fh.write(f"# Working directory: {out_dir}\n")
                fh.flush()

                proc = subprocess.Popen(
                    cmd,
                    stdout=fh,
                    stderr=subprocess.PIPE,
                    cwd=str(out_dir),
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )

            # -- monitor until completion or timeout -------------------------
            result = self._monitor_process(
                proc=proc,
                stdout_path=stdout_path,
                timeout=timeout,
                monitor_interval=monitor_interval,
                t_start=t_start,
            )

        except subprocess.TimeoutExpired:
            result.status = "timeout"
            result.wall_time = time.perf_counter() - t_start
            logger.error("REST calculation timed out after %.0f s", timeout)

        except FileNotFoundError:
            raise FileNotFoundError(
                f"REST executable not found at '{self._rest_exe}'.\n"
                f"Ensure the conda environment '{self._conda_env}' is created "
                f"and contains REST, or pass an explicit path via "
                f"`rest_executable=...`."
            )

        except Exception:
            result.status = "failed"
            result.wall_time = time.perf_counter() - t_start
            result.stderr = getattr(result, "stderr", "")
            logger.exception("Unexpected error during REST execution")

        # -- post-process: parse output if available -------------------------
        if result.status in ("completed", "failed") and stdout_path.is_file():
            self._populate_from_output(result, stdout_path, t_start)

        return result

    # ------------------------------------------------------------------
    def run_batch(
        self,
        cards: Sequence[Union[str, Path]],
        output_dir: Optional[Union[str, Path]] = None,
        parallel: bool = False,
        timeout: float = 3600.0,
        monitor_interval: float = 10.0,
        job_name: Optional[str] = None,
    ) -> List[RunResult]:
        """Execute multiple REST calculations.

        Parameters
        ----------
        cards : sequence of str or Path
            Input cards or file paths, one per calculation.
        output_dir : str or Path or None
            Parent output directory (each job creates its own sub-directory).
        parallel : bool
            When ``True`` all jobs start concurrently (each managed by a
            separate subprocess); when ``False`` (default) they run
            sequentially.
        timeout : float
            Per-job wall-clock timeout in seconds.
        monitor_interval : float
            Seconds between output-file inspection passes.
        job_name : str or None
            Base label for output sub-directories.

        Returns
        -------
        list of RunResult
            One result per input card, in the same order.
        """
        results: List[RunResult] = []
        base_dir = Path(output_dir) if output_dir is not None else None

        if parallel:
            # Launch all jobs concurrently and collect results
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                futures: Dict[Any, int] = {}
                for idx, card in enumerate(cards):
                    fut = pool.submit(
                        self.run,
                        input_card=card,
                        output_dir=(
                            base_dir / f"job_{idx:03d}" if base_dir else None
                        ),
                        timeout=timeout,
                        monitor_interval=monitor_interval,
                        job_name=f"{job_name or 'batch'}_{idx:03d}",
                    )
                    futures[fut] = idx

                # Collect in submission order
                ordered: List[Optional[RunResult]] = [None] * len(cards)
                for fut in concurrent.futures.as_completed(futures):
                    idx = futures[fut]
                    try:
                        ordered[idx] = fut.result()
                    except Exception as exc:
                        # Wrap unexpected exceptions as a failed result
                        ordered[idx] = RunResult(
                            status="failed",
                            stderr=str(exc),
                        )
                results = [r for r in ordered if r is not None]

        else:
            for idx, card in enumerate(cards):
                result = self.run(
                    input_card=card,
                    output_dir=(
                        base_dir / f"job_{idx:03d}" if base_dir else None
                    ),
                    timeout=timeout,
                    monitor_interval=monitor_interval,
                    job_name=f"{job_name or 'batch'}_{idx:03d}",
                )
                results.append(result)

        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _detect_rest_executable(self) -> Path:
        """Locate the ``rest`` binary, preferring the conda environment.

        Strategy
        --------
        1. Check for ``rest`` / ``rest.exe`` on ``PATH``.
        2. Probe the conda environment's ``bin`` / ``Library/bin`` /
           ``Scripts`` directories.
        3. Attempt ``conda run -n <env> which rest`` as a last resort.

        Returns
        -------
        Path
            Absolute path to the REST executable.

        Raises
        ------
        FileNotFoundError
            If the binary cannot be located.
        """
        # 1. Direct PATH lookup ----------------------------------------------
        which = shutil.which("rest")
        if which is not None:
            logger.debug("REST found on PATH: %s", which)
            return Path(which)

        # 2. Conda environment directories -----------------------------------
        conda_prefix = os.environ.get("CONDA_PREFIX")
        if conda_prefix is None:
            # Try the common default locations
            for candidate in (
                Path.home() / "miniconda3",
                Path.home() / "anaconda3",
                Path.home() / "AppData" / "Local" / "miniconda3",
                Path.home() / "AppData" / "Local" / "anaconda3",
                Path("C:/") / "miniconda3",
                Path("C:/") / "anaconda3",
                Path.home() / "miniforge3",
                Path.home() / "mambaforge",
            ):
                if candidate.is_dir():
                    conda_prefix = str(candidate)
                    break

        if conda_prefix is not None:
            env_dir = Path(conda_prefix) / "envs" / self._conda_env
            if not env_dir.is_dir():
                # Maybe conda_env is the base environment itself
                env_dir = Path(conda_prefix)

            for sub in ("bin", "Library/bin", "Scripts", ""):
                candidate = (env_dir / sub / "rest") if sub else (env_dir / "rest")
                if sys.platform == "win32" and candidate.suffix != ".exe":
                    candidate = candidate.with_suffix(".exe")
                if candidate.is_file():
                    logger.debug("REST found in conda env: %s", candidate)
                    return candidate.resolve()

        # 3. conda-run fallback ----------------------------------------------
        try:
            proc = subprocess.run(
                ["conda", "run", "-n", self._conda_env, "which", "rest"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                exe_path = Path(proc.stdout.strip())
                if exe_path.is_file():
                    logger.debug("REST found via conda-run: %s", exe_path)
                    return exe_path.resolve()
        except Exception:
            pass

        raise FileNotFoundError(
            f"Could not locate the REST executable.\n\n"
            f"Tried:\n"
            f"  - PATH lookup\n"
            f"  - conda environment '{self._conda_env}'\n"
            f"  - common conda installation directories\n\n"
            f"Please ensure REST is installed in the '{self._conda_env}' "
            f"conda environment and try again, or pass an explicit path via "
            f"`rest_executable=...`."
        )

    # ------------------------------------------------------------------
    def _write_input_file(
        self,
        card: str,
        directory: Path,
        name: str,
    ) -> Path:
        """Write *card* body to a ``.in`` file and return its path.

        Parameters
        ----------
        card : str
            TOML content of the REST input.
        directory : Path
            Target directory (must already exist).
        name : str
            Stem for the ``.in`` file (``.in`` suffix is appended).

        Returns
        -------
        Path
            Absolute path of the written file.
        """
        # Sanitise the stem so it is a safe filename
        safe = re.sub(r"[^\w\-.]", "_", name)
        if not safe.lower().endswith(".in"):
            safe += ".in"
        dest = directory / safe

        dest.write_text(card, encoding="utf-8")
        logger.info("Input card written to %s", dest)
        return dest

    # ------------------------------------------------------------------
    def _monitor_process(
        self,
        proc: subprocess.Popen,
        stdout_path: Path,
        timeout: float,
        monitor_interval: float,
        t_start: float,
    ) -> RunResult:
        """Poll the REST process and periodically inspect the output file.

        Parameters
        ----------
        proc : subprocess.Popen
            Running REST subprocess.
        stdout_path : Path
            Path to the file where REST stdout is being written.
        timeout : float
            Maximum wall-clock seconds.
        monitor_interval : float
            Seconds between output scans.
        t_start : float
            ``time.perf_counter()`` value at process launch.

        Returns
        -------
        RunResult
            Populated with monitoring observations.
        """
        result = RunResult(status="running")
        last_cycle = 0

        try:
            while proc.poll() is None:
                elapsed = time.perf_counter() - t_start
                if elapsed > timeout:
                    proc.kill()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        pass
                    result.status = "timeout"
                    result.wall_time = time.perf_counter() - t_start
                    return result

                # -- inspect output so far ----------------------------------
                if stdout_path.is_file():
                    try:
                        text = stdout_path.read_text(
                            encoding="utf-8", errors="replace"
                        )
                        lines = text.splitlines()

                        # Track SCF cycle progress
                        cycle = self._count_scf_cycles(lines)
                        if cycle > last_cycle:
                            last_cycle = cycle
                            logger.debug(
                                "SCF cycle %d — elapsed %.0f s",
                                cycle,
                                elapsed,
                            )

                        # Early-failure detection
                        if self._detect_fatal(lines):
                            logger.warning(
                                "Early-failure pattern detected at %.0f s",
                                elapsed,
                            )

                        # Collect warnings on the fly
                        for line in lines[-20:]:  # only recent lines
                            if self._RE_WARNING.search(line):
                                stripped = line.strip()
                                if stripped not in result.warnings:
                                    result.warnings.append(stripped)

                    except (OSError, UnicodeDecodeError):
                        pass  # file may be temporarily locked

                time.sleep(monitor_interval)

            # -- process finished --------------------------------------------
            result.return_code = proc.returncode or 0
            result.wall_time = time.perf_counter() - t_start

            # Collect final stderr
            if proc.stderr is not None:
                try:
                    result.stderr, _ = proc.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    result.stderr = ""

        except Exception:
            # Ensure we don't leave a zombie
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            raise

        return result

    # ------------------------------------------------------------------
    def _populate_from_output(
        self,
        result: RunResult,
        stdout_path: Path,
        t_start: float,
    ) -> None:
        """Parse the completed output file and fill *result* fields.

        Integrates with ``OutputParser`` from ``.output_parser`` when
        available; otherwise performs a lightweight built-in parse.
        """
        try:
            text = stdout_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""

        result.stdout = text
        lines = text.splitlines()

        # -- SCF cycle count -------------------------------------------------
        result.scf_cycles = self._count_scf_cycles(lines)

        # -- SCF convergence -------------------------------------------------
        result.scf_converged = self._check_scf_status(lines)

        # -- Mission accomplished --------------------------------------------
        result.mission_accomplished = any(
            self._RE_MISSION.search(line) for line in lines
        )

        # -- Error / fatal detection -----------------------------------------
        if any(self._RE_ERROR.search(line) for line in lines):
            if result.status != "timeout":
                result.status = "failed"

        # -- Determine final status ------------------------------------------
        if result.return_code == 0 and result.mission_accomplished:
            result.status = "completed"

        # -- Extract energies ------------------------------------------------
        result.scf_energy = self._extract_final_scf_energy(lines)
        result.total_energy = self._extract_total_energy(lines)

        # -- Calculation type ------------------------------------------------
        result.calculation_type = self._detect_calculation_type(text)

        # -- Collect remaining warnings --------------------------------------
        for line in lines:
            if self._RE_WARNING.search(line):
                stripped = line.strip()
                if stripped not in result.warnings:
                    result.warnings.append(stripped)

        # -- Wall time refinement (output may contain its own timing) --------
        if result.wall_time == 0.0:
            result.wall_time = time.perf_counter() - t_start

        # -- Delegate to OutputParser for deeper extraction ------------------
        try:
            from .output_parser import OutputParser

            parser = OutputParser()
            parsed = parser.parse(text)

            # Enrich RunResult with parser-derived values when our own
            # extraction came up empty.
            if result.scf_energy is None and parsed.scf_energy is not None:
                result.scf_energy = parsed.scf_energy
            if result.total_energy is None and parsed.total_energy is not None:
                result.total_energy = parsed.total_energy
            if not result.scf_converged and parsed.scf_converged:
                result.scf_converged = parsed.scf_converged
            if result.scf_cycles == 0 and parsed.scf_cycles:
                result.scf_cycles = parsed.scf_cycles
            if result.calculation_type == "unknown" and parsed.calculation_type:
                result.calculation_type = parsed.calculation_type

        except ImportError:
            logger.debug("OutputParser not available; using built-in parsing only")
        except Exception:
            logger.debug("OutputParser raised an exception", exc_info=True)

    # ------------------------------------------------------------------
    @staticmethod
    def _count_scf_cycles(lines: List[str]) -> int:
        """Count SCF iteration lines in the output."""
        max_cycle = 0
        for line in lines:
            m = RestRunner._RE_SCF_CYCLE.search(line)
            if m:
                try:
                    cyc = int(m.group(1))
                    if cyc > max_cycle:
                        max_cycle = cyc
                except ValueError:
                    pass
        return max_cycle

    # ------------------------------------------------------------------
    @staticmethod
    def _check_scf_status(lines: List[str]) -> bool:
        """Return ``True`` when the output indicates SCF convergence.

        Checks for positive convergence messages and ensures no
        ``"SCF not converged"`` message follows.
        """
        converged = False
        for line in lines:
            if RestRunner._RE_SCF_CONVERGED.search(line):
                converged = True
            if RestRunner._RE_SCF_NOT_CONVERGED.search(line):
                converged = False
        return converged

    # ------------------------------------------------------------------
    @staticmethod
    def _detect_fatal(lines: List[str]) -> bool:
        """Detect early-failure patterns in recent output lines."""
        # Check the last ~30 lines for fatal signals
        recent = lines[-30:] if len(lines) > 30 else lines
        for line in recent:
            if re.search(r"(?i)(?:FATAL|SEGFAULT|ABORT|Traceback)", line):
                return True
            if re.search(r"SCF\s+not\s+converged", line, re.IGNORECASE):
                return True
        return False

    # ------------------------------------------------------------------
    @staticmethod
    def _extract_final_scf_energy(lines: List[str]) -> Optional[float]:
        """Extract the last SCF energy value from output lines.

        REST typically prints the SCF energy on each iteration line.
        This method scans backwards for the most recent match.
        """
        for line in reversed(lines):
            m = RestRunner._RE_SCF_ENERGY.search(line)
            if m:
                try:
                    return float(m.group(1))
                except ValueError:
                    continue
        return None

    # ------------------------------------------------------------------
    @staticmethod
    def _extract_total_energy(lines: List[str]) -> Optional[float]:
        """Extract a total-energy value from the output.

        Looks for patterns such as ``"Total energy = -76.123456"`` or
        ``"Final energy"``.
        """
        re_total = re.compile(
            r"(?:Total\s+(?:DFT\s+)?[Ee]nergy|Final\s+[Ee]nergy)\s*[:=]?\s*(-?\d+\.\d+)",
        )
        for line in reversed(lines):
            m = re_total.search(line)
            if m:
                try:
                    return float(m.group(1))
                except ValueError:
                    continue
        return None

    # ------------------------------------------------------------------
    @staticmethod
    def _detect_calculation_type(text: str) -> str:
        """Infer the calculation type from the output text."""
        patterns: Dict[str, str] = {
            "Geometry Optimization": "opt",
            "Single Point Energy": "energy",
            "Force Calculation": "force",
            "Frequency": "freq",
            "TD-DFT": "tddft",
            "TDDFT": "tddft",
            "GW": "gw",
            "BSE": "bse",
        }
        for keyword, job in patterns.items():
            if keyword.lower() in text.lower():
                return job
        return "unknown"

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def rest_executable(self) -> Path:
        """Path to the REST binary this runner will invoke."""
        return self._rest_exe

    @property
    def work_dir(self) -> Path:
        """Default parent directory for calculation outputs."""
        return self._work_dir