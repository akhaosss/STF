import json
import os
import tempfile
import unittest

from traffic_light_1d import (
    SIGNAL_CASES,
    canonical_hash,
    file_sha256,
    generate_signal_case_matrix,
    load_existing_result_records,
    update_matrix_manifest,
    validate_signal_matrix,
    write_result_artifacts,
)


class TrafficLight1DHelpersTest(unittest.TestCase):
    def test_matrix_is_deterministic_and_covers_both_cases(self):
        first, first_seed = generate_signal_case_matrix(41798, "Town:route:left")
        second, second_seed = generate_signal_case_matrix(41798, "Town:route:left")
        self.assertEqual(first, second)
        self.assertEqual(first_seed, second_seed)
        self.assertEqual(len(first), 3)
        self.assertEqual(set(first), set(SIGNAL_CASES))

    def test_matrix_changes_with_route_key(self):
        _, first_seed = generate_signal_case_matrix(41798, "route-a")
        _, second_seed = generate_signal_case_matrix(41798, "route-b")
        self.assertNotEqual(first_seed, second_seed)

    def test_canonical_hash_ignores_dictionary_order(self):
        self.assertEqual(canonical_hash({"a": 1, "b": 2}), canonical_hash({"b": 2, "a": 1}))

    def test_file_hash_is_stable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "checkpoint.bin")
            with open(path, "wb") as stream:
                stream.write(b"model")
            self.assertEqual(file_sha256(path), file_sha256(path))
            self.assertIsNone(file_sha256(os.path.join(directory, "missing")))

    def test_manifest_merges_entries_without_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            update_matrix_manifest(directory, [{"file": "b.json", "trial_index": 2}], 9)
            path = update_matrix_manifest(directory, [
                {"file": "a.json", "trial_index": 1},
                {"file": "b.json", "trial_index": 22},
            ], 9)
            with open(path, "r", encoding="utf-8") as stream:
                manifest = json.load(stream)
            self.assertEqual([item["file"] for item in manifest["entries"]], ["a.json", "b.json"])
            self.assertEqual(manifest["entries"][1]["trial_index"], 22)

    def test_result_writer_creates_all_formats(self):
        records = [{
            "scenario": "scenario_1d_0000_left_trial_01_turn_red",
            "matrix_id": "abc",
            "maneuver": "left",
            "trial_index": 1,
            "signal_case": "turn_red",
            "route_fingerprint": "fingerprint",
            "collision": False,
            "route_complete": True,
            "pass": True,
            "failure_reasons": [],
        }]
        with tempfile.TemporaryDirectory() as directory:
            paths = write_result_artifacts(records, directory, "1d", {"town": "Town03"})
            for path in paths.values():
                self.assertTrue(os.path.exists(path), path)
            with open(paths["markdown"], "r", encoding="utf-8") as stream:
                report = stream.read()
            self.assertIn("机动车信号灯（1.d）测试结果", report)
            self.assertIn("scenario_1d_0000_left", report)
            loaded = load_existing_result_records(directory, "1d")
            self.assertEqual(loaded[0]["matrix_id"], "abc")

    def test_matrix_validator_accepts_complete_route(self):
        configs = [
            {
                "maneuver": "left",
                "signal_case": case,
                "reproducibility": {
                    "route_fingerprint": "fingerprint",
                    "trial_index": index,
                    "matrix_seed": 42,
                },
            }
            for index, case in enumerate(("keep_green", "turn_red", "keep_green"), 1)
        ]
        summary = validate_signal_matrix(configs, require_all_maneuvers=False)
        self.assertEqual(summary["trial_count"], 3)
        with self.assertRaises(ValueError):
            validate_signal_matrix(configs[:2], require_all_maneuvers=False)


if __name__ == "__main__":
    unittest.main()
