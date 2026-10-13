"""
Chemical Task Intermediate Representation (IR)
==============================================

Machine-checkable, serialisable description of every REST calculation
task.  This module is the single source of truth for what AutoREST will
compute, how, and under what constraints — covering **all** REST job
types, not just GW-BSE.

Every ``CalculationTask`` can be hashed (SHA-256) for provenance, and its
``validate_electron_parity()`` method catches the most common
charge/multiplicity mismatch before a calculation even starts.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ═══════════════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════════════


class TaskIntent(str, Enum):
    """What kind of calculation the user (or the pipeline) intends to run."""

    ENERGY = "energy"
    """Single-point energy at a fixed geometry."""

    OPTIMIZATION = "optimization"
    """Geometry optimisation to a stationary point."""

    FORCE = "force"
    """Analytical nuclear gradient (forces)."""

    FREQUENCY = "frequency"
    """Harmonic vibrational frequencies + thermochemistry."""

    TDDFT = "tddft"
    """Time-dependent DFT excitation energies."""

    GW_ONLY = "gw_only"
    """G₀W₀ (or evGW, scGW) quasiparticle correction, no BSE."""

    BSE_SINGLET = "bse_singlet"
    """GW + Bethe-Salpeter singlet excitation energies."""

    BSE_TRIPLET = "bse_triplet"
    """GW + Bethe-Salpeter triplet excitation energies."""

    BSE_BOTH = "bse_both"
    """GW-BSE for both singlet and triplet (separate calculations)."""

    ABSORPTION_SPECTRUM = "absorption_spectrum"
    """Broadened absorption spectrum from excitation energies."""

    DELTA_EST = "delta_est"
    """Singlet-triplet gap ΔE_ST = E(S₁) − E(T₁) (from two BSE runs)."""


class MolecularCharacter(str, Enum):
    """Qualitative classification of the target molecule's electronic structure.

    Used by the planning layer to bias method recommendations — NOT a
    hard-coded rule, but a hint that the Skill/LLM layer can combine with
    literature evidence.
    """

    SMALL_RYDBERG = "small_rydberg"
    """Small molecule with significant Rydberg character (e.g. H₂O, NH₃)."""

    N_TO_PI_STAR = "n_to_pi_star"
    """n → π* transitions (e.g. carbonyls, azo compounds)."""

    HIGH_SYMMETRY_PI = "high_symmetry_pi"
    """π → π* in high-symmetry aromatics (benzene, PNA, coumarin)."""

    CHARGE_TRANSFER = "charge_transfer"
    """Significant intramolecular charge-transfer character."""

    EXTENDED_CHROMOPHORE = "extended_chromophore"
    """Large conjugated π-system (polyenes, porphyrins, rylene dyes)."""

    TRANSITION_METAL = "transition_metal"
    """Open d-shell; needs careful SCF, possible spin contamination."""

    GENERIC = "generic"
    """Fallback when no specific pattern is identified."""


# ═══════════════════════════════════════════════════════════════════════════════
# Geometry
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class Atom:
    """One atom: element symbol and Cartesian coordinates."""

    symbol: str
    x: float
    y: float
    z: float

    def __str__(self) -> str:
        return f"{self.symbol:<2s}  {self.x:14.8f}  {self.y:14.8f}  {self.z:14.8f}"


@dataclass
class Geometry:
    """Molecular geometry: a list of atoms with a known unit."""

    atoms: List[Atom]
    unit: str  # "angstrom" or "bohr"

    def to_rest_position(self) -> str:
        """Return the multi-line string expected by REST ``[geom].position``.

        Format::

            Element  x  y  z
            Element  x  y  z
            ...
        """
        return "\n".join(str(a) for a in self.atoms)

    @property
    def n_atoms(self) -> int:
        return len(self.atoms)

    @classmethod
    def from_xyz_lines(cls, lines: str, unit: str = "angstrom") -> "Geometry":
        """Parse a multi-line ``Element x y z`` string into a ``Geometry``."""
        atoms: List[Atom] = []
        for line in lines.strip().splitlines():
            fields = line.split()
            if len(fields) < 4:
                raise ValueError(
                    f"Geometry line has {len(fields)} field(s); "
                    f"need at least 4 (Element x y z): {line!r}"
                )
            atoms.append(
                Atom(
                    symbol=fields[0],
                    x=float(fields[1]),
                    y=float(fields[2]),
                    z=float(fields[3]),
                )
            )
        return cls(atoms=atoms, unit=unit)

    def total_electrons(self) -> int:
        """Sum of atomic numbers (neutral electron count)."""
        _Z = {
            "H": 1, "He": 2,
            "Li": 3, "Be": 4, "B": 5, "C": 6, "N": 7, "O": 8, "F": 9, "Ne": 10,
            "Na": 11, "Mg": 12, "Al": 13, "Si": 14, "P": 15, "S": 16,
            "Cl": 17, "Ar": 18,
            "K": 19, "Ca": 20,
            "Sc": 21, "Ti": 22, "V": 23, "Cr": 24, "Mn": 25,
            "Fe": 26, "Co": 27, "Ni": 28, "Cu": 29, "Zn": 30,
            "Br": 35,
            "I": 53,
        }
        total = 0
        for a in self.atoms:
            z = _Z.get(a.symbol)
            if z is None:
                raise ValueError(f"Unknown element symbol: {a.symbol!r}")
            total += z
        return total


# ═══════════════════════════════════════════════════════════════════════════════
# Plans
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class MethodPlan:
    """All method-level choices for a REST calculation.

    Covers DFT, GW, BSE, TDDFT, and frequency settings — unused fields
    are left at their defaults and ignored during card generation.
    """

    # ── DFT core ──────────────────────────────────────────────────
    xc: str = "PBE0"
    """Exchange-correlation functional (exact REST name)."""

    basis: str = "def2-SVP"
    """Orbital basis set short name."""

    aux_basis: Optional[str] = None
    """Auxiliary (RI) basis set.  When None, REST auto-selects."""

    empirical_dispersion: Optional[str] = None
    """``"d3"``, ``"d3bj"``, or ``"d4"``.  Omitted for double-hybrid/RPA."""

    eri_type: str = "ri-v"
    """ERI evaluation method (``"ri-v"``, ``"direct"``, …)."""

    use_ri_symm: bool = True
    """Exploit RI integral symmetry."""

    # ── GW ────────────────────────────────────────────────────────
    gw_enabled: bool = False
    gw_scheme: str = "extrapolated"
    """``"extrapolated"``, ``"linearize"``, or ``"qp equation"``."""

    scgw: str = "g0w0"
    """``"g0w0"``, ``"evgw0"``, ``"evgw"``, ``"scgw0"``."""

    gw_use_low_rank_contour: bool = True

    gw_n_roots: int = 5

    # ── BSE ───────────────────────────────────────────────────────
    bse_enabled: bool = False
    bse_spin: str = "singlet"
    """``"singlet"`` or ``"triplet"`` (always keep ground-state spin separate)."""

    bse_tda: bool = True
    """Tamm-Dancoff approximation."""

    bse_n_roots: int = 5

    bse_davidson_max_subspace: int = 50

    bse_davidson_restart: int = 10

    # ── TDDFT ─────────────────────────────────────────────────────
    tddft_enabled: bool = False
    tddft_spin: str = "singlet"
    tddft_method: str = "tda"
    """``"tda"`` or ``"lr"`` (linear response)."""

    tddft_n_roots: int = 6

    # ── Frequency / thermochemistry ───────────────────────────────
    frequency_enabled: bool = False
    temperature: float = 298.15
    """Temperature for thermochemistry (K)."""

    pressure: float = 1.0
    """Pressure for thermochemistry (atm)."""

    frequency_scale_factor: float = 1.0


@dataclass
class ResourcePlan:
    """Computational resource budget for a single REST job."""

    num_threads: int = 10
    max_memory_mb: Optional[int] = None
    walltime_s: Optional[float] = None
    """Soft wall-time estimate in seconds."""


@dataclass
class VerificationPlan:
    """What must hold for the result to be trusted.

    Each field is a *requirement* — the pipeline treats a violation as
    a failure.
    """

    require_scf_converged: bool = True
    """SCF cycle must reach convergence."""

    require_optimization_converged: bool = False
    """Geometry optimisation must converge (only for OPTIMIZATION intent)."""

    require_davidson_converged: bool = False
    """BSE Davidson eigensolver must converge."""

    require_all_roots: bool = False
    """All requested roots must be obtained (BSE / TDDFT)."""

    require_positive_qp_gap: bool = False
    """The quasiparticle gap must be positive."""

    require_mission_accomplished: bool = True
    """REST must print ``"Mission accomplished"``."""

    max_imaginary_frequencies: int = 0
    """Maximum allowed imaginary vibrational modes (0 for a minimum)."""

    max_spin_contamination_pct: float = 10.0
    """Maximum allowed spin contamination deviation from S(S+1)."""

    gradient_tolerance_au: float = 4.5e-4
    """Maximum allowed gradient for an optimised geometry."""


# ═══════════════════════════════════════════════════════════════════════════════
# CalculationTask
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class CalculationTask:
    """Complete, machine-checkable description of one REST calculation.

    This is the central data structure that flows through the entire
    AutoREST pipeline: Task IR → input generation → execution → parsing
    → QA → provenance.

    Every task carries enough information to be independently reproduced:
    geometry, method, resources, verification criteria, and a stable
    fingerprint.
    """

    # ── Identity ──────────────────────────────────────────────────
    system_name: str
    """Short, human-readable label (``"H2O"``, ``"benzene_opt"``, …)."""

    intent: TaskIntent
    """What kind of calculation this is."""

    # ── Input state ───────────────────────────────────────────────
    geometry: Geometry
    """Starting (or fixed) geometry."""

    molecular_character: MolecularCharacter = MolecularCharacter.GENERIC
    """Qualitative electronic structure classification."""

    charge: int = 0
    """Net molecular charge."""

    spin: int = 1
    """Spin multiplicity 2S+1 (minimum 1)."""

    # ── Method ────────────────────────────────────────────────────
    method: MethodPlan = field(default_factory=MethodPlan)

    # ── Resources ─────────────────────────────────────────────────
    resources: ResourcePlan = field(default_factory=ResourcePlan)

    # ── Verification ──────────────────────────────────────────────
    verification: VerificationPlan = field(default_factory=VerificationPlan)

    # ── Meta ──────────────────────────────────────────────────────
    tags: List[str] = field(default_factory=list)
    """User-defined labels for filtering / grouping."""

    notes: str = ""
    """Free-text notes (why this method, expected challenges, …)."""

    # ── Dependencies ──────────────────────────────────────────────
    depends_on: List[str] = field(default_factory=list)
    """Fingerprints of prerequisite tasks (for workflow ordering)."""

    # ── Methods ───────────────────────────────────────────────────

    def validate_electron_parity(self) -> List[str]:
        """Check charge + multiplicity compatibility.

        Rule:  (total electrons) = (sum of atomic numbers) − charge.

        * Even number of electrons → odd multiplicity (singlet, triplet, …)
        * Odd  number of electrons → even multiplicity (doublet, quartet, …)

        Returns
        -------
        list[str]
            Empty when everything is consistent, otherwise a list of
            human-readable issues.
        """
        issues: List[str] = []
        try:
            n_electrons = self.geometry.total_electrons() - self.charge
        except ValueError as exc:
            return [f"Cannot compute electron count: {exc}"]

        if n_electrons < 0:
            issues.append(
                f"Negative electron count ({n_electrons}) — "
                f"charge {self.charge} is too positive for this composition."
            )
            return issues

        if n_electrons % 2 == 0:
            # Even e⁻ → odd multiplicity
            if self.spin % 2 != 1:
                issues.append(
                    f"Even-electron system ({n_electrons} e⁻) must have "
                    f"odd multiplicity (1, 3, 5, …), got spin={self.spin}."
                )
        else:
            # Odd e⁻ → even multiplicity
            if self.spin % 2 != 0:
                issues.append(
                    f"Odd-electron system ({n_electrons} e⁻) must have "
                    f"even multiplicity (2, 4, 6, …), got spin={self.spin}."
                )

        if self.spin < 1:
            issues.append(f"Spin multiplicity must be >= 1, got {self.spin}.")

        return issues

    def fingerprint(self) -> str:
        """SHA-256 hash of the task's canonical JSON representation.

        This fingerprint is stable across Python runs on the same task —
        it captures the identity of *what* will be computed, not *when*
        or *where*.  It is used for provenance linking, workflow
        dependency tracking, and cache keying.
        """
        data = self._to_canonical_dict()
        # Sort keys for deterministic serialisation
        canonical = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _to_canonical_dict(self) -> Dict[str, Any]:
        """Convert the task to a dictionary suitable for hashing.

        Excludes volatile fields (notes, tags) that do not affect the
        scientific result.
        """
        return {
            "system_name": self.system_name,
            "intent": self.intent.value,
            "molecular_character": self.molecular_character.value,
            "geometry": {
                "atoms": [
                    {"symbol": a.symbol, "x": a.x, "y": a.y, "z": a.z}
                    for a in self.geometry.atoms
                ],
                "unit": self.geometry.unit,
            },
            "charge": self.charge,
            "spin": self.spin,
            "method": asdict(self.method),
            "resources": asdict(self.resources),
            "verification": asdict(self.verification),
            "depends_on": sorted(self.depends_on),
        }

    # ── Convenience ────────────────────────────────────────────────

    @property
    def needs_optimization(self) -> bool:
        return self.intent == TaskIntent.OPTIMIZATION

    @property
    def needs_gw(self) -> bool:
        return self.intent in (
            TaskIntent.GW_ONLY,
            TaskIntent.BSE_SINGLET,
            TaskIntent.BSE_TRIPLET,
            TaskIntent.BSE_BOTH,
            TaskIntent.DELTA_EST,
        )

    @property
    def needs_bse(self) -> bool:
        return self.intent in (
            TaskIntent.BSE_SINGLET,
            TaskIntent.BSE_TRIPLET,
            TaskIntent.BSE_BOTH,
            TaskIntent.DELTA_EST,
        )

    @property
    def needs_tddft(self) -> bool:
        return self.intent == TaskIntent.TDDFT

    @property
    def needs_frequency(self) -> bool:
        return self.intent == TaskIntent.FREQUENCY