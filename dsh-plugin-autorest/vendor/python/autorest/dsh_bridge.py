"""AutoREST DSH Bridge — Python side of the JSON bridge.

Usage:
    python -m autorest.dsh_bridge

Expects a JSON request on stdin (one line).  Writes a JSON response
to stdout.  All diagnostics and logging go to stderr.

This bridge is stateless: each invocation handles exactly one action.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import sys
import traceback
from typing import Any, Dict, Optional, Tuple

# ── lightweight local imports (no pip install needed) ────────────
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_THIS_DIR)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from autorest.input_generator import InputGenerator
from autorest.output_parser import OutputParser
from autorest.scientific_validator import ScientificValidator
from autorest.gwbse_parser import GWBSEModule
from autorest.bridge import build_request, build_response, ErrorCode, PROTOCOL_VERSION

# ═══════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════

_INPUT_GEN = InputGenerator()
_OUTPUT_PARSER = OutputParser()
_VALIDATOR = ScientificValidator()
_GWBSE = GWBSEModule()


def _log(msg: str) -> None:
    print(f"[autorest-bridge] {msg}", file=sys.stderr)


def _find_python() -> Optional[str]:
    """Return the Python interpreter that is running this bridge."""
    return sys.executable or shutil.which("python3") or shutil.which("python")


def _detect_rest() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Return (executable_path, version_string, source_description)."""
    candidates: Dict[str, str] = {}

    # 1. CONDA_PREFIX
    prefix = os.environ.get("CONDA_PREFIX")
    if prefix:
        for sub in ("bin", "Library/bin"):
            exe = os.path.join(prefix, sub, "rest.exe" if sys.platform == "win32" else "rest")
            if os.path.isfile(exe) and exe not in candidates:
                candidates[exe] = "active conda environment"

    # 2. Common conda env locations
    for base in [
        os.path.expanduser("~/anaconda3/envs"),
        os.path.expanduser("~/miniconda3/envs"),
        os.path.expanduser("~/miniforge3/envs"),
        "C:/ProgramData/anaconda3/envs",
        "C:/ProgramData/miniconda3/envs",
        "/opt/anaconda3/envs",
        "/opt/miniconda3/envs",
    ]:
        if not os.path.isdir(base):
            continue
        try:
            for env in os.listdir(base):
                env_dir = os.path.join(base, env)
                for sub in ("bin", "Library/bin"):
                    exe = os.path.join(
                        env_dir, sub, "rest.exe" if sys.platform == "win32" else "rest"
                    )
                    if os.path.isfile(exe) and exe not in candidates:
                        candidates[exe] = f"conda env: {env} ({base})"
        except OSError:
            continue

    # 3. System PATH
    for exe in ("rest.exe", "rest"):
        path_exe = shutil.which(exe)
        if path_exe and os.path.isfile(path_exe) and path_exe not in candidates:
            candidates[path_exe] = "system PATH"

    if not candidates:
        return None, None, None

    # Pick the first found and try to get its version
    for exe_path, source in candidates.items():
        ver = None
        try:
            import subprocess
            r = subprocess.run(
                [exe_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if r.returncode == 0:
                ver = r.stdout.strip() or r.stderr.strip() or None
        except Exception:
            pass
        return exe_path, ver, source

    return None, None, None


def _find_rest() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Public alias for _detect_rest."""
    return _detect_rest()


# ═══════════════════════════════════════════════════════════════════
# Action handlers
# ═══════════════════════════════════════════════════════════════════


def _handle_detect(_payload: Dict[str, Any]) -> Dict[str, Any]:
    py_exe = _find_python()
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

    numpy_ok = False
    try:
        import numpy  # noqa: F401

        numpy_ok = True
    except ImportError:
        pass

    rest_exe, rest_ver, rest_source = _find_rest()

    capabilities = ["generate_input", "parse_output"]
    warnings: list[str] = []
    if not numpy_ok:
        warnings.append("numpy not available — some features may be slower")

    if rest_exe:
        next_action = (
            f"REST found at {rest_exe} ({rest_source or 'unknown source'}). "
            "You can generate .in files and optionally run them with REST."
        )
    else:
        next_action = (
            "REST not detected on this machine. AutoREST can still generate .in input files. "
            "Install REST via: conda create -n rest -c restgroup rest"
        )

    return build_response(
        ok=True,
        code="ENV_OK" if rest_exe else "REST_NOT_FOUND",
        message=next_action,
        data={
            "plugin_version": "4.0.0",
            "bridge_protocol_version": PROTOCOL_VERSION,
            "python_available": True,
            "python_version": py_ver,
            "python_executable": py_exe,
            "autorest_core_available": True,
            "numpy_available": numpy_ok,
            "rest_found": rest_exe is not None,
            "rest_executable": rest_exe,
            "rest_version": rest_ver,
            "rest_source": rest_source,
            "capabilities": capabilities,
            "warnings": warnings,
            "next_action": next_action,
        },
    )


def _handle_generate(payload: Dict[str, Any]) -> Dict[str, Any]:
    geometry = str(payload.get("geometry", "")).strip()
    if not geometry:
        return build_response(ok=False, code=ErrorCode.INVALID_TASK,
                              message="geometry is required", hint="Provide the molecule geometry in XYZ format.")
    try:
        from autorest.core.task_ir import CalculationTask

        method = payload.get("functional", "b3lyp")
        basis = payload.get("basis", "def2-SVP")
        charge = int(payload.get("charge", 0))
        spin = int(payload.get("spin", 1))
        job = payload.get("job_type", "energy")
        disp = payload.get("empirical_dispersion")
        bse = payload.get("bse_spin")
        nroots = int(payload.get("n_roots", 5))
        name = str(payload.get("system_name", "MOLECULE")).strip() or "MOLECULE"
        unit = str(payload.get("geometry_unit", "angstrom")).strip() or "angstrom"
        aux = payload.get("auxbas_path")
        threads = int(payload.get("num_threads", 4))

        # Basic validation
        known_jobs = {"energy", "opt", "force", "numerical dipole", "frequency"}
        if job not in known_jobs and not job.startswith("gw"):
            return build_response(ok=False, code=ErrorCode.UNSUPPORTED_TASK,
                                  message=f"Unknown job_type: {job}",
                                  hint=f"Supported: {', '.join(sorted(known_jobs))}, gw, gw-bse")
        if spin < 1:
            return build_response(ok=False, code=ErrorCode.INVALID_TASK,
                                  message="spin must be >= 1", hint="Spin multiplicity 2S+1 (e.g., 1 for singlet, 2 for doublet).")

        kwargs: Dict[str, Any] = dict(
            system_name=name, geometry=geometry, geometry_unit=unit,
            functional=method, basis=basis, charge=charge, spin=spin,
            num_threads=threads,
        )
        if disp:
            kwargs["empirical_dispersion"] = disp
        if aux:
            kwargs["auxbas_path"] = aux
        if bse and bse in ("singlet", "triplet"):
            kwargs["bse_spin"] = bse
            kwargs["n_roots"] = nroots

        if job == "energy":
            card = _INPUT_GEN.generate_energy(**kwargs)
        elif job == "opt":
            card = _INPUT_GEN.generate_optimization(**kwargs)
        elif job == "force":
            card = _INPUT_GEN.generate_force(**kwargs)
        elif job == "frequency":
            card = _INPUT_GEN.generate_frequency(**kwargs)
        elif job in ("gw", "gw-bse", "bse"):
            if bse and bse in ("singlet", "triplet"):
                card = _INPUT_GEN.generate_bse(**kwargs)
            else:
                card = _INPUT_GEN.generate_gw(**kwargs)
        else:
            card = _INPUT_GEN.generate_energy(**kwargs)

        safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in name).strip("_") or "molecule"
        filename = f"{safe_name}_{job}.in"

        return build_response(
            ok=True,
            code="INPUT_GENERATED",
            message=f"REST input card for {name} ({method}/{basis}, {job}) generated successfully.",
            hint="You can now save this card as a .in file and run it with REST.",
            data={
                "toml": card,
                "suggested_filename": filename,
                "task_summary": {
                    "system_name": name,
                    "job_type": job,
                    "functional": method,
                    "basis": basis,
                    "charge": charge,
                    "spin": spin,
                },
                "warnings": [],
                "version": "4.0.0",
            },
        )
    except Exception as exc:
        return build_response(
            ok=False,
            code=ErrorCode.INVALID_TASK,
            message=str(exc),
            hint="Check your input parameters and try again.",
        )


def _handle_parse(payload: Dict[str, Any]) -> Dict[str, Any]:
    text = str(payload.get("text", "") or payload.get("content", ""))
    if len(text) < 10:
        return build_response(
            ok=False,
            code=ErrorCode.PARSE_FAILED,
            message="Input text too short to be a valid REST output file.",
            hint="Make sure you are passing the full REST output content (not a filename).",
        )
    try:
        parsed = _OUTPUT_PARSER.parse(text)
        qa = _VALIDATOR.validate(parsed)
        has_imag = False
        if parsed.frequencies:
            has_imag = any(f < 0 for f in parsed.frequencies)
        bse_states: list = []
        try:
            gwbse_result = _GWBSE.parse_gwbse_output(text)
            bse_states = [dict(index=s.index, energy_ev=round(s.energy_ev, 4),
                               oscillator_strength=round(s.oscillator_strength, 6))
                          for s in gwbse_result.states]
        except Exception:
            pass

        return build_response(
            ok=True,
            code="PARSE_OK",
            message="REST output parsed successfully.",
            data={
                "scf_energy": parsed.scf_energy,
                "scf_converged": parsed.scf_converged,
                "scf_cycles": parsed.scf_cycles,
                "total_energy": parsed.total_energy,
                "dipole": parsed.dipole,
                "frequencies": parsed.frequencies,
                "imaginary_frequencies": [f for f in (parsed.frequencies or []) if f < 0] if has_imag else None,
                "zpe": parsed.zpe,
                "forces": parsed.forces,
                "optimized_geometry": parsed.optimized_geometry,
                "optimization_converged": parsed.optimization_converged,
                "optimization_steps": parsed.optimization_steps,
                "mission_accomplished": parsed.mission_accomplished,
                "wall_time_s": parsed.wall_time,
                "warnings": parsed.warnings or [],
                "bse_states": bse_states,
                "qa_checks": [dict(name=c.name, passed=c.passed, severity=c.severity, detail=c.detail)
                              for c in qa],
            },
        )
    except Exception as exc:
        return build_response(
            ok=False,
            code=ErrorCode.PARSE_FAILED,
            message=str(exc),
            hint="The REST output could not be fully parsed. Check that the file is a valid REST output.",
        )


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

_HANDLERS = {
    "detect": _handle_detect,
    "generate_input": _handle_generate,
    "parse_output": _handle_parse,
}


def main() -> None:
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            _log("empty stdin — exiting")
            resp = build_response(ok=False, code=ErrorCode.BRIDGE_PROTOCOL_ERROR,
                                  message="No input received on stdin.")
            json.dump(resp, sys.stdout)
            sys.stdout.flush()
            sys.exit(0)

        req = json.loads(raw)
        action = req.get("action")
        payload = req.get("payload", {})

        if action not in _HANDLERS:
            resp = build_response(
                ok=False,
                code=ErrorCode.BRIDGE_PROTOCOL_ERROR,
                message=f"Unknown action: {action}",
                hint=f"Supported actions: {', '.join(sorted(_HANDLERS))}",
            )
            json.dump(resp, sys.stdout)
            sys.stdout.flush()
            sys.exit(0)

        handler = _HANDLERS[action]
        resp = handler(payload)
        json.dump(resp, sys.stdout)
        sys.stdout.flush()
    except json.JSONDecodeError as e:
        _log(f"JSON decode error: {e}")
        resp = build_response(ok=False, code=ErrorCode.BRIDGE_PROTOCOL_ERROR,
                              message=f"Invalid JSON: {e}")
        json.dump(resp, sys.stdout)
        sys.stdout.flush()
    except Exception:
        _log(traceback.format_exc())
        resp = build_response(ok=False, code=ErrorCode.INTERNAL_ERROR,
                              message="An unexpected error occurred in the bridge.")
        json.dump(resp, sys.stdout)
        sys.stdout.flush()
        sys.exit(1)


if __name__ == "__main__":
    main()