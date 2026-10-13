"""
AutoREST GW-BSE Specialized Parser and Module
=============================================

Production-quality Python module for REST GW-BSE input card generation,
output parsing, scientific validation, and golden regression testing.

Critical Parsing Rules (from REST_GWBSE_Skill_Guide.md):
    1. HOMO/LUMO must be parsed from "Fermi Surface" separator, NOT from energy sign.
    2. REST MO indices are 0-based.
    3. Triplet oscillator strength = 0 is NORMAL for closed-shell/no-SOC workflows.
    4. "First 0 excitations" means Davidson failure, not "no excited states".
    5. Always check BSE type matches input bse_spin.

Author: AutoREST Team
License: MIT
"""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Golden Regression Data — 6-molecule reference suite
# ---------------------------------------------------------------------------

GOLDEN_REGRESSION: Dict[str, Dict[str, Any]] = {
    "H2O": {
        "qp_gap_ev": 16.1099,
        "S1_ev": 6.9549,
        "T1_ev": 6.1395,
        "delta_est_ev": 0.8154,
        "brightest": "S3 @ 10.0710 eV",
    },
    "NH3": {
        "qp_gap_ev": 14.5961,
        "S1_ev": 7.0365,
        "T1_ev": 6.1442,
        "delta_est_ev": 0.8923,
        "brightest": "S5 @ 12.1289 eV",
    },
    "CH3COCH3": {
        "qp_gap_ev": 10.8984,
        "S1_ev": 3.3838,
        "T1_ev": 2.7121,
        "delta_est_ev": 0.6718,
        "brightest": "S2 @ 5.6305 eV",
    },
    "C6H6": {
        "qp_gap_ev": 10.6339,
        "S1_ev": 4.7204,
        "T1_ev": 3.5802,
        "delta_est_ev": 1.1402,
        "brightest": "S4 @ 7.1321 eV",
    },
    "PNA": {
        "qp_gap_ev": 9.4950,
        "S1_ev": 2.5759,
        "T1_ev": 1.9275,
        "delta_est_ev": 0.6484,
        "brightest": "S5 @ 4.6009 eV",
    },
    "coumarin": {
        "qp_gap_ev": 7.7742,
        "S1_ev": 3.3055,
        "T1_ev": 2.1554,
        "delta_est_ev": 1.1501,
        "brightest": "S4 @ 4.1483 eV",
    },
}

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class BSEState:
    """Single BSE excited state with parsed observables."""

    index: int
    energy_ha: float
    energy_ev: float
    wavelength_nm: float
    oscillator_strength: float
    transition_dipole: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    dominant_transitions: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class GWBSEResult:
    """Complete GW-BSE calculation result.

    Attributes
    ----------
    scf_energy : float
        Final SCF total energy in Hartree.
    scf_converged : bool
        Whether the SCF cycle converged.
    gw_finished : bool
        Whether the GW quasiparticle step completed.
    qp_energies : list
        Quasiparticle energy corrections (Ha).
    qp_energy_types : list
        "calculated" or "extrapolated" for each QP energy.
    homo_index_0based : int or None
        0-based HOMO orbital index (from Fermi Surface).
    lumo_index_0based : int or None
        0-based LUMO orbital index (from Fermi Surface).
    homo_qp_ha : float or None
        HOMO quasiparticle energy (Ha).
    lumo_qp_ha : float or None
        LUMO quasiparticle energy (Ha).
    qp_gap_ev : float or None
        QP HOMO-LUMO gap in eV.
    fermi_surface_found : bool
        Whether the Fermi Surface separator was located.
    qp_warnings : list
        Warning messages from the GW step.
    bse_spin : str or None
        "singlet" or "triplet".
    bse_tda : bool
        Whether Tamm-Dancoff approximation was used.
    bse_finished : bool
        Whether the BSE step completed.
    davidson_iterations : int
        Number of Davidson iterations.
    davidson_converged : bool
        Whether Davidson diagonalization converged.
    requested_roots : int
        Number of roots requested.
    obtained_roots : int
        Number of roots actually obtained.
    states : list of BSEState
        Parsed BSE excited states.
    mission_accomplished : bool
        Whether REST reported "Mission accomplished".
    total_time_s : float or None
        Total wall-clock time in seconds.
    warnings : list
        All warning messages collected during parsing.
    raw_text : str
        The complete raw output text.
    """

    # --- GW section ---
    scf_energy: Optional[float] = None
    scf_converged: bool = False
    gw_finished: bool = False
    qp_energies: List[float] = field(default_factory=list)
    qp_energy_types: List[str] = field(default_factory=list)
    homo_index_0based: Optional[int] = None
    lumo_index_0based: Optional[int] = None
    homo_qp_ha: Optional[float] = None
    lumo_qp_ha: Optional[float] = None
    qp_gap_ev: Optional[float] = None
    fermi_surface_found: bool = False
    qp_warnings: List[str] = field(default_factory=list)

    # --- BSE section ---
    bse_spin: Optional[str] = None
    bse_tda: bool = True
    bse_finished: bool = False
    davidson_iterations: int = 0
    davidson_converged: bool = False
    requested_roots: int = 0
    obtained_roots: int = 0
    states: List[BSEState] = field(default_factory=list)

    # --- Meta ---
    mission_accomplished: bool = False
    total_time_s: Optional[float] = None
    warnings: List[str] = field(default_factory=list)
    raw_text: str = ""


