"""Integration test for all AutoREST modules."""
import sys
sys.path.insert(0, r"D:\REST-DSH\AutoREST")

from autorest import (
    InputGenerator, OutputParser, GWBSEModule,
    ParsedResult, GOLDEN_REGRESSION,
)

# Test InputGenerator
gen = InputGenerator()
card = gen.generate_energy(
    system_name="H2O",
    geometry="O 0 0 0\nH 0.75 0.58 0\nH -0.75 0.58 0",
    geometry_unit="angstrom",
    functional="b3lyp",
    basis="def2-SVP",
    charge=0,
    spin=1,
)
assert "[ctrl]" in card
assert "[geom]" in card
assert "b3lyp" in card
assert "H2O" in card
print("InputGenerator: energy card OK")

# Test GW card
gw_card = gen.generate_gw(
    system_name="H2O",
    geometry="O 0 0 0\nH 0.75 0.58 0\nH -0.75 0.58 0",
    geometry_unit="angstrom",
    functional="scan",
    basis="cc-pVDZ",
    charge=0,
    spin=1,
)
assert "[quasiparticle_methods]" in gw_card
print("InputGenerator: GW card OK")

# Test BSE card
bse_card = gen.generate_bse(
    system_name="H2O",
    geometry="O 0 0 0\nH 0.75 0.58 0\nH -0.75 0.58 0",
    geometry_unit="angstrom",
    functional="scan",
    basis="cc-pVDZ",
    bse_spin="singlet",
    charge=0,
    spin=1,
)
assert 'bse_spin = "singlet"' in bse_card
assert "spin = 1" in bse_card
print("InputGenerator: BSE card OK")

# Test GWBSEModule
gwbse = GWBSEModule()
s_card, t_card = gwbse.generate_bse_pair(
    system_name="H2O",
    geometry="O 0 0 0\nH 0.75 0.58 0\nH -0.75 0.58 0",
    functional="scan",
    basis="cc-pVDZ",
)
assert 'bse_spin = "singlet"' in s_card
assert 'bse_spin = "triplet"' in t_card
print("GWBSEModule: BSE pair OK")

# Test OutputParser
parser = OutputParser()
result = parser.parse(
    "SCF is converged in 9 cycles.\n"
    "Final SCF energy: -76.42345678 Ha\n"
    "REST: Mission accomplished"
)
assert result.scf_converged
assert abs(result.scf_energy - (-76.42345678)) < 1e-6
assert result.mission_accomplished
print("OutputParser: basic parse OK")

# Test Golden Regression
assert len(GOLDEN_REGRESSION) == 6
assert GOLDEN_REGRESSION["H2O"]["delta_est_ev"] == 0.8154
print("Golden Regression: data OK")

print()
print("=" * 50)
print("ALL INTEGRATION TESTS PASSED")
print("=" * 50)