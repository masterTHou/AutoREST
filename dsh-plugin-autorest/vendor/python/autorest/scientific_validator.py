"""
scientific_validator — Physical reasonableness checks for REST quantum chemistry results.

This module provides the ``ScientificValidator`` class, which applies a battery of
scientific sanity checks to parsed REST outputs.  It helps catch common failure modes —
SCF non-convergence, incorrect charge/multiplicity, imaginary frequencies,
spin contamination, and more — before the user acts on physically unreasonable data.

Checks are designed to be **fast, interpretable, and grounded in quantum chemistry
domain knowledge**.  Each check returns a ``ValidationCheck`` named-tuple with a
pass/fail status, a human-readable detail string, and a severity level
(``"ok"``, ``"warning"``, or ``"error"``).

Typical usage::

    from autorest import ScientificValidator

    validator = ScientificValidator()
    checks = validator.validate(parsed_result)
    for c in checks:
        print(f"{c.name}: {'PASS' if c.passed else 'FAIL'} [{c.severity}] — {c.detail}")

    # Get actionable recommendations
    print(validator.recommendation(checks))

    # Aggregate across a multi-step workflow
    summary = validator.validate_all([opt_result, freq_result, sp_result])
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections import namedtuple
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

# ---------------------------------------------------------------------------
# ValidationCheck namedtuple
# ---------------------------------------------------------------------------

ValidationCheck = namedtuple(
    "ValidationCheck",
    ["name", "passed", "detail", "severity"],
)
"""A single scientific validation result.

Parameters
----------
name : str
    Short name of the check (e.g. ``"scf_convergence"``).
passed : bool
    ``True`` if the check passed, ``False`` otherwise.
    A ``False`` on a ``"warning"`` severity does not necessarily mean the
    result is unusable, but it should be reviewed.
detail : str
    Human-readable description of what was checked and why it passed/failed.
severity : str
    One of ``"ok"`` — passed, no concern;
    ``"warning"`` — passed but marginal, or a minor issue that needs
    awareness; ``"error"`` — the result is likely physically incorrect.