# ---------------------------------------------------------------------------
# GWBSEModule — card generation + parsing + validation
# ---------------------------------------------------------------------------


class GWBSEModule:
    """GW-BSE specialized module for AutoREST.

    Provides REST GW-BSE TOML input card generation (delegating template
    assembly to the project's InputGenerator where appropriate), output
    parsing with the 12 critical rules from the GW-BSE skill guide, and
    scientific validation specific to GW-BSE workflows.

    Usage
    -----
    >>> gwbse = GWBSEModule()
    >>> card = gwbse.generate_gw("H2O", geometry=h2o_xyz, geometry_unit="angstrom")
    >>> # ... run REST ...
    >>> result = gwbse.parse_gwbse_output(open("gw_bse.out").read())
    >>> print(result.qp_gap_ev)
    """

    # ------------------------------------------------------------------
    # Card Generation (TOML)
    # ------------------------------------------------------------------

    def generate_gw(
        self,
        system_name: str,
        geometry: str,
        geometry_unit: str = "angstrom",
        functional: str = "scan",
        basis: str = "cc-pVDZ",
        auxbas_path: str = "def2-SV(P)-JKFIT",
        charge: int = 0,
        spin: int = 1,
        gw_scheme: str = "extrapolated",
        scgw: str = "g0w0",
        use_low_rank_contour: bool = True,
        num_threads: int = 10,
        eri_type: str = "ri-v",
        use_ri_symm: bool = True,
        print_level: int = 1,
        **kwargs: Any,
    ) -> str:
        """Generate a REST G₀W₀ quasiparticle energy TOML input card.

        Parameters
        ----------
        system_name : str
            Name of the molecular system.
        geometry : str
            Multi-line geometry string, one ``Element x y z`` per line.
        geometry_unit : str
            Coordinate unit: ``"angstrom"`` or ``"bohr"``.
        functional : str
            DFT exchange-correlation functional (default ``"scan"``).
        basis : str
            Orbital basis set path (default ``"cc-pVDZ"``).
        auxbas_path : str
            Auxiliary (RI) basis set path (default ``"def2-SV(P)-JKFIT"``).
        charge : int
            Net molecular charge (default 0).
        spin : int
            Spin multiplicity 2S+1 (default 1, singlet).
        gw_scheme : str
            GW frequency integration scheme: ``"extrapolated"`` or ``"contour"``.
        scgw : str
            Self-consistency level: ``"g0w0"``, ``"evgw0"``, ``"evgw"``, ``"scgw0"``.
        use_low_rank_contour : bool
            Enable low-rank contour deformation for efficiency.
        num_threads : int
            Number of OpenMP threads.
        eri_type : str
            ERI evaluation method (``"ri-v"`` recommended).
        use_ri_symm : bool
            Exploit RI integral symmetry.
        print_level : int
            REST output verbosity (0 = minimal, 1 = normal, 2 = verbose).

        Returns
        -------
        str
            Valid REST TOML input card as a string.
        """
        spin_polarization = "true" if spin != 1 else "false"

        card = textwrap.dedent(
            f"""\
            [ctrl]
            num_threads = {num_threads}
            print_level = {print_level}
            job_type = "energy"
            xc = "{functional}"
            basis_path = "{basis}"
            auxbas_path = "{auxbas_path}"
            eri_type = "{eri_type}"
            use_ri_symm = {str(use_ri_symm).lower()}
            charge = {float(charge):.1f}
            spin = {spin}
            spin_polarization = {spin_polarization}

            [quasiparticle_methods]
            gw_or_bse = "gw"
            gw_scheme = "{gw_scheme}"
            scgw = "{scgw}"
            use_low_rank_contour = {str(use_low_rank_contour).lower()}

            [geom]
            name = "{system_name}"
            unit = "{geometry_unit}"
            position = \"\"\"
        """
        )

        # Append geometry with proper indentation
        for line in geometry.strip().splitlines():
            card += "    " + line.strip() + "\n"

        card += '"""\n'
        return card

    def generate_bse(
        self,
        system_name: str,
        geometry: str,
        geometry_unit: str = "angstrom",
        functional: str = "scan",
        basis: str = "cc-pVDZ",
        auxbas_path: str = "def2-SV(P)-JKFIT",
        charge: int = 0,
        spin: int = 1,
        bse_spin: str = "singlet",
        bse_tda: bool = True,
        n_roots: int = 5,
        davidson_max_subspace: int = 50,
        davidson_restart: int = 10,
        use_low_rank_contour: bool = True,
        num_threads: int = 10,
        eri_type: str = "ri-v",
        use_ri_symm: bool = True,
        print_level: int = 1,
        **kwargs: Any,
    ) -> str:
        """Generate a REST BSE excitation energy TOML input card.

        Parameters
        ----------
        system_name : str
            Name of the molecular system.
        geometry : str
            Multi-line geometry string.
        geometry_unit : str
            Coordinate unit.
        functional : str
            DFT functional.
        basis : str
            Orbital basis set.
        auxbas_path : str
            Auxiliary basis set.
        charge : int
            Net molecular charge.
        spin : int
            Spin multiplicity (keep 1 for closed-shell reference even
            with ``bse_spin="triplet"``).
        bse_spin : str
            BSE excitation spin channel: ``"singlet"`` or ``"triplet"``.
        bse_tda : bool
            Use Tamm-Dancoff approximation.
        n_roots : int
            Number of excitation roots to solve.
        davidson_max_subspace : int
            Maximum Davidson subspace dimension.
        davidson_restart : int
            Davidson restart dimension.
        use_low_rank_contour : bool
            Enable low-rank contour deformation.
        num_threads : int
            Number of OpenMP threads.
        eri_type : str
            ERI evaluation method.
        use_ri_symm : bool
            Exploit RI integral symmetry.
        print_level : int
            REST output verbosity.

        Returns
        -------
        str
            Valid REST TOML input card.
        """
        spin_polarization = "true" if spin != 1 else "false"

        card = textwrap.dedent(
            f"""\
            [ctrl]
            num_threads = {num_threads}
            print_level = {print_level}
            job_type = "energy"
            xc = "{functional}"
            basis_path = "{basis}"
            auxbas_path = "{auxbas_path}"
            eri_type = "{eri_type}"
            use_ri_symm = {str(use_ri_symm).lower()}
            charge = {float(charge):.1f}
            spin = {spin}
            spin_polarization = {spin_polarization}

            [quasiparticle_methods]
            gw_or_bse = "bse"
            gw_scheme = "extrapolated"
            use_low_rank_contour = {str(use_low_rank_contour).lower()}
            bse_spin = "{bse_spin}"
            bse_tda = {str(bse_tda).lower()}
            bse_davidson_solver = true
            davidson_target_excitations = {n_roots}
            davidson_maximum_subspace_size = {davidson_max_subspace}
            davidson_restart_dimensions = {davidson_restart}

            [geom]
            name = "{system_name}"
            unit = "{geometry_unit}"
            position = \"\"\"
        """
        )

        for line in geometry.strip().splitlines():
            card += "    " + line.strip() + "\n"

        card += '"""\n'
        return card

    def generate_bse_pair(
        self,
        system_name: str,
        geometry: str,
        geometry_unit: str = "angstrom",
        functional: str = "scan",
        basis: str = "cc-pVDZ",
        auxbas_path: str = "def2-SV(P)-JKFIT",
        charge: int = 0,
        spin: int = 1,
        bse_tda: bool = True,
        n_roots: int = 5,
        davidson_max_subspace: int = 50,
        davidson_restart: int = 10,
        use_low_rank_contour: bool = True,
        num_threads: int = 10,
        **kwargs: Any,
    ) -> Tuple[str, str]:
        """Generate both singlet and triplet BSE input cards in one call.

        Returns
        -------
        (singlet_card, triplet_card) : tuple of str
            Two REST TOML input cards.
        """
        common = dict(
            system_name=system_name,
            geometry=geometry,
            geometry_unit=geometry_unit,
            functional=functional,
            basis=basis,
            auxbas_path=auxbas_path,
            charge=charge,
            spin=spin,
            bse_tda=bse_tda,
            n_roots=n_roots,
            davidson_max_subspace=davidson_max_subspace,
            davidson_restart=davidson_restart,
            use_low_rank_contour=use_low_rank_contour,
            num_threads=num_threads,
        )
        singlet_card = self.generate_bse(bse_spin="singlet", **common)
        triplet_card = self.generate_bse(bse_spin="triplet", **common)
        return singlet_card, triplet_card

    # ------------------------------------------------------------------
    # Output Parsing
    # ------------------------------------------------------------------

    def parse_gwbse_output(self, text: str, expected_bse_spin: Optional[str] = None,
                            requested_roots: Optional[int] = None) -> GWBSEResult:
        """Parse a complete REST GW-BSE output and return a structured result.

        Parameters
        ----------
        text : str
            Full REST stdout from a GW-BSE calculation.
        expected_bse_spin : str or None
            If provided, the BSE spin type declared in the input card.
            Used to check for BSE type mismatch.
        requested_roots : int or None
            If provided, the number of BSE roots requested in the input card.
            Merged with any value parsed from the output.

        Returns
        -------
        GWBSEResult
            Parsed results with all GW and BSE fields populated.
        """
        result = GWBSEResult(raw_text=text)

        # --- Meta ---
        result.mission_accomplished = "Mission accomplished" in text
        result.total_time_s = self._parse_total_time(text)

        # --- SCF ---
        result.scf_energy = self._parse_scf_energy(text)
        result.scf_converged = self._parse_scf_cycles(text) > 0

        # --- GW ---
        result.gw_finished = bool(re.search(
            r"One\s+round\s+of\s+GW|Quasiparticle\s+Energies\s+from\s+GW", text, re.I))
        result.qp_warnings = self._collect_qp_warnings(text)

        # QP energies and Fermi Surface
        fermi_info = self._parse_qp_section(text)
        result.qp_energies = fermi_info["qp_energies"]
        result.qp_energy_types = fermi_info["qp_energy_types"]
        result.homo_index_0based = fermi_info["homo_index"]
        result.lumo_index_0based = fermi_info["lumo_index"]
        result.homo_qp_ha = fermi_info["homo_qp_ha"]
        result.lumo_qp_ha = fermi_info["lumo_qp_ha"]
        result.fermi_surface_found = fermi_info["fermi_found"]
        result.qp_gap_ev = fermi_info["qp_gap_ev"]

        # --- BSE ---
        bse_info = self._parse_bse_section(text, expected_bse_spin=expected_bse_spin)
        result.bse_spin = bse_info["bse_spin"]
        result.bse_tda = bse_info["bse_tda"]
        result.bse_finished = bse_info["bse_finished"]
        result.states = bse_info["states"]
        result.requested_roots = bse_info["requested_roots"]
        result.obtained_roots = bse_info["obtained_roots"]

        if requested_roots is not None:
            result.requested_roots = requested_roots

        # Davidson diagnostics
        dav_info = self._parse_davidson_diagnostics(text)
        result.davidson_iterations = dav_info["iterations"]
        result.davidson_converged = dav_info["converged"]

        # BSE type validation
        if expected_bse_spin and result.bse_spin:
            if result.bse_spin.lower() != expected_bse_spin.lower():
                result.warnings.append(
                    f"BSE type mismatch: input={expected_bse_spin}, output={result.bse_spin}"
                )

        # Aggregate warnings
        result.warnings.extend(result.qp_warnings)
        if not result.scf_converged:
            result.warnings.append("SCF did not converge")
        if not result.davidson_converged and result.requested_roots > 0:
            result.warnings.append(
                f"Davidson did not converge: got {result.obtained_roots}/{result.requested_roots} roots"
            )
        if result.obtained_roots == 0 and result.bse_finished:
            result.warnings.append(
                "Davidson failure: 0 roots obtained (not 'no excited states')"
            )

        return result

    # ------------------------------------------------------------------
    # QP / Fermi Surface parser
    # ------------------------------------------------------------------

    def _parse_qp_section(self, text: str) -> Dict[str, Any]:
        _RE_QP_LINE = re.compile(
            r"\((calculated|extrapolated)\)\s*QP\s+Energy\s+of\s+Orbital\s+#(\d+):\s*([+-]?\d+\.\d+)", re.I)
        _RE_FERMI = re.compile(r"-{3,}\s*Fermi\s+Surface\s*-{3,}", re.I)
        HA_TO_EV = 27.2113845
        info: Dict[str, Any] = {
            "qp_energies": [], "qp_energy_types": [], "homo_index": None,
            "lumo_index": None, "homo_qp_ha": None, "lumo_qp_ha": None,
            "fermi_found": False, "qp_gap_ev": None,
        }
        entries = []
        for lineno, line in enumerate(text.splitlines(), start=1):
            m = _RE_QP_LINE.search(line)
            if m:
                entries.append((int(m.group(2)), float(m.group(3)), m.group(1).lower(), lineno))
        if not entries:
            return info
        fermi = _RE_FERMI.search(text)
        if fermi:
            info["fermi_found"] = True
            sep_line = text[: fermi.start()].count("\n") + 1
            occupied = [e for e in entries if e[3] < sep_line]
            virtual = [e for e in entries if e[3] > sep_line]
        else:
            occupied, virtual = [], []
        for _, energy, etype, _ in sorted(entries):
            info["qp_energies"].append(energy)
            info["qp_energy_types"].append(etype)
        if occupied:
            idx, energy, _, _ = max(occupied, key=lambda e: e[0])
            info["homo_index"], info["homo_qp_ha"] = idx, energy
        if virtual:
            idx, energy, _, _ = min(virtual, key=lambda e: e[0])
            info["lumo_index"], info["lumo_qp_ha"] = idx, energy
        if info["homo_qp_ha"] is not None and info["lumo_qp_ha"] is not None:
            info["qp_gap_ev"] = (info["lumo_qp_ha"] - info["homo_qp_ha"]) * HA_TO_EV
        return info

    # ------------------------------------------------------------------
    # BSE Section parser
    # ------------------------------------------------------------------

    def _parse_bse_section(
        self, text: str, expected_bse_spin: Optional[str] = None
    ) -> Dict[str, Any]:
        _RE_BSE_STATE = re.compile(r"#(\d+)\s+Excitation\s+energy\s*=\s*([+-]?\d+(?:\.\d+)?)", re.I)
        _RE_BSE_OSC = re.compile(r"Oscillator\s+Strength\s*:\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)", re.I)
        _RE_BSE_TRANS = re.compile(r"#(\d+)->#(\d+)\s*,\s*amplitude\s*=\s*([+-]?\d+(?:\.\d+)?)", re.I)
        _RE_BSE_WINDOW = re.compile(r"(\d+)\s+excitations?\s+within\s+the\s+window", re.I)
        _RE_NROOTS = re.compile(r"nroots?\s*=\s*(\d+)", re.I)
        HA_TO_EV = 27.2113845
        info: Dict[str, Any] = {
            "bse_spin": None, "bse_tda": True, "bse_finished": False,
            "states": [], "requested_roots": 0, "obtained_roots": 0,
        }
        m = re.search(r"BSE\s+Type\s*:\s*(singlet|triplet)", text, re.I)
        if m:
            info["bse_spin"] = m.group(1).lower()
        if re.search(r"full\s*BSE|without\s*TDA", text, re.I):
            info["bse_tda"] = False
        window = _RE_BSE_WINDOW.search(text)
        if not window:
            return info
        info["bse_finished"] = True
        info["requested_roots"] = int(window.group(1))
        body = text[window.end():]
        end = re.search(r"\n\s*\n", body)
        if end:
            body = body[: end.start()]
        states = []
        for line in body.splitlines():
            m = _RE_BSE_STATE.search(line)
            if m:
                e_ha = float(m.group(2))
                states.append({
                    "index": int(m.group(1)), "energy_ha": e_ha,
                    "energy_ev": e_ha * HA_TO_EV,
                    "wavelength_nm": 1239.84 / (e_ha * HA_TO_EV) if e_ha > 0 else 0.0,
                    "oscillator_strength": 0.0, "transition_dipole": [0.0, 0.0, 0.0],
                    "dominant_transitions": [],
                })
                continue
            m = _RE_BSE_OSC.search(line)
            if m and states:
                states[-1]["oscillator_strength"] = float(m.group(1))
                continue
            m = _RE_BSE_TRANS.search(line)
            if m and states:
                states[-1]["dominant_transitions"].append({
                    "from_orbital": int(m.group(1)), "to_orbital": int(m.group(2)),
                    "amplitude": float(m.group(3)),
                })
        info["states"] = [
            BSEState(**{**s, "dominant_transitions": sorted(
                s["dominant_transitions"], key=lambda d: abs(d["amplitude"]), reverse=True)[:5]})
            for s in states
        ]
        info["obtained_roots"] = len(info["states"])
        m = _RE_NROOTS.search(text)
        if m:
            info["requested_roots"] = max(info["requested_roots"], int(m.group(1)))
        return info

    @staticmethod
    def _build_bse_state(raw: Dict[str, Any]) -> BSEState:
        """Construct a BSEState from a raw dictionary collected during parsing."""
        return BSEState(
            index=raw["index"],
            energy_ha=raw["energy_ha"],
            energy_ev=raw["energy_ev"],
            wavelength_nm=raw["wavelength_nm"],
            oscillator_strength=raw["oscillator_strength"],
            transition_dipole=raw.get("transition_dipole", [0.0, 0.0, 0.0]),
            dominant_transitions=raw.get("dominant_transitions", []),
        )

    # ------------------------------------------------------------------
    # Davidson Diagnostics parser
    # ------------------------------------------------------------------

    def _parse_davidson_diagnostics(self, text: str) -> Dict[str, Any]:
        _RE_DAV_ITER = re.compile(r"^\s*iter\s+(\d+):\s*space=(\d+),\s*converged=(\d+)/(\d+)", re.I | re.M)
        info = {"iterations": 0, "converged": False, "restart_count": 0, "residuals": []}
        iters = _RE_DAV_ITER.findall(text)
        if iters:
            info["iterations"] = max(int(i[0]) for i in iters)
            spaces = [int(i[1]) for i in iters]
            info["restart_count"] = sum(1 for a, b in zip(spaces, spaces[1:]) if b < a)
            last = iters[-1]
            info["converged"] = int(last[2]) == int(last[3])
        if re.search(r"Davidson\s+Solver\s+has\s+converged", text, re.I):
            info["converged"] = True
        return info

    # ------------------------------------------------------------------
    # Helper Parsers (SCF, timing, warnings)
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_scf_energy(text: str) -> Optional[float]:
        _RE_SCF_FINAL = re.compile(r"The\s+SCF\s+energy\s*:\s*([+-]?\d+\.\d+)\s*Ha", re.I)
        _RE_SCF_LAST = re.compile(r"Energy:\s+([+-]?\d+\.\d+)\s+Ha", re.I)
        m = _RE_SCF_FINAL.search(text)
        if m:
            return float(m.group(1))
        hits = _RE_SCF_LAST.findall(text)
        return float(hits[-1]) if hits else None

    @staticmethod
    def _parse_scf_cycles(text: str) -> int:
        _RE_SCF_CYCLES = re.compile(r"SCF\s+is\s+converged\s+after\s+(\d+)\s+iterations", re.I)
        hits = _RE_SCF_CYCLES.findall(text)
        return int(hits[-1]) if hits else 0

    @staticmethod
    def _parse_total_time(text: str) -> Optional[float]:
        _RE_TIME = re.compile(r"Overall\s*\|:\s*([\d.]+)\s*s\s+for\s+the\s+whole\s+job", re.I)
        m = _RE_TIME.search(text)
        return float(m.group(1)) if m else None

    @staticmethod
    def _collect_qp_warnings(text: str) -> List[str]:
        """Collect quasiparticle-related warnings."""
        warnings: List[str] = []
        for pattern in [
            r"(Newton.*?(?:warning|failed|diverged).*?orbital\s+\d+)",
            r"(QP.*?(?:warning|caution).*?(?:orbital|energy))",
            r"(extrapolat\w*\s+(?:warning|error|failed))",
            r"(Linear\s+equation\s+solver.*?(?:warning|failed))",
        ]:
            for m in re.finditer(pattern, text, re.IGNORECASE):
                warnings.append(m.group(1).strip())
        return warnings

    # ------------------------------------------------------------------
    # Scientific Helper Methods
    # ------------------------------------------------------------------

    @staticmethod
    def find_brightest_state(states: List[BSEState]) -> Optional[BSEState]:
        """Return the BSE state with the maximum oscillator strength.

        For triplet states where all oscillator strengths may be zero,
        returns the state with the largest (possibly zero) oscillator
        strength, which is typically the first state.

        Parameters
        ----------
        states : list of BSEState
            Parsed BSE excited states.

        Returns
        -------
        BSEState or None
            The brightest state, or None if the list is empty.
        """
        if not states:
            return None
        return max(states, key=lambda s: s.oscillator_strength)

    @staticmethod
    def compute_delta_est(
        singlet_result: GWBSEResult, triplet_result: GWBSEResult
    ) -> Optional[float]:
        """Compute ΔE_ST = S₁ - T₁ in eV.

        Uses the first (lowest-energy) state from each spin channel.
        This is the singlet-triplet gap: a key quantity for evaluating
        thermally activated delayed fluorescence (TADF) candidates and
        benchmarking exchange-correlation functionals.

        Parameters
        ----------
        singlet_result : GWBSEResult
            Parsed singlet BSE result.
        triplet_result : GWBSEResult
            Parsed triplet BSE result.

        Returns
        -------
        float or None
            ΔE_ST in eV, or None if either result lacks states.
        """
        if not singlet_result.states or not triplet_result.states:
            return None
        # S1 = lowest singlet, T1 = lowest triplet
        s1_ev = min(s.energy_ev for s in singlet_result.states)
        t1_ev = min(s.energy_ev for s in triplet_result.states)
        return s1_ev - t1_ev

    @staticmethod
    def generate_summary(result: GWBSEResult, molecule_name: str = "") -> str:
        """Produce a human-readable summary of a GW-BSE result.

        Parameters
        ----------
        result : GWBSEResult
            Parsed GW-BSE result.
        molecule_name : str
            Optional molecule label for the header.

        Returns
        -------
        str
            Multi-line summary string.
        """
        lines = []
        header = f"GW-BSE Summary"
        if molecule_name:
            header += f" — {molecule_name}"
        lines.append("=" * len(header))
        lines.append(header)
        lines.append("=" * len(header))
        lines.append("")

        # SCF
        lines.append(f"  SCF Energy:       {result.scf_energy:.8f} Ha" if result.scf_energy else "  SCF Energy:       N/A")
        lines.append(f"  SCF Converged:    {result.scf_converged}")

        # GW
        lines.append(f"  GW Finished:      {result.gw_finished}")
        lines.append(f"  Fermi Surface:    {'Found' if result.fermi_surface_found else 'NOT FOUND'}")
        if result.homo_index_0based is not None:
            lines.append(f"  HOMO (0-based):   {result.homo_index_0based}")
        if result.lumo_index_0based is not None:
            lines.append(f"  LUMO (0-based):   {result.lumo_index_0based}")
        if result.homo_qp_ha is not None:
            lines.append(f"  HOMO QP:          {result.homo_qp_ha:.6f} Ha")
        if result.lumo_qp_ha is not None:
            lines.append(f"  LUMO QP:          {result.lumo_qp_ha:.6f} Ha")
        if result.qp_gap_ev is not None:
            lines.append(f"  QP Gap:           {result.qp_gap_ev:.4f} eV")

        # BSE
        lines.append("")
        lines.append(f"  BSE Spin:         {result.bse_spin or 'N/A'}")
        lines.append(f"  BSE TDA:          {result.bse_tda}")
        lines.append(f"  BSE Finished:     {result.bse_finished}")
        lines.append(f"  Davidson Iters:   {result.davidson_iterations}")
        lines.append(f"  Davidson Conv:    {result.davidson_converged}")
        lines.append(f"  Roots:            {result.obtained_roots}/{result.requested_roots}")

        # States
        if result.states:
            lines.append("")
            lines.append(f"  Excited States ({len(result.states)}):")
            lines.append(f"  {'State':<7} {'E(eV)':<10} {'λ(nm)':<10} {'f_osc':<10}")
            lines.append(f"  {'-'*6}  {'-'*9}  {'-'*9}  {'-'*9}")
            for s in result.states:
                lines.append(
                    f"  S{s.index:<6} {s.energy_ev:<10.4f} {s.wavelength_nm:<10.1f} {s.oscillator_strength:<10.6f}"
                )
            brightest = GWBSEModule.find_brightest_state(result.states)
            if brightest:
                lines.append(f"\n  Brightest: S{brightest.index} @ {brightest.energy_ev:.4f} eV (f = {brightest.oscillator_strength:.6f})")

        # Warnings
        if result.warnings:
            lines.append("")
            lines.append(f"  Warnings ({len(result.warnings)}):")
            for w in result.warnings:
                lines.append(f"    ⚠ {w}")

        # Timing
        if result.total_time_s is not None:
            lines.append(f"\n  Total Time:       {result.total_time_s:.1f} s")

        lines.append(f"\n  Mission:          {'✅ Accomplished' if result.mission_accomplished else '❌ Not accomplished'}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Scientific Validation (GW-BSE specific)
    # ------------------------------------------------------------------

    def validate_gwbse(
        self,
        result: GWBSEResult,
        expected_bse_spin: Optional[str] = None,
        check_regression: Optional[str] = None,
        regression_tolerance_ev: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """Run GW-BSE specific scientific validation checks.

        Parameters
        ----------
        result : GWBSEResult
            Parsed GW-BSE result.
        expected_bse_spin : str or None
            Expected BSE spin type for type-mismatch check.
        check_regression : str or None
            Molecule key in ``GOLDEN_REGRESSION`` for comparison.
        regression_tolerance_ev : float
            Maximum allowed deviation from golden values (eV).

        Returns
        -------
        list of dict
            Each check: {"name": str, "passed": bool, "severity": str, "detail": str}
        """
        checks: List[Dict[str, Any]] = []

        # 1. SCF convergence
        checks.append({
            "name": "SCF Convergence",
            "passed": result.scf_converged,
            "severity": "ERROR" if not result.scf_converged else "PASS",
            "detail": "SCF converged" if result.scf_converged else "SCF did NOT converge — result invalid",
        })

        # 2. Mission accomplished
        checks.append({
            "name": "Mission Accomplished",
            "passed": result.mission_accomplished,
            "severity": "WARNING" if not result.mission_accomplished else "PASS",
            "detail": "REST completed normally" if result.mission_accomplished else "REST may have terminated abnormally",
        })

        # 3. Fermi Surface found
        checks.append({
            "name": "Fermi Surface",
            "passed": result.fermi_surface_found,
            "severity": "ERROR" if not result.fermi_surface_found else "PASS",
            "detail": (
                "Fermi Surface separator found — HOMO/LUMO correctly identified"
                if result.fermi_surface_found
                else "Fermi Surface NOT found — HOMO/LUMO assignment may be wrong"
            ),
        })

        # 4. QP gap positive
        qp_gap_ok = result.qp_gap_ev is not None and result.qp_gap_ev > 0
        checks.append({
            "name": "QP Gap > 0",
            "passed": qp_gap_ok,
            "severity": "ERROR" if not qp_gap_ok else "PASS",
            "detail": (
                f"QP gap = {result.qp_gap_ev:.4f} eV"
                if qp_gap_ok
                else "QP gap is negative or missing — invalid"
            ),
        })

        # 5. BSE type match
        if expected_bse_spin and result.bse_spin:
            spin_match = result.bse_spin.lower() == expected_bse_spin.lower()
            checks.append({
                "name": "BSE Type Match",
                "passed": spin_match,
                "severity": "ERROR" if not spin_match else "PASS",
                "detail": (
                    f"BSE type matches input ({result.bse_spin})"
                    if spin_match
                    else f"BSE type MISMATCH: input={expected_bse_spin}, output={result.bse_spin}"
                ),
            })

        # 6. Davidson convergence
        dav_ok = result.davidson_converged or result.obtained_roots == result.requested_roots
        checks.append({
            "name": "Davidson Convergence",
            "passed": dav_ok,
            "severity": "WARNING" if not dav_ok else "PASS",
            "detail": (
                f"Davidson converged: {result.obtained_roots}/{result.requested_roots} roots, {result.davidson_iterations} iterations"
                if dav_ok
                else f"Davidson FAILED: only {result.obtained_roots}/{result.requested_roots} roots"
            ),
        })

        # 7. Triplet osc strength zero check (informational for triplets)
        if result.bse_spin == "triplet":
            all_zero = all(s.oscillator_strength == 0.0 for s in result.states)
            checks.append({
                "name": "Triplet Oscillator Strength",
                "passed": True,  # always passes — 0 is normal
                "severity": "INFO",
                "detail": (
                    "All oscillator strengths = 0 — NORMAL for closed-shell no-SOC triplet BSE"
                    if all_zero
                    else "Non-zero triplet oscillator strengths detected (SOC present?)"
                ),
            })

        # 8. Davidson failure check (0 roots)
        if result.obtained_roots == 0 and result.bse_finished:
            checks.append({
                "name": "Davidson Zero Roots",
                "passed": False,
                "severity": "ERROR",
                "detail": "'First 0 excitations' means Davidson convergence FAILURE, not 'no excited states'. Try increasing roots/subspace.",
            })

        # 9. QP warnings
        if result.qp_warnings:
            checks.append({
                "name": "QP Warnings",
                "passed": False,
                "severity": "WARNING",
                "detail": f"{len(result.qp_warnings)} QP warning(s): {'; '.join(result.qp_warnings[:3])}",
            })

        # 10. Golden regression check
        if check_regression and check_regression in GOLDEN_REGRESSION:
            golden = GOLDEN_REGRESSION[check_regression]
            deviations = []
            if result.qp_gap_ev is not None:
                d_qp = abs(result.qp_gap_ev - golden["qp_gap_ev"])
                deviations.append(f"QP gap Δ = {d_qp:.4f} eV")
            qp_ok = (result.qp_gap_ev is None) or (abs(result.qp_gap_ev - golden["qp_gap_ev"]) <= regression_tolerance_ev)
            ex_ok = True
            if result.states:
                target = golden["T1_ev"] if result.bse_spin == "triplet" else golden["S1_ev"]
                d_ex = abs(min(s.energy_ev for s in result.states) - target)
                deviations.append(f"{'T1' if result.bse_spin == 'triplet' else 'S1'} Δ = {d_ex:.4f} eV")
                ex_ok = d_ex <= regression_tolerance_ev
            all_ok = qp_ok and ex_ok
            checks.append({
                "name": f"Regression ({check_regression})",
                "passed": all_ok,
                "severity": "WARNING" if not all_ok else "PASS",
                "detail": (
                    f"Matches golden values within {regression_tolerance_ev} eV"
                    if all_ok
                    else f"Deviation from golden: {'; '.join(deviations)} (tol={regression_tolerance_ev} eV)"
                ),
            })

        return checks

    # ------------------------------------------------------------------
    # Output file parser (convenience wrapper)
    # ------------------------------------------------------------------

    def parse_output(self, path: str, expected_bse_spin: Optional[str] = None) -> GWBSEResult:
        raw = Path(path).read_bytes()
        if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
            text = raw.decode("utf-16")
        else:
            for enc in ("utf-8-sig", "utf-8"):
                try:
                    text = raw.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                text = raw.decode("cp936", errors="replace")
        return self.parse_gwbse_output(text, expected_bse_spin=expected_bse_spin)


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

def parse_gwbse_file(path: str, expected_bse_spin: Optional[str] = None) -> GWBSEResult:
    """Convenience function: parse a GW-BSE output file from disk.

    Equivalent to ``GWBSEModule().parse_output(path, expected_bse_spin)``.
    """
    return GWBSEModule().parse_output(path, expected_bse_spin=expected_bse_spin)


def generate_gw_card(
    system_name: str,
    geometry: str,
    geometry_unit: str = "angstrom",
    **kwargs: Any,
) -> str:
    """Convenience function: generate a GW TOML card."""
    return GWBSEModule().generate_gw(system_name, geometry, geometry_unit, **kwargs)


def generate_bse_card(
    system_name: str,
    geometry: str,
    geometry_unit: str = "angstrom",
    **kwargs: Any,
) -> str:
    """Convenience function: generate a BSE TOML card."""
    return GWBSEModule().generate_bse(system_name, geometry, geometry_unit, **kwargs)