import copy
import gzip
import json
import os
import tempfile
import unittest

from roundabout_2b import (
    SCHEMA_VERSION,
    STANDARD_TARGET_SPEED_KMH,
    aggregate_three_trial_verdict,
    canonical_hash,
    decode_vehicle_action,
    gate_crossing,
    gate_signed_distance,
    generate_roundabout_trial_matrix,
    load_existing_roundabout_records,
    roundabout_condition_payload,
    roundabout_record_summary,
    roundabout_route_fingerprint,
    roundabout_config_errors,
    required_vt1_initial_upstream_distance,
    roundabout_conflict_sync_distances,
    route_crosses_gate,
    update_roundabout_manifest,
    validate_roundabout_config,
    validate_roundabout_matrix,
    validate_route,
    write_roundabout_result_artifacts,
)


def vertical_gate(x, half_width=2.0, road_id=None, lane_id=None):
    gate = {
        "left": {"x": x, "y": half_width},
        "right": {"x": x, "y": -half_width},
        "forward": {"x": 1.0, "y": 0.0},
    }
    if road_id is not None and lane_id is not None:
        gate.update({
            "road_id": int(road_id), "section_id": 0, "lane_id": int(lane_id),
            "allowed_lanes": [{
                "road_id": int(road_id), "section_id": 0, "lane_id": int(lane_id),
            }],
        })
    return gate


def valid_config():
    geometry = {
        "ego_route": [{"x": -5, "y": 0}, {"x": 0, "y": 0}, {"x": 20, "y": 0}],
        "vt1_route": [{"x": 2, "y": 0.5}, {"x": 10, "y": 0.5}],
        "entry_gate": vertical_gate(0, road_id=1, lane_id=-1),
        "exit_gates": {
            str(index): vertical_gate(index * 10, road_id=index, lane_id=1)
            for index in (1, 2, 3)},
    }
    config = {
        "name": "scenario_2b_0000_trial_01",
        "ego_start": {"x": -5, "y": 0, "z": 0, "yaw": 0},
        "ego_route": geometry["ego_route"],
        "weather": {"cloudiness": 0.0},
        "extra_outer_field": "allowed",
        "other_actors": {
            "center": [
                {
                    "role": "vt1",
                    "model": "vehicle.tesla.model3",
                    "transform": {"x": 2, "y": 0.5, "z": 0, "yaw": 0},
                    "route": geometry["vt1_route"],
                    "motion": "route_follow",
                    "autopilot": False,
                },
                {
                    "role": "vt2",
                    "model": "vehicle.tesla.model3",
                    "transform": {"x": 5, "y": 0, "yaw": 0},
                    "route": [],
                    "motion": "stationary",
                    "autopilot": False,
                },
            ],
        },
        "roundabout_test": {
            "schema_version": SCHEMA_VERSION,
            "planned_exit": 2,
            "topology": {
                "verified": True,
                "arm_count": 3,
                "arms": [
                    {
                        "arm_id": "arm-{}".format(index),
                        "inbound_lane_count": 1,
                        "outbound_lane_count": 1,
                        "inbound_lanes": [{
                            "road_id": index,
                            "section_id": 0,
                            "lane_id": -1,
                        }],
                        "outbound_lanes": [{
                            "road_id": index,
                            "section_id": 0,
                            "lane_id": 1,
                        }],
                    }
                    for index in range(1, 4)
                ],
                "vut_entry_arm_id": "arm-1",
                "downstream_entry_arm_id": "arm-2",
                "exit_arm_ids": {
                    "1": "arm-1", "2": "arm-2", "3": "arm-3",
                },
                "circulation_order": ["arm-1", "arm-2", "arm-3"],
                "road_ids": [1, 2, 3],
                "operator_confirmation": {
                    "confirmed": True,
                    "method": "test_fixture",
                },
            },
            "entry_gate": geometry["entry_gate"],
            "exit_gates": geometry["exit_gates"],
            "downstream_entry": dict(
                vertical_gate(5),
                arm_id="arm-2",
                inbound_lanes=[{
                    "road_id": 2,
                    "section_id": 0,
                    "lane_id": -1,
                }],
            ),
            "roundabout_capable": True,
            "vut": {
                "role": "vut",
                "route": copy.deepcopy(geometry["ego_route"]),
            },
            "vt1": {
                "route": geometry["vt1_route"],
                "target_speed_kmh": STANDARD_TARGET_SPEED_KMH,
                "controller_extension": {"allowed": True},
            },
            "vt2": {
                "motion": "stationary",
                "transform": {"x": 5, "y": 0, "yaw": 0},
                "arm_id": "arm-2",
                "road_id": 2,
                "section_id": 0,
                "lane_id": -1,
                "lane": {
                    "road_id": 2,
                    "section_id": 0,
                    "lane_id": -1,
                },
            },
            "engineering": {
                "vt1_speed_tolerance_kmh": 1.0,
                "stop_speed_threshold_mps": 0.1,
                "scenario_timeout_s": 60.0,
                "vut_start_entry_gate_margin_m": 3.0,
                "speed_limit_kmh": 30.0,
                "future_parameter": "allowed",
            },
        },
    }
    topology = config["roundabout_test"]["topology"]
    topology_core = copy.deepcopy(topology)
    topology_core.pop("verified", None)
    topology["topology_hash"] = canonical_hash(topology_core)
    config["roundabout_test"]["topology_hash"] = topology["topology_hash"]
    trials, _, _ = generate_roundabout_trial_matrix(
        41798, roundabout_condition_payload(config))
    config["roundabout_test"]["reproducibility"] = trials[0]
    return config


