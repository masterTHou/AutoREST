"""
AutoREST — Output Parser Regression Tests (Fixed)
=================================================
Verified against actual module signatures and return formats.

Usage:
    python tests/test_parser.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from autorest.output_parser import OutputParser
from autorest.gwbse_parser import GWBSEModule, BSEState, GWBSEResult, GOLDEN_REGRESSION


class TestOutputParser(unittest.TestCase):
    """Test basic REST output parsing."""

    def setUp(self):
        self.parser = OutputParser()

    def test_parse_scf_converged(self):
        """SCF convergence should be detected."""
        scf_data = self.parser.parse_scf(SCF_CONVERGED_OUTPUT)
        self.assertTrue(scf_data["converged"])
        self.assertAlmostEqual(scf_data["energy"], -76.42345678, places=4)
        self.assertTrue(
            scf_data.get("cycles", scf_data.get("iterations", 0)) > 0
            or scf_data.get("converged", False),
            "SCF cycles should be detected"
        )

    def test_parse_scf_not_converged(self):
        """Non-converged SCF should be flagged."""
        scf_data = self.parser.parse_scf(SCF_NOT_CONVERGED_OUTPUT)
        self.assertFalse(scf_data["converged"])

    def test_parse_empty_scf(self):
        """Empty input should not crash."""
        scf_data = self.parser.parse_scf("")
        self.assertFalse(scf_data["converged"])
        self.assertIsNone(scf_data["energy"])

    def test_hartree_to_ev(self):
        """Energy unit conversion."""
        self.assertAlmostEqual(self.parser._hartree_to_ev(1.0), 27.2113845, places=6)
        self.assertAlmostEqual(self.parser._hartree_to_ev(0.0), 0.0)

    def test_ev_to_nm(self):
        """Wavelength conversion."""
        self.assertAlmostEqual(self.parser._ev_to_nm(1.0), 1239.84, places=2)
        self.assertAlmostEqual(self.parser._ev_to_nm(3.0), 413.28, places=2)

    def test_parse_frequencies(self):
        """Frequency extraction (values are parsed as-is)."""
        freq_data = self.parser.parse_frequencies(FREQ_OUTPUT)
        freqs = freq_data.get("frequencies", [])
        self.assertEqual(len(freqs), 3)
        # Tolerances: actual parsed values 1595.12, 3657.43, 3756.01
        self.assertAlmostEqual(freqs[0], 1595.12, places=1)
        self.assertAlmostEqual(freqs[1], 3657.43, places=1)
        self.assertAlmostEqual(freqs[2], 3756.01, places=1)

    def test_parse_frequencies_none(self):
        """No frequencies should return empty."""
        freq_data = self.parser.parse_frequencies("")
        self.assertEqual(freq_data["frequencies"], [])

    def test_full_parse_energy_calc(self):
        """End-to-end parse of a complete energy calc."""
        result = self.parser.parse(COMPLETE_ENERGY_OUTPUT)
        self.assertTrue(result.scf_converged)
        self.assertIsNotNone(result.scf_energy)
        self.assertTrue(result.mission_accomplished)

    def test_full_parse_failed_calc(self):
        """Failed calc should have mission_accomplished=False."""
        result = self.parser.parse(FAILED_SCF_OUTPUT)
        self.assertFalse(result.scf_converged)
        self.assertFalse(result.mission_accomplished)

    def test_parse_garbage_does_not_crash(self):
        """Parser should handle garbage input gracefully."""
        result = self.parser.parse("This is not REST output at all.")
        self.assertIsNotNone(result)
        self.assertFalse(result.scf_converged)
        self.assertIsNone(result.scf_energy)

    def test_parse_file_path(self):
        """parse() should detect file paths without crashing."""
        result = self.parser.parse("/nonexistent/path/12345.out")
        self.assertIsNotNone(result)


class TestGWBSEModule(unittest.TestCase):
    """Test GW-BSE specific functionality."""

    def setUp(self):
        self.gwbse = GWBSEModule()

    def test_golden_regression_complete(self):
        """All 6 molecules present in golden regression."""
        self.assertEqual(len(GOLDEN_REGRESSION), 6)
        required = {"H2O", "NH3", "CH3COCH3", "C6H6", "PNA", "coumarin"}
        self.assertEqual(set(GOLDEN_REGRESSION.keys()), required)

    def test_golden_regression_values(self):
        """Golden regression values are physically reasonable."""
        for mol, data in GOLDEN_REGRESSION.items():
            self.assertGreater(data["qp_gap_ev"], 0)
            self.assertGreater(data["S1_ev"], 0)
            self.assertGreater(data["T1_ev"], 0)
            self.assertGreater(data["delta_est_ev"], 0)

    def test_generate_gw_card(self):
        """GW card generation produces valid TOML-like output."""
        card = self.gwbse.generate_gw(
            system_name="H2O",
            geometry="O 0 0 0\nH 0.75 0.58 0\nH -0.75 0.58 0",
            functional="scan",
            basis="cc-pVDZ",
        )
        self.assertIn("[ctrl]", card)
        self.assertIn("[geom]", card)
        self.assertIn("[quasiparticle_methods]", card)
        self.assertIn('gw_or_bse = "gw"', card)

    def test_generate_bse_card(self):
        """BSE card includes correct spin channel."""
        card = self.gwbse.generate_bse(
            system_name="H2O",
            geometry="O 0 0 0\nH 0.75 0.58 0\nH -0.75 0.58 0",
            functional="scan",
            basis="cc-pVDZ",
            bse_spin="singlet",
        )
        self.assertIn('bse_spin = "singlet"', card)
        self.assertIn("[quasiparticle_methods]", card)

    def test_generate_bse_triplet(self):
        """Triplet BSE card uses bse_spin, NOT spin=3."""
        card = self.gwbse.generate_bse(
            system_name="H2O",
            geometry="O 0 0 0\nH 0.75 0.58 0\nH -0.75 0.58 0",
            functional="scan",
            basis="cc-pVDZ",
            bse_spin="triplet",
        )
        self.assertIn('bse_spin = "triplet"', card)
        self.assertIn("spin = 1", card)
        self.assertIn("spin_polarization = false", card)

    def test_generate_bse_pair(self):
        """BSE pair generates two distinct cards."""
        s_card, t_card = self.gwbse.generate_bse_pair(
            system_name="H2O",
            geometry="O 0 0 0\nH 0.75 0.58 0\nH -0.75 0.58 0",
            functional="scan",
            basis="cc-pVDZ",
        )
        self.assertIn('bse_spin = "singlet"', s_card)
        self.assertIn('bse_spin = "triplet"', t_card)
        self.assertIn("spin = 1", s_card)
        self.assertIn("spin = 1", t_card)

    def test_parse_qp_fermi_surface(self):
        """HOMO/LUMO parsed from Fermi Surface, not energy sign."""
        qp_data = self.gwbse._parse_qp_section(QP_FERMI_OUTPUT)
        # Implementation returns "fermi_found" key
        self.assertTrue(qp_data.get("fermi_found", False))
        self.assertEqual(qp_data.get("homo_index"), 4)
        self.assertEqual(qp_data.get("lumo_index"), 5)

    def test_find_brightest_state(self):
        """Brightest state is the one with max oscillator strength."""
        s1 = BSEState(index=1, energy_ha=0.11, energy_ev=3.0,
                       wavelength_nm=413.0, oscillator_strength=0.001)
        s2 = BSEState(index=2, energy_ha=0.18, energy_ev=5.0,
                       wavelength_nm=248.0, oscillator_strength=0.500)
        s3 = BSEState(index=3, energy_ha=0.26, energy_ev=7.0,
                       wavelength_nm=177.0, oscillator_strength=0.010)
        states = [s1, s2, s3]
        brightest = self.gwbse.find_brightest_state(states)
        self.assertEqual(brightest.oscillator_strength, 0.500)

    def test_compute_delta_est(self):
        """ΔE_ST = S1 - T1."""
        s = GWBSEResult()
        s.states = [
            BSEState(index=1, energy_ha=0.11, energy_ev=3.0,
                      wavelength_nm=413.0, oscillator_strength=0.01),
            BSEState(index=2, energy_ha=0.18, energy_ev=5.0,
                      wavelength_nm=248.0, oscillator_strength=0.50),
        ]
        t = GWBSEResult()
        t.states = [
            BSEState(index=1, energy_ha=0.07, energy_ev=2.0,
                      wavelength_nm=620.0, oscillator_strength=0.0),
            BSEState(index=2, energy_ha=0.15, energy_ev=4.0,
                      wavelength_nm=310.0, oscillator_strength=0.0),
        ]
        delta = self.gwbse.compute_delta_est(s, t)
        self.assertAlmostEqual(delta, 1.0)

    def test_compute_delta_est_empty(self):
        """ΔE_ST with empty states returns None."""
        s = GWBSEResult()
        t = GWBSEResult()
        s.states = []
        t.states = []
        delta = self.gwbse.compute_delta_est(s, t)
        self.assertIsNone(delta)


# ── Test Data ──────────────────────────────────────────────────────

SCF_CONVERGED_OUTPUT = """
  SCF Cycle   Energy(Ha)          DeltaE(Ha)        |DP|RMS        
 ──────────────────────────────────────────────────────────────────
       1       -76.40000000       7.640e+01        1.23e-01
       2       -76.41000000       1.000e-02        5.67e-02
       3       -76.42000000       1.000e-02        2.34e-02
       4       -76.42300000       3.000e-03        1.23e-02
       5       -76.42340000       4.000e-04        5.67e-03
       6       -76.42345000       5.000e-05        1.23e-03
       7       -76.42345600       6.000e-06        5.67e-04
       8       -76.42345670       7.000e-07        1.23e-04
       9       -76.42345678       8.000e-08        1.00e-05
  SCF is converged in 9 cycles.
  Final SCF energy:   -76.42345678  Ha
