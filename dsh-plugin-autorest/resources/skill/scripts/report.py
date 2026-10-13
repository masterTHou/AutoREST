"""
Human-Readable Report Generation
================================

Generates formatted terminal-ready reports for any REST calculation type.
Follows the AutoREST template with clear section separators and covers
all task intents: energy, optimisation, force, frequency, TDDFT, GW, BSE,
and absorption spectra.

The ``report()`` function takes a ``CalculationTask``, parsed result, and
optional QA results and returns a multi-line string ready for display.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .task_ir import CalculationTask, TaskIntent

# ═══════════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════════

HARTREE_TO_EV: float = 27.2113845
HARTREE_TO_KJ_MOL: float = 2625.4996
SEP: str = "─" * 60
BOLD_SEP: str = "═" * 60
THIN_SEP: str = "·" * 60


# ═══════════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════════


def report(
    task: CalculationTask,
    result: Any,              # ParsedResult or similar
    qa: Any = None,           # list of ValidationCheck or list of dict
) -> str:
    """Generate a human-readable report for a REST calculation.

    Parameters
    ----------
    task : CalculationTask
        The task that was submitted.
    result : ParsedResult or similar
        Parsed observables (expects ``.scf_energy``, ``.total_energy``,
        ``.scf_converged``, ``.scf_cycles``, ``.zpe``, ``.frequencies``,
        ``.dipole``, ``.forces``, ``.mission_accomplished``, ``.wall_time``,
        ``.optimization_converged``, ``.optimized_geometry``,
        ``.optimization_steps``).
    qa : list of ValidationCheck or list of dict or None
        Scientific validation / QA results.  Each item is expected to
        have ``.name``, ``.passed``, ``.severity``, and ``.detail``
        attributes (or corresponding dict keys).

    Returns
    -------
    str
        Formatted multi-line report string.
    """
    lines: List[str] = []

    # ── Header ────────────────────────────────────────────────────
    lines.append(BOLD_SEP)
    lines.append(_center(f"AutoREST  —  {_intent_label(task.intent)}"))
    lines.append(_center(f"System: {task.system_name}"))
    lines.append(BOLD_SEP)
    lines.append("")

    # ── System ─────────────────────────────────────────────────────
    lines.append("┌─ System")
    lines.append(f"│  Name:               {task.system_name}")
    lines.append(f"│  Intent:             {_intent_label(task.intent)}")
    lines.append(f"│  Character:          {task.molecular_character.value}")
    lines.append(f"│  Charge:             {task.charge}")
    lines.append(f"│  Spin (2S+1):        {task.spin}")
    lines.append(f"│  Atoms:              {task.geometry.n_atoms}")
    lines.append(f"│  Geometry unit:      {task.geometry.unit}")
    lines.append(f"│  Fingerprint:        {task.fingerprint()[:16]}…")
    lines.append("")

    # ── Method ─────────────────────────────────────────────────────
    lines.append("┌─ Method")
    m = task.method
    lines.append(f"│  Functional:         {m.xc}")
    lines.append(f"│  Basis:              {m.basis}")
    if m.aux_basis:
        lines.append(f"│  Aux basis:          {m.aux_basis}")
    if m.empirical_dispersion:
        lines.append(f"│  Dispersion:         {m.empirical_dispersion}")
    lines.append(f"│  ERI type:           {m.eri_type}")
    lines.append(f"│  RI symmetry:        {m.use_ri_symm}")
    lines.append(f"│  Threads:            {task.resources.num_threads}")

    if m.gw_enabled or task.intent in (TaskIntent.GW_ONLY, TaskIntent.BSE_SINGLET,
                                         TaskIntent.BSE_TRIPLET, TaskIntent.BSE_BOTH,
                                         TaskIntent.DELTA_EST):
        lines.append(f"│  GW scheme:          {m.gw_scheme}")
        lines.append(f"│  GW level:           {m.scgw}")
    if m.bse_enabled or task.intent in (TaskIntent.BSE_SINGLET, TaskIntent.BSE_TRIPLET,
                                          TaskIntent.BSE_BOTH, TaskIntent.DELTA_EST):
        lines.append(f"│  BSE spin:           {m.bse_spin}")
        lines.append(f"│  BSE TDA:            {m.bse_tda}")
        lines.append(f"│  BSE n_roots:        {m.bse_n_roots}")
    if m.tddft_enabled or task.intent == TaskIntent.TDDFT:
        lines.append(f"│  TDDFT spin:         {m.tddft_spin}")
        lines.append(f"│  TDDFT method:       {m.tddft_method}")
        lines.append(f"│  TDDFT n_roots:      {m.tddft_n_roots}")
    if m.frequency_enabled or task.intent == TaskIntent.FREQUENCY:
        lines.append(f"│  Temperature:        {m.temperature} K")
        lines.append(f"│  Pressure:           {m.pressure} atm")

    lines.append("")

    # ── Ground State ───────────────────────────────────────────────
    lines.append("┌─ Ground State")
    scf_energy = _get(result, "scf_energy")
    total_energy = _get(result, "total_energy")
    scf_converged = _get(result, "scf_converged", False)
    scf_cycles = _get(result, "scf_cycles", 0)

    if scf_energy is not None:
        lines.append(f"│  SCF Energy:         {scf_energy:16.10f} Ha")
        lines.append(f"│                      {scf_energy * HARTREE_TO_EV:16.6f} eV")
    if total_energy is not None and total_energy != scf_energy:
        lines.append(f"│  Total Energy:       {total_energy:16.10f} Ha")

    status_icon = "✓" if scf_converged else "✗"
    lines.append(f"│  SCF Converged:      {status_icon}  ({scf_cycles} cycles)")

    # Dipole
    dipole = _get(result, "dipole")
    if dipole is not None and len(dipole) >= 3:
        d_norm = (dipole[0]**2 + dipole[1]**2 + dipole[2]**2)**0.5
        lines.append(f"│  Dipole:             ({dipole[0]:.6f}, {dipole[1]:.6f}, {dipole[2]:.6f}) a.u.")
        lines.append(f"│  Dipole magnitude:   {d_norm:.6f} a.u.  =  {d_norm * 2.541746:.4f} Debye")

    # Optimisation
    opt_conv = _get(result, "optimization_converged", False)
    opt_steps = _get(result, "optimization_steps", 0)
    if opt_steps > 0 or task.intent == TaskIntent.OPTIMIZATION:
        opt_icon = "✓" if opt_conv else "✗"
        lines.append(f"│  Opt Converged:      {opt_icon}  ({opt_steps} steps)")

    lines.append("")

    # ── Excited States (GW / BSE / TDDFT) ──────────────────────────
    lines.extend(_build_excited_state_section(task, result))

    # ── Forces ─────────────────────────────────────────────────────
    forces = _get(result, "forces")
    if forces is not None and len(forces) > 0:
        lines.append("┌─ Forces (a.u.)")
        for i, f in enumerate(forces):
            if len(f) >= 3:
                f_norm = (f[0]**2 + f[1]**2 + f[2]**2)**0.5
                lines.append(
                    f"│  Atom {i+1:3d}:   "
                    f"({f[0]:10.6f}, {f[1]:10.6f}, {f[2]:10.6f})  "
                    f"|F| = {f_norm:.6f}"
                )
        lines.append("")

    # ── Frequencies ────────────────────────────────────────────────
    freqs = _get(result, "frequencies")
    zpe = _get(result, "zpe")
    if freqs is not None and len(freqs) > 0:
        lines.append("┌─ Vibrational Frequencies")
        imag = [f for f in freqs if f < 0]
        real_freqs = [f for f in freqs if f >= 0]
        if imag:
            lines.append(f"│  Imaginary:  {len(imag)} mode(s): {', '.join(f'{v:.2f}' for v in sorted(imag))}")
        if real_freqs:
            # Show first 6 and last 2
            if len(real_freqs) <= 8:
                lines.append(f"│  Real:       {', '.join(f'{v:.2f}' for v in real_freqs)}")
            else:
                head = ", ".join(f"{v:.2f}" for v in real_freqs[:6])
                tail = ", ".join(f"{v:.2f}" for v in real_freqs[-2:])
                lines.append(f"│  Real:       {head}, …, {tail}  ({len(real_freqs)} modes)")
        if zpe is not None:
            lines.append(f"│  ZPE:                {zpe:12.8f} Ha")
            lines.append(f"│                      {zpe * HARTREE_TO_KJ_MOL:12.4f} kJ/mol")
        lines.append("")

    # ── QA ─────────────────────────────────────────────────────────
    if qa is not None:
        qa_items = _normalise_qa(qa)
        lines.append("┌─ Scientific QA")
        passed = sum(1 for q in qa_items if q.get("passed", False))
        failed = sum(1 for q in qa_items if not q.get("passed", False))
        lines.append(f"│  Checks:  {passed} passed, {failed} failed")
        lines.append("│")
        for q in qa_items:
            name = q.get("name", "unknown")
            ok = q.get("passed", False)
            severity = q.get("severity", "ok")
            icon = "✓" if ok else ("⚠" if severity == "warning" else "✗")
            lines.append(f"│  {icon} [{severity:<7}] {name}")
        lines.append("")

    # ── Performance ────────────────────────────────────────────────
    lines.append("┌─ Performance")
    wall_time = _get(result, "wall_time")
    if wall_time is not None:
        if wall_time < 60:
            lines.append(f"│  Wall time:          {wall_time:.1f} s")
        elif wall_time < 3600:
            lines.append(f"│  Wall time:          {wall_time/60:.1f} min  ({wall_time:.0f} s)")
        else:
            lines.append(f"│  Wall time:          {wall_time/3600:.2f} h  ({wall_time:.0f} s)")
    lines.append(f"│  Threads:            {task.resources.num_threads}")

    mission = _get(result, "mission_accomplished", False)
    mission_icon = "✓" if mission else "✗"
    lines.append(f"│  Mission:            {mission_icon}  {'Accomplished' if mission else 'NOT accomplished'}")

    lines.append("")

    # ── Warnings ───────────────────────────────────────────────────
    parse_warnings = _get(result, "warnings", []) or []
    if parse_warnings:
        lines.append("┌─ Warnings")
        for w in parse_warnings[:10]:
            lines.append(f"│  ⚠ {w}")
        if len(parse_warnings) > 10:
            lines.append(f"│  … and {len(parse_warnings) - 10} more")
        lines.append("")

    # ── Footer ─────────────────────────────────────────────────────
    lines.append(BOLD_SEP)
    lines.append(_center("End of Report"))
    lines.append(BOLD_SEP)

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# Section builders
# ═══════════════════════════════════════════════════════════════════════════════


def _build_excited_state_section(
    task: CalculationTask,
    result: Any,
) -> List[str]:
    """Build the excited-state section for GW, BSE, or TDDFT results."""
    lines: List[str] = []

    # ── GW QP ──────────────────────────────────────────────────────
    gw = _get(result, "gwbse_result")  # Optional GWBSEResult attached by pipeline
    if gw is not None:
        lines.append("┌─ GW Quasiparticle")
        qp_gap = getattr(gw, "qp_gap_ev", None)
        homo_qp = getattr(gw, "homo_qp_ha", None)
        lumo_qp = getattr(gw, "lumo_qp_ha", None)
        fermi = getattr(gw, "fermi_surface_found", False)
        if qp_gap is not None:
            lines.append(f"│  QP Gap:             {qp_gap:.4f} eV")
        if homo_qp is not None:
            lines.append(f"│  HOMO QP:            {homo_qp:.6f} Ha  =  {homo_qp * HARTREE_TO_EV:.4f} eV")
        if lumo_qp is not None:
            lines.append(f"│  LUMO QP:            {lumo_qp:.6f} Ha  =  {lumo_qp * HARTREE_TO_EV:.4f} eV")
        lines.append(f"│  Fermi surface:      {'Found' if fermi else 'NOT FOUND'}")
        lines.append("")

        # ── BSE states ─────────────────────────────────────────────
        bse_states = getattr(gw, "states", None)
        if bse_states is not None and len(bse_states) > 0:
            bse_spin = getattr(gw, "bse_spin", task.method.bse_spin)
            lines.append(f"┌─ BSE Excited States ({bse_spin})")
            lines.append(f"│  {'State':<7} {'E(eV)':<10} {'λ(nm)':<10} {'f_osc':<10}")
            lines.append(f"│  {'─'*6}  {'─'*9}  {'─'*9}  {'─'*9}")
            for s in bse_states:
                idx = getattr(s, "index", "?")
                ev = getattr(s, "energy_ev", 0.0)
                nm = getattr(s, "wavelength_nm", 0.0)
                osc = getattr(s, "oscillator_strength", 0.0)
                lines.append(
                    f"│  S{idx:<6} {ev:<10.4f} {nm:<10.1f} {osc:<10.6f}"
                )
            lines.append("")

    # ── TDDFT states ───────────────────────────────────────────────
    tddft = _get(result, "tddft_result")
    if tddft is not None:
        tddft_states = getattr(tddft, "states", None) or _get(result, "tddft_states")
        if tddft_states is not None and len(tddft_states) > 0:
            lines.append("┌─ TDDFT Excited States")
            lines.append(f"│  {'State':<7} {'E(eV)':<10} {'λ(nm)':<10} {'f_osc':<10}")
            lines.append(f"│  {'─'*6}  {'─'*9}  {'─'*9}  {'─'*9}")
            for s in tddft_states:
                idx = getattr(s, "index", getattr(s, "state", "?"))
                ev = getattr(s, "energy_ev", getattr(s, "excitation_energy_ev", 0.0))
                nm = getattr(s, "wavelength_nm", 1240.0 / ev if ev > 0 else 0.0)
                osc = getattr(s, "oscillator_strength", 0.0)
                lines.append(
                    f"│  S{idx:<6} {ev:<10.4f} {nm:<10.1f} {osc:<10.6f}"
                )
            lines.append("")

    # ── ΔE_ST (for BSE_BOTH / DELTA_EST) ──────────────────────────
    delta_est = _get(result, "delta_est_ev")
    if delta_est is not None:
        lines.append("┌─ Singlet-Triplet Gap")
        lines.append(f"│  ΔE_ST = S₁ − T₁ = {delta_est:.4f} eV")
        lines.append("")

    return lines


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _get(obj: Any, attr: str, default: Any = None) -> Any:
    """Safely get an attribute or dict key from *obj*."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return getattr(obj, attr, default)