class Roundabout2BHelpersTest(unittest.TestCase):
    def test_decode_vehicle_action_preserves_brake_and_clamps(self):
        self.assertEqual(
            decode_vehicle_action([[1.4, -2.0, 0.8]]),
            (0.0, -1.0, 0.8),
        )
        self.assertEqual(
            decode_vehicle_action([0.7, 0.2, 0.05]),
            (0.7, 0.2, 0.05),
        )

        class NumpyLike:
            def tolist(self):
                return [[-0.2, 1.5, -1.0]]

        self.assertEqual(
            decode_vehicle_action(NumpyLike()),
            (0.0, 1.0, 0.0),
        )
        for malformed in (None, [], [0.1, 0.2], [[float("nan"), 0, 0]]):
            with self.subTest(malformed=malformed), self.assertRaises(ValueError):
                decode_vehicle_action(malformed)

    def test_required_vt1_initial_upstream_distance_accounts_for_timing(self):
        distance = required_vt1_initial_upstream_distance(20.0)
        self.assertAlmostEqual(distance, 34.5)
        self.assertAlmostEqual(
            required_vt1_initial_upstream_distance(
                0.0, stable_duration_s=0.0, setup_budget_s=0.0,
                entry_upstream_margin_m=0.0, timing_buffer_m=0.0),
            15.0,
        )
        self.assertGreater(
            required_vt1_initial_upstream_distance(30.0),
            required_vt1_initial_upstream_distance(20.0),
        )
        invalid_arguments = (
            {"vut_approach_distance_m": -1.0},
            {"vut_approach_distance_m": 1.0, "target_speed_kmh": 0.0},
            {"vut_approach_distance_m": 1.0, "vut_approach_speed_mps": 0.0},
            {"vut_approach_distance_m": 1.0, "timing_buffer_m": float("inf")},
        )
        for arguments in invalid_arguments:
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                required_vt1_initial_upstream_distance(**arguments)

    def test_vt1_distance_honours_explicit_vut_approach_time_budget(self):
        distance = required_vt1_initial_upstream_distance(
            5.0, vut_approach_time_budget_s=15.0)
        self.assertGreaterEqual(distance, 2.0 + (15.0 / 3.6) * 18.0)

    def test_conflict_sync_normalizes_release_by_route_distance(self):
        sync = roundabout_conflict_sync_distances(
            20.0, target_headway_s=2.5, headway_tolerance_s=1.5)
        self.assertAlmostEqual(sync["vut_approach_time_s"], 4.8)
        self.assertAlmostEqual(sync["target_entry_gap_m"], 9.25)
        self.assertAlmostEqual(sync["minimum_entry_gap_m"], 3.0)
        self.assertAlmostEqual(sync["maximum_entry_gap_m"], 15.5)
        self.assertAlmostEqual(sync["vt1_release_remaining_m"], 9.5833333)
        self.assertAlmostEqual(sync["entry_arrival_distance_m"], 19.6666667)
        self.assertAlmostEqual(sync["target_lead_time_s"], 2.5)
        farther = roundabout_conflict_sync_distances(30.0)
        self.assertGreater(
            farther["vt1_release_remaining_m"],
            sync["vt1_release_remaining_m"])
        with self.assertRaises(ValueError):
            roundabout_conflict_sync_distances(
                20.0, target_headway_s=1.0, headway_tolerance_s=1.5)

    def test_trial_matrix_is_stable_and_has_three_unique_seeds(self):
        geometry = {"route": [{"x": 0, "y": 0}, {"x": 1, "y": 0}]}
        first, first_matrix_seed, first_fingerprint = generate_roundabout_trial_matrix(
            41798, geometry)
        second, second_matrix_seed, second_fingerprint = generate_roundabout_trial_matrix(
            41798, geometry)
        self.assertEqual(first, second)
        self.assertEqual(first_matrix_seed, second_matrix_seed)
        self.assertEqual(first_fingerprint, second_fingerprint)
        self.assertEqual([item["trial_index"] for item in first], [1, 2, 3])
        self.assertEqual(len({item["trial_seed"] for item in first}), 3)
        self.assertTrue(all(0 <= item["trial_seed"] < 2 ** 32 for item in first))
        with self.assertRaises(ValueError):
            generate_roundabout_trial_matrix(41798, geometry, repetitions=2)

    def test_canonical_hash_ignores_mapping_order(self):
        self.assertEqual(
            canonical_hash({"a": 1, "b": {"c": 2}}),
            canonical_hash({"b": {"c": 2}, "a": 1}),
        )

    def test_manifest_merges_by_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            update_roundabout_manifest(
                directory, [{"file": "b.json", "trial_index": 2}], 8)
            path = update_roundabout_manifest(directory, [
                {"file": "a.json", "trial_index": 1},
                {"file": "b.json", "trial_index": 22},
            ], 8)
            with open(path, "r", encoding="utf-8") as stream:
                manifest = json.load(stream)
            self.assertEqual(manifest["schema_version"], SCHEMA_VERSION)
            self.assertEqual([entry["file"] for entry in manifest["entries"]], [
                "a.json", "b.json"])
            self.assertEqual(manifest["entries"][1]["trial_index"], 22)

    def test_manifest_preserves_per_entry_seed_across_editor_sessions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = update_roundabout_manifest(
                directory, [{"file": "seed-8.json"}], 8)
            update_roundabout_manifest(
                directory, [{"file": "seed-9.json"}], 9)
            with open(path, "r", encoding="utf-8") as stream:
                manifest = json.load(stream)
        seeds = {item["file"]: item["base_seed"] for item in manifest["entries"]}
        self.assertEqual(seeds, {"seed-8.json": 8, "seed-9.json": 9})
        self.assertIsNone(manifest["base_seed"])
        self.assertEqual(manifest["base_seeds"], [8, 9])

    def test_gate_signed_distance_and_directional_crossing(self):
        gate = vertical_gate(0, half_width=1.0)
        self.assertAlmostEqual(gate_signed_distance({"x": -2, "y": 0}, gate), -2.0)
        self.assertAlmostEqual(gate_signed_distance({"x": 2, "y": 0}, gate), 2.0)
        self.assertTrue(gate_crossing((-1, 0), (1, 0), gate))
        self.assertFalse(gate_crossing((1, 0), (-1, 0), gate))
        self.assertTrue(gate_crossing(
            (1, 0), (-1, 0), gate, direction="positive_to_negative"))
        self.assertFalse(gate_crossing((-1, 3), (1, 3), gate))
        self.assertTrue(gate_crossing((-1, 1.2), (1, 1.2), gate, margin_m=0.25))

    def test_gate_supports_center_width_and_explicit_normal(self):
        gate = {
            "center": {"x": 0, "y": 0},
            "width_m": 4.0,
            "normal": {"x": 1, "y": 0},
        }
        self.assertTrue(gate_crossing((-1, 0), (1, 0), gate))
        self.assertGreater(gate_signed_distance((1, 0), gate), 0)

        forward_gate = {
            "left": {"x": 0, "y": 2},
            "right": {"x": 0, "y": -2},
            "forward": {"x": -1, "y": 0},
        }
        self.assertGreater(gate_signed_distance((-1, 0), forward_gate), 0)
        self.assertTrue(gate_crossing(
            (1, 0), (-1, 0), forward_gate, direction="negative_to_positive"))

    def test_gate_validator_rejects_center_endpoint_disagreement(self):
        config = valid_config()
        config["roundabout_test"]["entry_gate"]["center"] = {
            "x": 1000.0, "y": 1000.0,
        }
        self.assertTrue(any(
            "center must equal" in error for error in roundabout_config_errors(config)))

    def test_config_validator_rejects_reversed_gate_orientation(self):
        config = valid_config()
        config["roundabout_test"]["entry_gate"]["forward"] = {"x": -1, "y": 0}
        errors = roundabout_config_errors(config)
        self.assertTrue(any(
            "entry_gate in its forward direction" in error for error in errors
        ))

    def test_route_validation_and_gate_crossing(self):
        route = [(-2, 0), (-1, 0), (2, 0)]
        summary = validate_route(route)
        self.assertEqual(summary["point_count"], 3)
        self.assertAlmostEqual(summary["length_m"], 4.0)
        self.assertTrue(route_crosses_gate(route, vertical_gate(0)))
        with self.assertRaises(ValueError):
            validate_route([(0, 0), (0, 0)])

    def test_config_validator_accepts_extensions(self):
        summary = validate_roundabout_config(valid_config())
        self.assertEqual(summary["planned_exit"], 2)
        self.assertEqual(summary["trial_index"], 1)
        self.assertEqual(roundabout_config_errors(valid_config()), [])

    def test_config_validator_reports_standard_violations(self):
        config = valid_config()
        config["roundabout_test"]["planned_exit"] = 1
        config["roundabout_test"]["vt1"]["target_speed_kmh"] = 14.9
        config["roundabout_test"]["vt2"]["motion"] = "autopilot"
        config["roundabout_test"]["vt2"]["route"] = [(0, 0), (1, 0)]
        errors = roundabout_config_errors(config)
        self.assertTrue(any("planned_exit" in error for error in errors))
        self.assertTrue(any("target_speed_kmh" in error for error in errors))
        self.assertTrue(any("vt2.motion" in error for error in errors))
        self.assertTrue(any("must not have a moving route" in error for error in errors))
        with self.assertRaises(ValueError):
            validate_roundabout_config(config)

    def test_config_validator_requires_boolean_capability_branch(self):
        for value in (None, 0, 1, "false", "true"):
            config = valid_config()
            config["roundabout_test"]["roundabout_capable"] = value
            with self.subTest(value=value):
                errors = roundabout_config_errors(config)
                self.assertTrue(any(
                    "roundabout_capable must be a boolean" in error
                    for error in errors
                ))

    def test_config_validator_requires_one_vut_route_source(self):
        config = valid_config()
        config["roundabout_test"]["vut"]["route"].append(
            {"x": 21, "y": 0})
        errors = roundabout_config_errors(config)
        self.assertTrue(any(
            "ego_route must exactly match roundabout_test.vut.route" in error
            for error in errors
        ))

    def test_config_validator_requires_vt2_in_downstream_inbound_lane(self):
        config = valid_config()
        config["roundabout_test"]["vt2"]["lane_id"] = -2
        errors = roundabout_config_errors(config)
        self.assertTrue(any(
            "must match a downstream_entry inbound lane" in error
            for error in errors
        ))

        missing_lanes = valid_config()
        missing_lanes["roundabout_test"]["downstream_entry"].pop(
            "inbound_lanes")
        errors = roundabout_config_errors(missing_lanes)
        self.assertTrue(any(
            "downstream_entry.inbound_lanes must be a non-empty list" in error
            for error in errors
        ))

    def test_config_validator_collects_malformed_engineering_errors(self):
        malformed = (
            ("vt2_downstream_entry_max_distance_m", None),
            ("vt2_downstream_entry_max_distance_m", "far"),
            ("gate_margin_m", None),
            ("gate_margin_m", "wide"),
            ("vut_start_entry_gate_margin_m", None),
            ("vut_start_entry_gate_margin_m", "near"),
        )
        for field, value in malformed:
            config = valid_config()
            config["roundabout_test"]["engineering"][field] = value
            with self.subTest(field=field, value=value):
                errors = roundabout_config_errors(config)
                self.assertTrue(any(field in error for error in errors))

        missing_object = valid_config()
        missing_object["roundabout_test"]["engineering"] = None
        self.assertTrue(any(
            "engineering must be an object" in error
            for error in roundabout_config_errors(missing_object)
        ))

    def test_config_validator_requires_vut_start_entry_margin(self):
        too_close = valid_config()
        too_close["roundabout_test"]["engineering"].pop(
            "vut_start_entry_gate_margin_m")
        too_close["ego_start"]["x"] = -2.9
        errors = roundabout_config_errors(
            too_close, require_reproducibility=False)
        self.assertTrue(any(
            "ego_start must be upstream" in error for error in errors
        ))

        boundary = valid_config()
        boundary["ego_start"]["x"] = -3.0
        errors = roundabout_config_errors(
            boundary, require_reproducibility=False)
        self.assertFalse(any(
            "ego_start must be upstream" in error for error in errors
        ))

        configured = valid_config()
        configured["roundabout_test"]["engineering"][
            "vut_start_entry_gate_margin_m"] = 6.0
        errors = roundabout_config_errors(
            configured, require_reproducibility=False)
        self.assertTrue(any(
            "at least 6.0 m center margin" in error for error in errors
        ))

    def test_config_validator_requires_verified_three_arm_two_way_topology(self):
        config = valid_config()
        topology = config["roundabout_test"]["topology"]
        topology["verified"] = False
        topology["arm_count"] = 2
        topology["arms"] = topology["arms"][:2]
        topology["arms"][0]["outbound_lane_count"] = 0
        errors = roundabout_config_errors(config)
        self.assertTrue(any("topology.verified" in error for error in errors))
        self.assertTrue(any("topology.arm_count" in error for error in errors))
        self.assertTrue(any("at least 3 access arms" in error for error in errors))
        self.assertTrue(any("outbound_lane_count" in error for error in errors))

        unconfirmed = valid_config()
        unconfirmed["roundabout_test"]["topology"][
            "operator_confirmation"]["confirmed"] = False
        errors = roundabout_config_errors(unconfirmed)
        self.assertTrue(any(
            "operator_confirmation.confirmed" in error for error in errors))

        missing = valid_config()
        del missing["roundabout_test"]["topology"]
        self.assertTrue(any(
            "topology must be an object" in error
            for error in roundabout_config_errors(missing)
        ))

        inconsistent = valid_config()
        inconsistent["roundabout_test"]["topology"]["arms"][0].pop("arm_id")
        inconsistent["roundabout_test"]["topology_hash"] = "0" * 64
        errors = roundabout_config_errors(inconsistent)
        self.assertTrue(any("arm_id is required" in error for error in errors))
        self.assertTrue(any(
            "roundabout_test.topology_hash must match" in error
            for error in errors))

        missing_lanes = valid_config()
        missing_lanes["roundabout_test"]["topology"]["arms"][0][
            "inbound_lanes"] = []
        errors = roundabout_config_errors(missing_lanes)
        self.assertTrue(any("inbound_lanes" in error for error in errors))

    def test_config_validator_requires_exact_role_tagged_targets(self):
        config = valid_config()
        actors = config["other_actors"]["center"]
        actors[0]["autopilot"] = True
        actors[1]["route"] = [{"x": 5, "y": 0}, {"x": 6, "y": 0}]
        actors.append({
            "role": "traffic",
            "model": "vehicle.tesla.model3",
            "transform": {"x": 8, "y": 0},
            "autopilot": False,
        })
        errors = roundabout_config_errors(config)
        self.assertTrue(any("VT1 actor autopilot" in error for error in errors))
        self.assertTrue(any("VT2 actor must not have" in error for error in errors))
        self.assertTrue(any("only VT1 and VT2" in error for error in errors))

    def test_config_validator_checks_vt2_downstream_entry_placement(self):
        config = valid_config()
        config["roundabout_test"]["vt2"]["transform"]["x"] = 200
        config["other_actors"]["center"][1]["transform"]["x"] = 200
        errors = roundabout_config_errors(config)
        self.assertTrue(any(
            "upstream of and within" in error for error in errors))

    def test_matrix_validator_requires_indexes_one_two_three(self):
        base = valid_config()
        trials, _, _ = generate_roundabout_trial_matrix(
            41798, roundabout_condition_payload(base))
        configs = []
        for trial in trials:
            item = copy.deepcopy(base)
            item["roundabout_test"]["reproducibility"] = trial
            configs.append(item)
        summary = validate_roundabout_matrix(configs)
        self.assertEqual(summary["matrix_count"], 1)
        self.assertEqual(summary["trial_count"], 3)
        with self.assertRaises(ValueError):
            validate_roundabout_matrix(configs[:2])

    def test_matrix_validator_recomputes_complete_trial_condition(self):
        base = valid_config()
        trials, _, _ = generate_roundabout_trial_matrix(
            41798, roundabout_condition_payload(base))
        configs = []
        for trial in trials:
            item = copy.deepcopy(base)
            item["name"] = "scenario_2b_trial_{:02d}".format(
                trial["trial_index"])
            item["roundabout_test"]["reproducibility"] = trial
            configs.append(item)
        validate_roundabout_matrix(configs)

        mutations = {
            "VUT route": lambda item: item["ego_route"].append(
                {"x": 21, "y": 0}),
            "VT2 transform": lambda item: item["roundabout_test"]["vt2"][
                "transform"].update({"x": 6}),
            "capability branch": lambda item: item["roundabout_test"].update(
                {"roundabout_capable": False}),
            "weather": lambda item: item.update(
                {"weather": {"cloudiness": 50.0}}),
            "engineering threshold": lambda item: item["roundabout_test"][
                "engineering"].update({"stop_duration_s": 2.0}),
        }
        for label, mutate in mutations.items():
            changed = copy.deepcopy(configs)
            mutate(changed[2])
            with self.subTest(label=label), self.assertRaises(ValueError):
                validate_roundabout_matrix(changed)

    def test_aggregate_requires_three_valid_passes(self):
        passing = [
            {"trial_index": index, "trial_valid": True, "pass": True}
            for index in (1, 2, 3)
        ]
        verdict = aggregate_three_trial_verdict(passing)
        self.assertEqual(verdict["status"], "pass")
        self.assertIs(verdict["pass"], True)

        failing = copy.deepcopy(passing)
        failing[1].update({"pass": False, "failure_reasons": ["wrong_exit"]})
        verdict = aggregate_three_trial_verdict(failing)
        self.assertEqual(verdict["status"], "fail")
        self.assertIs(verdict["pass"], False)
        self.assertTrue(any("wrong_exit" in reason for reason in verdict["failure_reasons"]))

        invalid = copy.deepcopy(passing)
        invalid[2].update({"trial_valid": False, "pass": False,
                           "invalid_reason": "VT1 not stable"})
        verdict = aggregate_three_trial_verdict(invalid)
        self.assertEqual(verdict["status"], "incomplete")
        self.assertIsNone(verdict["pass"])

    def test_aggregate_uses_latest_valid_retry_per_trial(self):
        records = [
            {"trial_index": 1, "trial_valid": False, "pass": None,
             "invalid_reason": "old setup failure"},
            {"trial_index": 2, "trial_valid": True, "pass": True},
            {"trial_index": 3, "trial_valid": True, "pass": True},
            {"trial_index": 1, "trial_valid": True, "pass": True},
            {"trial_index": 1, "trial_valid": False, "pass": None,
             "invalid_reason": "new setup failure"},
        ]
        verdict = aggregate_three_trial_verdict(records)
        self.assertEqual(verdict["status"], "pass")
        self.assertIs(verdict["pass"], True)
        self.assertEqual(verdict["attempt_count"], 5)
        self.assertEqual(verdict["trial_count"], 3)
        self.assertEqual(verdict["valid_trial_count"], 3)
        self.assertFalse(any(
            "setup failure" in reason for reason in verdict["failure_reasons"]
        ))

    def test_aggregate_latest_valid_attempt_replaces_prior_verdict(self):
        records = [
            {"trial_index": 1, "trial_valid": True, "pass": True},
            {"trial_index": 2, "trial_valid": True, "pass": True},
            {"trial_index": 3, "trial_valid": True, "pass": True},
            {"trial_index": 1, "trial_valid": True, "pass": False,
             "failure_reasons": ["latest failure"]},
        ]
        verdict = aggregate_three_trial_verdict(records)
        self.assertEqual(verdict["status"], "fail")
        self.assertIs(verdict["pass"], False)
        self.assertEqual(verdict["attempt_count"], 4)
        self.assertTrue(any(
            "latest failure" in reason for reason in verdict["failure_reasons"]
        ))

        undecided = copy.deepcopy(records)
        undecided[-1] = {
            "trial_index": 1, "trial_valid": True, "pass": None,
        }
        verdict = aggregate_three_trial_verdict(undecided)
        self.assertEqual(verdict["status"], "incomplete")
        self.assertIsNone(verdict["pass"])

    def test_aggregate_rejects_conflicting_validity_fields(self):
        records = [
            {"trial_index": index, "trial_valid": True,
             "precondition_valid": index != 2, "pass": True}
            for index in (1, 2, 3)
        ]
        verdict = aggregate_three_trial_verdict(records)
        self.assertEqual(verdict["status"], "incomplete")
        self.assertIsNone(verdict["pass"])

    def test_aggregate_uses_last_invalid_when_no_valid_retry_exists(self):
        records = [
            {"trial_index": 1, "trial_valid": False, "pass": None,
             "invalid_reason": "superseded invalid"},
            {"trial_index": 2, "trial_valid": True, "pass": True},
            {"trial_index": 3, "trial_valid": True, "pass": True},
            {"trial_index": 1, "trial_valid": False, "pass": None,
             "invalid_reason": "latest invalid"},
        ]
        verdict = aggregate_three_trial_verdict(records)
        self.assertEqual(verdict["status"], "incomplete")
        self.assertIsNone(verdict["pass"])
        self.assertEqual(verdict["attempt_count"], 4)
        self.assertTrue(any(
            "latest invalid" in reason for reason in verdict["failure_reasons"]
        ))
        self.assertFalse(any(
            "superseded invalid" in reason for reason in verdict["failure_reasons"]
        ))

    def test_aggregate_rejects_non_integer_trial_indexes(self):
        for invalid_index in (True, 1.0, "1", 4, None):
            records = [
                {"trial_index": 1, "trial_valid": True, "pass": True},
                {"trial_index": 2, "trial_valid": True, "pass": True},
                {"trial_index": 3, "trial_valid": True, "pass": True},
                {"trial_index": invalid_index, "trial_valid": True, "pass": True},
            ]
            with self.subTest(invalid_index=invalid_index):
                verdict = aggregate_three_trial_verdict(records)
                self.assertEqual(verdict["status"], "incomplete")
                self.assertIsNone(verdict["pass"])

    def test_result_writer_has_roundabout_heading_and_aggregate(self):
        records = [
            {
                "run_id": "run-1",
                "scenario": "scenario_2b_0000_trial_{:02d}".format(index),
                "matrix_id": "matrix-a",
                "trial_index": index,
                "planned_exit": 2,
                "trial_valid": True,
                "route_complete": True,
                "pass": True,
                "failure_reasons": [],
            }
            for index in (1, 2, 3)
        ]
        with tempfile.TemporaryDirectory() as directory:
            paths = write_roundabout_result_artifacts(
                records, directory, metadata={"town": "SafeBenchHK"})
            for path in paths.values():
                self.assertTrue(os.path.exists(path), path)
            with open(paths["markdown"], "r", encoding="utf-8") as stream:
                report = stream.read()
            self.assertIn("环形路口（2.b）测试结果", report)
            self.assertIn("matrix-a", report)
            with open(paths["json"], "r", encoding="utf-8") as stream:
                payload = json.load(stream)
            self.assertEqual(payload["aggregates"][0]["status"], "pass")
            loaded = load_existing_roundabout_records(directory)
            self.assertEqual(len(loaded), 3)

    def test_route_fingerprint_ignores_weather_and_target_models(self):
        first = valid_config()
        second = copy.deepcopy(first)
        second["weather"] = {"cloudiness": 90.0}
        second["other_actors"]["center"][0]["model"] = "vehicle.audi.tt"
        self.assertEqual(
            roundabout_route_fingerprint(first),
            roundabout_route_fingerprint(second))
        second["ego_route"][1]["y"] += 1.0
        self.assertNotEqual(
            roundabout_route_fingerprint(first),
            roundabout_route_fingerprint(second))

    def test_structured_writer_separates_telemetry_and_quantitative_summary(self):
        records = []
        for index, speed in enumerate((2.0, 3.0, 4.0), start=1):
            records.append({
                "run_id": "run-structured",
                "scenario": "scenario_2b_0001_trial_{:02d}".format(index),
                "matrix_id": "matrix-structured",
                "trial_index": index,
                "attempt_index": 1,
                "planned_exit": 2,
                "roundabout_capable": True,
                "trial_valid": True,
                "pass": True,
                "average_speed_mps": speed,
                "condition_id": "sunny_01--tesla_model3",
                "condition_fingerprint": "a" * 64,
                "drawn_route_id": "route_0001",
                "route_definition_fingerprint": "b" * 64,
                "scenario_snapshot": {"name": "snapshot"},
                "timeline_samples": [{
                    "frame": index,
                    "sim_time": index * 0.05,
                    "trial_time": index * 0.05,
                    "phase": "APPROACHING",
                    "vut": {"speed_mps": speed},
                }],
            })
        with tempfile.TemporaryDirectory() as directory:
            paths = write_roundabout_result_artifacts(records, directory)
            condition = os.path.join(
                directory, "route_0001_exit2_capable",
                "sunny_01--tesla_model3__c_aaaaaaaaaa")
            # One writer call materialises the newest attempt; normal runner
            # operation calls the writer after every attempt.
            attempt = os.path.join(condition, "trial_03", "attempt_01")
            self.assertTrue(os.path.isfile(os.path.join(condition, "condition.json")))
            self.assertTrue(os.path.isfile(os.path.join(condition, "aggregate.json")))
            self.assertTrue(os.path.isfile(os.path.join(attempt, "summary.json")))
            telemetry_path = os.path.join(attempt, "telemetry.csv.gz")
            with gzip.open(telemetry_path, "rt", encoding="utf-8") as stream:
                self.assertIn("vut_speed_mps", stream.readline())
            with open(os.path.join(condition, "aggregate.json"),
                      "r", encoding="utf-8") as stream:
                aggregate = json.load(stream)
            stats = aggregate["quantitative_statistics"]["average_speed_mps"]
            self.assertEqual(stats["mean"], 3.0)
            self.assertEqual(stats["min"], 2.0)
            self.assertEqual(stats["max"], 4.0)
            with open(paths["json"], "r", encoding="utf-8") as stream:
                ledger = json.load(stream)
            self.assertNotIn("timeline_samples", ledger["records"][-1])
            self.assertTrue(os.path.isfile(paths["json"]))

    def test_lightweight_batch_flush_does_not_erase_attempt_evidence(self):
        record = {
            "run_id": "run-preserve",
            "scenario": "scenario_2b_preserve",
            "trial_index": 1,
            "attempt_index": 1,
            "execution_mode": "screening",
            "planned_exit": 2,
            "roundabout_capable": True,
            "trial_valid": True,
            "pass": False,
            "condition_id": "sunny_01--tesla_model3",
            "condition_fingerprint": "c" * 64,
            "drawn_route_id": "route_0000",
            "route_definition_fingerprint": "d" * 64,
            "scenario_snapshot": {"name": "full evidence"},
            "collision_events": [{"frame": 42, "other_actor_type": "vehicle.test"}],
            "timeline_samples": [{
                "frame": 41,
                "sim_time": 2.05,
                "trial_time": 1.0,
                "phase": "IN_ROUNDABOUT",
                "vut": {"speed_mps": 3.5},
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            write_roundabout_result_artifacts([record], directory)
            attempt = os.path.join(
                directory, "route_0000_exit2_capable",
                "sunny_01--tesla_model3__c_cccccccccc",
                "screening", "attempt_01")
            telemetry_path = os.path.join(attempt, "telemetry.csv.gz")
            events_path = os.path.join(attempt, "events.json")
            with open(telemetry_path, "rb") as stream:
                telemetry_before = stream.read()
            with open(events_path, "rb") as stream:
                events_before = stream.read()

            lightweight = roundabout_record_summary(record)
            write_roundabout_result_artifacts([lightweight], directory)

            with open(telemetry_path, "rb") as stream:
                self.assertEqual(stream.read(), telemetry_before)
            with open(events_path, "rb") as stream:
                self.assertEqual(stream.read(), events_before)
            with gzip.open(telemetry_path, "rt", encoding="utf-8") as stream:
                self.assertIn("vut_speed_mps", stream.readline())
            with open(events_path, "r", encoding="utf-8") as stream:
                self.assertEqual(
                    json.load(stream)["collision_events"][0]["frame"], 42)

    def test_corrupt_existing_ledger_fails_loudly(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "2b_result.json")
            with open(path, "w", encoding="utf-8") as stream:
                stream.write("{not-json")
            with self.assertRaisesRegex(RuntimeError, "cannot read existing"):
                load_existing_roundabout_records(directory)

    def test_result_writer_never_combines_different_test_runs(self):
        records = [
            {"run_id": "run-a", "matrix_id": "matrix-a", "trial_index": 1,
             "planned_exit": 2, "trial_valid": True, "pass": True},
            {"run_id": "run-a", "matrix_id": "matrix-a", "trial_index": 2,
             "planned_exit": 2, "trial_valid": True, "pass": True},
            {"run_id": "run-a", "matrix_id": "matrix-a", "trial_index": 3,
             "planned_exit": 2, "trial_valid": False, "pass": None,
             "invalid_reason": "old setup failure"},
            {"run_id": "run-b", "matrix_id": "matrix-a", "trial_index": 3,
             "planned_exit": 2, "trial_valid": True, "pass": True},
        ]
        with tempfile.TemporaryDirectory() as directory:
            paths = write_roundabout_result_artifacts(records, directory)
            with open(paths["json"], "r", encoding="utf-8") as stream:
                aggregates = json.load(stream)["aggregates"]
        self.assertEqual(len(aggregates), 2)
        self.assertEqual(
            {item["run_id"]: item["status"] for item in aggregates},
            {"run-a": "incomplete", "run-b": "incomplete"},
        )
        self.assertTrue(all(item["status"] != "pass" for item in aggregates))


if __name__ == "__main__":
    unittest.main()
