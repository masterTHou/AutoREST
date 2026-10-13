"""
REST Output Parsing Module
==========================

Parses REST electronic-structure output files and extracts structured
information: SCF energies, geometry optimisations, frequencies, forces,
dipole moments, MP2 correlation energies, and GW-BSE results.

The public entry point is :meth:`OutputParser.parse`, which accepts
either a file path or the output text itself and returns a
:class:`ParsedResult` dataclass.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HARTREE_TO_EV: float = 27.2113845
EV_TO_NM_FACTOR: float = 1239.84  # nm·eV
CM1_TO_EV: float = 1.0 / 8065.54429  # approximate

logger = logging.getLogger(__name__)


# ===================================================================
# ParsedResult
# ===================================================================


@dataclass
class ParsedResult:
    """Container for all parsed data extracted from a REST output file.

    Every field defaults to ``None`` (or an empty list) and is populated
    only when the corresponding section is found and successfully
    parsed.
    """

    # -- SCF -----------------------------------------------------------------
    scf_energy: Optional[float] = None
    """Final SCF energy in Hartree."""

    scf_converged: bool = False
    """Whether the SCF cycle reached convergence."""

    scf_cycles: int = 0
    """Number of SCF iterations."""

    scf_energy_change: Optional[float] = None
    """Energy difference between the last two SCF cycles (Hartree)."""

    # -- Optimisation --------------------------------------------------------
    optimized_geometry: Optional[str] = None
    """Optimised geometry in XYZ format (element x y z lines)."""

    optimization_steps: int = 0
    """Number of geometry optimisation steps."""

    optimization_converged: bool = False
    """Whether the geometry optimisation reached convergence."""

    # -- Forces --------------------------------------------------------------
    forces: Optional[List[List[float]]] = None
    """Forces on each atom, shape ``(n_atoms, 3)``."""

    # -- Vibrational ---------------------------------------------------------
    frequencies: List[float] = field(default_factory=list)
    """Harmonic vibrational frequencies in cm⁻¹."""

    zpe: Optional[float] = None
    """Zero-point vibrational energy (Hartree)."""

    # -- Dipole --------------------------------------------------------------
    dipole: Optional[List[float]] = None
    """Dipole moment vector ``[dx, dy, dz]`` in atomic units (e·a₀)."""

    # -- MP2 correlation (double-hybrid / post-SCF) ---------------------------
    mp2_correlation: Optional[Dict[str, Any]] = None
    """MP2 correlation energy and related quantities."""

    # -- Total energy --------------------------------------------------------
    total_energy: Optional[float] = None
    """Total energy reported by REST (may include post-SCF corrections)."""

    # -- Timing --------------------------------------------------------------
    wall_time: Optional[float] = None
    """Total wall-clock time in seconds."""

    # -- Status --------------------------------------------------------------
    mission_accomplished: bool = False
    """Whether the ``REST: Mission accomplished`` marker was found."""

    # -- Diagnostics ---------------------------------------------------------
    warnings: List[str] = field(default_factory=list)
    """Non-fatal warnings collected during parsing."""

    raw_text: str = ""
    """The full, unmodified output text (for debugging)."""


# ===================================================================
# OutputParser
# ===================================================================


class OutputParser:
    """Parser for REST electronic-structure output files.

    Parameters
    ----------
    text : str, optional
        If given, the parser is immediately initialised with this text.
    """

    # ------------------------------------------------------------------
    # Compile-once regex patterns
    # ------------------------------------------------------------------
    # Order matters for some multi-pattern searches.

    # SCF
    _RE_SCF_CONVERGED: re.Pattern = re.compile(
        r"SCF\s+(?:is\s+)?converged", re.IGNORECASE
    )
    _RE_SCF_FINAL: re.Pattern = re.compile(
        r"The\s+SCF\s+energy\s*:\s*([+-]?\d+\.\d+)\s*Ha", re.IGNORECASE,
    )
    _RE_SCF_LAST: re.Pattern = re.compile(
        r"Energy:\s+([+-]?\d+\.\d+)\s+Ha", re.IGNORECASE,
    )
    _RE_SCF_CONVERGED_AFTER: re.Pattern = re.compile(
        r"SCF\s+is\s+converged\s+after\s+(\d+)\s+iterations", re.IGNORECASE,
    )
    _RE_SCF_ITERATION: re.Pattern = re.compile(
        r"\b(?:SCF\s+)?(?:cycle|iteration)\s*\d+\s*[:=]",
        re.IGNORECASE,
    )
    _RE_SCF_CYCLE_LINE: re.Pattern = re.compile(
        r"\b(?:SCF|cycle|iter)\s*(\d+)\b", re.IGNORECASE,
    )
    _RE_ENERGY_CHANGE: re.Pattern = re.compile(
        r"(?:delta E|energy\s*change|ΔE|dE)\s*[:=]?\s*(-?\d+\.\d+(?:[eE][+-]?\d+)?)",
        re.IGNORECASE,
    )
    _RE_DENSITY_CHANGE: re.Pattern = re.compile(
        r"(?:density\s*change|Δρ|drms)\s*[:=]?\s*(\d+\.\d+(?:[eE][+-]?\d+)?)",
        re.IGNORECASE,
    )
    _RE_EIGENVALUE_CHANGE: re.Pattern = re.compile(
        r"(?:eigenvalue\s*change|Δε|deigen)\s*[:=]?\s*(\d+\.\d+(?:[eE][+-]?\d+)?)",
        re.IGNORECASE,
    )

    # Geometry optimisation
    _RE_OPT_CONVERGED: re.Pattern = re.compile(
        r"(?:Optimization\s+converged|Geometry\s+optimization\s+converged"
        r"|OPTIMIZATION\s+CONVERGED)",
        re.IGNORECASE,
    )
    _RE_OPT_STEP: re.Pattern = re.compile(
        r"(?:Geometry\s+)?(?:optimization|opt)\s*(?:step|cycle)\s*[:=\s]*(\d+)",
        re.IGNORECASE,
    )
    _RE_OPT_ENERGY: re.Pattern = re.compile(
        r"(?:Optimized energy|Final energy|opt energy)\s*[:=]?\s*(-?\d+\.\d+)",
        re.IGNORECASE,
    )

    # Geometry / coordinates
    _RE_GEOM_BLOCK: re.Pattern = re.compile(
        r"(?:Final\s+)?(?:Cartesian\s+)?[Cc]oordinates\s*\(?(?:angstrom|bohr|a\.u\.)?\)?"
        r"(?:.*?\n){0,2}"
        r"(?:-{3,}\s*\n)?"
        r"((?:\s*\w+\s+[-+]?\d+\.\d+\s+[-+]?\d+\.\d+\s+[-+]?\d+\.\d+\s*\n)+)",
        re.IGNORECASE,
    )
    _RE_COORD_LINE: re.Pattern = re.compile(
        r"^\s*(\w+)\s+([-+]?\d+\.\d+)\s+([-+]?\d+\.\d+)\s+([-+]?\d+\.\d+)\s*$",
        re.MULTILINE,
    )
    _RE_XYZ_COORD: re.Pattern = re.compile(
        r"(\w{1,2})\s+([-+]?\d+\.\d+)\s+([-+]?\d+\.\d+)\s+([-+]?\d+\.\d+)",
    )

    # Frequencies & thermochemistry
    _RE_FREQ_SECTION: re.Pattern = re.compile(
        r"Frequencies?\s*(?:\(cm\^-1\))?\s*[-:]\s*([\d\s\.]+)",
        re.IGNORECASE,
    )
    _RE_FREQ_VALUES: re.Pattern = re.compile(
        r"(?:Frequencies?\s*[-:]\s*)?([\d\s.]+)",
    )
    _RE_ZPE: re.Pattern = re.compile(
        r"(?:Zero.point(?:\s+energy|correction)?|ZPE)\s*[:=]?\s*"
        r"(-?\d+\.\d+)\s*(?:Hartree|Ha|a\.u\.|kJ/mol|kcal/mol)?",
        re.IGNORECASE,
    )
    _RE_THERMO_LINE: re.Pattern = re.compile(
        r"(?:Enthalpy|Entropy|Gibbs\s+free\s+energy|Thermal\s+correction"
        r"|Thermal\s+enthalpy|Thermal\s+free\s+energy)\s*[:=]?\s*"
        r"(-?\d+\.\d+)",
        re.IGNORECASE,
    )

    # Forces
    _RE_FORCE_SECTION: re.Pattern = re.compile(
        r"(?:Atomic\s+)?[Ff]orces?\s*(?:\(.*?\))?\s*\n"
        r"(?:-{3,}\s*\n)?"
        r"((?:\s*\w+\s+[-+]?\d+\.\d+\s+[-+]?\d+\.\d+\s+[-+]?\d+\.\d+\s*\n)+)",
    )
    _RE_FORCE_ATOM: re.Pattern = re.compile(
        r"\b(\w+)\s+([-+]?\d+\.\d+)\s+([-+]?\d+\.\d+)\s+([-+]?\d+\.\d+)",
    )

    # Dipole
    _RE_DIPOLE_SECTION: re.Pattern = re.compile(
        r"[Dd]ipole\s+moment",
        re.IGNORECASE,
    )
    _RE_DIPOLE_COMP: re.Pattern = re.compile(
        r"[Dd](?:ipole)?\s*[xyz]\s*[:=]?\s*(-?\d+\.\d+)",
        re.IGNORECASE,
    )
    _RE_DIPOLE_TOTAL: re.Pattern = re.compile(
        r"(?:Total\s+)?[Dd]ipole\s*(?:moment|magnitude)?\s*[:=]?\s*(-?\d+\.\d+)",
        re.IGNORECASE,
    )
    _RE_DIPOLE_VECTOR: re.Pattern = re.compile(
        r"(?:Dipole\s*(?:moment\s*)?(?:vector|components?)?\s*[:=]?\s*)"
        r"\(\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)\s*\)",
        re.IGNORECASE,
    )
    _RE_DIPOLE_COL: re.Pattern = re.compile(
        r"(?:Dipole\s+)?[XYZ]\s*[:=]?\s*(-?\d+\.\d+)",
        re.IGNORECASE,
    )

    # MP2 correlation
    _RE_MP2_CORR: re.Pattern = re.compile(
        r"(?:MP2\s+)?correlation\s+energy\s*[:=]?\s*(-?\d+\.\d+)",
        re.IGNORECASE,
    )
    _RE_MP2_TOTAL: re.Pattern = re.compile(
        r"(?:MP2\s+)?total\s+energy\s*[:=]?\s*(-?\d+\.\d+)",
        re.IGNORECASE,
    )
    _RE_RI_MP2: re.Pattern = re.compile(
        r"RI[- ]MP2\s+correlation\s*[:=]?\s*(-?\d+\.\d+)",
        re.IGNORECASE,
    )

    # Wall time
    _RE_WALL_TIME: re.Pattern = re.compile(
        r"(?:Total\s+)?[Ww]all\s+time\s*[:=]?\s*"
        r"(\d+\.?\d*)\s*(?:s|sec|seconds?)",
        re.IGNORECASE,
    )
    _RE_CPU_TIME: re.Pattern = re.compile(
        r"(?:Total\s+)?[Cc]pu\s+time\s*[:=]?\s*"
        r"(\d+\.?\d*)\s*(?:s|sec|seconds?)",
        re.IGNORECASE,
    )
    _RE_TIMING: re.Pattern = re.compile(
        r"(?:Elapsed|Total)\s+time\s*[:=]?\s*"
        r"(\d+\.?\d*)\s*(?:s|sec|seconds?)?",
        re.IGNORECASE,
    )

    # Mission accomplished
    _RE_MISSION: re.Pattern = re.compile(
        r"REST\s*:\s*Mission\s+accomplished",
        re.IGNORECASE,
    )

    # GW-BSE ----------------------------------------------------------------
    _RE_QP_ENERGY: re.Pattern = re.compile(
        r"(?:QP|quasiparticle)\s+energy\s*"
        r"(?:band\s+\d+\s*)?(?:kpt\s+\d+\s*)?[:=]?\s*(-?\d+\.\d+)",
        re.IGNORECASE,
    )
    _RE_BSE_STATE: re.Pattern = re.compile(
        r"(?:BSE\s+)?(?:state|excited\s+state)\s+\d+\s*[:=]?\s*"
        r"(-?\d+\.\d+)\s*(?:eV|Ha)?",
        re.IGNORECASE,
    )
    _RE_BSE_OSC: re.Pattern = re.compile(
        r"[Oo]scillator\s+(?:strength|str)\s*[:=]?\s*(\d+\.\d+(?:[eE][+-]?\d+)?)",
        re.IGNORECASE,
    )
    _RE_BSE_DOM_TRANS: re.Pattern = re.compile(
        r"(?:dominant|leading)\s+transitions?\s*[:=]?\s*"
        r"(\w+)\s*(?:->|→)\s*(\w+)",
        re.IGNORECASE,
    )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def __init__(self, text: Optional[str] = None) -> None:
        self._text: str = text or ""

    # ------------------------------------------------------------------
    def parse(self, text_or_path: Union[str, Path]) -> ParsedResult:
        """Parse a REST output file and return a :class:`ParsedResult`.

        Parameters
        ----------
        text_or_path : str or pathlib.Path
            Either the output text itself or the path to a file that
            contains it.

        Returns
        -------
        ParsedResult
            The populated result object.  Fields that could not be
            parsed are left at their default (``None`` / empty).
        """
        path: Optional[Path] = None
        if isinstance(text_or_path, Path):
            path = text_or_path
        elif isinstance(text_or_path, str):
            candidate = Path(text_or_path)
            # Heuristic: treat as path when the string looks like a file
            # and the file exists, else treat as raw text.
            if candidate.exists() and candidate.is_file():
                path = candidate
            elif "\n" not in text_or_path and len(text_or_path) < 512:
                # Could still be a file path – try to resolve
                maybe = Path(text_or_path)
                if maybe.exists() and maybe.is_file():
                    path = maybe

        if path is not None:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                logger.exception("Failed to read output file %s", path)
                result = ParsedResult()
                result.warnings.append(f"Could not read {path}")
                return result
        else:
            text = text_or_path  # already a string

        # Ensure str type
        text = str(text)
        self._text = text

        result = ParsedResult(raw_text=text)

        # Parse each section independently
        scf = self.parse_scf(text)
        result.scf_energy = scf.get("energy")
        result.scf_converged = bool(scf.get("converged"))
        result.scf_cycles = int(scf.get("cycles", 0))
        result.scf_energy_change = scf.get("energy_change")

        geom = self.parse_geometry(text)
        result.optimized_geometry = geom.get("coordinates")
        result.optimization_steps = int(geom.get("steps", 0))
        result.optimization_converged = bool(geom.get("converged"))

        freq = self.parse_frequencies(text)
        if freq.get("frequencies"):
            result.frequencies = freq["frequencies"]
        result.zpe = freq.get("zpe")

        force = self.parse_force(text)
        result.forces = force.get("forces")

        dipole = self.parse_dipole(text)
        result.dipole = dipole.get("dipole")

        mp2 = self.parse_mp2_correlation(text)
        if mp2:
            result.mp2_correlation = mp2

        result.wall_time = self._parse_wall_time(text)

        # Total energy: prefer SCF energy, but post-SCF corrections
        # may be present.
        result.total_energy = self._resolve_total_energy(text, scf, mp2)

        result.mission_accomplished = self._parse_mission(text)

        # Collect any parse-level warnings
        result.warnings.extend(self._collect_warnings(result))

        return result

    # ------------------------------------------------------------------
    # Section parsers
    # ------------------------------------------------------------------

    def parse_scf(self, text: str) -> Dict[str, Any]:
        """Extract SCF convergence information.

        Returns
        -------
        dict
            Keys: ``energy``, ``converged``, ``cycles``,
            ``energy_change``, ``density_change``, ``eigenvalue_change``.
        """
        info: Dict[str, Any] = {
            "energy": None,
            "converged": False,
            "cycles": 0,
            "energy_change": None,
            "density_change": None,
            "eigenvalue_change": None,
        }

        # Convergence status
        if self._RE_SCF_CONVERGED.search(text):
            info["converged"] = True

        # Energy
        # Try the definitive summary line first
        m = self._RE_SCF_FINAL.search(text)
        if m:
            info["energy"] = float(m.group(1))
        else:
            # Fall back to last "Energy:" line
            hits = self._RE_SCF_LAST.findall(text)
            info["energy"] = float(hits[-1]) if hits else None

        # Cycle count – look for convergence declaration
        hits = self._RE_SCF_CONVERGED_AFTER.findall(text)
        info["cycles"] = int(hits[-1]) if hits else 0
        if info["cycles"] == 0:
            cycles = len(self._RE_SCF_ITERATION.findall(text))
            if cycles == 0:
                cycles = len(self._RE_SCF_CYCLE_LINE.findall(text))
            info["cycles"] = cycles if cycles else 0

        # Convergence metrics
        info["energy_change"] = self._extract_float_after(
            text, self._RE_ENERGY_CHANGE, group=1
        )
        info["density_change"] = self._extract_float_after(
            text, self._RE_DENSITY_CHANGE, group=1
        )
        info["eigenvalue_change"] = self._extract_float_after(
            text, self._RE_EIGENVALUE_CHANGE, group=1
        )

        return info

    # ------------------------------------------------------------------
    def parse_geometry(self, text: str) -> Dict[str, Any]:
        """Extract optimised geometry.

        Returns
        -------
        dict
            Keys: ``coordinates`` (str, XYZ lines), ``name``, ``unit``,
            ``steps``, ``converged``.
        """
        info: Dict[str, Any] = {
            "coordinates": None,
            "name": None,
            "unit": None,
            "steps": 0,
            "converged": False,
        }

        if self._RE_OPT_CONVERGED.search(text):
            info["converged"] = True

        # Optimisation steps
        step_matches = self._RE_OPT_STEP.findall(text)
        if step_matches:
            try:
                info["steps"] = max(int(s) for s in step_matches)
            except (ValueError, TypeError):
                pass

        # Geometry block
        geom_match = self._RE_GEOM_BLOCK.search(text)
        if geom_match:
            block = geom_match.group(1)
            lines = block.strip().splitlines()
            coord_lines = []
            for line in lines:
                m = self._RE_COORD_LINE.match(line)
                if m:
                    coord_lines.append(f"{m.group(1):>2s}  "
                                      f"{float(m.group(2)):14.8f}  "
                                      f"{float(m.group(3)):14.8f}  "
                                      f"{float(m.group(4)):14.8f}")
            if coord_lines:
                info["coordinates"] = "\n".join(coord_lines)

        # Unit detection
        for unit_pattern, unit_name in [
            (r"\(angstrom\)", "angstrom"),
            (r"\(bohr\)", "bohr"),
            (r"\(a\.\s*u\.\s*\)", "bohr"),
            (r"\bAngstrom\b", "angstrom"),
            (r"\bBohr\b", "bohr"),
        ]:
            if re.search(unit_pattern, text, re.IGNORECASE):
                info["unit"] = unit_name
                break

        return info

    # ------------------------------------------------------------------
    def parse_frequencies(self, text: str) -> Dict[str, Any]:
        """Extract harmonic frequencies and ZPE.

        Returns
        -------
        dict
            Keys: ``frequencies`` (list[float]), ``zpe``,
            ``thermochemistry`` (dict or None).
        """
        info: Dict[str, Any] = {
            "frequencies": [],
            "zpe": None,
            "thermochemistry": None,
        }

        # Frequencies
        freq_section = self._extract_block(text, r"Frequencies?\s*(?:\(cm\^-1\))?")
        if freq_section:
            # Find all floating numbers in the block
            values: List[float] = []
            for line in freq_section.splitlines():
                nums = re.findall(r"[-+]?\d+\.\d+", line)
                for n in nums:
                    try:
                        val = float(n)
                        # Only keep physically reasonable frequencies
                        if -500.0 < val < 50000.0:
                            values.append(val)
                    except ValueError:
                        pass
            # Remove duplicates (same line may match multiple patterns)
            info["frequencies"] = list(dict.fromkeys(values))
        else:
            # Fallback: search the whole text for frequency-like numbers
            freq_matches = self._RE_FREQ_SECTION.findall(text)
            if freq_matches:
                all_vals: List[float] = []
                for match in freq_matches:
                    nums = re.findall(r"[-+]?\d+\.\d+", match)
                    for n in nums:
                        try:
                            val = float(n)
                            if -500.0 < val < 50000.0:
                                all_vals.append(val)
                        except ValueError:
                            pass
                info["frequencies"] = list(dict.fromkeys(all_vals))

        # ZPE
        zpe_match = self._RE_ZPE.search(text)
        if zpe_match:
            info["zpe"] = float(zpe_match.group(1))

        # Thermochemistry
        thermo: Dict[str, float] = {}
        for m in self._RE_THERMO_LINE.finditer(text):
            label = m.group(1).strip().lower().replace(" ", "_")
            thermo[label] = float(m.group(2))
        if thermo:
            info["thermochemistry"] = thermo

        return info

    # ------------------------------------------------------------------
    def parse_force(self, text: str) -> Dict[str, Any]:
        """Extract atomic forces.

        Returns
        -------
        dict
            Key ``forces``: ``list[list[float]]`` (n_atoms × 3).
        """
        info: Dict[str, Any] = {"forces": None}

        section = self._RE_FORCE_SECTION.search(text)
        if not section:
            # Try a looser extraction
            block = self._extract_block(text, r"[Ff]orces?\s*\n")
            if block:
                section = re.search(
                    r"((?:\s*\w+\s+[-+]?\d+\.\d+\s+[-+]?\d+\.\d+\s+[-+]?\d+\.\d+\s*\n)+)",
                    block,
                )
                if section:
                    section = type("_", (), {"group": lambda self, g=1: section.group(1) if g == 1 else ""})()

        if section:
            block_text = section.group(1) if hasattr(section, "group") else str(section)
            forces: List[List[float]] = []
            for line in block_text.strip().splitlines():
                m = self._RE_FORCE_ATOM.search(line)
                if m:
                    try:
                        forces.append(
                            [float(m.group(2)), float(m.group(3)), float(m.group(4))]
                        )
                    except ValueError:
                        continue
            if forces:
                info["forces"] = forces

        return info

    # ------------------------------------------------------------------
    def parse_dipole(self, text: str) -> Dict[str, Any]:
        """Extract dipole moment.

        Returns
        -------
        dict
            Key ``dipole``: ``[dx, dy, dz]`` (list of 3 floats).
        """
        info: Dict[str, Any] = {"dipole": None}

        section = self._extract_block(
            text,
            r"[Dd]ipole\s+moment",
            end_marker=r"\n\s*\n",
        )
        search_text = section if section else text

        # Try vector notation first: (dx, dy, dz)
        vec = self._RE_DIPOLE_VECTOR.search(search_text)
        if vec:
            info["dipole"] = [float(vec.group(1)), float(vec.group(2)), float(vec.group(3))]
            return info

        # Try individual components
        comps = self._RE_DIPOLE_COMP.findall(search_text)
        if not comps:
            comps = self._RE_DIPOLE_COL.findall(search_text)

        if len(comps) >= 3:
            try:
                info["dipole"] = [float(c) for c in comps[:3]]
            except ValueError:
                pass

        return info

    # ------------------------------------------------------------------
    def parse_mp2_correlation(self, text: str) -> Dict[str, Any]:
        """Extract MP2 / double-hybrid correlation data.

        Returns
        -------
        dict
            Keys may include ``correlation_energy``, ``total_energy``,
            ``ri_mp2_correlation``.
        """
        info: Dict[str, Any] = {}

        corr = self._extract_float_after(text, self._RE_MP2_CORR, group=1)
        if corr is not None:
            info["correlation_energy"] = corr

        total = self._extract_float_after(text, self._RE_MP2_TOTAL, group=1)
        if total is not None:
            info["total_energy"] = total

        ri = self._extract_float_after(text, self._RE_RI_MP2, group=1)
        if ri is not None:
            info["ri_mp2_correlation"] = ri

        return info if info else {}

    # ------------------------------------------------------------------
    # GW-BSE (basic hooks – detailed parsing delegates to gwbse_parser)
    # ------------------------------------------------------------------

    def parse_qp_energies(self, text: str) -> List[float]:
        """Extract quasiparticle energies (GW).

        Detailed GW parsing is handled by :mod:`gwbse_parser`; this
        method provides a fast inline extraction.
        """
        energies: List[float] = []
        for m in self._RE_QP_ENERGY.finditer(text):
            try:
                energies.append(float(m.group(1)))
            except (ValueError, IndexError):
                continue
        return energies

    def parse_bse_states(self, text: str) -> List[Dict[str, Any]]:
        """Extract BSE excited-state information.

        Detailed parsing is delegated to :mod:`gwbse_parser`; this
        provides a fast inline extraction.

        Returns
        -------
        list[dict]
            Each dict may contain ``energy`` (eV), ``oscillator_strength``,
            and ``dominant_transitions``.
        """
        states: List[Dict[str, Any]] = []

        # Look for BSE state blocks
        block = self._extract_block(
            text,
            r"(?:BSE|Excited\s+state)\b",
            end_marker=r"\n\s*\n",
        )
        search_text = block if block else text

        for m in self._RE_BSE_STATE.finditer(search_text):
            state: Dict[str, Any] = {"dominant_transitions": []}
            try:
                state["energy"] = float(m.group(1))
            except (ValueError, IndexError):
                continue

            # Try to get oscillator strength nearby
            osc = self._RE_BSE_OSC.search(search_text, m.start())
            if osc:
                state["oscillator_strength"] = float(osc.group(1))

            # Dominant transitions
            for dt in self._RE_BSE_DOM_TRANS.finditer(
                search_text, m.start(), min(m.end() + 500, len(search_text))
            ):
                state["dominant_transitions"].append(
                    {"from": dt.group(1), "to": dt.group(2)}
                )

            states.append(state)

        return states

    # ------------------------------------------------------------------
    # Helper utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _hartree_to_ev(ha: float) -> float:
        """Convert Hartree to electronvolts."""
        return ha * HARTREE_TO_EV

    @staticmethod
    def _ev_to_nm(ev: float) -> float:
        """Convert photon energy (eV) to wavelength (nm)."""
        if ev == 0.0:
            return float("inf")
        return EV_TO_NM_FACTOR / abs(ev)

    @staticmethod
    def _extract_float_after(
        text: str,
        pattern: Union[str, re.Pattern],
        group: int = 0,
        take_last: bool = False,
    ) -> Optional[float]:
        """Extract a float after a pattern match.

        Args:
            text: The text to search.
            pattern: Regex pattern with a capturing group.
            group: The capture group that contains the float value.
            take_last: If True, return the LAST match; otherwise the FIRST.
                WARNING: For SCF energy, always use the definitive "The SCF energy"
                line instead of this method, as it may match initial-guess energies.

        Returns
        -------
        float or None
        """
        try:
            if isinstance(pattern, str):
                matches = re.findall(pattern, text)
            else:
                matches = pattern.findall(text)
        except (ValueError, TypeError, IndexError):
            return None

        if not matches:
            return None

        # matches may be a list of strings (single group) or tuples (multi-group)
        def _to_float(val):
            if isinstance(val, (tuple, list)):
                try:
                    return float(val[group - 1] if group > 0 else val[0])
                except (IndexError, ValueError, TypeError):
                    return None
            return float(val)

        idx = -1 if take_last else 0
        try:
            return _to_float(matches[idx])
        except (ValueError, IndexError, TypeError):
            return None

    @staticmethod
    def _extract_block(
        text: str,
        start_marker: str,
        end_marker: Optional[str] = None,
    ) -> Optional[str]:
        """Extract a block of text between *start_marker* and
        *end_marker*.

        If *end_marker* is ``None``, the block extends to the end of
        the next empty line.

        Returns
        -------
        str or None
        """
        try:
            start_pat = re.compile(start_marker, re.IGNORECASE)
        except re.error:
            logger.warning("Invalid start marker regex: %s", start_marker)
            return None

        m = start_pat.search(text)
        if not m:
            return None

        start_pos = m.start()
        remaining = text[start_pos:]

        if end_marker is None:
            # Capture until a blank line or end-of-text
            end_match = re.search(r"\n\s*\n", remaining)
            if end_match:
                return remaining[: end_match.start()]
            return remaining

        try:
            end_pat = re.compile(end_marker, re.IGNORECASE)
        except re.error:
            logger.warning("Invalid end marker regex: %s", end_marker)
            return remaining

        end_match = end_pat.search(remaining, 1)  # skip the start marker itself
        if end_match:
            return remaining[: end_match.start()]
        return remaining

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_wall_time(self, text: str) -> Optional[float]:
        """Extract wall-clock time in seconds."""
        m = self._RE_WALL_TIME.search(text)
        if m:
            return float(m.group(1))
        # Fallbacks
        for pat in (self._RE_TIMING, self._RE_CPU_TIME):
            m = pat.search(text)
            if m:
                return float(m.group(1))
        return None

    def _parse_mission(self, text: str) -> bool:
        """Check for the ``REST: Mission accomplished`` banner."""
        return bool(self._RE_MISSION.search(text))

    def _resolve_total_energy(
        self,
        text: str,
        scf: Dict[str, Any],
        mp2: Dict[str, Any],
    ) -> Optional[float]:
        """Pick the best total-energy estimate from available sections."""
        # Prefer MP2 total if available (double-hybrid)
        if mp2 and "total_energy" in mp2:
            return float(mp2["total_energy"])
        # Fall back to SCF energy
        if scf.get("energy") is not None:
            return float(scf["energy"])
        # Last-chance scan
        for pat in (
            r"Total\s+energy\s*[:=]?\s*(-?\d+\.\d+)",
            r"Final\s+energy\s*[:=]?\s*(-?\d+\.\d+)",
            r"Energy\s*[:=]?\s*(-?\d+\.\d+)\s*(?:Hartree|Ha)",
        ):
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return float(m.group(1))
        return None

    @staticmethod
    def _collect_warnings(result: ParsedResult) -> List[str]:
        """Build a list of diagnostics after parsing."""
        warnings: List[str] = []
        if not result.scf_converged and result.scf_cycles > 0:
            warnings.append("SCF did not converge")
        if result.optimization_steps > 0 and not result.optimization_converged:
            warnings.append("Geometry optimisation did not converge")
        if result.scf_energy is None and result.total_energy is None:
            warnings.append("No energy could be extracted")
        if not result.frequencies and result.zpe is not None:
            warnings.append("ZPE present without frequency list")
        return warnings