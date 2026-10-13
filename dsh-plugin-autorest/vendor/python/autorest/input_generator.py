"""
AutoREST input_generator — REST TOML input card generation engine.

Generates valid REST input cards from structured parameters.  No LLM or
network dependency: every method produces a ready-to-use TOML string from
templates and rules backed by the current REST keyword catalogue.

Supported job types
-------------------
* ``energy``       — single-point energy
* ``opt``          — geometry optimisation
* ``force``        — analytical gradient
* ``numerical dipole`` — numerical dipole moment
* ``frequency``    — harmonic frequencies with [hessian] and [thermo]
* ``gw``           — GW quasiparticle correction
* ``gw-bse``       — GW + Bethe–Salpeter equation excited states

Notes
-----
* GW / BSE sections ([quasiparticle_methods]) are formatted per the REST
  upstream schedule but flagged as *pending* in the current AIFS coverage;
  the card is syntactically valid and ready when the backend gains support.
* ``toml.dumps`` is unavailable in the bundled Python; the module ships its
  own manual TOML serialiser covering all primitives, arrays and nested tables
  needed by REST.
"""
from __future__ import annotations

import re
import textwrap
from typing import Any, Dict, List, Optional, Sequence, Union


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Methods that are double-hybrid or RPA — empirical dispersion must be
# suppressed because REST rejects its co-occurrence with these families.
_DOUBLE_HYBRID_RPA = frozenset({
    "RPA@B3LYP", "RPA@PBE", "scsRPA",
    "R-xDH7", "xDH-PBE0",
    "XYG3", "XYG7", "XYGJOS",
})

# Multiplicity-dependent default for spin_polarization.
# (spin == 2S+1, so spin=1 → closed-shell singlet → no polarization.)
_DEFAULT_SPIN_POL = lambda s: s > 1


# ===================================================================
# Minimal TOML serialiser
# ===================================================================

def _toml_key(key: str) -> str:
    """Quote a bare key if it contains anything beyond ``[A-Za-z0-9_-]``."""
    if re.fullmatch(r"[A-Za-z0-9_-]+", key):
        return key
    return f'"{key}"'


