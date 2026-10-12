"""
AutoREST — Acetone Multi-Step Workflow
=======================================
Demonstrates a complete workflow: optimization → frequency → GW-BSE.

Usage:
    python examples/acetone_workflow.py
"""

from autorest import AutoREST
from autorest import GWBSEModule


def main():
    # Acetone geometry (approximate)
    acetone_xyz = """C  -0.178508  0.470977   0.051150
O   1.041002  0.442691   0.053199
C  -0.993865 -0.820462   0.051122
H  -2.088934 -0.660239   0.049121
H  -0.710704 -1.422781  -0.836135
H  -0.713683 -1.420928   0.940579
C  -0.957885  1.774885   0.048553
H  -1.621133  1.825266  -0.841333
H  -1.623961  1.827085   0.936219
H  -0.262896  2.634271   0.048780"""

    ar = AutoREST()
    gwbse = GWBSEModule()

    print("=" * 60)
    print("Acetone (CH₃COCH₃) Complete Workflow")
    print("=" * 60)
    print()
    print("This workflow consists of 3 steps:")
    print("  Step 1: Geometry optimization")
    print("  Step 2: Frequency check (verify minimum)")
    print("  Step 3: G₀W₀-BSE excitation energies")
    print()

    # ── Step 1: Generate optimization card ────────────────────
    opt_card = ar.optimize(
        system_name="CH3COCH3",
        geometry=acetone_xyz,
        functional="scan",
        basis="cc-pVDZ",
        charge=0,
        spin=1,
        run=False,
    )
    print("Step 1 — Optimization Input Card:")
    print(opt_card[:500] + "\n... (truncated)\n")

    # ── Step 2: Generate frequency card ───────────────────────
    # (Would use optimized geometry from Step 1)
    freq_card = ar.frequency(
        system_name="CH3COCH3",
        geometry=acetone_xyz,  # Would be opt result
        functional="scan",
        basis="cc-pVDZ",
        charge=0,
        spin=1,
        run=False,
    )
    print("Step 2 — Frequency Input Card:")
    print(freq_card[:500] + "\n... (truncated)\n")

    # ── Step 3: GW-BSE (both spin channels) ───────────────────
    singlet_card, triplet_card = gwbse.generate_bse_pair(
        system_name="CH3COCH3",
        geometry=acetone_xyz,  # Would be opt result
        functional="scan",
        basis="cc-pVDZ",
        n_roots=5,
    )
    print("Step 3 — BSE Singlet Input Card:")
    print(singlet_card[:500] + "\n... (truncated)\n")

    print("=" * 60)
    print("Golden Regression (SCAN/cc-pVDZ):")
    print("  QP Gap: 10.8984 eV")
    print("  S1:      3.3838 eV (n→π*, dark)")
    print("  T1:      2.7121 eV")
    print("  ΔE_ST:   0.6718 eV")
    print("  Brightest: S2 @ 5.6305 eV")
    print()
    print("Note: S1 is NOT the brightest state —")
    print("      the lowest excitation (n→π*) has near-zero oscillator strength.")
    print("      Always report both S1 and the brightest state!")


if __name__ == "__main__":
    main()