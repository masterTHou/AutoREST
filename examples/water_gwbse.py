"""
AutoREST — H₂O GW-BSE Example
==============================
G₀W₀-BSE singlet and triplet excitation energies for water.

This example generates input cards for both spin channels and
shows how to interpret the results.

Usage:
    python examples/water_gwbse.py
"""

from autorest import AutoREST
from autorest import GWBSEModule


def main():
    # Water geometry
    h2o_xyz = """O   0.000000   0.000000   0.000000
H   0.756950   0.585882   0.000000
H  -0.756950   0.585882   0.000000"""

    ar = AutoREST()
    gwbse = GWBSEModule()

    # ── Step 1: Generate input cards ──────────────────────────

    singlet_card, triplet_card = gwbse.generate_bse_pair(
        system_name="H2O",
        geometry=h2o_xyz,
        functional="scan",
        basis="cc-pVDZ",
        n_roots=5,
    )

    print("=" * 60)
    print("H₂O G₀W₀-BSE Input Cards")
    print("=" * 60)

    print("\n--- Singlet Card ---")
    print(singlet_card)

    print("\n--- Triplet Card ---")
    print(triplet_card)

    print("\n" + "=" * 60)
    print("Important Notes:")
    print("=" * 60)
    print("1. Ground-state: spin=1, spin_polarization=false for BOTH cards")
    print("2. Triplet excitation: bse_spin='triplet' (NOT spin=3!)")
    print("3. HOMO/LUMO identified by 'Fermi Surface' in output")
    print("4. Triplet oscillator strength = 0 is NORMAL (no SOC)")
    print()
    print("Golden Regression (SCAN/cc-pVDZ):")
    print("  QP Gap: 16.1099 eV")
    print("  S1:     6.9549 eV")
    print("  T1:     6.1395 eV")
    print("  ΔE_ST:  0.8154 eV")


if __name__ == "__main__":
    main()