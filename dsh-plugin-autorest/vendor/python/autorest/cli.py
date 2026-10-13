"""
AutoREST Command-Line Interface
===============================
Unified CLI for all REST calculation types.

Usage:
  python -m autorest --task energy --functional b3lyp --basis def2-SVP \\
      --geometry water.xyz --charge 0 --spin 1

  python -m autorest --task gwbse --functional scan --basis cc-pVDZ \\
      --geometry mol.xyz --charge 0 --spin 1 --bse-roots 5

  python -m autorest --task optimization --functional pbe0 \\
      --basis cc-pVTZ --geometry mol.xyz --charge 0 --spin 1 --freq
"""

import argparse
import sys
from pathlib import Path


def parse_geometry(geom_arg: str) -> str:
    """Parse geometry from a file path or inline string."""
    geom_path = Path(geom_arg)
    if geom_path.exists():
        return geom_path.read_text()
    return geom_arg


def main():
    parser = argparse.ArgumentParser(
        prog="autorest",
        description="AutoREST — AI-Driven REST Electronic Structure Automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  autorest --task energy --functional b3lyp --basis def2-SVP --geometry water.xyz --charge 0 --spin 1
  autorest --task optimization --functional pbe0 --basis cc-pVTZ --geometry mol.xyz --charge 0 --spin 1 --freq
  autorest --task gwbse --functional scan --basis cc-pVDZ --geometry mol.xyz --charge 0 --spin 1 --bse-roots 5
        """,
    )

    # ── Required ──────────────────────────────────────────────────
    parser.add_argument("--task", required=True,
                        choices=["energy", "optimization", "force", "frequency",
                                 "tddft", "gw", "bse", "gwbse"],
                        help="Calculation task type")
    parser.add_argument("--functional", required=True,
                        help="Exchange-correlation functional (e.g., b3lyp, scan, pbe0)")
    parser.add_argument("--basis", required=True,
                        help="Orbital basis set (e.g., def2-SVP, cc-pVTZ)")
    parser.add_argument("--charge", type=float, required=True,
                        help="Net molecular charge")
    parser.add_argument("--spin", type=int, required=True,
                        help="Spin multiplicity (2S+1, minimum 1)")

    # ── Geometry ──────────────────────────────────────────────────
    parser.add_argument("--geometry", required=True,
                        help="Geometry file (.xyz) or inline string")
    parser.add_argument("--geometry-unit", default="angstrom",
                        choices=["angstrom", "bohr"],
                        help="Coordinate unit (default: angstrom)")

    # ── System ────────────────────────────────────────────────────
    parser.add_argument("--name", default="MOLECULE",
                        help="System name for the input card")

    # ── Optional ──────────────────────────────────────────────────
    parser.add_argument("--auxbas", default=None,
                        help="Auxiliary basis set")
    parser.add_argument("--dispersion", default=None,
                        choices=["d3", "d3bj", "d4"],
                        help="Empirical dispersion correction")
    parser.add_argument("--spin-polarization", action="store_true", default=None,
                        help="Force spin-polarized calculation")
    parser.add_argument("--num-threads", type=int, default=4,
                        help="Number of CPU threads (default: 4)")
    parser.add_argument("--print-level", type=int, default=1,
                        help="Output verbosity (0-2, default: 1)")

    # ── Output ────────────────────────────────────────────────────
    parser.add_argument("--output-dir", default="./calc",
                        help="Output directory (default: ./calc)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Generate input card only, do not run")

    # ── Optimization ──────────────────────────────────────────────
    parser.add_argument("--opt-maxiter", type=int, default=300,
                        help="Max optimization steps (default: 300)")
    parser.add_argument("--opt-energy-conv", type=float, default=1e-6,
                        help="Energy convergence threshold")
    parser.add_argument("--opt-grms-conv", type=float, default=3e-4,
                        help="Gradient RMS convergence threshold")

    # ── Frequency ─────────────────────────────────────────────────
    parser.add_argument("--freq", action="store_true",
                        help="Run frequency calculation after optimization")

    # ── GW-BSE ────────────────────────────────────────────────────
    parser.add_argument("--bse-spin", default="singlet",
                        choices=["singlet", "triplet", "both"],
                        help="BSE excitation spin channel (default: singlet)")
    parser.add_argument("--bse-roots", type=int, default=5,
                        help="Number of BSE roots (default: 5)")
    parser.add_argument("--bse-tda", action="store_true", default=True,
                        help="Use Tamm-Dancoff approximation (default: on)")
    parser.add_argument("--no-bse-tda", action="store_true",
                        help="Disable TDA (full BSE)")
    parser.add_argument("--gw-scheme", default="extrapolated",
                        choices=["extrapolated", "linearize", "qp equation"],
                        help="GW quasiparticle scheme (default: extrapolated)")
    parser.add_argument("--scgw", default="g0w0",
                        choices=["g0w0", "evgw"],
                        help="GW self-consistency (default: g0w0)")

    # ── TD-DFT ────────────────────────────────────────────────────
    parser.add_argument("--tddft-spin", default="singlet",
                        choices=["singlet", "triplet", "both"],
                        help="TD-DFT spin channel")
    parser.add_argument("--tddft-roots", type=int, default=6,
                        help="TD-DFT roots (default: 6)")
    parser.add_argument("--tddft-method", default="tda",
                        choices=["tda", "lr"],
                        help="TD-DFT method (default: tda)")

    args = parser.parse_args()

    # Resolve BSE TDA
    if args.no_bse_tda:
        args.bse_tda = False

    # Resolve spin_polarization
    if args.spin_polarization is None:
        args.spin_polarization = args.spin > 1

    # Parse geometry
    geometry = parse_geometry(args.geometry)

    from .input_generator import InputGenerator

    gen = InputGenerator()

    # ── Generate input card ───────────────────────────────────────
    task_map = {
        "energy": gen.generate_energy,
        "optimization": gen.generate_optimization,
        "force": gen.generate_force,
        "frequency": gen.generate_frequency,
        "tddft": gen.generate_tddft,
        "gw": gen.generate_gw,
        "bse": gen.generate_bse,
        "gwbse": gen.generate_bse_pair,
    }

    generate_fn = task_map[args.task]

    # Build kwargs
    common = dict(
        system_name=args.name,
        geometry=geometry,
        geometry_unit=args.geometry_unit,
        functional=args.functional,
        basis=args.basis,
        charge=args.charge,
        spin=args.spin,
        spin_polarization=args.spin_polarization,
        auxbas_path=args.auxbas,
        empirical_dispersion=args.dispersion,
        num_threads=args.num_threads,
        print_level=args.print_level,
    )

    task_specific = {}
    if args.task in ("optimization",):
        task_specific.update(
            opt_maxiter=args.opt_maxiter,
            opt_converge_energy=args.opt_energy_conv,
            opt_converge_grms=args.opt_grms_conv,
        )
    if args.task in ("gw", "bse", "gwbse"):
        task_specific.update(
            gw_scheme=args.gw_scheme,
            scgw=args.scgw,
            bse_tda=args.bse_tda,
            n_roots=args.bse_roots,
        )
        if args.task in ("bse", "gwbse"):
            task_specific["bse_spin"] = args.bse_spin
    if args.task == "tddft":
        task_specific.update(
            tddft_method=args.tddft_method,
            tddft_spin=args.tddft_spin,
            n_roots=args.tddft_roots,
        )

    card = generate_fn(**common, **task_specific)

    # ── Output ────────────────────────────────────────────────────
    if args.dry_run:
        print(card)
        return 0

    # Write and (optionally) run
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    from .rest_runner import RestRunner

    runner = RestRunner()
    result = runner.run(card, output_dir=output_dir)

    # ── Parse result ──────────────────────────────────────────────
    from .output_parser import OutputParser

    parser_out = OutputParser()
    parsed = parser_out.parse(result.stdout)

    # ── Validate ──────────────────────────────────────────────────
    from .scientific_validator import ScientificValidator

    validator = ScientificValidator()
    checks = validator.validate(parsed)

    # ── Report ────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"  AutoREST — {args.task.upper()} — {result.status.upper()}")
    print("=" * 60)
    if parsed.scf_energy:
        print(f"  SCF Energy:    {parsed.scf_energy:14.8f} Ha")
    if parsed.total_energy:
        print(f"  Total Energy:  {parsed.total_energy:14.8f} Ha")
    print(f"  SCF Cycles:    {parsed.scf_cycles}")
    print(f"  Wall Time:     {result.wall_time:.1f} s")
    print()
    print("  Validation Checks:")
    for check in checks:
        icon = "✓" if check.passed else "✗"
        print(f"    {icon} {check.name}: {check.detail}")
    print("=" * 60)

    return 0 if result.status == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())