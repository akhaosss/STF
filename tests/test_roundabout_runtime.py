import importlib.util
import pathlib
import sys
import types
import unittest
import threading
import numpy as np


class _VehicleControl:
    def __init__(self, throttle=0.0, steer=0.0, brake=0.0):
        self.throttle = throttle
        self.steer = steer
        self.brake = brake
        self.hand_brake = False


class _Location:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x, self.y, self.z = x, y, z

    def distance(self, other):
        return ((self.x - other.x) ** 2 + (self.y - other.y) ** 2
                + (self.z - other.z) ** 2) ** 0.5


def _load_scene_with_carla_stub():
    carla = types.ModuleType("carla")
    carla.VehicleControl = _VehicleControl
    carla.Location = _Location
    carla.Transform = type("Transform", (), {})
    carla.Rotation = type("Rotation", (), {})
    carla.Vector3D = _Location
    carla.WalkerControl = type("WalkerControl", (), {})
    carla.LaneType = types.SimpleNamespace(Driving="Driving")
    carla.VehicleLightState = type(
        "VehicleLightState", (int,), {"RightBlinker": 1})

    tcp = types.ModuleType("model.tcp")
    tcp.TCPAgent = type("TCPAgent", (), {})
    tcp.TCPRoutePlanner = type("TCPRoutePlanner", (), {})
    tcp.TCP_CAMERA_WIDTH = 900
    tcp.TCP_CAMERA_HEIGHT = 256
    tcp.TCP_CAMERA_FOV = 100.0
    tcp.TCP_CAMERA_X = -1.5
    tcp.TCP_CAMERA_Y = 0.0
    tcp.TCP_CAMERA_Z = 2.0

    collision = types.ModuleType("collision_enhancer")
    collision.load_collision_config = lambda *args, **kwargs: {}
    collision.get_collision_config = lambda *args, **kwargs: {}
    collision.get_adjusted_trigger_distance = lambda value, *args, **kwargs: value
    collision.get_adjusted_throttle = lambda value, *args, **kwargs: value
    collision.apply_ga_params_to_npcs = lambda *args, **kwargs: None
    collision.get_optimized_npc_control = lambda *args, **kwargs: None
    collision.SimpleGeneticOptimizer = type("SimpleGeneticOptimizer", (), {})
    collision.get_npc_speed_boost = lambda *args, **kwargs: 1.0

    replacements = {
        "carla": carla,
        "model.tcp": tcp,
        "collision_enhancer": collision,
    }
    previous = {name: sys.modules.get(name) for name in replacements}
    sys.modules.update(replacements)
    try:
        path = pathlib.Path(__file__).resolve().parents[1] / "scene.py"
        spec = importlib.util.spec_from_file_location(
            "_roundabout_scene_runtime_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name, value in previous.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


SCENE_MODULE = _load_scene_with_carla_stub()


class _FakeEgo:
    def __init__(self):
        self.applied = None

    def apply_control(self, control):
        self.applied = control


class RoundaboutRuntimeContractTest(unittest.TestCase):
    def test_vt1_fixture_can_enable_local_constant_speed(self):
        class Actor:
            target = None

            def enable_constant_velocity(self, velocity):
                self.target = velocity

        actor = Actor()
        SCENE_MODULE.EgoRouteFollowScene._roundabout_enable_constant_speed(
            actor, 15.0 / 3.6)
        self.assertAlmostEqual(actor.target.x, 15.0 / 3.6)
        self.assertEqual(actor.target.y, 0.0)
        self.assertEqual(actor.target.z, 0.0)

    def test_vt1_fixture_target_speed_follows_vehicle_heading(self):
        class Actor:
            target = None

            def get_transform(self):
                return types.SimpleNamespace(
                    get_forward_vector=lambda: types.SimpleNamespace(
                        x=0.6, y=0.8, z=0.0))

            def set_target_velocity(self, velocity):
                self.target = velocity

        actor = Actor()
        SCENE_MODULE.EgoRouteFollowScene._roundabout_set_planar_target_speed(
            actor, 5.0)
        self.assertAlmostEqual(actor.target.x, 3.0)
        self.assertAlmostEqual(actor.target.y, 4.0)
        self.assertEqual(actor.target.z, 0.0)

    def test_vt1_route_end_continues_on_connected_lane_after_exit(self):
        class Actor:
            def __init__(self):
                self.is_alive = True
                self.control = None

            def get_location(self):
                return _Location(10.0, 0.0)

            def get_transform(self):
                return types.SimpleNamespace(
                    rotation=types.SimpleNamespace(yaw=0.0),
                    get_forward_vector=lambda: _Location(1.0, 0.0, 0.0))

            def get_velocity(self):
                return _Location(15.0 / 3.6, 0.0, 0.0)

            def apply_control(self, control):
                self.control = control

        continuation = types.SimpleNamespace(
            transform=types.SimpleNamespace(location=_Location(16.0, 0.0)))
        lane = types.SimpleNamespace(next=lambda distance: [continuation])
        scene = SCENE_MODULE.EgoRouteFollowScene.__new__(
            SCENE_MODULE.EgoRouteFollowScene)
        scene.vt1_actor = Actor()
        scene.map = types.SimpleNamespace(get_waypoint=lambda *args, **kwargs: lane)
        scene.vt1_route = [_Location(0.0, 0.0), _Location(10.0, 0.0)]
        scene.vt1_target_idx = 1
        scene.rb_vt1_route_lookahead = 2.0
        scene.rb_vt1_exit1_crossed = True
        scene.rb_vt1_drawn_route_finished = False
        scene.rb_vt1_topology_fallback_reported = False
        scene.rb_vt1_speed_integral = 0.0
        scene.vt1_target_speed_mps = 15.0 / 3.6
        scene.rb_vt1_speed_control_mode = "pid"
        scene.rb_vt1_corner_speed_compensation = 0.12

        scene._roundabout_follow_vt1()

        self.assertTrue(scene.rb_vt1_drawn_route_finished)
        self.assertIsNotNone(scene.vt1_actor.control)
        self.assertEqual(scene.vt1_actor.control.brake, 0.0)
        self.assertGreater(scene.vt1_actor.control.throttle, 0.0)

    def test_vt1_is_removed_only_after_post_exit_clearance(self):
        class Actor:
            def __init__(self):
                self.is_alive = True
                self.disabled = False
                self.destroyed = False

            def get_location(self):
                return _Location(2.0, 0.0)

            def disable_constant_velocity(self):
                self.disabled = True

            def destroy(self):
                self.destroyed = True
                self.is_alive = False

        actor = Actor()
        events = []
        scene = SCENE_MODULE.EgoRouteFollowScene.__new__(
            SCENE_MODULE.EgoRouteFollowScene)
        scene.vt1_actor = actor
        scene.rb_vt1_departed = False
        scene.rb_vt1_exit1_crossed = True
        scene.rb_vt1_conflict_crossed = True
        scene.rb_vt1_exit_clearance_last_location = _Location(0.0, 0.0)
        scene.rb_vt1_exit_clearance_travel_m = 4.0
        scene.rb_vt1_post_exit_clearance_distance = 5.0
        scene.vt1_target_speed_mps = 15.0 / 3.6
        scene.rb_vt1_constant_velocity_enabled = True
        scene.vt1_route_finished = False
        scene.rb_vt1_departure_time = None
        scene.roundabout_exit_gates = {}
        scene._roundabout_vt1_upstream_remaining = lambda: -1.0
        scene._roundabout_record_event = (
            lambda *args, **kwargs: events.append((args, kwargs)))

        scene._roundabout_update_vt1_fixture(12.0, 0.05)

        self.assertTrue(scene.rb_vt1_departed)
        self.assertTrue(scene.vt1_route_finished)
        self.assertTrue(actor.disabled)
        self.assertTrue(actor.destroyed)
        self.assertIsNone(scene.vt1_actor)
        self.assertEqual(events[-1][0][1], "VT1_CLEARED_EXIT_AND_REMOVED")
        self.assertGreaterEqual(
            events[-1][1]["clearance_distance_m"], 5.0)

    def test_roundabout_vehicle_speed_ignores_spawn_settling_velocity(self):
        actor = types.SimpleNamespace(get_velocity=lambda: types.SimpleNamespace(
            x=0.0, y=0.0, z=-1.96))
        speed = SCENE_MODULE.EgoRouteFollowScene._roundabout_vehicle_speed(actor)
        self.assertEqual(speed, 0.0)

    def test_vt1_projection_can_be_bounded_away_from_later_route_revisit(self):
        scene_type = SCENE_MODULE.EgoRouteFollowScene
        route = [
            _Location(0, 0), _Location(10, 0), _Location(20, 0),
            _Location(20, 10), _Location(10, 0.1), _Location(0, 0.1),
        ]
        cumulative = scene_type._roundabout_route_distances(route)
        location = _Location(5, 0.08)
        global_progress, _ = scene_type._roundabout_project_route(
            location, route, cumulative)
        local_progress, _ = scene_type._roundabout_project_route(
            location, route, cumulative, start_index=0, end_index=2)
        self.assertGreater(global_progress, 30.0)
        self.assertAlmostEqual(local_progress, 5.0, delta=0.1)

    def test_lane_guidance_uses_confirmed_route_corridor_not_lane_token(self):
        scene = SCENE_MODULE.EgoRouteFollowScene.__new__(
            SCENE_MODULE.EgoRouteFollowScene)
        scene.route_points = [
            _Location(0, 0), _Location(10, 0), _Location(20, 0)]
        scene.rb_vut_route_s = scene._roundabout_route_distances(
            scene.route_points)
        scene.rb_vut_route_segment_idx = 0
        scene.rb_vut_route_progress_s = 0.0
        scene.rb_vut_route_lane_half_widths = [1.75, 1.75, 1.75]
        scene.rb_lane_corridor_min_half_width_m = 1.75
        scene.rb_lane_corridor_max_half_width_m = 4.0
        scene.rb_lane_corridor_extra_m = 0.75

        detail, allowed = scene._roundabout_vut_route_corridor(
            _Location(12.0, 0.3))

        self.assertAlmostEqual(detail["distance_m"], 0.3)
        self.assertAlmostEqual(detail["progress_m"], 12.0)
        self.assertLess(detail["distance_m"], allowed)
        self.assertEqual(scene.rb_vut_route_segment_idx, 1)

    def test_vut_entry_records_gap_miss_without_truncating_experiment(self):
        scene = SCENE_MODULE.EgoRouteFollowScene.__new__(
            SCENE_MODULE.EgoRouteFollowScene)
        scene.rb_entry_arrived = False
        scene.rb_entry_arrival_time = None
        scene.roundabout_capable = True
        scene.vt1_actor = types.SimpleNamespace(
            get_velocity=lambda: types.SimpleNamespace(x=15.0 / 3.6, y=0.0))
        scene.vt2_actor = types.SimpleNamespace(
            get_velocity=lambda: types.SimpleNamespace(x=0.0, y=0.0))
        scene.vt1_target_speed_mps = 15.0 / 3.6
        scene.rb_vt1_speed_tolerance = 0.1
        scene.rb_vt2_stationary_speed = 0.1
        scene.rb_vt1_entry_gap_min_m = 4.0
        scene.rb_vt1_entry_gap_max_m = 16.0
        scene.rb_vt1_entry_gap_target_m = 10.0
        scene.rb_entry_sync_missed = False
        scene._roundabout_vt1_is_upstream = lambda: (True, 20.0)
        events = []
        terminal_invalid = []
        deferred_invalid = []
        scene._roundabout_record_event = (
            lambda *args, **kwargs: events.append((args, kwargs)))
        scene._roundabout_invalidate = (
            lambda now, reason: terminal_invalid.append(reason))
        scene._roundabout_defer_invalid = (
            lambda now, reason: deferred_invalid.append(reason))

        self.assertTrue(scene._roundabout_capture_entry_conditions(12.0))
        self.assertEqual(terminal_invalid, [])
        self.assertEqual(deferred_invalid, [])
        self.assertTrue(scene.rb_entry_sync_missed)
        self.assertEqual(events[-1][0][1], "VT1_CONFLICT_GAP_OUT_OF_WINDOW")

    def test_vut_entry_after_vt1_departure_is_diagnostic_without_runner_error(self):
        scene = SCENE_MODULE.EgoRouteFollowScene.__new__(
            SCENE_MODULE.EgoRouteFollowScene)
        scene.rb_entry_arrived = False
        scene.rb_entry_arrival_time = None
        scene.roundabout_capable = True
        scene.vt1_actor = None
        scene.vt2_actor = types.SimpleNamespace(
            get_velocity=lambda: types.SimpleNamespace(x=0.0, y=0.0))
        scene.rb_vt1_departed = True
        scene.vt1_route_finished = True
        scene.rb_vt1_speed_at_entry = None
        scene.rb_vt1_upstream_at_entry = None
        scene.rb_vt1_remaining_at_entry = None
        scene.rb_vt1_conflict_ttc_at_entry_s = None
        scene.rb_entry_sync_missed = False
        scene.rb_invalid_reasons = []
        scene.rb_vt2_stationary_speed = 0.1
        events = []
        terminal_invalid = []
        deferred_invalid = []
        scene._roundabout_record_event = (
            lambda *args, **kwargs: events.append((args, kwargs)))
        scene._roundabout_invalidate = (
            lambda now, reason: terminal_invalid.append(reason))
        scene._roundabout_defer_invalid = (
            lambda now, reason: deferred_invalid.append(reason))

        self.assertTrue(scene._roundabout_capture_entry_conditions(12.0))
        self.assertEqual(terminal_invalid, [])
        self.assertEqual(deferred_invalid, [])
        self.assertTrue(scene.rb_entry_sync_missed)
        self.assertIsNone(scene.rb_vt1_speed_at_entry)
        self.assertEqual(events[-1][0][1], "VT1_UNAVAILABLE_AT_VUT_ENTRY")
        self.assertEqual(
            events[-1][1]["reason"], "vt1_passed_entry_before_vut_entry")

    def test_experiment_clock_excludes_fixture_stabilisation(self):
        scene = SCENE_MODULE.EgoRouteFollowScene.__new__(
            SCENE_MODULE.EgoRouteFollowScene)
        scene.rb_start_sim_time = 100.0
        scene.rb_trial_start_sim_time = 107.35

        self.assertAlmostEqual(
            scene._roundabout_experiment_elapsed(227.35), 120.0)

    def test_result_fails_when_vut_enters_before_vt1_crosses_merge_point(self):
        scene = self._result_scene()
        scene.rb_vt1_exit1_crossed = True
        scene.rb_vut_entered_before_vt1 = True
        scene.rb_vt1_conflict_crossing_time = None
        scene.rb_vut_entry_crossing_time = 12.0
        scene.rb_vt1_lead_time_at_vut_entry_s = None

        result = scene.get_result()

        self.assertTrue(result["trial_valid"])
        self.assertFalse(result["pass"])
        self.assertIn("vut_entered_before_vt1_at_merge", result["failure_reasons"])
        self.assertFalse(result["vt1_conflict_crossed_before_vut"])

    @staticmethod
    def _result_scene():
        scene = SCENE_MODULE.EgoRouteFollowScene.__new__(
            SCENE_MODULE.EgoRouteFollowScene)
        values = {
            "is_roundabout_2b": True,
            "rb_collision_recorded": False,
            "rb_speed_limit_observed": True,
            "rb_speed_limit_unobservable_gap": False,
            "rb_invalid_reasons": [],
            "rb_invalid_events": [],
            "rb_entry_sync_missed": False,
            "rb_approach_time_budget_exceeded": False,
            "rb_valid_collision_time": None,
            "rb_timed_out": False,
            "rb_vt2_moved": False,
            "rb_speed_limit_exceeded": False,
            "rb_solid_line_invasion": False,
            "rb_lane_direction_violation": False,
            "rb_lane_guidance_violation": False,
            "rb_off_road": False,
            "rb_sut_failure": None,
            "roundabout_capable": True,
            "rb_entry_crossed": True,
            "rb_wrong_exit": None,
            "rb_correct_exit_crossed": True,
            "rb_exit_indicator_observed": True,
            "rb_exit_lane_correct": True,
            "finished": True,
            "rb_vt1_exit1_crossed": False,
            "rb_emergency_braking": False,
            "rb_stopped_in_roundabout": False,
            "roundabout_cfg": {"reproducibility": {}, "topology": {}},
            "roundabout_planned_exit": 2,
            "rb_phase": "COMPLETE",
            "rb_vt1_ready": True,
            "vt1_target_speed_mps": 15.0 / 3.6,
            "rb_vt1_speed_at_entry": 15.0 / 3.6,
            "rb_vt1_upstream_at_entry": True,
            "rb_vt1_remaining_at_entry": 3.0,
            "rb_vt1_speed_maintained": True,
            "rb_vt1_post_exit_clearance_distance": 25.0,
            "rb_vt1_exit_clearance_travel_m": 0.0,
            "rb_vt1_departed": False,
            "rb_vt1_departure_time": None,
            "rb_vt1_drawn_route_finished": False,
            "rb_vt2_max_speed": 0.0,
            "rb_max_speed_mps": 5.0,
            "rb_observed_speed_limit_kmh": 30.0,
            "rb_lane_invasion_events": [],
            "rb_indicator_evidence_source": "test",
            "rb_indicator_lookback": 3.0,
            "roundabout_engineering": {},
            "rb_max_deceleration": 0.0,
            "rb_odd_alert_observed": False,
            "rb_odd_alert_source": None,
            "rb_odd_alert_debug_observed": False,
            "rb_formal_hmi_evidence": True,
            "rb_collision_vt1": False,
            "rb_collision_vt2": False,
            "rb_infrastructure_collision": False,
            "rb_other_collision": False,
            "rb_sut_error": None,
            "rb_phase_history": [],
            "rb_events": [],
            "timeline_samples": [],
        }
        for name, value in values.items():
            setattr(scene, name, value)
        return scene

    def test_entry_sync_miss_does_not_prevent_an_otherwise_passing_result(self):
        scene = self._result_scene()
        scene.rb_vt1_exit1_crossed = True
        scene.rb_entry_sync_missed = True

        result = scene.get_result()

        self.assertTrue(result["trial_valid"])
        self.assertTrue(result["pass"])
        self.assertTrue(result["entry_sync_missed"])
        self.assertEqual(result["failure_reasons"], [])

    def test_missing_exit_indicator_is_diagnostic_not_failure(self):
        scene = self._result_scene()
        scene.rb_vt1_exit1_crossed = True
        scene.rb_exit_indicator_observed = False
        scene.rb_indicator_evidence_source = None

        result = scene.get_result()

        self.assertTrue(result["trial_valid"])
        self.assertTrue(result["pass"])
        self.assertFalse(result["exit_indicator_observed"])
        self.assertIsNone(result["turn_signal_violation"])
        self.assertFalse(result["indicator_policy"]["evaluated_as_failure"])
        self.assertNotIn("exit_indicator_not_observed", result["failure_reasons"])

    def test_exit_lane_mismatch_is_diagnostic_not_failure(self):
        scene = self._result_scene()
        scene.rb_vt1_exit1_crossed = True
        scene.rb_exit_lane_correct = False

        result = scene.get_result()

        self.assertTrue(result["trial_valid"])
        self.assertTrue(result["pass"])
        self.assertFalse(result["correct_exit_lane"])
        self.assertFalse(result["exit_lane_evaluated_as_failure"])
        self.assertNotIn("incorrect_exit_lane", result["failure_reasons"])

    def test_vut_entry_arrival_timeout_is_a_valid_failure(self):
        scene = self._result_scene()
        scene.rb_vt1_exit1_crossed = True
        scene.rb_approach_time_budget_exceeded = True

        result = scene.get_result()

        self.assertTrue(result["trial_valid"])
        self.assertFalse(result["pass"])
        self.assertTrue(result["approach_time_budget_exceeded"])
        self.assertIn("vut_entry_arrival_timeout", result["failure_reasons"])

    def test_carla_bgra_camera_is_converted_to_rgb(self):
        image = types.SimpleNamespace(
            raw_data=bytes([10, 20, 30, 255]), height=1, width=1)
        rgb = SCENE_MODULE.EgoRouteFollowScene._roundabout_decode_camera_rgb(image)
        np.testing.assert_array_equal(rgb, np.array([[[30, 20, 10]]], dtype=np.uint8))

    def test_roundabout_tcp_camera_matches_upstream_sensor_contract(self):
        attributes = {}

        class Blueprint:
            def set_attribute(self, key, value):
                attributes[key] = value

        class Sensor:
            def listen(self, callback):
                self.callback = callback

        sensor = Sensor()
        world = types.SimpleNamespace(
            get_blueprint_library=lambda: types.SimpleNamespace(
                find=lambda identifier: Blueprint()),
            spawn_actor=lambda blueprint, transform, attach_to=None: sensor,
        )
        scene = SCENE_MODULE.EgoRouteFollowScene.__new__(
            SCENE_MODULE.EgoRouteFollowScene)
        scene.world = world
        scene.ego = object()
        scene.actors = []
        scene.camera_condition = threading.Condition()
        locations = []
        original_transform = SCENE_MODULE.carla.Transform
        SCENE_MODULE.carla.Transform = lambda location: locations.append(location) or location
        try:
            scene.spawn_camera()
        finally:
            SCENE_MODULE.carla.Transform = original_transform

        self.assertEqual(attributes["image_size_x"], "900")
        self.assertEqual(attributes["image_size_y"], "256")
        self.assertEqual(attributes["fov"], "100.0")
        self.assertEqual(locations[0].x, -1.5)
        self.assertEqual(locations[0].y, 0.0)
        self.assertEqual(locations[0].z, 2.0)
        self.assertIs(scene.camera_sensor, sensor)

    def test_tcp_camera_requires_the_current_world_frame(self):
        scene = SCENE_MODULE.EgoRouteFollowScene.__new__(
            SCENE_MODULE.EgoRouteFollowScene)
        scene.camera_data = object()
        scene.camera_frame = 100
        scene.camera_condition = threading.Condition()
        scene.rb_camera_frame_timeout = 0.001
        self.assertTrue(scene._roundabout_wait_for_camera_frame(100))
        self.assertFalse(scene._roundabout_wait_for_camera_frame(101))

    def test_incapable_branch_captures_arrival_without_vt_fixture_checks(self):
        scene = SCENE_MODULE.EgoRouteFollowScene.__new__(
            SCENE_MODULE.EgoRouteFollowScene)
        scene.rb_entry_arrived = False
        scene.rb_entry_arrival_time = None
        scene.roundabout_capable = False
        events = []
        scene._roundabout_record_event = lambda *args: events.append(args)

        self.assertTrue(scene._roundabout_capture_entry_conditions(12.0))
        self.assertTrue(scene.rb_entry_arrived)
        self.assertEqual(scene.rb_entry_arrival_time, 12.0)
        self.assertEqual(events[0][1], "VUT_REACHED_ROUNDABOUT_ENTRY")

    def test_non_vut_fixture_collision_invalidates_the_attempt(self):
        scene = SCENE_MODULE.EgoRouteFollowScene.__new__(
            SCENE_MODULE.EgoRouteFollowScene)
        scene.is_roundabout_2b = True
        scene.ego = types.SimpleNamespace(id=1)
        scene._roundabout_sensor_time = lambda event, fallback=None: 8.0
        scene._roundabout_record_event = lambda *args, **kwargs: None
        invalidated = []
        scene._roundabout_invalidate = lambda now, reason: invalidated.append(reason)
        scene.record_fixture_collision(
            "vt1", types.SimpleNamespace(
                frame=80, other_actor=types.SimpleNamespace(id=2, type_id="static.wall")))
        self.assertEqual(invalidated, ["vt1_fixture_collision"])

        invalidated.clear()
        scene.record_fixture_collision(
            "vt1", types.SimpleNamespace(
                frame=81, other_actor=types.SimpleNamespace(id=1, type_id="vehicle.ego")))
        self.assertEqual(invalidated, [])

    def test_tcp_brake_channel_is_applied_and_cancels_throttle(self):
        scene = SCENE_MODULE.EgoRouteFollowScene.__new__(
            SCENE_MODULE.EgoRouteFollowScene)
        scene.rb_trial_start_sim_time = 0.0
        scene.finished = False
        scene.rb_tcp_required = True
        scene.camera_data = object()
        scene.tcp = types.SimpleNamespace(
            get_action=lambda image, ego: [[0.8, -0.25, 0.7]])
        scene.ego = _FakeEgo()
        scene.control = _VehicleControl()

        scene._roundabout_apply_ego_control()

        self.assertAlmostEqual(scene.ego.applied.brake, 0.7)
        self.assertAlmostEqual(scene.ego.applied.steer, -0.25)
        self.assertAlmostEqual(scene.ego.applied.throttle, 0.0)

    def test_terminal_phase_cannot_be_overwritten_by_gate_detection(self):
        scene = SCENE_MODULE.EgoRouteFollowScene.__new__(
            SCENE_MODULE.EgoRouteFollowScene)
        scene.rb_phase = "COMPLETE"

        def unexpected_gate_check(*args, **kwargs):
            raise AssertionError("terminal state evaluated a gate")

        scene._roundabout_gate_crossed = unexpected_gate_check
        scene._roundabout_update_gate_events(12.0)
        self.assertEqual(scene.rb_phase, "COMPLETE")

    def test_auxiliary_exit_gate_does_not_fail_before_planned_exit(self):
        scene = SCENE_MODULE.EgoRouteFollowScene.__new__(
            SCENE_MODULE.EgoRouteFollowScene)
        scene.rb_phase = "IN_ROUNDABOUT"
        scene.rb_entry_crossed = True
        scene.roundabout_exit_gates = {1: "auxiliary", 2: "planned"}
        scene.roundabout_planned_exit = 2
        scene.rb_wrong_exit = None
        scene.rb_correct_exit_crossed = False
        scene.rb_indicator_observable = False
        scene.rb_exit_indicator_observed = None
        scene.ego = types.SimpleNamespace(
            get_location=lambda: _Location(10.0, 0.0, 0.0))
        events = []
        scene._roundabout_record_event = lambda *args, **kwargs: events.append(
            (args, kwargs))
        scene._roundabout_transition = lambda phase, now, **kwargs: setattr(
            scene, "rb_phase", phase)

        scene._roundabout_gate_crossed = (
            lambda actor, key, gate: gate == "auxiliary")
        scene._roundabout_update_gate_events(12.0)

        self.assertEqual(scene.rb_phase, "IN_ROUNDABOUT")
        self.assertIsNone(scene.rb_wrong_exit)
        self.assertFalse(scene.rb_correct_exit_crossed)

        scene._roundabout_gate_crossed = (
            lambda actor, key, gate: gate == "planned")
        scene._roundabout_update_gate_events(13.0)

        self.assertEqual(scene.rb_phase, "EXITED")
        self.assertTrue(scene.rb_correct_exit_crossed)

    def test_collision_before_release_invalidates_the_fixture(self):
        scene = SCENE_MODULE.EgoRouteFollowScene.__new__(
            SCENE_MODULE.EgoRouteFollowScene)
        scene.is_roundabout_2b = True
        scene.rb_trial_start_sim_time = None
        scene.rb_collision_recorded = False
        scene.rb_collision_vt1 = False
        scene.rb_collision_vt2 = False
        scene.rb_infrastructure_collision = False
        scene.rb_other_collision = False
        scene.vt1_actor = None
        scene.vt2_actor = None
        invalidated = []
        scene._roundabout_invalidate = lambda now, reason: invalidated.append(reason)
        scene._roundabout_record_event = lambda *args, **kwargs: None
        event = types.SimpleNamespace(timestamp=4.0, frame=80, other_actor=None)

        scene.record_collision(event)

        self.assertEqual(invalidated, ["collision_before_trial_start"])
        self.assertTrue(scene.rb_collision_recorded)

    def test_delayed_pretrial_sensor_event_uses_event_timestamp(self):
        scene = SCENE_MODULE.EgoRouteFollowScene.__new__(
            SCENE_MODULE.EgoRouteFollowScene)
        scene.is_roundabout_2b = True
        scene.rb_trial_start_sim_time = 5.0
        scene.rb_collision_recorded = False
        scene.rb_collision_vt1 = False
        scene.rb_collision_vt2 = False
        scene.rb_infrastructure_collision = False
        scene.rb_other_collision = False
        scene.vt1_actor = None
        scene.vt2_actor = None
        invalidated = []
        scene._roundabout_invalidate = lambda now, reason: invalidated.append(reason)
        scene._roundabout_record_event = lambda *args, **kwargs: None

        scene.record_collision(types.SimpleNamespace(
            timestamp=4.95, frame=99, other_actor=None))

        self.assertEqual(invalidated, ["collision_before_trial_start"])

    def test_result_cannot_pass_before_vt1_crosses_exit_one(self):
        scene = self._result_scene()

        result = scene.get_result()

        self.assertFalse(result["pass"])
        self.assertIn("vt1_exit_1_not_observed", result["failure_reasons"])

    def test_collision_failure_is_not_relabelled_as_vt1_fixture_invalid(self):
        scene = self._result_scene()
        scene.rb_collision_recorded = True
        scene.rb_events = [{"event": "COLLISION"}]
        scene.rb_invalid_reasons = [
            "vt1_exit_1_not_observed_before_fixture_timeout"]

        result = scene.get_result()

        self.assertTrue(result["trial_valid"])
        self.assertFalse(result["pass"])
        self.assertIn("collision", result["failure_reasons"])
        self.assertNotIn(
            "vt1_exit_1_not_observed", result["failure_reasons"])

    def test_post_release_collision_overrides_same_frame_secondary_invalids(self):
        scene = self._result_scene()
        scene.rb_collision_recorded = True
        scene.rb_valid_collision_time = 10.0
        scene.rb_events = [{"event": "COLLISION", "sim_time": 10.0}]
        scene.rb_invalid_reasons = [
            "vt1_speed_invalid_at_vut_entry",
            "speed_limit_not_observable_during_trial",
        ]
        scene.rb_invalid_events = [
            {"reason": reason, "sim_time": 10.0}
            for reason in scene.rb_invalid_reasons
        ]
        scene.rb_speed_limit_unobservable_gap = True

        result = scene.get_result()

        self.assertTrue(result["trial_valid"])
        self.assertFalse(result["pass"])
        self.assertEqual(result["failure_reasons"], ["collision"])

    def test_speed_limit_evidence_gap_invalidates_result(self):
        scene = self._result_scene()
        scene.rb_vt1_exit1_crossed = True
        scene.rb_speed_limit_unobservable_gap = True

        result = scene.get_result()

        self.assertFalse(result["trial_valid"])
        self.assertIsNone(result["pass"])
        self.assertIn(
            "speed_limit_not_observable_during_trial", result["invalid_reasons"])


if __name__ == "__main__":
    unittest.main()