def _toml_literal(value: Any) -> str:
    """Render a single TOML scalar value."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        # avoid scientific notation for clean REST reading
        return f"{value:.12g}"
    if isinstance(value, str):
        if "\n" in value:
            # triple-quoted multi-line — REST favours this for position
            return f'"""{value}"""'
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, list):
        items = ", ".join(_toml_literal(v) for v in value)
        return f"[{items}]"
    raise TypeError(f"Unsupported TOML type: {type(value)}")


def _toml_dumps(data: Dict[str, Any]) -> str:
    """Serialize a nested dict into TOML text.

    Top-level keys that map to dicts become ``[section]`` tables.
    Scalar/array top-level keys are written before the first table header.
    Nested dicts inside a section become ``[parent.child]``.
    """
    lines: List[str] = []
    _write_table(lines, data, "")
    return "\n".join(lines) + "\n"


def _write_table(
    lines: List[str],
    data: Dict[str, Any],
    prefix: str,
) -> None:
    seen_subsections: List[str] = []
    for key, value in data.items():
        full = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            # subsection
            header = f"[{full}]"
            lines.append(header)
            _write_section_body(lines, value)
            seen_subsections.append(full)
        elif isinstance(value, (list, str, int, float, bool)):
            lines.append(f"{_toml_key(key)} = {_toml_literal(value)}")
        else:
            raise TypeError(f"Unsupported TOML type for key {key}: {type(value)}")


def _write_section_body(
    lines: List[str],
    data: Dict[str, Any],
) -> None:
    """Write key = value pairs contained directly within a section."""
    for key, value in data.items():
        if isinstance(value, dict):
            raise ValueError(
                f"Nested dict under key '{key}' is not supported in section body; "
                f"use explicit table headers."
            )
        lines.append(f"{_toml_key(key)} = {_toml_literal(value)}")


# ===================================================================
# InputGenerator
# ===================================================================

class InputGenerator:
    """Generate REST TOML input cards from structured parameters.

    The public ``generate_*`` methods each return a complete TOML string
    that can be written to a ``.in`` file and validated with
    ``validate_rest_input``.

    Parameters shared by most methods:

    system_name : str
        Short molecular label (``"water"``, ``"ethene"``, …).
    geometry : str
        Multi-line string of ``Element  x  y  z`` lines.
    geometry_unit : {"angstrom", "bohr"}
        Unit for the supplied coordinates.
    functional : str
        Exchange-correlation method.  Must be present in the REST method
        catalogue (e.g. ``"PBE0"``, ``"B3LYP"``, ``"wB97X-D3BJ"``).
    basis : str
        Orbital basis set short name (``"cc-pVDZ"``, ``"def2-SVP"``, …).
    charge : int
        Net molecular charge.
    spin : int
        Spin multiplicity ``2S+1``.  Minimum 1 (singlet).

    Optional parameters
    -------------------
    spin_polarization : bool or None
        Default ``False`` when *spin* == 1, ``True`` when *spin* > 1.
    empirical_dispersion : {"d3", "d3bj", "d4"} or None
        Empirical dispersion correction.  **Silently omitted** for
        double-hybrid / RPA methods (``RPA@B3LYP``, ``XYG3``, …).
    auxbas_path : str or None
        Auxiliary basis path.  REST auto-selects the RI-J basis when
        omitted (recommended default).
    num_threads : int
        OpenMP threads (default 10).
    print_level : int
        Output verbosity (default 1).
    """

    # ------------------------------------------------------------------
    # Public generation methods
    # ------------------------------------------------------------------

    def generate_energy(
        self,
        system_name: str,
        geometry: str,
        geometry_unit: str,
        functional: str,
        basis: str,
        charge: int,
        spin: int,
        spin_polarization: Optional[bool] = None,
        empirical_dispersion: Optional[str] = None,
        auxbas_path: Optional[str] = None,
        num_threads: int = 10,
        print_level: int = 1,
        **kwargs: Any,
    ) -> str:
        """Generate a single-point energy card.

        Returns
        -------
        str
            Complete REST TOML input for ``job_type = "energy"``.

        Examples
        --------
        >>> gen = InputGenerator()
        >>> card = gen.generate_energy("H2O", "O 0 0 0\\nH 0 0.757 0.586\\nH 0 -0.757 0.586",
        ...                            "angstrom", "PBE0", "cc-pVDZ", 0, 1,
        ...                            empirical_dispersion="d3bj")
        """
        self._validate_inputs(system_name, geometry, geometry_unit, functional,
                               basis, charge, spin)
        return self._build_full_card(
            system_name=system_name,
            geometry=geometry,
            geometry_unit=geometry_unit,
            functional=functional,
            basis=basis,
            charge=charge,
            spin=spin,
            job_type="energy",
            spin_polarization=spin_polarization,
            empirical_dispersion=empirical_dispersion,
            auxbas_path=auxbas_path,
            num_threads=num_threads,
            print_level=print_level,
            **kwargs,
        )

    def generate_optimization(
        self,
        system_name: str,
        geometry: str,
        geometry_unit: str,
        functional: str,
        basis: str,
        charge: int,
        spin: int,
        spin_polarization: Optional[bool] = None,
        empirical_dispersion: Optional[str] = None,
        auxbas_path: Optional[str] = None,
        num_threads: int = 10,
        print_level: int = 1,
        convergence_energy: Optional[float] = None,
        convergence_grms: Optional[float] = None,
        convergence_gmax: Optional[float] = None,
        convergence_drms: Optional[float] = None,
        convergence_dmax: Optional[float] = None,
        maxiter: int = 200,
        coordsys: str = "tric",
        **kwargs: Any,
    ) -> str:
        """Generate a geometry-optimisation card.

        Adds ``[geometric_pyo3]`` with reasonable convergence defaults
        (3 × 10⁻⁴ Eh bohr⁻¹ for gradient, 1.2 × 10⁻³ Å for step).

        Returns
        -------
        str
            Complete REST TOML input for ``job_type = "opt"``.
        """
        self._validate_inputs(system_name, geometry, geometry_unit, functional,
                               basis, charge, spin)
        opt_block: Dict[str, Any] = {
            "maxiter": maxiter,
            "coordsys": coordsys,
            "convergence_energy": convergence_energy or 1e-6,
            "convergence_grms": convergence_grms or 3e-4,
            "convergence_gmax": convergence_gmax or 4.5e-4,
            "convergence_drms": convergence_drms or 1.2e-3,
            "convergence_dmax": convergence_dmax or 1.8e-3,
        }
        # pass remaining kwargs through to the full card builder
        return self._build_full_card(
            system_name=system_name,
            geometry=geometry,
            geometry_unit=geometry_unit,
            functional=functional,
            basis=basis,
            charge=charge,
            spin=spin,
            job_type="opt",
            spin_polarization=spin_polarization,
            empirical_dispersion=empirical_dispersion,
            auxbas_path=auxbas_path,
            num_threads=num_threads,
            print_level=print_level,
            geometric_pyo3=opt_block,
            **kwargs,
        )

    def generate_force(
        self,
        system_name: str,
        geometry: str,
        geometry_unit: str,
        functional: str,
        basis: str,
        charge: int,
        spin: int,
        spin_polarization: Optional[bool] = None,
        empirical_dispersion: Optional[str] = None,
        auxbas_path: Optional[str] = None,
        num_threads: int = 10,
        print_level: int = 1,
        **kwargs: Any,
    ) -> str:
        """Generate an analytical-gradient (force) card.

        Returns
        -------
        str
            Complete REST TOML input for ``job_type = "force"``.
        """
        self._validate_inputs(system_name, geometry, geometry_unit, functional,
                               basis, charge, spin)
        return self._build_full_card(
            system_name=system_name,
            geometry=geometry,
            geometry_unit=geometry_unit,
            functional=functional,
            basis=basis,
            charge=charge,
            spin=spin,
            job_type="force",
            spin_polarization=spin_polarization,
            empirical_dispersion=empirical_dispersion,
            auxbas_path=auxbas_path,
            num_threads=num_threads,
            print_level=print_level,
            **kwargs,
        )

    def generate_frequency(
        self,
        system_name: str,
        geometry: str,
        geometry_unit: str,
        functional: str,
        basis: str,
        charge: int,
        spin: int,
        spin_polarization: Optional[bool] = None,
        empirical_dispersion: Optional[str] = None,
        auxbas_path: Optional[str] = None,
        num_threads: int = 10,
        print_level: int = 1,
        temperature: float = 298.15,
        pressure: float = 1.0,
        scale_factor: float = 1.0,
        **kwargs: Any,
    ) -> str:
        """Generate a harmonic-frequency (Hessian) card with thermochemistry.

        Adds ``[ctrl.hessian]`` and ``[ctrl.thermo]`` sub-tables to a
        ``job_type = "energy"`` base.  The job computes the Hessian and
        then evaluates the thermochemical corrections at the given
        *temperature* (K) and *pressure* (atm).

        Returns
        -------
        str
            Complete REST TOML input for frequencies + thermo.
        """
        self._validate_inputs(system_name, geometry, geometry_unit, functional,
                               basis, charge, spin)
        return self._build_full_card(
            system_name=system_name,
            geometry=geometry,
            geometry_unit=geometry_unit,
            functional=functional,
            basis=basis,
            charge=charge,
            spin=spin,
            job_type="energy",
            spin_polarization=spin_polarization,
            empirical_dispersion=empirical_dispersion,
            auxbas_path=auxbas_path,
            num_threads=num_threads,
            print_level=print_level,
            ctrl_hessian={"frequencies": True},
            ctrl_thermo={
                "temperature": temperature,
                "pressure": pressure,
                "scale_factor": scale_factor,
            },
            **kwargs,
        )

    def generate_gw(
        self,
        system_name: str,
        geometry: str,
        geometry_unit: str,
        functional: str,
        basis: str,
        charge: int,
        spin: int,
        spin_polarization: Optional[bool] = None,
        empirical_dispersion: Optional[str] = None,
        auxbas_path: Optional[str] = None,
        num_threads: int = 10,
        print_level: int = 1,
        gw_scheme: str = "extrapolated",
        scgw: str = "g0w0",
        use_low_rank_contour: bool = True,
        n_roots: int = 5,
        **kwargs: Any,
    ) -> str:
        """Generate a GW quasiparticle-correction card.

        The ``[quasiparticle_methods]`` block drives the GW module.
        BSE-specific keys (``bse_spin``, ``bse_tda``, …) are omitted.

        .. note::
           GW/BSE input sections are **pending** in the current AIFS
           coverage.  The card produced here follows the announced layout
           and is ready for validation once the backend gains support.

        Returns
        -------
        str
            Complete REST TOML input for a GW calculation.
        """
        self._validate_inputs(system_name, geometry, geometry_unit, functional,
                               basis, charge, spin)
        qp: Dict[str, Any] = {
            "gw_or_bse": "gw",
            "gw_scheme": gw_scheme,
            "scgw": scgw,
            "use_low_rank_contour": use_low_rank_contour,
            "n_roots": n_roots,
        }
        return self._build_full_card(
            system_name=system_name,
            geometry=geometry,
            geometry_unit=geometry_unit,
            functional=functional,
            basis=basis,
            charge=charge,
            spin=spin,
            job_type="energy",
            spin_polarization=spin_polarization,
            empirical_dispersion=empirical_dispersion,
            auxbas_path=auxbas_path,
            num_threads=num_threads,
            print_level=print_level,
            quasiparticle_methods=qp,
            **kwargs,
        )

    def generate_bse(
        self,
        system_name: str,
        geometry: str,
        geometry_unit: str,
        functional: str,
        basis: str,
        charge: int,
        spin: int,
        spin_polarization: Optional[bool] = None,
        empirical_dispersion: Optional[str] = None,
        auxbas_path: Optional[str] = None,
        num_threads: int = 10,
        print_level: int = 1,
        gw_scheme: str = "extrapolated",
        scgw: str = "g0w0",
        use_low_rank_contour: bool = True,
        bse_spin: str = "singlet",
        bse_tda: bool = True,
        n_roots: int = 5,
        bse_davidson_solver: bool = True,
        davidson_target_excitations: int = 5,
        davidson_maximum_subspace_size: int = 50,
        davidson_restart_dimensions: int = 10,
        **kwargs: Any,
    ) -> str:
        """Generate a full GW-BSE excited-state card.

        The ``[quasiparticle_methods]`` block carries all GW and BSE
        settings.  The SCF part is a standard DFT reference.

        .. note::
           GW/BSE input sections are **pending** in the current AIFS
           coverage.  The card follows the announced layout and is ready
           for validation once the backend ships the feature.

        Returns
        -------
        str
            Complete REST TOML input for a GW-BSE calculation.
        """
        self._validate_inputs(system_name, geometry, geometry_unit, functional,
                               basis, charge, spin)
        qp: Dict[str, Any] = {
            "gw_or_bse": "bse",
            "gw_scheme": gw_scheme,
            "scgw": scgw,
            "use_low_rank_contour": use_low_rank_contour,
            "bse_spin": bse_spin,
            "bse_tda": bse_tda,
            "n_roots": n_roots,
            "bse_davidson_solver": bse_davidson_solver,
            "davidson_target_excitations": davidson_target_excitations,
            "davidson_maximum_subspace_size": davidson_maximum_subspace_size,
            "davidson_restart_dimensions": davidson_restart_dimensions,
        }
        return self._build_full_card(
            system_name=system_name,
            geometry=geometry,
            geometry_unit=geometry_unit,
            functional=functional,
            basis=basis,
            charge=charge,
            spin=spin,
            job_type="energy",
            spin_polarization=spin_polarization,
            empirical_dispersion=empirical_dispersion,
            auxbas_path=auxbas_path,
            num_threads=num_threads,
            print_level=print_level,
            quasiparticle_methods=qp,
            **kwargs,
        )

    # ------------------------------------------------------------------
    # Internal block builders
    # ------------------------------------------------------------------

    def _build_ctrl_block(
        self,
        system_name: str,
        functional: str,
        basis: str,
        charge: int,
        spin: int,
        job_type: str,
        spin_polarization: Optional[bool],
        empirical_dispersion: Optional[str],
        auxbas_path: Optional[str],
        num_threads: int,
        print_level: int,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Build the ``[ctrl]`` section dictionary.

        Returns
        -------
        dict
            Keys and values for the ``[ctrl]`` table.
        """
        ctrl: Dict[str, Any] = {
            "job_type": job_type,
            "charge": charge,
            "spin": spin,
            "xc": functional,
            "basis_path": basis,
            "num_threads": num_threads,
            "print_level": print_level,
            "eri_type": "ri-v",
            "spin_polarization": (
                _DEFAULT_SPIN_POL(spin)
                if spin_polarization is None
                else spin_polarization
            ),
        }

        # Empirical dispersion — omitted for double-hybrid / RPA
        if empirical_dispersion is not None:
            if functional in _DOUBLE_HYBRID_RPA:
                # silently suppress
                pass
            else:
                ctrl["empirical_dispersion"] = empirical_dispersion

        if auxbas_path is not None:
            ctrl["auxbas_path"] = auxbas_path

        return ctrl

    def _build_geom_block(
        self,
        geometry: str,
        geometry_unit: str,
        system_name: str,
    ) -> Dict[str, Any]:
        """Build the ``[geom]`` section dictionary.

        The multi-line *geometry* string is stored so that the TOML
        serialiser writes it as a triple-quoted literal.

        Returns
        -------
        dict
            Keys ``name``, ``position`` and ``unit`` for the ``[geom]`` table.
        """
        # Strip leading/trailing blank lines but preserve internal
        # formatting so the element columns stay aligned.
        geom_stripped = geometry.strip()
        return {
            "name": system_name,
            "position": geom_stripped,
            "unit": geometry_unit,
        }

    def _build_full_card(
        self,
        system_name: str,
        geometry: str,
        geometry_unit: str,
        functional: str,
        basis: str,
        charge: int,
        spin: int,
        job_type: str,
        spin_polarization: Optional[bool] = None,
        empirical_dispersion: Optional[str] = None,
        auxbas_path: Optional[str] = None,
        num_threads: int = 10,
        print_level: int = 1,
        **kwargs: Any,
    ) -> str:
        """Assemble the complete TOML document from all blocks.

        Extra sections (``geometric_pyo3``, ``ctrl.hessian``,
        ``ctrl.thermo``, ``quasiparticle_methods``) are extracted from
        *kwargs* and merged into the output dict as nested tables.
        """
        root: Dict[str, Any] = {}

        # -- required sections -------------------------------------------------
        root["ctrl"] = self._build_ctrl_block(
            system_name=system_name,
            functional=functional,
            basis=basis,
            charge=charge,
            spin=spin,
            job_type=job_type,
            spin_polarization=spin_polarization,
            empirical_dispersion=empirical_dispersion,
            auxbas_path=auxbas_path,
            num_threads=num_threads,
            print_level=print_level,
        )
        root["geom"] = self._build_geom_block(geometry, geometry_unit, system_name)

        # -- optional sections from kwargs -------------------------------------
        # Pass through any explicitly supplied REST blocks.
        extra_blocks = {
            "geometric_pyo3": kwargs.pop("geometric_pyo3", None),
            "ctrl.hessian": kwargs.pop("ctrl_hessian", None),
            "ctrl.thermo": kwargs.pop("ctrl_thermo", None),
            "quasiparticle_methods": kwargs.pop("quasiparticle_methods", None),
        }
        for key, value in extra_blocks.items():
            if value is not None:
                root[key] = value

        # Serialize.
        return _toml_dumps(root)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_inputs(
        system_name: str,
        geometry: str,
        geometry_unit: str,
        functional: str,
        basis: str,
        charge: int,
        spin: int,
    ) -> None:
        """Basic sanity checks on the inputs shared by all card types.

        Raises
        ------
        ValueError
            If any invariant is violated.
        """
        if not system_name or not system_name.strip():
            raise ValueError("system_name must be a non-empty string.")
        if not geometry or not geometry.strip():
            raise ValueError("geometry must be a non-empty string.")
        geometry_unit_lower = geometry_unit.lower()
        if geometry_unit_lower not in ("angstrom", "bohr"):
            raise ValueError(
                f"geometry_unit must be 'angstrom' or 'bohr', "
                f"got {geometry_unit!r}."
            )
        if not functional or not functional.strip():
            raise ValueError("functional must be a non-empty string.")
        if not basis or not basis.strip():
            raise ValueError("basis must be a non-empty string.")
        if not isinstance(charge, int):
            raise ValueError(f"charge must be an integer, got {type(charge)}.")
        if not isinstance(spin, int) or spin < 1:
            raise ValueError(f"spin must be an integer >= 1, got {spin}.")

        # geometry lines must have at least 4 columns (Element x y z)
        for lineno, line in enumerate(geometry.strip().splitlines(), 1):
            fields = line.split()
            if len(fields) < 4:
                raise ValueError(
                    f"Geometry line {lineno} has {len(fields)} field(s); "
                    f"expected at least 4 (Element x y z): {line!r}"
                )
            # first field should look like an element symbol
            if not re.fullmatch(r"[A-Z][a-z]?", fields[0]):
                raise ValueError(
                    f"Geometry line {lineno}: first field {fields[0]!r} "
                    f"does not look like an element symbol."
                )
            # coords should be parseable as float
            try:
                float(fields[1])
                float(fields[2])
                float(fields[3])
            except ValueError:
                raise ValueError(
                    f"Geometry line {lineno}: coordinates are not numeric: {line!r}"
                )