"""
Provenance Tracking
===================

Builds hashable, complete records for every REST run so that any result
can be audited, reproduced, and traced back to its exact inputs.

Every record includes:
* Schema version (for forward compatibility)
* Task fingerprint, method, geometry hash, input card hash
* Software version, host info, timestamps
* Execution status, parsed observables, QA results, warnings
* The raw input text (for full reproducibility)

Records are serialised as JSON and saved to disk with a deterministic
filename keyed to the task fingerprint.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import platform
from pathlib import Path
from typing import Any, Dict, List, Optional

from .task_ir import CalculationTask

# ═══════════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════════

SCHEMA_VERSION: str = "1.0.0"
"""Provenance record schema version.  Increment on breaking changes."""


# ═══════════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════════


def build_provenance(
    task: CalculationTask,
    run_record: Any,              # RunResult or similar
    parse_result: Any,            # ParsedResult or similar
    qa_report: Any,               # list of ValidationCheck or list of dict
    input_text: str,
) -> Dict[str, Any]:
    """Build a complete, hashable provenance record.

    Parameters
    ----------
    task : CalculationTask
        The original task that was submitted.
    run_record : RunResult or similar
        Execution result (expects ``.status``, ``.wall_time``,
        ``.return_code``, ``.stdout``, ``.stderr``, ``.warnings``).
    parse_result : ParsedResult or similar
        Parsed observables (expects ``.scf_energy``, ``.total_energy``,
        ``.scf_converged``, ``.scf_cycles``, ``.mission_accomplished``).
    qa_report : list of ValidationCheck or list of dict
        Scientific QA results.
    input_text : str
        The exact REST TOML input card that was submitted.

    Returns
    -------
    dict
        Complete provenance record ready for serialisation.
    """
    now = datetime.datetime.now(datetime.timezone.utc)

    # ── System info ─────────────────────────────────────────────────
    system = {
        "hostname": platform.node(),
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "cpu_count_logical": os.cpu_count(),
    }

    # ── Software version (best-effort) ─────────────────────────────
    software = _detect_rest_version(run_record)

    # ── Task identity ──────────────────────────────────────────────
    task_fingerprint = task.fingerprint()
    input_hash = hashlib.sha256(input_text.encode("utf-8")).hexdigest()
    geometry_hash = hashlib.sha256(
        task.geometry.to_rest_position().encode("utf-8")
    ).hexdigest()

    # ── Run info ────────────────────────────────────────────────────
    run_info = _extract_run_info(run_record)

    # ── Results ─────────────────────────────────────────────────────
    results = _extract_results(parse_result)

    # ── QA ──────────────────────────────────────────────────────────
    qa_normalised = _normalise_qa(qa_report)

    # ── Warnings ────────────────────────────────────────────────────
    parse_warnings = getattr(parse_result, "warnings", []) or []
    run_warnings = getattr(run_record, "warnings", []) or []
    all_warnings: List[str] = list(dict.fromkeys(
        list(run_warnings) + list(parse_warnings)
    ))

    # ── Assemble record ─────────────────────────────────────────────
    record: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_at": now.isoformat(),
        "system": system,
        "software": software,
        "task": {
            "system_name": task.system_name,
            "intent": task.intent.value,
            "molecular_character": task.molecular_character.value,
            "charge": task.charge,
            "spin": task.spin,
            "method": {
                "xc": task.method.xc,
                "basis": task.method.basis,
                "aux_basis": task.method.aux_basis,
                "empirical_dispersion": task.method.empirical_dispersion,
                "eri_type": task.method.eri_type,
                "use_ri_symm": task.method.use_ri_symm,
            },
            "geometry": {
                "n_atoms": task.geometry.n_atoms,
                "unit": task.geometry.unit,
                "hash": geometry_hash,
            },
            "fingerprint": task_fingerprint,
            "depends_on": task.depends_on,
            "tags": task.tags,
        },
        "input": {
            "text": input_text,
            "hash": input_hash,
        },
        "run": run_info,
        "results": results,
        "qa": qa_normalised,
        "warnings": all_warnings,
        "notes": task.notes,
    }

    return record


def save_provenance(
    record: Dict[str, Any],
    directory: str,
    name: Optional[str] = None,
) -> str:
    """Save a provenance record to disk as a JSON file.

    The filename is ``{name}_{fingerprint[:12]}.provenance.json`` where
    *name* is either the provided label or the task's ``system_name``.

    Parameters
    ----------
    record : dict
        A provenance record as returned by :func:`build_provenance`.
    directory : str or Path
        Target directory (will be created if missing).
    name : str or None
        Optional label for the filename.  When ``None``, uses the
        ``system_name`` from the record.

    Returns
    -------
    str
        Absolute path of the written file.
    """
    out_dir = Path(directory)
    out_dir.mkdir(parents=True, exist_ok=True)

    fingerprint = record.get("task", {}).get("fingerprint", "unknown")[:12]
    system_name = record.get("task", {}).get("system_name", name or "calc")

    stem = name or system_name
    # Sanitise for safe filenames
    safe_stem = "".join(c if c.isalnum() or c in "_-" else "_" for c in stem)
    filename = f"{safe_stem}_{fingerprint}.provenance.json"

    path = out_dir / filename
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, ensure_ascii=False, default=str)

    return str(path.resolve())


# ═══════════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _detect_rest_version(run_record: Any) -> Dict[str, Any]:
    """Best-effort REST version detection from output."""
    version = "unknown"
    commit = "unknown"

    stdout = getattr(run_record, "stdout", "") or ""
    # Common REST version banner patterns
    import re
    m = re.search(
        r"(?:REST|rest)\s+(?:version\s+)?(?:v\s*)?(\d+\.\d+\.\d+)",
        stdout,
    )
    if m:
        version = m.group(1)
    m2 = re.search(
        r"(?:git\s+)?(?:commit|revision|hash)\s*[:=]?\s*([0-9a-f]{7,40})",
        stdout,
        re.IGNORECASE,
    )
    if m2:
        commit = m2.group(1)

    return {"name": "REST", "version": version, "commit": commit}


def _extract_run_info(run_record: Any) -> Dict[str, Any]:
    """Extract execution metadata from the run result."""
    status = getattr(run_record, "status", "unknown")
    wall_time = getattr(run_record, "wall_time", 0.0)
    return_code = getattr(run_record, "return_code", -1)
    mission = getattr(run_record, "mission_accomplished", False)

    return {
        "status": status,
        "wall_time_s": wall_time,
        "return_code": return_code,
        "mission_accomplished": mission,
    }


def _extract_results(parse_result: Any) -> Dict[str, Any]:
    """Extract structured observables from the parsed result."""
    scf_energy = getattr(parse_result, "scf_energy", None)
    total_energy = getattr(parse_result, "total_energy", None)
    scf_converged = getattr(parse_result, "scf_converged", False)
    scf_cycles = getattr(parse_result, "scf_cycles", 0)
    dipole = getattr(parse_result, "dipole", None)
    frequencies = getattr(parse_result, "frequencies", None)
    zpe = getattr(parse_result, "zpe", None)
    forces = getattr(parse_result, "forces", None)
    mp2_correlation = getattr(parse_result, "mp2_correlation", None)
    mission = getattr(parse_result, "mission_accomplished", False)

    results: Dict[str, Any] = {}

    if scf_energy is not None:
        results["scf_energy_ha"] = scf_energy
    if total_energy is not None:
        results["total_energy_ha"] = total_energy
    results["scf_converged"] = scf_converged
    results["scf_cycles"] = scf_cycles
    if dipole is not None:
        results["dipole_au"] = dipole
    if frequencies is not None:
        results["frequencies_cm1"] = (
            list(frequencies) if hasattr(frequencies, "__iter__") else frequencies
        )
    if zpe is not None:
        results["zpe_ha"] = zpe
    if forces is not None:
        results["forces_au"] = forces
    if mp2_correlation is not None:
        results["mp2_correlation"] = mp2_correlation
    results["mission_accomplished"] = mission

    return results


def _normalise_qa(qa_report: Any) -> List[Dict[str, Any]]:
    """Normalise QA results to a list of dicts, regardless of input type."""
    if qa_report is None:
        return []

    normalised: List[Dict[str, Any]] = []
    for item in qa_report:
        if isinstance(item, dict):
            normalised.append(item)
        elif hasattr(item, "_asdict"):
            # namedtuple-style (e.g. ValidationCheck)
            normalised.append(item._asdict())
        elif hasattr(item, "__dict__"):
            normalised.append({
                "name": getattr(item, "name", "unknown"),
                "passed": getattr(item, "passed", False),
                "severity": getattr(item, "severity", "unknown"),
                "detail": getattr(item, "detail", ""),
            })
        else:
            normalised.append({"raw": str(item)})

    return normalised