"""


# ===================================================================
# Registry of known checks  (name -> docstring)
# ===================================================================

_CHECK_DOCS: Dict[str, str] = {
    "scf_convergence": (
        "Check that the SCF (self-consistent field) procedure converged.  "
        "A non-converged SCF means the wavefunction is not a valid solution "
        "of the Kohn-Sham / Hartree-Fock equations; derived properties "
        "(energies, gradients, dipole moments) are unreliable."
    ),
    "scf_energy_magnitude": (
        "Check that the total SCF energy lies in a physically reasonable "
        "range: not NaN, not positive for neutral species, and not absurdly "
        "large in magnitude.  A positive SCF energy for a neutral molecule "
        "often indicates an incorrect charge or spin multiplicity."
    ),
    "spin_contamination": (
        "For unrestricted (UHF / UKS) calculations, compare the computed "
        "<S²> expectation value with the ideal S(S+1).  Heavy spin "
        "contamination (>10 % deviation) indicates significant mixing with "
        "higher spin states, degrading geometries, frequencies, and "
        "barrier heights."
    ),
    "imaginary_frequencies": (
        "Check whether any vibrational frequencies are imaginary (negative).  "
        "One small imaginary frequency may signal a transition state or a "
        "shallow minimum; multiple or large imaginary frequencies mean the "
        "geometry is not a true minimum on the potential energy surface."
    ),
    "frequency_range": (
        "Verify that vibrational frequencies lie in the physically reasonable "
        "range for molecular vibrations (roughly 0–4000 cm⁻¹ for organic "
        "molecules).  Values far outside this range may indicate linear-molecule "
        "treatment issues or numerical artifacts in the Hessian."
    ),
    "wavefunction_stability": (
        "Check whether a wavefunction stability analysis was performed and, "
        "if so, whether the wavefunction was found to be stable.  An unstable "
        "wavefunction suggests a lower-energy solution with broken symmetry "
        "(e.g., an open-shell singlet) may exist."
    ),
    "orbital_occupation": (
        "Check that the HOMO-LUMO gap is positive (the HOMO energy is below "
        "the LUMO energy).  A negative or zero gap indicates the Aufbau "
        "occupation is violated, which can signal ground-state instability "
        "or an incorrect initial guess."
    ),
    "energy_consistency": (
        "For workflows with multiple related calculations, verify that "
        "energy ordering is physically consistent (e.g., triplet ≥ singlet "
        "for a closed-shell ground state, anion more stable than neutral "
        "for electron-attaching species, or optimization final energy ≤ "
        "initial energy)."
    ),
    "optimization_quality": (
        "Check that a geometry optimization converged and that the final "
        "gradient and step norms satisfy the convergence thresholds.  "
        "A poorly converged optimization gives geometries and energies "
        "that are not stationary points."
    ),
    "charge_spin_consistency": (
        "Verify that the combination of charge and spin multiplicity is "
        "consistent with the total number of electrons (parity check).  "
        "An even-electron system must have an odd multiplicity (singlet, "
        "triplet, quintet, …) and an odd-electron system must have an "
        "even multiplicity (doublet, quartet, …).  Mismatches produce "
        "unphysical wavefunctions."
    ),
}

# All check names in a stable order
_ALL_CHECKS: Tuple[str, ...] = tuple(_CHECK_DOCS.keys())


# ===================================================================
# ScientificValidator
# ===================================================================


class ScientificValidator:
    """Validate quantum chemistry calculation results for physical reasonableness.

    The validator runs a set of named checks against a ``ParsedResult`` (from
    ``output_parser``).  Each check inspects one aspect of the calculation —
    SCF convergence, energy magnitude, spin contamination, vibrational
    frequencies, etc. — and returns a ``ValidationCheck`` with a pass/fail
    outcome, a human-readable detail, and a severity level.

    Parameters
    ----------
    config : dict, optional
        A dictionary of configuration overrides.  Supported keys:

        - ``scf_energy_max_magnitude_ha`` (float): maximum allowed |SCF energy|
          before a warning (default 1e4).
        - ``spin_contamination_threshold_pct`` (float): max allowed deviation
          of <S²> from S(S+1), in percent (default 10.0).
        - ``imaginary_freq_warn_threshold_cm1`` (float): frequencies more
          negative than this are errors rather than warnings (default -100.0).
        - ``freq_min_cm1`` (float): lowest reasonable real frequency
          (default 0.0).
        - ``freq_max_cm1`` (float): highest reasonable real frequency for
          typical organic molecules (default 4000.0).
        - ``freq_max_extended_cm1`` (float): absolute ceiling before an error
          is raised (default 5000.0).
        - ``scf_min_cycles`` (int): minimum SCF iterations below which a
          warning is raised (default 3).
        - ``scf_max_cycles`` (int): maximum SCF iterations before a warning
          (default 200).
        - ``gradient_tolerance_au`` (float): max allowed gradient for an
          optimization to be considered converged (default 4.5e-4).
        - ``step_tolerance_au`` (float): max allowed step for an optimization
          (default 1.8e-3).

    Attributes
    ----------
    available_checks : Tuple[str, ...]
        Names of all checks that `validate` can run.
    """

    # ------------------------------------------------------------------
    # Default configuration
    # ------------------------------------------------------------------
    _DEFAULTS: Dict[str, Any] = {
        "scf_energy_max_magnitude_ha": 1e4,
        "spin_contamination_threshold_pct": 10.0,
        "imaginary_freq_warn_threshold_cm1": -100.0,
        "freq_min_cm1": 0.0,
        "freq_max_cm1": 4000.0,
        "freq_max_extended_cm1": 5000.0,
        "scf_min_cycles": 3,
        "scf_max_cycles": 200,
        "gradient_tolerance_au": 4.5e-4,
        "step_tolerance_au": 1.8e-3,
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self._config = dict(self._DEFAULTS)
        if config:
            self._config.update(config)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def available_checks(self) -> Tuple[str, ...]:
        """Return the names of all available validation checks."""
        return _ALL_CHECKS

    def validate(
        self,
        parsed_result: Any,
        checks: Optional[Sequence[str]] = None,
    ) -> List[ValidationCheck]:
        """Run scientific validation checks on a parsed REST result.

        Parameters
        ----------
        parsed_result : ParsedResult
            A parsed calculation result from ``output_parser.OutputParser``.
            Expected to expose attributes such as ``scf_energy``,
            ``scf_converged``, ``frequencies``, ``spin``, ``charge``, etc.
        checks : sequence of str, optional
            Names of checks to execute.  If ``None`` (default), all
            *applicable* checks are run — a check is skipped when the
            parsed result lacks the data it needs (e.g. ``imaginary_frequencies``
            is skipped when no frequency list is present).

        Returns
        -------
        List[ValidationCheck]
            One ``ValidationCheck`` per executed check, ordered by the
            check-name list.
        """
        names: Tuple[str, ...]
        if checks is None:
            names = _ALL_CHECKS
        else:
            names = tuple(checks)
            unknown = set(names) - set(_ALL_CHECKS)
            if unknown:
                raise ValueError(
                    f"Unknown check(s): {sorted(unknown)}. "
                    f"Available: {list(_ALL_CHECKS)}"
                )

        results: List[ValidationCheck] = []
        for name in names:
            method = getattr(self, f"_check_{name}", None)
            if method is None:
                # Should not happen given the guard above, but be defensive
                results.append(
                    ValidationCheck(
                        name=name,
                        passed=True,
                        detail=f"Check '{name}' is not implemented.",
                        severity="ok",
                    )
                )
                continue
            try:
                vc = method(parsed_result)
            except Exception as exc:
                vc = ValidationCheck(
                    name=name,
                    passed=False,
                    detail=f"Internal error while running check: {exc}",
                    severity="error",
                )
            results.append(vc)
        return results

    def validate_all(
        self, results_list: Sequence[Any]
    ) -> Dict[str, Any]:
        """Run all applicable checks on a sequence of parsed results and return
        an aggregate summary.

        Parameters
        ----------
        results_list : sequence of ParsedResult
            Parsed results from multiple calculations in a workflow (e.g.
            optimization → frequency → single-point).

        Returns
        -------
        dict
            A dictionary with keys:

            - ``"total_checks"`` (int): total number of checks executed.
            - ``"passed"`` (int): number of passing checks.
            - ``"warnings"`` (int): number of checks with severity ``"warning"``.
            - ``"errors"`` (int): number of checks with severity ``"error"``.
            - ``"by_check"`` (dict): ``{check_name: {"passed": int, "warning": int, "error": int}}``
            - ``"by_result"`` (list of dict): per-result breakdowns.
            - ``"overall"`` (str): ``"pass"``, ``"warning"``, or ``"error"``.
        """
        all_checks: List[ValidationCheck] = []
        per_result: List[Dict[str, Any]] = []

        for idx, res in enumerate(results_list):
            vcs = self.validate(res)
            all_checks.extend(vcs)
            per_result.append(
                {
                    "index": idx,
                    "system": getattr(res, "system_name", f"result_{idx}"),
                    "checks": [vc._asdict() for vc in vcs],  # type: ignore[attr-defined]
                    "num_passed": sum(1 for v in vcs if v.passed),
                    "num_warning": sum(1 for v in vcs if v.severity == "warning"),
                    "num_error": sum(1 for v in vcs if v.severity == "error"),
                }
            )

        by_check: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"passed": 0, "warning": 0, "error": 0}
        )
        for vc in all_checks:
            if vc.passed:
                by_check[vc.name]["passed"] += 1
            else:
                by_check[vc.name][vc.severity] += 1

        num_errors = sum(1 for v in all_checks if v.severity == "error" and not v.passed)
        num_warnings = sum(
            1 for v in all_checks if v.severity == "warning" and not v.passed
        )
        num_passed = sum(1 for v in all_checks if v.passed)

        if num_errors > 0:
            overall = "error"
        elif num_warnings > 0:
            overall = "warning"
        else:
            overall = "pass"

        return {
            "total_checks": len(all_checks),
            "passed": num_passed,
            "warnings": num_warnings,
            "errors": num_errors,
            "by_check": dict(by_check),
            "by_result": per_result,
            "overall": overall,
        }

    def recommendation(self, check_results: Sequence[ValidationCheck]) -> str:
        """Generate human-readable recommendations based on failed checks.

        Parameters
        ----------
        check_results : sequence of ValidationCheck
            The results returned by :meth:`validate` or :meth:`validate_all`
            (in the latter case, concatenate ``by_result[*]["checks"]`` or
            use the raw list).

        Returns
        -------
        str
            A multi-line summary of actionable recommendations, or a short
            message stating that all checks passed.
        """
        failed = [vc for vc in check_results if not vc.passed]
        if not failed:
            return "All scientific validation checks passed. The results appear physically reasonable."

        lines: List[str] = []
        lines.append(f"=== Scientific Validation: {len(failed)} issue(s) found ===\n")

        # Group by severity
        errors = [vc for vc in failed if vc.severity == "error"]
        warnings = [vc for vc in failed if vc.severity == "warning"]

        advice_map: Dict[str, str] = {
            "scf_convergence": (
                "→ SCF did not converge.  Try: (1) use a different initial guess "
                "(2) switch to a smaller basis set for the initial guess "
                "(3) enable level-shifting or smearing "
                "(4) use a more robust SCF algorithm (ADIIS+DIIS)."
            ),
            "scf_energy_magnitude": (
                "→ SCF energy is outside the physically reasonable range.  "
                "Verify the molecular charge and spin multiplicity.  A positive "
                "energy for a neutral molecule suggests an incorrect electron count."
            ),
            "spin_contamination": (
                "→ Significant spin contamination detected.  Consider: "
                "(1) using a restricted open-shell (ROHF/ROKS) formalism if available "
                "(2) spin-annihilation of the UHF/UKS wavefunction "
                "(3) switching to a functional with lower self-interaction error "
                "(e.g. a range-separated or double-hybrid functional)."
            ),
            "imaginary_frequencies": (
                "→ Imaginary frequencies indicate the geometry is NOT a minimum.  "
                "Action: (1) visualize the imaginary mode(s) to identify the softer "
                "degree of freedom (2) displace the geometry along the mode and "
                "re-optimize (3) tighten the optimization convergence criteria "
                "(4) ensure the integration grid is sufficiently fine."
            ),
            "frequency_range": (
                "→ Vibrational frequencies are outside the typical chemical range.  "
                "Check: (1) is the molecule linear?  If so, ensure the Hessian "
                "handles the correct number of vibrational degrees of freedom "
                "(2) inspect for numerical noise in very low-frequency modes "
                "(3) verify the coordinate system and unit conversion."
            ),
            "wavefunction_stability": (
                "→ The wavefunction is unstable; a lower-energy broken-symmetry "
                "solution may exist.  Action: (1) re-run with a broken-symmetry "
                "initial guess (2) if the calculation supports it, follow the "
                "instability eigenvector to the lower solution (3) check whether "
                "an open-shell singlet or a different electronic state is expected."
            ),
            "orbital_occupation": (
                "→ HOMO-LUMO gap is non-positive, which suggests the Aufbau "
                "occupation is violated.  This can arise from: (1) a poor initial "
                "guess (2) near-degeneracies at the Fermi level (3) a genuine "
                "ground-state instability.  Try a different initial guess or "
                "enable fractional occupation / smearing."
            ),
            "energy_consistency": (
                "→ Energy ordering is inconsistent.  Verify that: "
                "(1) the multiplicities and charges are correct for each step "
                "(2) the same functional and basis were used throughout "
                "(3) geometries are comparable (optimized vs. single-point at "
                "the same structure) (4) the energy differences make physical "
                "sense for the chemical process."
            ),
            "optimization_quality": (
                "→ Geometry optimization did not reach a satisfactory stationary "
                "point.  Action: (1) restart the optimization from the last "
                "geometry (2) tighten convergence thresholds if needed "
                "(3) use a different coordinate system (redundant internal vs. "
                "Cartesian) (4) check for a shallow potential energy surface."
            ),
            "charge_spin_consistency": (
                "→ The charge and spin multiplicity are inconsistent with the "
                "electron count (parity mismatch).  Double-check: "
                "(1) the total number of electrons = sum(atomic numbers) - charge "
                "(2) multiplicity parity: even electron → odd multiplicity, "
                "odd electron → even multiplicity."
            ),
        }

        if errors:
            lines.append("❌ ERRORS (likely physically incorrect results):")
            for vc in errors:
                lines.append(f"  [{vc.name}] {vc.detail}")
                advice = advice_map.get(vc.name)
                if advice:
                    lines.append(f"    {advice}")
            lines.append("")

        if warnings:
            lines.append("⚠️  WARNINGS (review before relying on these results):")
            for vc in warnings:
                lines.append(f"  [{vc.name}] {vc.detail}")
                advice = advice_map.get(vc.name)
                if advice:
                    lines.append(f"    {advice}")
            lines.append("")

        lines.append(
            "Recommendation: address errors before using the results for "
            "further analysis.  Warnings should be reviewed but may be "
            "acceptable depending on the scientific context."
        )
        return "\n".join(lines)

    # ==================================================================
    # Individual check implementations
    # ==================================================================

    # -- helpers -------------------------------------------------------

    @staticmethod
    def _has_attr(obj: Any, *attrs: str) -> bool:
        """Return True if *obj* has all named attributes and they are not None."""
        for a in attrs:
            if not hasattr(obj, a) or getattr(obj, a, None) is None:
                return False
        return True

    @staticmethod
    def _get(obj: Any, attr: str, default: Any = None) -> Any:
        """Safely get an attribute, returning *default* if missing or None."""
        val = getattr(obj, attr, default)
        return val if val is not None else default

    @staticmethod
    def _method_is_unrestricted(method: Optional[str]) -> bool:
        """Return True if the method type string indicates unrestricted."""
        if method is None:
            return False
        return method.upper().startswith("U")

    @staticmethod
    def _method_is_wavefunction(method: Optional[str]) -> bool:
        """Return True if the method is wavefunction-based (HF, MP2, etc.)
        rather than DFT."""
        if method is None:
            return False
        upper = method.upper()
        # HF / UHF / RHF; MP2 might appear as RI-MP2, etc.
        return upper in ("HF", "RHF", "UHF", "ROHF") or "MP2" in upper

    # -- check: scf_convergence ---------------------------------------

    def _check_scf_convergence(self, r: Any) -> ValidationCheck:
        """Check that the SCF procedure converged.

        **Why it matters:**  A non-converged SCF means the electronic
        energy and wavefunction are not self-consistent solutions of the
        Kohn-Sham / Hartree-Fock equations.  Any property derived from them
        — total energy, dipole moment, forces, response properties — is
        unreliable and may be physically nonsensical.
        """
        name = "scf_convergence"

        # 1. explicit convergence flag
        if self._has_attr(r, "scf_converged"):
            if not r.scf_converged:
                return ValidationCheck(
                    name=name,
                    passed=False,
                    detail="SCF procedure did NOT converge. "
                    "Check the SCF convergence threshold and initial guess.",
                    severity="error",
                )

        # 2. check SCF iteration count for oddities
        if self._has_attr(r, "scf_cycles"):
            cycles: int = r.scf_cycles
            min_c = self._config["scf_min_cycles"]
            max_c = self._config["scf_max_cycles"]
            if cycles < min_c:
                return ValidationCheck(
                    name=name,
                    passed=False,
                    detail=(
                        f"SCF converged in only {cycles} iteration(s) "
                        f"(minimum expected: {min_c}).  This may indicate an "
                        "unrealistically easy convergence or a pre-converged "
                        "initial guess that masks a poor-quality wavefunction."
                    ),
                    severity="warning",
                )
            if cycles > max_c:
                return ValidationCheck(
                    name=name,
                    passed=False,
                    detail=(
                        f"SCF required {cycles} iterations "
                        f"(threshold: {max_c}).  The system may suffer from "
                        "near-degeneracies, a poor initial guess, or a "
                        "difficult electronic structure (e.g. transition metal)."
                    ),
                    severity="warning",
                )

        # 3. energy change magnitude (if available)
        if self._has_attr(r, "scf_energy_change", "scf_converged"):
            delta = abs(r.scf_energy_change)
            if delta > 1e-4:
                return ValidationCheck(
                    name=name,
                    passed=False,
                    detail=(
                        f"Final SCF energy change ({delta:.2e} Ha) is larger "
                        "than 1e-4 Ha.  The SCF may not be tightly converged."
                    ),
                    severity="warning",
                )

        # 4. If none of the signals are available, skip
        if not self._has_attr(r, "scf_converged") and not self._has_attr(r, "scf_cycles"):
            return ValidationCheck(
                name=name,
                passed=True,
                detail="SCF convergence data not available — check skipped.",
                severity="ok",
            )

        return ValidationCheck(
            name=name,
            passed=True,
            detail="SCF procedure converged with a reasonable iteration count.",
            severity="ok",
        )

    # -- check: scf_energy_magnitude ----------------------------------

    def _check_scf_energy_magnitude(self, r: Any) -> ValidationCheck:
        """Check that the total SCF energy is in a physically reasonable range.

        **Why it matters:**  Total SCF energies for real molecules are
        always negative (bound) and scale with system size.  A NaN value
        signals a catastrophic numerical failure.  A positive energy for a
        neutral molecule almost always means an incorrect charge or spin
        multiplicity was supplied.  An absurdly large magnitude (|E| > 1e4 Ha
        for typical systems) may indicate a unit-conversion error or a
        pathological geometry with near-overlapping atoms.
        """
        name = "scf_energy_magnitude"

        if not self._has_attr(r, "scf_energy"):
            return ValidationCheck(
                name=name,
                passed=True,
                detail="SCF energy not available — check skipped.",
                severity="ok",
            )

        energy: float = r.scf_energy
        max_mag = self._config["scf_energy_max_magnitude_ha"]

        # --- NaN ---
        if math.isnan(energy):
            return ValidationCheck(
                name=name,
                passed=False,
                detail="SCF energy is NaN — the calculation failed numerically.",
                severity="error",
            )

        # --- Absurd magnitude ---
        if abs(energy) > max_mag:
            return ValidationCheck(
                name=name,
                passed=False,
                detail=(
                    f"SCF energy ({energy:.6f} Ha) has an implausible magnitude "
                    f"(> {max_mag} Ha).  Check the geometry for overlapping atoms "
                    "and verify the unit conversion."
                ),
                severity="error",
            )

        # --- Positive for neutral ---
        charge: Optional[int] = self._get(r, "charge")
        if charge is not None and charge == 0 and energy > 0.0:
            return ValidationCheck(
                name=name,
                passed=False,
                detail=(
                    f"SCF energy ({energy:.6f} Ha) is positive for a neutral "
                    "molecule.  This strongly suggests an incorrect charge or "
                    "spin multiplicity."
                ),
                severity="error",
            )

        # --- Near-zero ---
        if abs(energy) < 1e-6:
            return ValidationCheck(
                name=name,
                passed=False,
                detail=(
                    f"SCF energy ({energy:.6e} Ha) is suspiciously close to "
                    "zero.  The calculation may have produced only the nuclear "
                    "repulsion or may have terminated early."
                ),
                severity="warning",
            )

        return ValidationCheck(
            name=name,
            passed=True,
            detail=(
                f"SCF energy ({energy:.10f} Ha) is in a physically "
                "reasonable range."
            ),
            severity="ok",
        )

    # -- check: spin_contamination ------------------------------------

    def _check_spin_contamination(self, r: Any) -> ValidationCheck:
        """Check spin contamination for unrestricted calculations.

        **Why it matters:**  Unrestricted wavefunctions (UHF, UKS) are not
        eigenfunctions of the total spin operator S².  The deviation of the
        computed <S²> from the ideal S(S+1) is called *spin contamination*.
        Heavy contamination (>10%) introduces errors in geometries
        (bond lengths too long), vibrational frequencies (too soft), and
        energy barriers (too low).  It is especially common in open-shell
        organic radicals and transition-metal systems.

        For restricted (RHF, RKS) calculations this check always passes
        because the wavefunction is a spin eigenfunction by construction.
        """
        name = "spin_contamination"

        method: Optional[str] = self._get(r, "method_type")
        if not self._method_is_unrestricted(method):
            return ValidationCheck(
                name=name,
                passed=True,
                detail=(
                    "Not an unrestricted calculation "
                    f"(method={method or 'unknown'}) — check skipped."
                ),
                severity="ok",
            )

        # Need S² actual and expected
        s2_actual = self._get(r, "s2_actual")
        s2_expected = self._get(r, "s2_expected")

        if s2_actual is None or s2_expected is None:
            return ValidationCheck(
                name=name,
                passed=False,
                detail=(
                    "Cannot check spin contamination: <S²> values not found in "
                    "the parsed output.  The REST output parsing may be incomplete."
                ),
                severity="warning",
            )

        if s2_expected == 0.0:
            # Unrestricted singlet — special case
            deviation = s2_actual
            if deviation < 0.1:
                return ValidationCheck(
                    name=name,
                    passed=True,
                    detail=(
                        f"<S²> = {s2_actual:.4f} (expected 0.0 for singlet).  "
                        "Negligible spin contamination."
                    ),
                    severity="ok",
                )
            return ValidationCheck(
                name=name,
                passed=False,
                detail=(
                    f"<S²> = {s2_actual:.4f} (expected 0.0).  "
                    "Unrestricted singlet shows significant spin contamination "
                    "— consider a restricted formalism or a broken-symmetry approach."
                ),
                severity="error",
            )

        diff = abs(s2_actual - s2_expected)
        pct = (diff / s2_expected) * 100.0
        threshold = self._config["spin_contamination_threshold_pct"]

        if pct <= threshold:
            return ValidationCheck(
                name=name,
                passed=True,
                detail=(
                    f"<S²> = {s2_actual:.4f} (expected {s2_expected:.4f}).  "
                    f"Deviation {pct:.1f}% ≤ {threshold:.0f}% — acceptable."
                ),
                severity="ok",
            )
        elif pct <= threshold * 2:
            return ValidationCheck(
                name=name,
                passed=False,
                detail=(
                    f"<S²> = {s2_actual:.4f} (expected {s2_expected:.4f}).  "
                    f"Deviation {pct:.1f}% — moderate spin contamination.  "
                    "Review the results with caution."
                ),
                severity="warning",
            )
        else:
            return ValidationCheck(
                name=name,
                passed=False,
                detail=(
                    f"<S²> = {s2_actual:.4f} (expected {s2_expected:.4f}).  "
                    f"Deviation {pct:.1f}% — severe spin contamination.  "
                    "Results are unreliable; consider ROHF/ROKS or a different "
                    "functional."
                ),
                severity="error",
            )

    # -- check: imaginary_frequencies ---------------------------------

    def _check_imaginary_frequencies(self, r: Any) -> ValidationCheck:
        """Check for imaginary (negative) vibrational frequencies.

        **Why it matters:**  For a true minimum on the potential energy
        surface (PES), all vibrational frequencies must be real (positive).
        Imaginary frequencies mean the Hessian has negative curvature along
        one or more normal modes — the geometry lies on a saddle point
        rather than a minimum.

        - 0 imaginary modes: the geometry is a confirmed minimum.
        - 1 small imaginary mode (e.g. > −100 cm⁻¹): may be a transition
          state or a numerical artifact; warrants inspection.
        - Multiple or large imaginary modes: the geometry is not a minimum
          and must be re-optimized.

        Note:  For transition-state searches, one imaginary frequency is
        expected — this check should be skipped in that context.
        """
        name = "imaginary_frequencies"

        freqs = self._get(r, "frequencies")
        if freqs is None or (hasattr(freqs, "__len__") and len(freqs) == 0):
            return ValidationCheck(
                name=name,
                passed=True,
                detail="No frequency data available — check skipped.",
                severity="ok",
            )

        if not isinstance(freqs, (list, tuple)):
            freqs = list(freqs)

        imag = [f for f in freqs if f < 0.0]
        if not imag:
            return ValidationCheck(
                name=name,
                passed=True,
                detail=(
                    f"All {len(freqs)} vibrational frequencies are real — "
                    "geometry is a confirmed minimum."
                ),
                severity="ok",
            )

        warn_thresh = self._config["imaginary_freq_warn_threshold_cm1"]
        imag_sorted = sorted(imag)

        if len(imag) == 1 and imag_sorted[0] >= warn_thresh:
            return ValidationCheck(
                name=name,
                passed=False,
                detail=(
                    f"1 small imaginary frequency ({imag_sorted[0]:.2f} cm⁻¹).  "
                    "This may be a transition state or numerical noise.  "
                    "Displace and re-optimize if a minimum is required."
                ),
                severity="warning",
            )

        largest = imag_sorted[0]  # most negative
        return ValidationCheck(
            name=name,
            passed=False,
            detail=(
                f"{len(imag)} imaginary frequency/frequencies found "
                f"(largest: {largest:.2f} cm⁻¹).  "
                "The geometry is NOT a minimum on the PES.  Re-optimize."
            ),
            severity="error",
        )

    # -- check: frequency_range ---------------------------------------

    def _check_frequency_range(self, r: Any) -> ValidationCheck:
        """Check that vibrational frequencies lie in the physically
        reasonable range for molecular vibrations.

        **Why it matters:**  Molecular vibrational frequencies for organic
        systems typically range from ~0 cm⁻¹ (translations/rotations of the
        whole molecule) to ~4000 cm⁻¹ (X–H stretches).  Frequencies far
        outside this range indicate:

        - All frequencies near zero: the molecule may be linear, and the
          Hessian may not have correctly identified the rotational degrees
          of freedom.
        - Extremely high frequencies (>5000 cm⁻¹): likely a numerical
          artifact from a poorly converged Hessian, a faulty geometry, or
          a unit-conversion error.
        """
        name = "frequency_range"

        freqs = self._get(r, "frequencies")
        if freqs is None or (hasattr(freqs, "__len__") and len(freqs) == 0):
            return ValidationCheck(
                name=name,
                passed=True,
                detail="No frequency data available — check skipped.",
                severity="ok",
            )

        if not isinstance(freqs, (list, tuple)):
            freqs = list(freqs)

        # Filter to real, positive frequencies only (imaginary handled separately)
        real_freqs = [f for f in freqs if f >= 0.0]
        if not real_freqs:
            return ValidationCheck(
                name=name,
                passed=True,
                detail="No real (positive) frequencies to check — skipping range check.",
                severity="ok",
            )

        max_freq = max(real_freqs)
        min_freq = min(real_freqs)
        min_ok = self._config["freq_min_cm1"]
        max_ok = self._config["freq_max_cm1"]
        max_ext = self._config["freq_max_extended_cm1"]

        issues: List[str] = []

        # All frequencies suspiciously close to zero
        if max_freq < 10.0:
            issues.append(
                "All real frequencies are < 10 cm⁻¹.  "
                "If the molecule is linear, the Hessian processing may not have "
                "correctly subtracted rotational degrees of freedom."
            )

        # Very high frequencies
        if max_freq > max_ok:
            if max_freq > max_ext:
                issues.append(
                    f"Maximum frequency ({max_freq:.2f} cm⁻¹) is far above the "
                    f"extended limit ({max_ext:.0f} cm⁻¹).  Likely a numerical "
                    "artifact — check geometry and Hessian."
                )
            else:
                issues.append(
                    f"Maximum frequency ({max_freq:.2f} cm⁻¹) is above the "
                    f"typical organic range ({max_ok:.0f} cm⁻¹).  This may be "
                    "acceptable for X–H stretches in very light atoms, but "
                    "verify the value."
                )

        # Very low (non-zero) real frequencies for non-linear:
        # this is common (soft modes) and not necessarily an error,
        # but flag if all are < 1 cm⁻¹
        if max_freq < 1.0 and len(real_freqs) > 0:
            issues.append(
                f"All real frequencies are < 1 cm⁻¹ ({min_freq:.4f}–{max_freq:.4f}).  "
                "This may indicate a near-zero-gradient issue or a flat PES."
            )

        if issues:
            severity = "error" if max_freq > max_ext else "warning"
            return ValidationCheck(
                name=name,
                passed=False,
                detail=" | ".join(issues),
                severity=severity,
            )

        return ValidationCheck(
            name=name,
            passed=True,
            detail=(
                f"Real frequencies range from {min_freq:.2f} to "
                f"{max_freq:.2f} cm⁻¹ — within the typical 0–{max_ok:.0f} cm⁻¹ range."
            ),
            severity="ok",
        )

    # -- check: wavefunction_stability --------------------------------

    def _check_wavefunction_stability(self, r: Any) -> ValidationCheck:
        """Check the result of a wavefunction stability analysis.

        **Why it matters:**  The SCF procedure finds a *stationary point* of
        the energy functional, but not necessarily the global minimum.  A
        stability analysis tests whether the converged wavefunction is
        stable against symmetry-breaking perturbations (e.g. → broken-
        symmetry open-shell singlet).  If unstable, a lower-energy solution
        exists and the computed properties may be qualitatively wrong.

        If stability analysis was not requested in the calculation, this
        check is skipped with a neutral ``"ok"`` severity.
        """
        name = "wavefunction_stability"

        checked: Optional[bool] = self._get(r, "stability_checked")
        if checked is None or not checked:
            return ValidationCheck(
                name=name,
                passed=True,
                detail=(
                    "Wavefunction stability analysis was not performed "
                    "— check skipped.  Consider enabling it for open-shell "
                    "or near-degenerate systems."
                ),
                severity="ok",
            )

        stable: Optional[bool] = self._get(r, "stability_stable")
        if stable is None:
            return ValidationCheck(
                name=name,
                passed=False,
                detail="Stability analysis was run but the result could not be parsed.",
                severity="warning",
            )

        if stable:
            return ValidationCheck(
                name=name,
                passed=True,
                detail="Wavefunction is stable against symmetry-breaking perturbations.",
                severity="ok",
            )
        else:
            return ValidationCheck(
                name=name,
                passed=False,
                detail=(
                    "Wavefunction is UNSTABLE — a lower-energy broken-symmetry "
                    "solution exists.  Follow the instability eigenvector to "
                    "the lower state or consider an open-shell singlet."
                ),
                severity="error",
            )

    # -- check: orbital_occupation ------------------------------------

    def _check_orbital_occupation(self, r: Any) -> ValidationCheck:
        """Check that the HOMO-LUMO gap is positive.

        **Why it matters:**  In the ground-state Aufbau principle, all
        occupied orbitals have lower energy than all virtual orbitals.
        The HOMO-LUMO gap is:

            gap = ε_LUMO − ε_HOMO

        A positive gap confirms the expected electronic configuration.
        A zero or negative gap indicates that the ground-state occupation
        is not Aufbau — the system may have an open-shell ground state,
        a near-degeneracy, or a poor initial guess.  A negative gap is
        a sign of ground-state instability.
        """
        name = "orbital_occupation"

        homo = self._get(r, "homo_energy")
        lumo = self._get(r, "lumo_energy")

        if homo is None or lumo is None:
            return ValidationCheck(
                name=name,
                passed=True,
                detail="HOMO/LUMO energies not available — check skipped.",
                severity="ok",
            )

        gap = lumo - homo

        if gap > 0.0:
            return ValidationCheck(
                name=name,
                passed=True,
                detail=(
                    f"HOMO-LUMO gap = {gap:.4f} Ha ({gap * 27.2114:.3f} eV) — "
                    "Aufbau occupation confirmed."
                ),
                severity="ok",
            )
        elif gap == 0.0:
            return ValidationCheck(
                name=name,
                passed=False,
                detail=(
                    "HOMO-LUMO gap is zero.  The system may have degenerate "
                    "frontier orbitals (e.g. open-shell ground state).  "
                    "Verify the occupation."
                ),
                severity="warning",
            )
        else:
            return ValidationCheck(
                name=name,
                passed=False,
                detail=(
                    f"HOMO-LUMO gap = {gap:.4f} Ha ({gap * 27.2114:.3f} eV) — "
                    "negative gap!  The ground-state occupation violates the "
                    "Aufbau principle.  Check for ground-state instability or "
                    "an incorrect initial guess."
                ),
                severity="error",
            )

    # -- check: optimization_quality ----------------------------------

    def _check_optimization_quality(self, r: Any) -> ValidationCheck:
        """Check the quality of a geometry optimization.

        **Why it matters:**  A geometry optimization must converge to a
        stationary point where the energy gradient is (near) zero and the
        displacement step is below the convergence threshold.  A poorly
        converged optimization means the reported geometry and energy are
        not reliable — subsequent single-point, frequency, or response
        calculations at that geometry will inherit the error.

        This check examines:
        - The explicit ``opt_converged`` flag (if available).
        - Maximum gradient norm (should be ≤ ~4.5 × 10⁻⁴ Ha/bohr).
        - RMS gradient norm.
        - Maximum displacement step (should be ≤ ~1.8 × 10⁻³ bohr).
        - RMS displacement step.
        """
        name = "optimization_quality"

        # If there's no optimization data at all, skip
        has_opt_data = any(
            self._has_attr(r, a)
            for a in (
                "opt_converged",
                "max_gradient",
                "rms_gradient",
                "max_step",
                "rms_step",
            )
        )
        if not has_opt_data:
            return ValidationCheck(
                name=name,
                passed=True,
                detail="No optimization data available — check skipped.",
                severity="ok",
            )

        issues: List[str] = []
        severity: str = "ok"

        # --- convergence flag ---
        if self._has_attr(r, "opt_converged"):
            if not r.opt_converged:
                issues.append("Optimization did NOT converge.")
                severity = "error"

        grad_tol = self._config["gradient_tolerance_au"]
        step_tol = self._config["step_tolerance_au"]

        # --- max gradient ---
        max_g = self._get(r, "max_gradient")
        if max_g is not None:
            if max_g > grad_tol * 10:
                issues.append(
                    f"Maximum gradient ({max_g:.2e}) is far above the "
                    f"convergence threshold ({grad_tol:.2e})."
                )
                severity = "error"
            elif max_g > grad_tol:
                issues.append(
                    f"Maximum gradient ({max_g:.2e}) slightly exceeds the "
                    f"threshold ({grad_tol:.2e})."
                )
                if severity == "ok":
                    severity = "warning"

        # --- rms gradient ---
        rms_g = self._get(r, "rms_gradient")
        if rms_g is not None:
            rms_g_tol = grad_tol / 3.0 if grad_tol > 0 else 1.5e-4
            if rms_g > rms_g_tol * 10:
                issues.append(
                    f"RMS gradient ({rms_g:.2e}) is far above the "
                    f"expected threshold (~{rms_g_tol:.2e})."
                )
                if severity == "ok":
                    severity = "error"

        # --- max step ---
        max_s = self._get(r, "max_step")
        if max_s is not None:
            if max_s > step_tol * 10:
                issues.append(
                    f"Maximum displacement ({max_s:.2e}) is far above the "
                    f"threshold ({step_tol:.2e})."
                )
                if severity == "ok":
                    severity = "error"
            elif max_s > step_tol:
                issues.append(
                    f"Maximum displacement ({max_s:.2e}) slightly exceeds the "
                    f"threshold ({step_tol:.2e})."
                )
                if severity == "ok":
                    severity = "warning"

        # --- rms step ---
        rms_s = self._get(r, "rms_step")
        if rms_s is not None:
            rms_s_tol = step_tol / 3.0 if step_tol > 0 else 6.0e-4
            if rms_s > rms_s_tol * 10:
                issues.append(
                    f"RMS displacement ({rms_s:.2e}) is far above the "
                    f"expected threshold (~{rms_s_tol:.2e})."
                )
                if severity == "ok":
                    severity = "error"

        if not issues:
            return ValidationCheck(
                name=name,
                passed=True,
                detail="Geometry optimization converged within all thresholds.",
                severity="ok",
            )

        return ValidationCheck(
            name=name,
            passed=(severity != "error"),
            detail=" | ".join(issues),
            severity=severity,
        )

    # -- check: energy_consistency ------------------------------------

    def _check_energy_consistency(self, r: Any) -> ValidationCheck:
        """Check energy consistency for multi-step workflows.

        **Why it matters:**  In a multi-step workflow (e.g. optimization →
        frequency → single-point), certain energy relationships must hold
        for physical consistency:

        - The final energy of an optimization should be ≤ the initial energy
          (energy should go down during minimization).
        - For a closed-shell singlet ground state, the triplet single-point
          energy at the same geometry should be ≥ the singlet energy.
        - An anion should be more stable (lower energy) than the neutral
          if the electron affinity is positive.

        This check relies on the parsed result carrying workflow context
        (previous energies, spin labels, etc.).  If no context is available
        the check is skipped.
        """
        name = "energy_consistency"

        # Look for workflow context
        has_context = any(
            self._has_attr(r, a)
            for a in ("initial_energy", "reference_energy", "comparison_energies")
        )
        if not has_context:
            return ValidationCheck(
                name=name,
                passed=True,
                detail="No multi-step workflow context available — check skipped.",
                severity="ok",
            )

        cur_energy = self._get(r, "scf_energy")
        issues: List[str] = []
        severity: str = "ok"

        # --- optimization: final ≤ initial ---
        init_e = self._get(r, "initial_energy")
        if init_e is not None and cur_energy is not None:
            if cur_energy > init_e + 1e-6:
                issues.append(
                    f"Optimization final energy ({cur_energy:.8f} Ha) is "
                    f"higher than the initial energy ({init_e:.8f} Ha).  "
                    "Energy should decrease during minimization."
                )
                severity = "error"

        # --- singlet/triplet ordering ---
        ref_e = self._get(r, "reference_energy")
        ref_label = self._get(r, "reference_label", "")
        if ref_e is not None and cur_energy is not None:
            # e.g. if reference is singlet and current is triplet at same geometry
            if "singlet" in str(ref_label).lower():
                cur_spin_label = self._get(r, "spin_label", "")
                if "triplet" in str(cur_spin_label).lower():
                    if cur_energy < ref_e - 1e-6:
                        issues.append(
                            f"Triplet energy ({cur_energy:.8f} Ha) is lower than "
                            f"singlet ({ref_e:.8f} Ha) at the same geometry.  "
                            "This suggests the ground state may actually be a triplet."
                        )
                        severity = "warning"

        # --- comparison energies (general) ---
        comparisons = self._get(r, "comparison_energies")
        if isinstance(comparisons, dict):
            for label, expected_relation in comparisons.items():
                comp_e = self._get(r, f"energy_{label}") if hasattr(r, f"energy_{label}") else None
                if comp_e is None:
                    comp_e = comparisons.get(label)
                if comp_e is not None and cur_energy is not None:
                    if expected_relation == "lower" and cur_energy >= comp_e:
                        issues.append(
                            f"Energy ({cur_energy:.8f} Ha) is not lower than "
                            f"{label} ({comp_e:.8f} Ha)."
                        )
                        severity = "warning"
                    elif expected_relation == "higher" and cur_energy <= comp_e:
                        issues.append(
                            f"Energy ({cur_energy:.8f} Ha) is not higher than "
                            f"{label} ({comp_e:.8f} Ha)."
                        )
                        severity = "warning"

        if not issues:
            return ValidationCheck(
                name=name,
                passed=True,
                detail="Energy consistency checks passed across workflow steps.",
                severity="ok",
            )

        return ValidationCheck(
            name=name,
            passed=(severity != "error"),
            detail=" | ".join(issues),
            severity=severity,
        )

    # -- check: charge_spin_consistency -------------------------------

    def _check_charge_spin_consistency(self, r: Any) -> ValidationCheck:
        """Verify that the charge and spin multiplicity are consistent with
        the total number of electrons.

        **Why it matters:**  The total number of electrons in a quantum
        chemistry calculation is:

            N_e = Σ Z_atom − charge

        The spin multiplicity (2S + 1) defines the total spin S, which
        determines the number of unpaired electrons (2S).  The parity rule
        is strict:

        - **Even N_e** → odd multiplicity (1, 3, 5, … — singlet, triplet, quintet, …)
        - **Odd N_e** → even multiplicity (2, 4, 6, … — doublet, quartet, sextet, …)

        Violating this rule produces a wavefunction that does not correspond
        to a physically realizable spin state.
        """
        name = "charge_spin_consistency"

        charge: Optional[int] = self._get(r, "charge")
        spin: Optional[int] = self._get(r, "spin")

        if charge is None or spin is None:
            return ValidationCheck(
                name=name,
                passed=True,
                detail="Charge or spin not available — check skipped.",
                severity="ok",
            )

        if spin < 1:
            return ValidationCheck(
                name=name,
                passed=False,
                detail=f"Spin multiplicity ({spin}) must be ≥ 1.",
                severity="error",
            )

        # Determine N_e
        num_electrons: Optional[int] = self._get(r, "num_electrons")
        if num_electrons is None:
            # Try to derive from atomic numbers
            atomic_numbers: Optional[List[int]] = self._get(r, "atomic_numbers")
            if atomic_numbers is not None:
                num_electrons = sum(atomic_numbers) - charge
            else:
                return ValidationCheck(
                    name=name,
                    passed=True,
                    detail=(
                        "Cannot determine total electron count — check skipped.  "
                        "Provide either `num_electrons` or `atomic_numbers` in "
                        "the parsed result."
                    ),
                    severity="ok",
                )

        is_even = (num_electrons % 2 == 0)
        multiplicity_is_odd = (spin % 2 == 1)

        if is_even and not multiplicity_is_odd:
            return ValidationCheck(
                name=name,
                passed=False,
                detail=(
                    f"Parity mismatch: {num_electrons} electrons (even) but spin "
                    f"multiplicity = {spin} (even).  Even-electron systems must "
                    "have an odd multiplicity (1, 3, 5, …)."
                ),
                severity="error",
            )
        elif not is_even and multiplicity_is_odd:
            return ValidationCheck(
                name=name,
                passed=False,
                detail=(
                    f"Parity mismatch: {num_electrons} electrons (odd) but spin "
                    f"multiplicity = {spin} (odd).  Odd-electron systems must "
                    "have an even multiplicity (2, 4, 6, …)."
                ),
                severity="error",
            )

        # Extra: check that multiplicity does not exceed N_e + 1
        if spin > num_electrons + 1:
            return ValidationCheck(
                name=name,
                passed=False,
                detail=(
                    f"Spin multiplicity ({spin}) exceeds the maximum possible "
                    f"for {num_electrons} electrons ({num_electrons + 1})."
                ),
                severity="error",
            )

        return ValidationCheck(
            name=name,
            passed=True,
            detail=(
                f"Charge ({charge:+d}) and spin multiplicity ({spin}) are "
                f"consistent with {num_electrons} electrons."
            ),
            severity="ok",
        )