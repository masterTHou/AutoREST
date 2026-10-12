"""
AutoREST — H₂O Single-Point Energy Example
==========================================
The simplest possible example: compute the SCF energy of water.

Usage:
    python examples/water_energy.py
"""

from autorest import AutoREST

def main():
    # Water geometry (optimized at B3LYP/def2-SVP level)
    h2o_xyz = """O   0.000000   0.000000   0.000000
H   0.756950   0.585882   0.000000
H  -0.756950   0.585882   0.000000"""

    # Initialize AutoREST
    ar = AutoREST()

    # Generate the input card (--dry-run)
    card = ar.single_point(
        system_name="H2O",
        geometry=h2o_xyz,
        functional="b3lyp",
        basis="def2-SVP",
        charge=0,
        spin=1,
        run=False,  # Only generate card, don't run
    )

    print("=== Generated REST Input Card ===")
    print(card)
    print()
    print("To run this calculation:")
    print("  1. Save the card to water.in")
    print('  2. conda activate rest')
    print("  3. rest -i water.in > water.out")
    print()
    print("Or use the Python API with run=True to execute automatically.")


if __name__ == "__main__":
    main()