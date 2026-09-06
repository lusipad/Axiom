from __future__ import annotations

import copy
import unittest

from pydantic import ValidationError

from axiom.benchmark import benchmark_case_hash, cnc_benchmark_example, compare_cnc_exports


def request_payload():
    return cnc_benchmark_example().model_dump(mode="json", by_alias=True, exclude_none=True)


def bind_case(payload):
    for role in ("baseline", "candidate"):
        payload[role]["caseContentHash"] = benchmark_case_hash(payload["case"])


class CncBenchmarkTests(unittest.TestCase):
    def test_known_path_regression_is_localized_without_an_f4_solver(self):
        report = compare_cnc_exports(request_payload())
        self.assertEqual(report.outcome, "CandidateViolatesLimits")
        failure = next(c for c in report.candidate.checks if c.status == "Violated")
        self.assertEqual(failure.check_id, "sampled-path-deviation")
        self.assertAlmostEqual(failure.value, 0.08)
        self.assertEqual(failure.location.sample_index, 5)
        self.assertAlmostEqual(failure.location.t, 0.05)
        self.assertEqual(failure.location.reference_segment_index, 0)
        self.assertEqual(report.scope, "sampled-xyz-command")
        self.assertIn("continuous-inter-sample-constraints", report.unchecked_properties)

    def test_different_sample_counts_and_time_laws_can_be_compared(self):
        payload = request_payload()
        payload["candidate"]["samples"] = [
            {"sampleIndex": i, "t": i * 0.01, "positionMm": [i / 20, 0, 0]}
            for i in range(21)
        ]
        report = compare_cnc_exports(payload)
        self.assertEqual(report.outcome, "Regressed")
        duration = report.differences[0]
        self.assertAlmostEqual(duration.delta, 0.1)
        self.assertEqual(report.candidate.metrics["sampledPathDeviationMaxMm"].value, 0)

    def test_shortcut_is_detected_at_sampled_midpoint_of_l_shaped_path(self):
        payload = request_payload()
        payload["case"]["referencePath"] = [[0, 0, 0], [1, 0, 0], [1, 1, 0]]
        payload["candidate"]["samples"] = [
            {"sampleIndex": i, "t": i * 0.01, "positionMm": [i / 10, i / 10, 0]}
            for i in range(11)
        ]
        bind_case(payload)
        report = compare_cnc_exports(payload)
        self.assertAlmostEqual(report.candidate.metrics["sampledPathDeviationMaxMm"].value, 0.5)

    def test_finite_difference_velocity_uses_physical_units_and_locates_axis(self):
        payload = request_payload()
        payload["candidate"] = copy.deepcopy(payload["baseline"])
        payload["case"]["axisLimits"][0]["maximumVelocityMmS"] = 9
        bind_case(payload)
        report = compare_cnc_exports(payload)
        violation = next(c for c in report.candidate.checks if c.check_id == "X.discrete-velocity")
        self.assertEqual(violation.status, "Violated")
        self.assertAlmostEqual(violation.value, 10)
        self.assertEqual(violation.unit, "mm/s")
        self.assertEqual(violation.location.axis, "X")

    def test_repeated_reference_vertices_do_not_break_distance_computation(self):
        payload = request_payload()
        payload["case"]["referencePath"].insert(1, [0, 0, 0])
        bind_case(payload)
        report = compare_cnc_exports(payload)
        self.assertAlmostEqual(report.candidate.metrics["sampledPathDeviationMaxMm"].value, 0.08)

    def test_clock_hash_frame_and_units_cannot_be_silently_changed(self):
        for field, value in (("caseContentHash", "0" * 64), ("coordinateFrame", "machine"), ("unit", "inch"), ("samplePeriodSeconds", 0.02)):
            with self.subTest(field=field):
                payload = request_payload()
                payload["candidate"][field] = value
                with self.assertRaises(ValidationError):
                    compare_cnc_exports(payload)

    def test_missing_duplicate_and_reordered_samples_are_rejected(self):
        for change in ("missing", "duplicate", "clock"):
            with self.subTest(change=change):
                payload = request_payload()
                if change == "missing":
                    del payload["candidate"]["samples"][3]
                elif change == "duplicate":
                    payload["candidate"]["samples"][3]["sampleIndex"] = 2
                else:
                    payload["candidate"]["samples"][3]["t"] = 0.031
                with self.assertRaises(ValidationError):
                    compare_cnc_exports(payload)

    def test_non_numbers_non_finite_and_unknown_fields_are_rejected(self):
        for value in (True, "0.1", float("nan"), float("inf")):
            with self.subTest(value=value):
                payload = request_payload()
                payload["candidate"]["samples"][1]["positionMm"][0] = value
                with self.assertRaises(ValidationError):
                    compare_cnc_exports(payload)
        payload = request_payload()
        payload["candidate"]["velocityAlreadyCertified"] = True
        with self.assertRaises(ValidationError):
            compare_cnc_exports(payload)

    def test_too_few_samples_cannot_support_jerk_comparison(self):
        payload = request_payload()
        for role in ("baseline", "candidate"):
            payload[role]["samples"] = [
                {"sampleIndex": 0, "t": 0, "positionMm": [0, 0, 0]},
                {"sampleIndex": 1, "t": 0.01, "positionMm": [1, 0, 0]},
            ]
        report = compare_cnc_exports(payload)
        self.assertEqual(report.outcome, "Inconclusive")
        self.assertIsNone(report.candidate.metrics["discreteJerkMax"].value)
        self.assertEqual(next(c for c in report.candidate.checks if c.check_id == "X.discrete-jerk").status, "InsufficientSamples")

    def test_timing_requires_same_environment_and_measurement_method(self):
        payload = request_payload()
        payload["candidate"] = copy.deepcopy(payload["baseline"])
        payload["baseline"]["computation"] = {"elapsedSeconds": 0.01, "environmentId": "pc-A", "method": "single-thread-warmed-call"}
        payload["candidate"]["computation"] = {"elapsedSeconds": 0.001, "environmentId": "pc-B", "method": "single-thread-warmed-call"}
        report = compare_cnc_exports(payload)
        self.assertEqual(report.differences[-1].status, "NotComparable")
        self.assertIsNone(report.differences[-1].delta)
        self.assertEqual(report.outcome, "WithinTolerance")
        payload["candidate"]["computation"]["environmentId"] = "pc-A"
        report = compare_cnc_exports(payload)
        self.assertEqual(report.differences[-1].status, "Improved")
        self.assertIn("producer-reported", " ".join(report.reasons))

    def test_user_tolerance_and_tradeoffs_are_respected(self):
        payload = request_payload()
        payload["case"]["maximumPathDeviationMm"] = 0.1
        payload["case"]["comparisonTolerances"]["pathDeviationMm"] = 0.09
        bind_case(payload)
        self.assertEqual(compare_cnc_exports(payload).outcome, "WithinTolerance")
        payload["case"]["comparisonTolerances"]["pathDeviationMm"] = 0.01
        payload["baseline"]["computation"] = {"elapsedSeconds": 0.01, "environmentId": "pc", "method": "warm"}
        payload["candidate"]["computation"] = {"elapsedSeconds": 0.001, "environmentId": "pc", "method": "warm"}
        bind_case(payload)
        self.assertEqual(compare_cnc_exports(payload).outcome, "Tradeoff")

    def test_invalid_baseline_and_mixed_evidence_do_not_promote_candidate(self):
        payload = request_payload()
        payload["baseline"], payload["candidate"] = payload["candidate"], payload["baseline"]
        self.assertEqual(compare_cnc_exports(payload).outcome, "Inconclusive")
        payload["baseline"] = copy.deepcopy(payload["candidate"])
        payload["candidate"]["sourceKind"] = "algorithm-export"
        self.assertEqual(compare_cnc_exports(payload).outcome, "Inconclusive")

    def test_report_is_replayable_and_exports_are_not_mutated(self):
        payload = request_payload()
        original = copy.deepcopy(payload)
        first = compare_cnc_exports(payload)
        second = compare_cnc_exports(payload)
        self.assertEqual(first, second)
        self.assertEqual(payload, original)
        payload["candidate"]["algorithmVersion"] = "new-build"
        self.assertNotEqual(first.report_content_hash, compare_cnc_exports(payload).report_content_hash)

    def test_case_identity_normalizes_schema_numbers_without_lossy_rounding(self):
        payload = request_payload()
        case = payload["case"]
        initial = benchmark_case_hash(case)
        case["referencePath"][0][0] = 0.0
        self.assertEqual(initial, benchmark_case_hash(case))
        case["referencePath"][1][0] += 1e-12
        self.assertNotEqual(initial, benchmark_case_hash(case))


if __name__ == "__main__":
    unittest.main()