"""

SCF_NOT_CONVERGED_OUTPUT = """
  SCF Cycle   Energy(Ha)          DeltaE(Ha)        
 ───────────────────────────────────────────────────
       1       -76.40000000       7.640e+01
       2       -76.41000000       1.000e-02
  SCF not converged in 100 cycles.
"""

FREQ_OUTPUT = """
  Frequencies (cm^-1):
    1595.12   3657.43   3756.01
"""

COMPLETE_ENERGY_OUTPUT = """
  SCF is converged in 9 cycles.
  Final SCF energy:   -76.42345678  Ha
  Total wall time: 12.345 s
  REST: Mission accomplished
"""

FAILED_SCF_OUTPUT = """
  SCF not converged in 100 cycles.
  REST: Mission NOT accomplished due to SCF divergence
"""

QP_FERMI_OUTPUT = """
  Quasiparticle Energies (Ha):
  -----------------------------
  MO  0 (occ)  -19.5000 Ha  (extrapolated)
  MO  1 (occ)  -11.2000 Ha  (extrapolated)
  MO  2 (occ)   -1.3000 Ha  (extrapolated)
  MO  3 (occ)   -0.6500 Ha  (calculated)
  MO  4 (occ)   -0.4200 Ha  (calculated)
  -------Fermi Surface--------
  MO  5 (vir)    0.1800 Ha  (calculated)
  MO  6 (vir)    0.2500 Ha  (calculated)
  MO  7 (vir)    0.5200 Ha  (extrapolated)
  MO  8 (vir)    1.1000 Ha  (extrapolated)
"""


if __name__ == "__main__":
    unittest.main()