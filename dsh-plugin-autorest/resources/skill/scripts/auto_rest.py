"""
AutoREST — Main Facade
======================
Unified entry point for all AutoREST functionality.

Usage:
    from autorest import AutoREST
    ar = AutoREST()
    result = ar.single_point(system_name="H2O", geometry=..., functional="b3lyp", ...)
"""

import time
from pathlib import Path
from typing import Optional, Union, List

from .input_generator import InputGenerator
from .rest_runner import RestRunner
from .output_parser import OutputParser
from .scientific_validator import ScientificValidator
from .gwbse_parser import GWBSEModule


class AutoREST:
    """Unified facade for REST electronic structure automation.

    Constructs and coordinates InputGenerator, RestRunner, OutputParser,
    ScientificValidator, and GWBSEModule for end-to-end workflows.
    """

    def __init__(
        self,
        conda_env: str = "rest",
        rest_executable: Optional[str] = None,
        work_dir: Optional[str] = None,
        num_threads: int = 4,
    ):
        """Initialize AutoREST.

        Args:
            conda_env: Conda environment name where REST is installed.
            rest_executable: Optional explicit path to REST binary.
            work_dir: Working directory for calculations.
            num_threads: Default number of CPU threads.
        """
        self.num_threads = num_threads
        self.input_generator = InputGenerator()
        self.runner = RestRunner(
            conda_env=conda_env,
            rest_executable=rest_executable,
            work_dir=work_dir,
        )
        self.output_parser = OutputParser()
        self.validator = ScientificValidator()
        self.gwbse = GWBSEModule()

    # ── Convenience: Input-only (no execution) ───────────────────

    def generate_card(self, task: str, **kwargs) -> str:
        """Generate a REST input card without executing.

        Args:
            task: One of "energy", "optimization", "force", "frequency",
                  "gw", "bse_singlet", "bse_triplet".
            **kwargs: Passed to the corresponding InputGenerator method.

        Returns:
            TOML input card as string.
        """
        method_map = {
            "energy": self.input_generator.generate_energy,
            "optimization": self.input_generator.generate_optimization,
            "force": self.input_generator.generate_force,
            "frequency": self.input_generator.generate_frequency,
            "gw": self.input_generator.generate_gw,
            "bse_singlet": self.input_generator.generate_bse,
            "bse_triplet": self.input_generator.generate_bse,
        }
        fn = method_map.get(task)
        if fn is None:
            raise ValueError(f"Unknown task: {task}. Choose from: {list(method_map)}")
        if task in ("bse_singlet", "bse_triplet"):
            kwargs.setdefault("bse_spin", task.split("_")[1])
        return fn(**kwargs)

    # ── Single-Point Energy ─────────────────────────────────────

    def single_point(
        self,
        system_name: str,
        geometry: str,
        geometry_unit: str = "angstrom",
        functional: str = "b3lyp",
        basis: str = "def2-SVP",
        charge: float = 0.0,
        spin: int = 1,
        run: bool = True,
        **kwargs,
    ):
        """Run a single-point energy calculation.

        Args:
            system_name: Name of the molecular system.
            geometry: Multi-line "Element x y z" string or path to .xyz file.
            geometry_unit: "angstrom" or "bohr".
            functional: Exchange-correlation functional.
            basis: Orbital basis set.
            charge: Net molecular charge.
            spin: Spin multiplicity (2S+1).
            run: If True, execute REST; if False, return card only.
            **kwargs: Additional InputGenerator parameters.

        Returns:
            If run=True: RunResult with parsed and validated data.
            If run=False: TOML input card string.
        """
        card = self.input_generator.generate_energy(
            system_name=system_name,
            geometry=geometry,
            geometry_unit=geometry_unit,
            functional=functional,
            basis=basis,
            charge=charge,
            spin=spin,
            num_threads=self.num_threads,
            **kwargs,
        )
        if not run:
            return card
        return self._execute_and_validate(card)

    # ── Geometry Optimization ───────────────────────────────────

    def optimize(
        self,
        system_name: str,
        geometry: str,
        geometry_unit: str = "angstrom",
        functional: str = "b3lyp",
        basis: str = "def2-SVP",
        charge: float = 0.0,
        spin: int = 1,
        run: bool = True,
        **kwargs,
    ):
        """Run a geometry optimization.

        Returns optimized geometry in parsed result.
        """
        card = self.input_generator.generate_optimization(
            system_name=system_name,
            geometry=geometry,
            geometry_unit=geometry_unit,
            functional=functional,
            basis=basis,
            charge=charge,
            spin=spin,
            num_threads=self.num_threads,
            **kwargs,
        )
        if not run:
            return card
        return self._execute_and_validate(card)

    # ── Force Calculation ───────────────────────────────────────

    def force(
        self,
        system_name: str,
        geometry: str,
        geometry_unit: str = "angstrom",
        functional: str = "b3lyp",
        basis: str = "def2-SVP",
        charge: float = 0.0,
        spin: int = 1,
        run: bool = True,
        **kwargs,
    ):
        """Calculate atomic forces at current geometry."""
        card = self.input_generator.generate_force(
            system_name=system_name,
            geometry=geometry,
            geometry_unit=geometry_unit,
            functional=functional,
            basis=basis,
            charge=charge,
            spin=spin,
            num_threads=self.num_threads,
            **kwargs,
        )
        if not run:
            return card
        return self._execute_and_validate(card)

    # ── Frequency + Thermochemistry ─────────────────────────────

    def frequency(
        self,
        system_name: str,
        geometry: str,
        geometry_unit: str = "angstrom",
        functional: str = "b3lyp",
        basis: str = "def2-SVP",
        charge: float = 0.0,
        spin: int = 1,
        run: bool = True,
        **kwargs,
    ):
        """Run Hessian + frequency + thermochemistry."""
        card = self.input_generator.generate_frequency(
            system_name=system_name,
            geometry=geometry,
            geometry_unit=geometry_unit,
            functional=functional,
            basis=basis,
            charge=charge,
            spin=spin,
            num_threads=self.num_threads,
            **kwargs,
        )
        if not run:
            return card
        return self._execute_and_validate(card)

    # ── G₀W₀ Quasiparticle ─────────────────────────────────────

    def gw(
        self,
        system_name: str,
        geometry: str,
        geometry_unit: str = "angstrom",
        functional: str = "scan",
        basis: str = "cc-pVDZ",
        auxbas: str = "def2-SV(P)-JKFIT",
        charge: float = 0.0,
        spin: int = 1,
        run: bool = True,
        **kwargs,
    ):
        """Run G₀W₀ quasiparticle energy calculation.

        Note: G₀W₀ has starting-point dependence. SCAN is the verified
        baseline but not the only correct starting point.
        """
        card = self.input_generator.generate_gw(
            system_name=system_name,
            geometry=geometry,
            geometry_unit=geometry_unit,
            functional=functional,
            basis=basis,
            auxbas_path=auxbas,
            charge=charge,
            spin=spin,
            num_threads=self.num_threads,
            **kwargs,
        )
        if not run:
            return card
        return self._execute_and_validate(card)

    # ── BSE Excited State ───────────────────────────────────────

    def bse(
        self,
        system_name: str,
        geometry: str,
        geometry_unit: str = "angstrom",
        functional: str = "scan",
        basis: str = "cc-pVDZ",
        auxbas: str = "def2-SV(P)-JKFIT",
        charge: float = 0.0,
        spin: int = 1,
        bse_spin: str = "singlet",
        n_roots: int = 5,
        run: bool = True,
        **kwargs,
    ):
        """Run G₀W₀-BSE excited state calculation.

        Important: For closed-shell singlet reference on triplet BSE,
        keep spin=1 and set bse_spin="triplet" — do NOT change spin to 3.
        """
        card = self.input_generator.generate_bse(
            system_name=system_name,
            geometry=geometry,
            geometry_unit=geometry_unit,
            functional=functional,
            basis=basis,
            auxbas_path=auxbas,
            charge=charge,
            spin=spin,
            bse_spin=bse_spin,
            n_roots=n_roots,
            num_threads=self.num_threads,
            **kwargs,
        )
        if not run:
            return card
        return self._execute_and_validate(card)

    # ── Full G₀W₀-BSE Pair ─────────────────────────────────────

    def gwbse(
        self,
        system_name: str,
        geometry: str,
        geometry_unit: str = "angstrom",
        functional: str = "scan",
        basis: str = "cc-pVDZ",
        auxbas: str = "def2-SV(P)-JKFIT",
        charge: float = 0.0,
        spin: int = 1,
        n_roots: int = 5,
        run: bool = True,
        **kwargs,
    ):
        """Run both singlet and triplet G₀W₀-BSE calculations.

        Returns:
            dict with keys "singlet_card", "triplet_card", "singlet_result",
            "triplet_result", "delta_est_ev".
        """
        singlet_card, triplet_card = self.input_generator.generate_bse_pair(
            system_name=system_name,
            geometry=geometry,
            geometry_unit=geometry_unit,
            functional=functional,
            basis=basis,
            auxbas_path=auxbas,
            charge=charge,
            spin=spin,
            n_roots=n_roots,
            num_threads=self.num_threads,
            **kwargs,
        )

        result = {
            "singlet_card": singlet_card,
            "triplet_card": triplet_card,
        }

        if run:
            singlet_result = self._execute_and_validate(singlet_card)
            triplet_result = self._execute_and_validate(triplet_card)
            result["singlet_result"] = singlet_result
            result["triplet_result"] = triplet_result

            # Parse GW-BSE outputs
            parsed_s = self.gwbse.parse_gwbse_output(
                singlet_result.stdout, expected_bse_spin="singlet"
            )
            parsed_t = self.gwbse.parse_gwbse_output(
                triplet_result.stdout, expected_bse_spin="triplet"
            )
            result["delta_est_ev"] = self.gwbse.compute_delta_est(parsed_s, parsed_t)
            result["singlet_parsed"] = parsed_s
            result["triplet_parsed"] = parsed_t

        return result

    # ── Internal: Execute + Parse + Validate ────────────────────

    def _execute_and_validate(self, card: str):
        """Execute a REST calculation, parse output, and run validation.

        Returns the RunResult with .parsed and .validation attributes attached.
        """
        result = self.runner.run(card)
        result.parsed = self.output_parser.parse(result.stdout)
        result.validation = self.validator.validate(result.parsed)
        result.all_passed = all(c.passed for c in result.validation
                                if c.severity == "error")
        return result

    # ── Summary ─────────────────────────────────────────────────

    def print_summary(self, result):
        """Print a formatted summary of calculation results."""
        print("\n" + "=" * 60)
        print(f"  AutoREST — {result.calculation_type or 'Calculation'}")
        print(f"  Status: {result.status.upper()}")
        print("=" * 60)

        if hasattr(result, "parsed") and result.parsed:
            p = result.parsed
            if p.scf_energy:
                print(f"  SCF Energy:    {p.scf_energy:14.8f} Ha")
            if p.total_energy:
                print(f"  Total Energy:  {p.total_energy:14.8f} Ha")
            print(f"  SCF Cycles:    {p.scf_cycles}")
            if p.zpe is not None:
                print(f"  ZPE:           {p.zpe:.6f} Ha")
                print(f"  ZPE:           {p.zpe * 2625.5:.2f} kJ/mol")

        print(f"  Wall Time:     {result.wall_time:.1f} s" if result.wall_time else "")
        print()

        if hasattr(result, "validation") and result.validation:
            print("  Validation:")
            for check in result.validation:
                icon = "✓" if check.passed else "✗"
                print(f"    {icon} [{check.severity:7s}] {check.name}: {check.detail}")

        print("=" * 60)