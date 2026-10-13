"""Protocol types for the AutoREST DSH bridge."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class DetectResult(TypedDict, total=False):
    """Structured result of the environment scan."""

    plugin_version: str
    bridge_protocol_version: int
    python_available: bool
    python_version: Optional[str]
    python_executable: Optional[str]
    autorest_core_available: bool
    numpy_available: bool
    rest_found: bool
    rest_executable: Optional[str]
    rest_version: Optional[str]
    rest_source: Optional[str]
    conda_env: Optional[str]
    conda_prefix: Optional[str]
    capabilities: List[str]
    warnings: List[str]
    all_rest_installations: List[Dict[str, Any]]
    next_action: str


class GenerateInputResult(TypedDict, total=False):
    """Structured result of input card generation."""

    ok: bool
    code: str
    message: str
    hint: str
    toml: str
    suggested_filename: str
    task_summary: Dict[str, Any]
    warnings: List[str]
    fingerprint: Optional[str]
    version: str


class ParseOutputResult(TypedDict, total=False):
    """Structured result of REST output parsing."""

    ok: bool
    code: str
    message: str
    hint: str
    scf_energy: Optional[float]
    scf_converged: bool
    scf_cycles: int
    total_energy: Optional[float]
    dipole: Optional[List[float]]
    frequencies: Optional[List[float]]
    imaginary_frequencies: Optional[List[float]]
    zpe: Optional[float]
    forces: Optional[List[List[float]]]
    optimized_geometry: Optional[str]
    optimization_converged: bool
    optimization_steps: int
    gw_finished: bool
    qp_gap_ev: Optional[float]
    homo_index_0based: Optional[int]
    lumo_index_0based: Optional[int]
    bse_spin: Optional[str]
    bse_states: List[Dict[str, Any]]
    mission_accomplished: bool
    wall_time_s: Optional[float]
    warnings: List[str]
    qa_checks: List[Dict[str, Any]]
    diagnosis: Optional[Dict[str, Any]]