def _intent_label(intent: TaskIntent) -> str:
    """Human-readable label for a TaskIntent."""
    labels: Dict[TaskIntent, str] = {
        TaskIntent.ENERGY: "Single-Point Energy",
        TaskIntent.OPTIMIZATION: "Geometry Optimisation",
        TaskIntent.FORCE: "Force Calculation",
        TaskIntent.FREQUENCY: "Frequency + Thermochemistry",
        TaskIntent.TDDFT: "TD-DFT Excitation",
        TaskIntent.GW_ONLY: "GW Quasiparticle",
        TaskIntent.BSE_SINGLET: "GW-BSE (Singlet)",
        TaskIntent.BSE_TRIPLET: "GW-BSE (Triplet)",
        TaskIntent.BSE_BOTH: "GW-BSE (Singlet + Triplet)",
        TaskIntent.ABSORPTION_SPECTRUM: "Absorption Spectrum",
        TaskIntent.DELTA_EST: "ΔE_ST (Singlet-Triplet Gap)",
    }
    return labels.get(intent, intent.value)


def _center(text: str, width: int = 60) -> str:
    """Centre *text* in a field of *width*."""
    return text.center(width)


def _normalise_qa(qa: Any) -> List[Dict[str, Any]]:
    """Normalise QA results to a list of dicts."""
    if qa is None:
        return []
    normalised: List[Dict[str, Any]] = []
    for item in qa:
        if isinstance(item, dict):
            normalised.append(item)
        elif hasattr(item, "_asdict"):
            normalised.append(item._asdict())
        elif hasattr(item, "__dict__"):
            normalised.append({
                "name": getattr(item, "name", "unknown"),
                "passed": getattr(item, "passed", False),
                "severity": getattr(item, "severity", "unknown"),
                "detail": getattr(item, "detail", ""),
            })
        else:
            normalised.append({"name": str(item), "passed": True, "severity": "ok", "detail": ""})
    return normalised