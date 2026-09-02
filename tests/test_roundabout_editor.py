import importlib.util
import json
import math
import os
import pathlib
import sys
import tempfile
import types
import unittest
from unittest import mock

from roundabout_2b import (
    canonical_hash,
    validate_roundabout_config,
)


def _load_editor_with_carla_stub():
    carla = types.ModuleType("carla")
    previous = sys.modules.get("carla")
    sys.modules["carla"] = carla
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    try:
        path = pathlib.Path(__file__).resolve().parents[1] / "waypoints.py"
        spec = importlib.util.spec_from_file_location(
            "_roundabout_editor_serialization_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if previous is None:
            sys.modules.pop("carla", None)
        else:
            sys.modules["carla"] = previous


EDITOR_MODULE = _load_editor_with_carla_stub()


class _Location:
    def __init__(self, x, y=0.0, z=0.0):
        self.x, self.y, self.z = float(x), float(y), float(z)


class _Waypoint:
    def __init__(self, x, road_id=1, lane_id=1, y=0.0):
        self.transform = types.SimpleNamespace(
            location=_Location(x, y, 0.0),
            rotation=types.SimpleNamespace(yaw=0.0),
        )
        self.transform.get_forward_vector = lambda: types.SimpleNamespace(
            x=1.0, y=0.0, z=0.0)
        self.road_id = int(road_id)
        self.section_id = 0
        self.lane_id = int(lane_id)
        self.s = float(x)
        self.lane_width = 3.5
        self.is_junction = False


def _gate(x, number=None, road_id=1):
    gate = {
        "center": {"x": float(x), "y": 0.0, "z": 0.2},
        "left": {"x": float(x), "y": 2.0, "z": 0.2},
        "right": {"x": float(x), "y": -2.0, "z": 0.2},
        "forward": {"x": 1.0, "y": 0.0, "z": 0.0},
        "approach_yaw": 0.0,
        "width_m": 4.0,
        "road_id": int(road_id),
        "section_id": 0,
        "lane_id": 1,
    }
    if number is not None:
        gate["number"] = int(number)
        gate["allowed_lanes"] = [{
            "road_id": int(road_id), "section_id": 0, "lane_id": 1,
        }]
    return gate


def _analysis():
    arms = [
        {
            "arm_id": "arm-{}".format(index),
            "inbound_lane_count": 1,
            "outbound_lane_count": 1,
            "inbound_lanes": [{
                "road_id": index, "section_id": 0, "lane_id": 1,
            }],
            "outbound_lanes": [{
                "road_id": index, "section_id": 0, "lane_id": 1,
            }],
        }
        for index in (1, 2, 3)
    ]
    topology_core = {
        "map_name": "FakeRoundaboutMap",
        "arm_count": 3,
        "arms": arms,
        "vut_entry_arm_id": "arm-1",
        "downstream_entry_arm_id": "arm-2",
        "exit_arm_ids": {"1": "arm-1", "2": "arm-2", "3": "arm-3"},
        "circulation_order": ["arm-1", "arm-2", "arm-3"],
        "ring_center": {"x": 0.0, "y": 0.0},
        "ring_radius_m": 20.0,
        "travel_direction": "counterclockwise",
        "operator_confirmation": {
            "confirmed": True,
            "method": "test_fixture",
        },
        "vt1_initial_upstream_arc_m": 40.0,
        "vt1_initial_minimum_upstream_arc_m": 30.0,
        "vt1_entry_upstream_minimum_m": 3.0,
        "vut_approach_distance_m": 5.0,
        "vut_start_gate_signed_m": -5.0,
    }
    topology_hash = canonical_hash(topology_core)
    topology = dict(topology_core)
    topology.update({
        "verified": True,
        "topology_hash": topology_hash,
        "detection_method": "fake_carla_connectivity_test",
    })
    downstream = _gate(0.0, road_id=2)
    downstream.update({
        "arm_id": "arm-2",
        "inbound_lanes": [{"road_id": 2, "section_id": 0, "lane_id": 1}],
    })
    return {
        "planned_exit": 2,
        "entry_gate": _gate(0.0),
        "exit_gates": {
            "1": _gate(10.0, number=1, road_id=1),
            "2": _gate(20.0, number=2, road_id=2),
            "3": _gate(30.0, number=3, road_id=3),
        },
        "downstream_entry": downstream,
        "topology": topology,
        "topology_hash": topology_hash,
        "vut_dense": [
            _Waypoint(-5.0), _Waypoint(0.0), _Waypoint(20.0, road_id=2),
            _Waypoint(22.0, road_id=2),
        ],
        "vut_route_options": [4, 3, 2, 4],
        "vt1_dense": [
            _Waypoint(-20.0), _Waypoint(10.0), _Waypoint(12.0),
        ],
        "vt1_route_options": [4, 2, 4],
        "vt1": {"x": -20.0, "y": 0.0, "z": 0.0, "yaw": 0.0},
        "vt2": {"x": -5.0, "y": 0.0, "z": 0.0, "yaw": 0.0},
        "vt2_waypoint": _Waypoint(-5.0, road_id=2, lane_id=1),
        "downstream_arm": {"arm_id": "arm-2"},
        "circle": {"radius": 20.0},
        "vt1_upstream_arc_m": 40.0,
        "vt1_initial_upstream_minimum_m": 30.0,
        "vt1_entry_upstream_minimum_m": 3.0,
        "vt1_setup_budget_s": 2.0,
        "vt1_timing_buffer_m": 2.0,
        "vut_approach_speed_assumption_kmh": 15.0,
        "vut_approach_time_budget_s": 15.0,
        "vut_approach_distance_m": 5.0,
        "vut_start_entry_margin_m": 3.0,
        "speed_limit_by_road_id": {"1": 30.0, "2": 30.0},
        "speed_limit_source": "fake_opendrive",
    }


class RoundaboutEditorSerializationTest(unittest.TestCase):
    def test_map_bound_topology_cache_round_trip_and_xodr_identity(self):
        seeds = [{
            "arm_id": "arm_01",
            "inbound": {
                "gate": _gate(1.0, road_id=1),
                "lane": {"road_id": 1, "section_id": 0, "lane_id": 1},
            },
            "outbound": {
                "gate": _gate(2.0, road_id=2),
                "lane": {"road_id": 2, "section_id": 0, "lane_id": 1},
            },
        }]
        with tempfile.TemporaryDirectory() as directory:
            writer = EDITOR_MODULE.CarlaMapEditor0916.__new__(
                EDITOR_MODULE.CarlaMapEditor0916)
            writer.map = types.SimpleNamespace(
                name="/Game/Maps/STF-2-b",
                to_opendrive=lambda: "<OpenDRIVE id='same-map'/>")
            writer.roundabout_topology_cache_dir = directory
            writer.roundabout_topology_seeds = seeds
            saved_path = writer._save_roundabout_topology_cache()

            self.assertTrue(pathlib.Path(saved_path).is_file())
            document = json.loads(pathlib.Path(saved_path).read_text("utf-8"))
            self.assertEqual(document["map_name"], "/Game/Maps/STF-2-b")
            self.assertEqual(len(document["opendrive_sha256"]), 64)

            reader = EDITOR_MODULE.CarlaMapEditor0916.__new__(
                EDITOR_MODULE.CarlaMapEditor0916)
            reader.map = writer.map
            reader.roundabout_topology_cache_dir = directory
            reader.roundabout_topology_seeds = []
            reader.roundabout_topology_confirmed = False
            reader._feedback = lambda *args, **kwargs: None
            review = {"arms": [], "arm_count": 1, "lane_count": 2, "warnings": []}
            reader._build_roundabout_topology_review = lambda: (review, [])

            self.assertTrue(reader._load_roundabout_topology_cache())
            self.assertEqual(reader.roundabout_topology_seeds, seeds)
            self.assertTrue(reader.roundabout_topology_review_ready)
            self.assertFalse(reader.roundabout_topology_confirmed)

            reader.map = types.SimpleNamespace(
                name="/Game/Maps/STF-2-b",
                to_opendrive=lambda: "<OpenDRIVE id='changed-map'/>")
            reader.roundabout_topology_seeds = []
            self.assertFalse(reader._load_roundabout_topology_cache())
            self.assertEqual(reader.roundabout_topology_seeds, [])

    def test_v_t_y_roles_share_ctrl_left_placement_dispatch(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.selected_mode = None
        editor.selected_agent_idx = -1
        editor.actor_points = []
        messages = []
        editor._feedback = lambda message, error=False: messages.append(
            (message, error))
        calls = []
        editor.add_roundabout_vut = lambda x, y: calls.append(("vut", x, y)) or True
        editor.add_roundabout_actor = lambda x, y: calls.append(
            (editor.roundabout_place_role, x, y)) or True

        for role in ("vut", "vt1", "vt2"):
            editor.set_roundabout_role(role)
            self.assertTrue(editor.place_roundabout_selected_role(1.0, 2.0))

        self.assertEqual(
            calls,
            [("vut", 1.0, 2.0), ("vt1", 1.0, 2.0), ("vt2", 1.0, 2.0)])
        self.assertTrue(all("右键放置" not in message for message, _ in messages))

    def test_mouse_zoom_is_bounded_and_keeps_cursor_world_anchor(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.zoom = 15.0
        editor.offset_x = 600.0
        editor.offset_y = 400.0
        anchor = (731, 287)
        before = editor.screen_to_world(*anchor)

        editor._zoom_at(*anchor, 100)

        self.assertEqual(editor.zoom, EDITOR_MODULE.MAX_ZOOM)
        after = editor.screen_to_world(*anchor)
        self.assertAlmostEqual(before[0], after[0], places=9)
        self.assertAlmostEqual(before[1], after[1], places=9)

        editor._zoom_at(*anchor, -200)
        self.assertEqual(editor.zoom, EDITOR_MODULE.MIN_ZOOM)
        after_zoom_out = editor.screen_to_world(*anchor)
        self.assertAlmostEqual(before[0], after_zoom_out[0], places=9)
        self.assertAlmostEqual(before[1], after_zoom_out[1], places=9)

    def test_far_offscreen_waypoints_are_not_sent_to_pygame_draw(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.zoom = EDITOR_MODULE.MAX_ZOOM
        editor.offset_x = 600.0
        editor.offset_y = 400.0
        editor.screen = types.SimpleNamespace(get_size=lambda: (1200, 800))
        editor.waypoints = [_Waypoint(1_000_000.0)]
        editor._waypoint_is_signal_route = lambda waypoint: False

        with mock.patch.object(EDITOR_MODULE.pygame.draw, "circle") as draw_circle, \
                mock.patch.object(EDITOR_MODULE.pygame.draw, "line") as draw_line:
            editor.draw_waypoints()

        draw_circle.assert_not_called()
        draw_line.assert_not_called()

    def test_roundabout_zoom_out_does_not_create_grey_waypoint_bands(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.is_roundabout_2b = True
        editor.zoom = EDITOR_MODULE.MIN_ZOOM
        editor.offset_x = 600.0
        editor.offset_y = 400.0
        editor.screen = EDITOR_MODULE.pygame.Surface((1200, 800))
        editor.waypoints = [_Waypoint(float(x)) for x in range(101)]
        editor._waypoint_is_signal_route = lambda waypoint: False

        with mock.patch.object(EDITOR_MODULE.pygame.draw, "circle") as draw_circle, \
                mock.patch.object(EDITOR_MODULE.pygame.draw, "line") as draw_line:
            editor.draw_waypoints()

        draw_circle.assert_not_called()
        self.assertLess(
            draw_line.call_count, 10,
            "zoomed-out 2.b lane arrows must be screen-space sampled")
        self.assertGreater(draw_line.call_count, 0)

    def test_roundabout_direction_marker_has_an_arrowhead(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.screen = EDITOR_MODULE.pygame.Surface((200, 120))

        with mock.patch.object(EDITOR_MODULE.pygame.draw, "line") as draw_line:
            editor._draw_direction_arrow((0, 255, 0), (20, 60), 0.0, width=2)

        self.assertEqual(draw_line.call_count, 3)
        shaft = draw_line.call_args_list[0].args
        left_wing = draw_line.call_args_list[1].args
        right_wing = draw_line.call_args_list[2].args
        self.assertGreater(shaft[3][0], shaft[2][0])
        self.assertEqual(left_wing[2], shaft[3])
        self.assertEqual(right_wing[2], shaft[3])
        self.assertNotEqual(left_wing[3][1], right_wing[3][1])

    def test_topology_gate_stays_fixed_width_during_large_zoom_and_pan(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.zoom = 100.0
        editor.offset_x = 600.0
        editor.offset_y = 400.0
        editor.screen = EDITOR_MODULE.pygame.Surface((1200, 800))
        EDITOR_MODULE.pygame.font.init()
        editor.font = EDITOR_MODULE.pygame.font.SysFont(None, 18)
        gate = {
            "left": {"x": -1.75, "y": 0.0},
            "right": {"x": 1.75, "y": 0.0},
            "center": {"x": 0.0, "y": 0.0},
            "approach_yaw": 90.0,
        }

        with mock.patch.object(editor, "_draw_clipped_line") as draw_line, \
                mock.patch.object(editor, "_draw_direction_arrow"):
            editor._draw_roundabout_topology_marker(
                gate, (0, 255, 0), "A01 IN")

        left, right = draw_line.call_args_list[0].args[1:3]
        self.assertAlmostEqual(math.dist(left, right), 48.0, places=5)

    def test_huge_offscreen_topology_gate_is_fully_culled(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.zoom = 100.0
        editor.offset_x = 600.0
        editor.offset_y = 400.0
        editor.screen = EDITOR_MODULE.pygame.Surface((1200, 800))
        EDITOR_MODULE.pygame.font.init()
        editor.font = EDITOR_MODULE.pygame.font.SysFont(None, 18)
        gate = {
            "left": {"x": -1_000_001.75, "y": 0.0},
            "right": {"x": -999_998.25, "y": 0.0},
            "center": {"x": -1_000_000.0, "y": 0.0},
            "approach_yaw": 90.0,
        }

        with mock.patch.object(EDITOR_MODULE.pygame.draw, "line") as draw_line, \
                mock.patch.object(EDITOR_MODULE.pygame.draw, "circle") as draw_circle:
            editor._draw_roundabout_topology_marker(
                gate, (0, 255, 0), "A05 IN")

        draw_line.assert_not_called()
        draw_circle.assert_not_called()

    def test_huge_crossing_line_is_clipped_to_actual_viewport(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.screen = EDITOR_MODULE.pygame.Surface((1200, 800))

        with mock.patch.object(EDITOR_MODULE.pygame.draw, "line") as draw_line:
            editor._draw_clipped_line(
                (0, 255, 0), (-1_000_000_000.0, 400.0),
                (1_000_000_000.0, 400.0), 4)

        draw_line.assert_called_once()
        self.assertEqual(draw_line.call_args.args[2], (0, 400))
        self.assertEqual(draw_line.call_args.args[3], (1199, 400))

    def test_route_chord_with_both_anchors_offscreen_is_not_drawn(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.screen = EDITOR_MODULE.pygame.Surface((1200, 800))

        with mock.patch.object(editor, "_draw_clipped_line") as draw_line:
            editor._draw_clipped_polyline(
                [(-1000, 760), (2200, 760)], (0, 255, 128), 4)

        draw_line.assert_not_called()

    def test_route_segment_remains_visible_when_one_anchor_is_near_view(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.screen = EDITOR_MODULE.pygame.Surface((1200, 800))

        with mock.patch.object(editor, "_draw_clipped_line") as draw_line:
            editor._draw_clipped_polyline(
                [(600, 400), (2200, 760)], (0, 255, 128), 4)

        draw_line.assert_called_once()

    def test_zoomed_route_tail_is_bounded_instead_of_spanning_viewport(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.screen = EDITOR_MODULE.pygame.Surface((1200, 800))

        with mock.patch.object(editor, "_draw_clipped_line") as draw_line:
            editor._draw_clipped_polyline(
                [(600, 400), (5000, 400)], (0, 225, 255), 4)

        draw_line.assert_called_once()
        drawn_start, drawn_end = draw_line.call_args.args[1:3]
        self.assertEqual(drawn_start, (600, 400))
        self.assertLessEqual(
            math.dist(drawn_start, drawn_end),
            EDITOR_MODULE.MAX_ROUTE_VISIBLE_TAIL_PX + 1e-6)

        with mock.patch.object(editor, "_draw_clipped_line") as draw_line:
            editor._draw_clipped_polyline(
                [(-100, 400), (1300, 400)], (0, 225, 255), 4)
        draw_line.assert_not_called()

    def test_analysis_gate_is_fixed_width_and_culled_by_center(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.zoom = 100.0
        editor.offset_x = 600.0
        editor.offset_y = 400.0
        editor.screen = EDITOR_MODULE.pygame.Surface((1200, 800))
        EDITOR_MODULE.pygame.font.init()
        editor.font = EDITOR_MODULE.pygame.font.SysFont(None, 18)
        gate = {
            "left": {"x": -1.75, "y": 0.0},
            "right": {"x": 1.75, "y": 0.0},
            "center": {"x": 0.0, "y": 0.0},
            "approach_yaw": 90.0,
        }

        with mock.patch.object(editor, "_draw_clipped_line") as draw_line:
            editor._draw_gate(gate, (0, 255, 0), "ENTRY")

        left, right = draw_line.call_args.args[1:3]
        self.assertAlmostEqual(math.dist(left, right), 48.0, places=5)

        gate["center"] = {"x": 0.0, "y": -1000.0}
        gate["left"] = {"x": -1.75, "y": -1000.0}
        gate["right"] = {"x": 1.75, "y": -1000.0}
        with mock.patch.object(editor, "_draw_clipped_line") as draw_line:
            editor._draw_gate(gate, (0, 255, 0), "ENTRY")
        draw_line.assert_not_called()

    def test_roundabout_route_visual_connects_actor_to_first_anchor(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.zoom = 1.0
        editor.offset_x = 0.0
        editor.offset_y = 100.0
        editor.screen = EDITOR_MODULE.pygame.Surface((200, 120))
        EDITOR_MODULE.pygame.font.init()
        editor.font = EDITOR_MODULE.pygame.font.SysFont(None, 18)
        actor_start = {"x": 10.0, "y": 10.0}
        anchors = [{"x": 30.0, "y": 10.0}]

        with mock.patch.object(editor, "_draw_clipped_polyline") as draw_polyline:
            editor._draw_route(
                anchors, (0, 255, 0), "V", width=4,
                actor_start=actor_start)

        drawn_points = draw_polyline.call_args.args[0]
        self.assertEqual(drawn_points[0], editor.world_to_screen(10.0, 10.0))
        self.assertEqual(drawn_points[1], editor.world_to_screen(30.0, 10.0))

    def test_roundabout_densifier_uses_bounded_forward_lane_graph(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.is_roundabout_2b = True
        nodes = [_Waypoint(float(index)) for index in range(11)]
        for index, node in enumerate(nodes):
            node.next = (lambda _distance, index=index:
                         [nodes[index + 1]] if index + 1 < len(nodes) else [])
        editor.map = types.SimpleNamespace(get_waypoint=lambda location, **kwargs:
                                           nodes[0] if location.x < 5.0 else nodes[-1])
        editor._get_global_route_planner = mock.Mock(
            side_effect=AssertionError("2.b must not use the global planner"))
        lane_type = types.SimpleNamespace(Driving=1)

        with mock.patch.object(
                EDITOR_MODULE.carla, "Location", _Location, create=True), \
                mock.patch.object(
                    EDITOR_MODULE.carla, "LaneType", lane_type, create=True):
            dense, options = editor._densify_route(
                [{"x": 10.0, "y": 0.0, "z": 0.0}],
                actor_start={"x": 0.0, "y": 0.0, "z": 0.0})

        self.assertEqual([item.transform.location.x for item in dense],
                         list(map(float, range(8))))
        self.assertLessEqual(
            abs(dense[-1].transform.location.x - 10.0),
            EDITOR_MODULE.ROUNDABOUT_LOCAL_TRACE_GOAL_TOLERANCE_M)
        self.assertEqual(len(options), len(dense))
        editor._get_global_route_planner.assert_not_called()

    def test_roundabout_local_trace_rejects_long_detour_to_near_anchor(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        nodes = [_Waypoint(0.0, y=float(index)) for index in range(56)]
        for index, node in enumerate(nodes):
            node.s = float(index)
            node.next = (lambda _distance, index=index:
                         [nodes[index + 1]] if index + 1 < len(nodes) else [])
        target = _Waypoint(10.0)

        with mock.patch.object(
                EDITOR_MODULE.carla, "Location", _Location, create=True):
            with self.assertRaises(
                    EDITOR_MODULE.RoundaboutRouteTraceError) as captured:
                editor._bounded_forward_trace_segment(
                    nodes[0], {"x": 10.0, "y": 0.0, "z": 0.0}, target)

        self.assertIn("最多允许搜索50.0m", str(captured.exception))
        self.assertIn("不会改用全局绕行", str(captured.exception))

    def test_roundabout_trace_does_not_accept_a_nearby_wrong_lane(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        start = _Waypoint(0.0, road_id=1, lane_id=1)
        target = _Waypoint(1.0, road_id=9, lane_id=2)
        start.next = lambda _distance: []

        with mock.patch.object(
                EDITOR_MODULE.carla, "Location", _Location, create=True):
            with self.assertRaises(EDITOR_MODULE.RoundaboutRouteTraceError):
                editor._bounded_lane_graph_trace_segment(
                    start, {"x": 1.0, "y": 0.0, "z": 0.0}, target)

    def test_roundabout_anchor_is_restored_by_exact_xodr_identity(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        exact = _Waypoint(18.0, road_id=24, lane_id=-3)
        get_xodr = mock.Mock(return_value=exact)
        get_xy = mock.Mock(side_effect=AssertionError(
            "an identified anchor must not be re-snapped by XY"))
        editor.map = types.SimpleNamespace(
            get_waypoint_xodr=get_xodr, get_waypoint=get_xy)

        resolved = editor._resolve_roundabout_anchor_waypoint({
            "x": 17.6, "y": 2.0, "z": 0.2, "yaw": 0.0,
            "road_id": 24, "section_id": 0, "lane_id": -3, "s": 18.0,
        })

        self.assertIs(resolved, exact)
        get_xodr.assert_called_once_with(24, -3, 18.0)
        get_xy.assert_not_called()

    def test_roundabout_lane_graph_search_uses_legal_left_lane_change(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        driving = object()
        lane_change = types.SimpleNamespace(Left=2, Right=1)
        lane_type = types.SimpleNamespace(Driving=driving)
        current_lane = [_Waypoint(float(index), lane_id=1, y=0.0)
                        for index in range(11)]
        left_lane = [_Waypoint(float(index), lane_id=2, y=3.5)
                     for index in range(11)]
        for lane in (current_lane, left_lane):
            for index, node in enumerate(lane):
                node.lane_type = driving
                node.lane_change = 0
                node.left_lane_marking = types.SimpleNamespace(
                    lane_change=0, type="Broken")
                node.right_lane_marking = types.SimpleNamespace(
                    lane_change=0, type="Broken")
                node.next = (lambda distance, lane=lane, index=index: [
                    lane[min(
                        len(lane) - 1,
                        index + max(1, int(round(float(distance)))))]
                ] if index + 1 < len(lane) else [])
                node.get_left_lane = lambda: None
                node.get_right_lane = lambda: None
        current_lane[0].lane_change = 2
        current_lane[0].left_lane_marking = types.SimpleNamespace(
            lane_change=2, type="Broken")
        current_lane[0].get_left_lane = lambda: left_lane[0]

        with mock.patch.object(
                EDITOR_MODULE.carla, "Location", _Location, create=True), \
                mock.patch.object(
                    EDITOR_MODULE.carla, "LaneType", lane_type, create=True), \
                mock.patch.object(
                    EDITOR_MODULE.carla, "LaneChange", lane_change, create=True):
            route, diagnostics = editor._bounded_lane_graph_trace_segment(
                current_lane[0],
                {"x": 10.0, "y": 3.5, "z": 0.0}, left_lane[-1])

        self.assertIn(2, [waypoint.lane_id for waypoint in route])
        first_left = next(
            waypoint for waypoint in route if waypoint.lane_id == 2)
        self.assertGreaterEqual(first_left.transform.location.x, 8.0)
        self.assertEqual(diagnostics["lane_changes"], 1)
        self.assertGreater(diagnostics["lateral_edges_considered"], 0)
        self.assertIn(5, editor._fallback_route_options(route))

    def test_roundabout_lane_graph_never_crosses_explicit_solid_marking(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        driving = object()
        lane_change = types.SimpleNamespace(Left=2, Right=1)
        lane_type = types.SimpleNamespace(Driving=driving)
        start = _Waypoint(0.0, lane_id=1, y=0.0)
        adjacent = _Waypoint(0.0, lane_id=2, y=3.5)
        target = _Waypoint(10.0, lane_id=2, y=3.5)
        for waypoint in (start, adjacent, target):
            waypoint.lane_type = driving
            waypoint.next = lambda _distance: []
            waypoint.get_left_lane = lambda: None
            waypoint.get_right_lane = lambda: None
        start.lane_change = 2
        start.left_lane_marking = types.SimpleNamespace(
            lane_change=2, type="Solid")
        start.get_left_lane = lambda: adjacent

        with mock.patch.object(
                EDITOR_MODULE.carla, "Location", _Location, create=True), \
                mock.patch.object(
                    EDITOR_MODULE.carla, "LaneType", lane_type, create=True), \
                mock.patch.object(
                    EDITOR_MODULE.carla, "LaneChange", lane_change, create=True):
            with self.assertRaises(
                    EDITOR_MODULE.RoundaboutRouteTraceError) as captured:
                editor._bounded_lane_graph_trace_segment(
                    start, {"x": 10.0, "y": 3.5, "z": 0.0}, target)

        self.assertIn("0条合法左右变道边", str(captured.exception))
        self.assertIn("实线", str(captured.exception))

    def test_roundabout_route_uses_final_exit_crossing(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        route = [_Waypoint(x) for x in (0.0, 6.0, 10.0, 16.0)]
        arms = [
            {"arm_id": "arm_01", "outbound": [{"gate": _gate(5.0)}]},
            {"arm_id": "arm_02", "outbound": [{"gate": _gate(15.0)}]},
        ]

        exit_arm, crossing_index = editor._route_exit_arm(
            route, arms, route_label="VUT")

        self.assertEqual(exit_arm["arm_id"], "arm_02")
        self.assertEqual(crossing_index, 3)

    def test_physical_out_gate_crossing_is_not_vetoed_by_lane_id(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        route = [
            _Waypoint(0.0, road_id=9, lane_id=-1),
            _Waypoint(10.0, road_id=9, lane_id=-1),
        ]
        arm = {
            "arm_id": "arm_02",
            "outbound": [{
                "lane_key": (5, 0, -1),
                "waypoint": _Waypoint(5.0, road_id=5, lane_id=-1),
                "gate": _gate(5.0, road_id=5),
            }],
        }

        exit_arm, crossing_index = editor._route_exit_arm(
            route, [arm], route_label="VUT")

        self.assertEqual(exit_arm["arm_id"], "arm_02")
        self.assertEqual(crossing_index, 1)

    def test_crossing_out_gate_along_its_reviewed_lane_is_an_exit(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        route = [
            _Waypoint(0.0, road_id=5, lane_id=-1),
            _Waypoint(10.0, road_id=5, lane_id=-1),
        ]
        arm = {
            "arm_id": "arm_02",
            "outbound": [{
                "lane_key": (5, 0, -1),
                "waypoint": _Waypoint(5.0, road_id=5, lane_id=-1),
                "gate": _gate(5.0, road_id=5),
            }],
        }

        exit_arm, crossing_index = editor._route_exit_arm(
            route, [arm], route_label="VUT")

        self.assertEqual(exit_arm["arm_id"], "arm_02")
        self.assertEqual(crossing_index, 1)

    def test_confirmed_route_preview_draws_dense_path_and_direction_arrows(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.zoom = 5.0
        editor.offset_x = 20.0
        editor.offset_y = 100.0
        editor.screen = EDITOR_MODULE.pygame.Surface((300, 200))
        cache = {
            "payload": [
                {"x": float(index), "y": 0.0, "z": 0.0, "yaw": 0.0}
                for index in range(21)
            ],
        }

        with mock.patch.object(editor, "_draw_clipped_polyline") as draw_route, \
                mock.patch.object(editor, "_draw_direction_arrow") as draw_arrow:
            editor._draw_confirmed_roundabout_route(
                cache, EDITOR_MODULE.ROUNDABOUT_COLOR_VUT)

        draw_route.assert_called_once()
        self.assertGreater(draw_arrow.call_count, 0)

    def test_roundabout_map_labels_follow_help_toggle(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.is_roundabout_2b = True
        editor.roundabout_help_expanded = False
        editor.roundabout_topology_confirmed = False
        self.assertTrue(
            editor._roundabout_map_labels_visible(),
            "STEP 1 marking/review must always identify IN and OUT in text")

        editor.roundabout_topology_confirmed = True
        self.assertFalse(editor._roundabout_map_labels_visible())

        editor.roundabout_help_expanded = True
        self.assertTrue(editor._roundabout_map_labels_visible())

        editor.is_roundabout_2b = False
        editor.roundabout_help_expanded = False
        self.assertTrue(editor._roundabout_map_labels_visible())

    def test_collapsed_roundabout_hides_marker_and_route_text(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.is_roundabout_2b = True
        editor.roundabout_help_expanded = False
        editor.roundabout_topology_confirmed = True
        editor.zoom = 1.0
        editor.offset_x = 100.0
        editor.offset_y = 100.0
        editor.screen = EDITOR_MODULE.pygame.Surface((300, 200))
        editor.font = mock.Mock()
        gate = {
            "left": {"x": -1.75, "y": 0.0},
            "right": {"x": 1.75, "y": 0.0},
            "center": {"x": 0.0, "y": 0.0},
            "approach_yaw": 0.0,
        }

        with mock.patch.object(editor, "_draw_clipped_line"), \
                mock.patch.object(editor, "_draw_direction_arrow"), \
                mock.patch.object(editor, "_draw_clipped_polyline"):
            editor._draw_roundabout_topology_marker(
                gate, EDITOR_MODULE.ROUNDABOUT_COLOR_IN, "A01 IN")
            editor._draw_gate(
                gate, EDITOR_MODULE.ROUNDABOUT_COLOR_EXIT_1, "EXIT 1")
            editor._draw_route(
                [{"x": 10.0, "y": 0.0}, {"x": 20.0, "y": 0.0}],
                EDITOR_MODULE.ROUNDABOUT_COLOR_VUT, "V")

        editor.font.render.assert_not_called()

    def test_roundabout_help_panel_is_compact_by_default(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.is_roundabout_2b = True
        editor.ego_point = None
        editor.ego_route_points = []
        editor.actor_points = []
        editor.selected_agent_idx = -1
        editor.selected_mode = None
        editor.roundabout_place_role = "vt1"
        editor.roundabout_capable = True
        editor.roundabout_analysis = None
        editor.roundabout_errors = ["missing VUT", "missing VT1", "missing VT2"]
        editor.roundabout_warnings = []
        editor.roundabout_history = []
        editor.roundabout_help_expanded = False
        editor.last_feedback = "follow current step"
        editor.last_feedback_error = False
        editor.screen = EDITOR_MODULE.pygame.Surface((1200, 800))
        editor.screen.fill((255, 255, 255))
        EDITOR_MODULE.pygame.font.init()
        editor.font, editor.font_supports_cjk = editor._load_editor_font(22)
        editor.panel_font, panel_cjk = editor._load_editor_font(16)
        editor.font_supports_cjk = editor.font_supports_cjk and panel_cjk
        editor._ensure_roundabout_analysis = lambda force=False: None

        editor._draw_roundabout_panel()

        covered_rows = [
            y for y in range(editor.screen.get_height())
            if editor.screen.get_at((8, y))[:3] != (255, 255, 255)
        ]
        self.assertTrue(covered_rows)
        self.assertLess(max(covered_rows), 180)

    def test_initial_roundabout_panel_treats_missing_objects_as_pending(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        rendered = []

        class _PanelFont:
            def get_linesize(self):
                return 16

            def size(self, text):
                return (len(text) * 8, 16)

            def render(self, text, antialias, color):
                rendered.append(text)
                return EDITOR_MODULE.pygame.Surface((1, 1))

        editor.is_roundabout_2b = True
        editor.ego_point = None
        editor.ego_route_points = []
        editor.actor_points = []
        editor.selected_agent_idx = -1
        editor.selected_mode = None
        editor.roundabout_place_role = "vt1"
        editor.roundabout_capable = True
        editor.roundabout_analysis = None
        editor.roundabout_errors = ["missing VUT", "missing VT1"]
        editor.roundabout_warnings = []
        editor.roundabout_validation_attempted = False
        editor.roundabout_history = []
        editor.roundabout_help_expanded = True
        editor.last_feedback = "start editing"
        editor.last_feedback_error = False
        editor.screen = EDITOR_MODULE.pygame.Surface((1200, 800))
        editor.font = _PanelFont()
        editor.panel_font = _PanelFont()
        editor.font_supports_cjk = False
        editor._ensure_roundabout_analysis = lambda force=False: None

        editor._draw_roundabout_panel()

        self.assertTrue(any("IN PROGRESS" in text for text in rendered))
        self.assertFalse(any("SAVE BLOCKED" in text for text in rendered))
        self.assertFalse(any("missing VUT" in text for text in rendered))

    def test_compact_panel_prioritizes_wrapped_operation_failure_over_suggestion(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        rendered = []

        class _PanelFont:
            def get_linesize(self):
                return 16

            def size(self, text):
                return (len(text) * 8, 16)

            def render(self, text, antialias, color):
                rendered.append(text)
                return EDITOR_MODULE.pygame.Surface((1, 1))

        editor.is_roundabout_2b = True
        editor.ego_point = {"x": 0.0, "y": 0.0}
        editor.ego_route_points = [{"x": float(index), "y": 0.0} for index in range(7)]
        editor.actor_points = []
        editor.selected_agent_idx = -1
        editor.selected_mode = "ego"
        editor.roundabout_place_role = "vt1"
        editor.roundabout_capable = True
        editor.roundabout_branch_confirmed = True
        editor.roundabout_topology_confirmed = True
        editor.roundabout_topology_review_ready = False
        editor.roundabout_topology_seeds = []
        editor.roundabout_analysis = None
        editor.roundabout_errors = []
        editor.roundabout_warnings = []
        editor.roundabout_history = []
        editor.roundabout_help_expanded = False
        editor.roundabout_vut_route_confirmed = False
        editor.roundabout_vt1_route_confirmed = False
        editor.roundabout_vut_recommendation = {
            "entry_arm_id": "arm_02",
            "exit_gates": {
                "2": {"arm_id": "arm_04"},
                "3": {"arm_id": "arm_05"},
            },
        }
        editor.last_feedback = (
            "VUT路线无法确认：arm_01进口达到100m搜索上限；"
            "最接近拟合环处仍位于外侧，请检查详细诊断。")
        editor.last_feedback_error = True
        editor.screen = EDITOR_MODULE.pygame.Surface((1200, 800))
        editor.font = _PanelFont()
        editor.panel_font = _PanelFont()
        editor.font_supports_cjk = True

        editor._draw_roundabout_panel()

        self.assertTrue(any("操作/校验失败" in text for text in rendered))
        self.assertTrue(any("arm_01" in text for text in rendered))
        self.assertFalse(any(
            text.startswith("初步建议：") for text in rendered))

    def test_ring_trace_reports_distance_limit_and_geometry_metrics(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        nodes = [_Waypoint(x) for x in (100.0, 98.0, 96.0, 94.0)]
        for index, node in enumerate(nodes):
            node.next = lambda distance, index=index: (
                [nodes[index + 1]] if index + 1 < len(nodes) else [])
            node.previous = lambda distance: []

        trace = editor._trace_waypoint_to_ring(
            nodes[0], {"center": (0.0, 0.0), "radius": 20.0},
            direction=1, maximum_distance=4.0)
        message = editor._describe_ring_trace_failure(
            "arm_01", "进口", (1, 0, 1), (1, 0, 1), trace)

        self.assertFalse(trace["reached"])
        self.assertEqual(trace["reason"], "distance_limit")
        self.assertIn("固定距离上限", message)
        self.assertIn("拟合环半径20.0m", message)
        self.assertIn("切向指标", message)

    def test_entry_arm_association_reports_nearest_arm_and_60m_limit(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        nodes = [_Waypoint(x, road_id=9) for x in (100.0, 98.0, 96.0, 94.0)]
        target = _Waypoint(0.0, road_id=2)
        for index, node in enumerate(nodes):
            node.previous = lambda distance, index=index: (
                [nodes[index + 1]] if index + 1 < len(nodes) else [])
            node.next = lambda distance: []
        records = [{
            "lane_key": (target.road_id, target.section_id, target.lane_id),
            "waypoint": target,
        }]

        trace = editor._trace_waypoint_to_records(
            nodes[0], records, maximum_distance=4.0,
            trace_direction="backward")
        message = editor._describe_arm_association_failure(
            nodes[0], "inbound", [{
                "arm": {"arm_id": "arm_02"},
                "trace": trace,
            }], entry_source="route_curvature_fallback")

        self.assertFalse(trace["reached"])
        self.assertEqual(trace["reason"], "distance_limit")
        self.assertIn("最接近arm_02", message)
        self.assertIn("入口来源=route_curvature_fallback", message)
        self.assertIn("直线距离96.0m", message)

    def test_large_roundabout_arm_clustering_does_not_merge_nearby_roads(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        records = []
        for angle_deg, road_id in ((0.0, 1), (3.0, 1), (15.0, 2), (18.0, 2)):
            waypoint = _Waypoint(0.0, road_id=road_id)
            records.append({
                "angle": math.radians(angle_deg),
                "waypoint": waypoint,
            })
        clusters = editor._cluster_arm_records(records, ring_radius=80.0)
        self.assertEqual(len(clusters), 2)

    def test_divided_inbound_and_outbound_clusters_are_paired_as_one_arm(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)

        def record(direction, angle_deg, road_id):
            return {
                "direction": direction,
                "angle": math.radians(angle_deg),
                "waypoint": _Waypoint(0.0, road_id=road_id),
                "lane_key": (road_id, 0, 1),
                "initial_cluster": road_id,
            }

        clusters = [
            [record("inbound", 0.0, 1)],
            [record("outbound", 13.0, 2)],
            [record("inbound", 120.0, 3), record("outbound", 123.0, 4)],
        ]
        paired, repair_count = editor._pair_split_carriageway_clusters(
            clusters, ring_radius=60.0)

        self.assertEqual(repair_count, 1)
        self.assertEqual(len(paired), 2)
        self.assertIn(
            {"inbound", "outbound"},
            [{item["direction"] for item in cluster} for cluster in paired])

    def test_five_arm_global_pairing_handles_a_widely_offset_carriageway(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)

        def record(direction, angle_deg, road_id):
            return {
                "direction": direction,
                "angle": math.radians(angle_deg),
                "waypoint": _Waypoint(0.0, road_id=road_id),
                "lane_key": (road_id, 0, 1),
                "initial_cluster": road_id,
            }

        clusters = [
            [record("inbound", 0.0, 1)],
            [record("outbound", 35.0, 2)],
        ]
        road_id = 10
        for angle in (72.0, 144.0, 216.0, 288.0):
            clusters.append([
                record("inbound", angle, road_id),
                record("outbound", angle + 2.0, road_id + 1),
            ])
            road_id += 2

        paired, repair_count = editor._pair_split_carriageway_clusters(
            clusters, ring_radius=60.0)

        self.assertEqual(repair_count, 1)
        self.assertEqual(len(paired), 5)
        self.assertTrue(all(
            {item["direction"] for item in cluster} == {"inbound", "outbound"}
            for cluster in paired))

    def test_global_pairing_does_not_join_unrelated_distant_one_way_arms(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)

        def record(direction, angle_deg, road_id):
            return {
                "direction": direction,
                "angle": math.radians(angle_deg),
                "waypoint": _Waypoint(0.0, road_id=road_id),
                "lane_key": (road_id, 0, 1),
                "initial_cluster": road_id,
            }

        clusters = [
            [record("inbound", 0.0, 1)],
            [record("outbound", 60.0, 2)],
        ]
        for angle, road_id in ((90.0, 10), (180.0, 12), (270.0, 14)):
            clusters.append([
                record("inbound", angle, road_id),
                record("outbound", angle + 2.0, road_id + 1),
            ])

        paired, repair_count = editor._pair_split_carriageway_clusters(
            clusters, ring_radius=60.0)

        self.assertEqual(repair_count, 0)
        self.assertEqual(len(paired), 5)

    def test_exit_and_entry_order_use_separate_lane_mouth_angles(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        entry = {
            "arm_id": "entry", "inbound": [1], "outbound": [1],
            "inbound_angle": math.radians(0.0),
            "outbound_angle": math.radians(35.0),
        }
        first = {
            "arm_id": "first", "inbound": [1], "outbound": [1],
            "inbound_angle": math.radians(50.0),
            "outbound_angle": math.radians(20.0),
        }
        second = {
            "arm_id": "second", "inbound": [1], "outbound": [1],
            "inbound_angle": math.radians(120.0),
            "outbound_angle": math.radians(110.0),
        }

        exits, entries = editor._roundabout_arm_orders(
            [entry, second, first], entry, direction=1)

        self.assertEqual([arm["arm_id"] for arm in exits], [
            "first", "second", "entry"])
        self.assertEqual([arm["arm_id"] for arm in entries], [
            "first", "second"])

    def test_arm_connection_can_be_traced_backward_across_connector_roads(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        arm_sample = _Waypoint(10.0, road_id=1)
        gate_sample = _Waypoint(20.0, road_id=2)
        arm_sample.next = lambda distance: [gate_sample]
        arm_sample.previous = lambda distance: []
        gate_sample.next = lambda distance: []
        gate_sample.previous = lambda distance: [arm_sample]
        records = [{
            "lane_key": (arm_sample.road_id, arm_sample.section_id, arm_sample.lane_id),
            "waypoint": arm_sample,
        }]

        self.assertFalse(editor._route_reaches_records(
            gate_sample, records, trace_direction="forward"))
        self.assertTrue(editor._route_reaches_records(
            gate_sample, records, trace_direction="backward"))

    def test_unreliable_topology_suppresses_cascading_exit_errors(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.ego_point = {"x": 0.0, "y": 0.0, "z": 0.0}
        editor.ego_route_points = [{"x": 1.0}, {"x": 2.0}]
        editor.actor_points = [
            {"role": "vt1", "x": 0.0, "y": 0.0,
             "route_points": [{"x": 1.0}, {"x": 2.0}]},
            {"role": "vt2", "x": 0.0, "y": 0.0},
        ]
        editor.roundabout_warnings = []
        editor.roundabout_topology_repair_count = 0
        dense = [_Waypoint(float(index)) for index in range(8)]
        editor._densify_route = lambda points, actor_start=None: (dense, [4] * len(dense))
        editor._roundabout_route_speed_limits = lambda route: ({"1": 30.0}, "test")
        editor._topology_preview_from_vut_route = mock.Mock(
            side_effect=RuntimeError("reviewed topology is incomplete"))

        analysis, errors, _ = editor._analyse_roundabout()

        self.assertIsNone(analysis)
        self.assertEqual(errors, ["reviewed topology is incomplete"])
        self.assertFalse(any("route is inferred as exit" in error for error in errors))

    def test_vut_open_path_uses_reviewed_arm_lanes_without_circle_fit(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)

        def record(road_id, lane_id, gate_x):
            waypoint = _Waypoint(gate_x, road_id=road_id, lane_id=lane_id)
            return {
                "lane_key": (road_id, 0, lane_id),
                "waypoint": waypoint,
                "gate": _gate(gate_x, road_id=road_id),
                "angle": 0.0,
            }

        entry = {
            "arm_id": "arm_01", "angle": 0.0,
            "inbound_angle": 0.0, "outbound_angle": -0.1,
            "inbound": [record(1, 1, 1.0)],
            "outbound": [record(4, 1, -10.0)],
        }
        exit_one = {
            "arm_id": "arm_02", "angle": 0.6,
            "inbound_angle": 0.7, "outbound_angle": 0.5,
            "inbound": [record(2, 1, 20.0)],
            "outbound": [record(5, 1, 20.0)],
        }
        exit_two = {
            "arm_id": "arm_03", "angle": 1.1,
            "inbound_angle": 1.2, "outbound_angle": 1.0,
            "inbound": [record(3, 1, 30.0)],
            "outbound": [record(6, 1, 4.5)],
        }
        arms = [entry, exit_one, exit_two]
        route = [
            _Waypoint(0.0, road_id=1, lane_id=1),
            _Waypoint(2.0, road_id=1, lane_id=1),
            # Merely seeing exit-one's lane identity must not count as an
            # exit because its reviewed gate is at x=20 and is not crossed.
            _Waypoint(3.0, road_id=5, lane_id=1),
            _Waypoint(4.0, road_id=9, lane_id=1),
            _Waypoint(5.0, road_id=6, lane_id=1),
        ]
        editor._reviewed_roundabout_topology = lambda: (
            arms, (0.0, 0.0), 1)
        editor._estimate_roundabout_circle = mock.Mock(
            side_effect=AssertionError("circle fitting must not be used"))

        preview = editor._topology_preview_from_vut_route(route)

        self.assertEqual(preview["entry_arm_id"], "arm_01")
        self.assertEqual(preview["planned_exit"], 2)
        self.assertEqual(preview["exit_arm"]["arm_id"], "arm_03")
        editor._estimate_roundabout_circle.assert_not_called()

    def test_vut_route_before_out_gate_reports_incomplete_not_wrong_exit(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        record = {
            "lane_key": (5, 0, 1),
            "waypoint": _Waypoint(20.0, road_id=5, lane_id=1),
            "gate": _gate(20.0, road_id=5),
        }
        arm = {"arm_id": "arm_02", "outbound": [record]}
        route = [
            _Waypoint(0.0, road_id=1),
            _Waypoint(5.0, road_id=5),
            _Waypoint(10.0, road_id=5),
        ]

        with self.assertRaisesRegex(RuntimeError, "尚未.*穿过.*OUT门线"):
            editor._route_exit_arm(route, [arm], route_label="VUT")

    def test_out_gate_accepts_connected_opendrive_id_transition(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        before = _Waypoint(-1.0, road_id=126, lane_id=-1)
        after = _Waypoint(1.0, road_id=126, lane_id=-1)
        reviewed = _Waypoint(2.0, road_id=142, lane_id=-1)
        before.next = lambda _distance: [after]
        after.next = lambda _distance: [reviewed]
        reviewed.next = lambda _distance: []
        before.previous = after.previous = reviewed.previous = \
            lambda _distance: []
        gate = _gate(0.0, road_id=142)
        gate["lane_id"] = -1
        record = {
            "lane_key": (142, 0, -1),
            "waypoint": reviewed,
            "gate": gate,
        }
        route = [before, after]
        payload = [editor._waypoint_payload(item) for item in route]

        accepted, evidence = editor._route_gate_crossing_evidence(
            route, payload, 1, record)

        self.assertTrue(accepted)
        self.assertFalse(evidence["exact_lane_match"])
        self.assertTrue(evidence["topology_lane_match"])
        self.assertEqual(
            evidence["topology_proof"]["direction"], "forward")

    def test_out_gate_rejects_unconnected_geometric_crossing(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        before = _Waypoint(-1.0, road_id=126, lane_id=-1)
        after = _Waypoint(1.0, road_id=126, lane_id=-1)
        reviewed = _Waypoint(2.0, road_id=142, lane_id=-1)
        for waypoint in (before, after, reviewed):
            waypoint.next = lambda _distance: []
            waypoint.previous = lambda _distance: []
        gate = _gate(0.0, road_id=142)
        gate["lane_id"] = -1
        record = {
            "lane_key": (142, 0, -1),
            "waypoint": reviewed,
            "gate": gate,
        }
        route = [before, after]
        payload = [editor._waypoint_payload(item) for item in route]

        accepted, evidence = editor._route_gate_crossing_evidence(
            route, payload, 1, record)

        self.assertFalse(accepted)
        self.assertTrue(evidence["geometric_crossing"])
        self.assertFalse(evidence["lane_match"])

    def test_out_gate_accepts_reviewed_physical_crossing_downstream(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        before = _Waypoint(-1.0, road_id=126, lane_id=-1)
        after = _Waypoint(1.0, road_id=126, lane_id=-1)
        downstream = _Waypoint(3.0, road_id=126, lane_id=-1)
        reviewed = _Waypoint(0.0, road_id=142, lane_id=-1)
        for waypoint in (before, after, downstream, reviewed):
            waypoint.next = lambda _distance: []
            waypoint.previous = lambda _distance: []
        gate = _gate(0.0, road_id=142)
        gate["lane_id"] = -1
        record = {
            "lane_key": (142, 0, -1),
            "waypoint": reviewed,
            "gate": gate,
        }
        route = [before, after, downstream]
        payload = [editor._waypoint_payload(item) for item in route]

        accepted, evidence = editor._route_gate_crossing_evidence(
            route, payload, 1, record)

        self.assertTrue(accepted)
        self.assertFalse(evidence["lane_match"])
        self.assertTrue(evidence["physical_gate_match"])
        self.assertEqual(evidence["downstream_signed_m"], 3.0)

    def test_out_gate_accepts_crossing_when_downstream_road_changes_again(self):
        """Regression for route 126 -> downstream 15 crossing gate road 142."""
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        route = [
            _Waypoint(-1.0, road_id=126, lane_id=-1),
            _Waypoint(1.0, road_id=126, lane_id=-1),
            _Waypoint(6.0, road_id=15, lane_id=-3),
        ]
        reviewed = _Waypoint(0.0, road_id=142, lane_id=-1)
        for waypoint in route + [reviewed]:
            waypoint.next = lambda _distance: []
            waypoint.previous = lambda _distance: []
        gate = _gate(0.0, road_id=142)
        gate["lane_id"] = -1
        arm = {
            "arm_id": "arm_03",
            "outbound": [{
                "lane_key": (142, 0, -1),
                "waypoint": reviewed,
                "gate": gate,
            }],
        }

        exit_arm, crossing_index = editor._route_exit_arm(
            route, [arm], route_label="VUT")

        self.assertEqual(exit_arm["arm_id"], "arm_03")
        self.assertEqual(crossing_index, 1)

    def test_editor_extracts_auditable_opendrive_speed_limits(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.roundabout_speed_limit_kmh = None
        editor.map = types.SimpleNamespace(to_opendrive=lambda: """
            <OpenDRIVE>
              <road id="1"><type s="0"><speed max="30" unit="km/h"/></type></road>
              <road id="2"><type s="0"><speed max="10" unit="m/s"/></type></road>
            </OpenDRIVE>
        """)
        limits, source = editor._roundabout_route_speed_limits([
            _Waypoint(0.0, road_id=1), _Waypoint(1.0, road_id=2)])
        self.assertEqual(limits, {"1": 30.0, "2": 36.0})
        self.assertEqual(source, "opendrive")

        editor.map = types.SimpleNamespace(to_opendrive=lambda: "<OpenDRIVE/>")
        with self.assertRaisesRegex(RuntimeError, "显式提供工程回退值"):
            editor._roundabout_route_speed_limits([_Waypoint(0.0, road_id=1)])

    def test_roundabout_editor_rejects_a_different_loaded_map(self):
        loaded_map = types.SimpleNamespace(
            name="/Game/Carla/Maps/FakeRoundaboutMap")
        resolver = EDITOR_MODULE.CarlaMapEditor0916._resolve_loaded_map_name
        self.assertEqual(
            resolver(loaded_map, "FakeRoundaboutMap"), "FakeRoundaboutMap")
        with self.assertRaisesRegex(RuntimeError, "地图不一致"):
            resolver(loaded_map, "AnotherMap")

    def test_roundabout_actor_heading_cannot_be_manually_overridden(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.is_roundabout_2b = True
        editor.actor_points = [{"role": "vt1", "yaw": 12.0}]
        editor.selected_agent_idx = 0
        messages = []
        editor._feedback = lambda message, error=False: messages.append((message, error))

        editor.set_agent_yaw(2)

        self.assertEqual(editor.actor_points[0]["yaw"], 12.0)
        self.assertTrue(messages[-1][1])
        self.assertIn("自动确定", messages[-1][0])

    def test_roundabout_route_point_can_be_undone(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.is_roundabout_2b = True
        editor.ego_point = {"x": 0.0, "y": 0.0, "z": 0.0, "yaw": 0.0}
        editor.ego_route_points = []
        editor.actor_points = []
        editor.selected_agent_idx = -1
        editor.selected_mode = "ego"
        editor.roundabout_place_role = "vt1"
        editor.roundabout_capable = True
        editor.roundabout_history = []
        editor.roundabout_dirty = False
        editor.roundabout_analysis = {"stale": True}
        editor.get_nearest_waypoint = lambda x, y: _Waypoint(x, y=y)
        editor._densify_route = lambda points, actor_start=None: (
            [actor_start] + list(points), [4] * (len(points) + 1))
        messages = []
        editor._feedback = lambda message, error=False: messages.append((message, error))

        editor.add_active_route_point(15.0, 0.0)
        self.assertEqual(len(editor.ego_route_points), 1)
        self.assertEqual(len(editor.roundabout_history), 1)
        self.assertIn("15.0m", messages[-1][0])

        with mock.patch.object(EDITOR_MODULE.pygame.display, "set_caption"):
            self.assertTrue(editor.undo_roundabout_action())

        self.assertEqual(editor.ego_route_points, [])
        self.assertEqual(editor.selected_mode, "ego")
        self.assertEqual(len(editor.roundabout_history), 0)
        self.assertIn("已撤销", messages[-1][0])

    def test_enter_confirms_vut_route_and_advances_workflow(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.is_roundabout_2b = True
        editor.ego_point = {"x": 0.0, "y": 0.0, "z": 0.0, "yaw": 0.0}
        editor.ego_route_points = [
            {"x": 10.0, "y": 0.0, "z": 0.2, "yaw": 0.0},
            {"x": 20.0, "y": 0.0, "z": 0.2, "yaw": 0.0},
        ]
        editor.actor_points = []
        editor.selected_agent_idx = -1
        editor.selected_mode = "ego"
        editor.roundabout_place_role = "vt2"
        editor.roundabout_capable = True
        editor.roundabout_vut_route_confirmed = False
        editor.roundabout_history = []
        editor._densify_route = lambda points, actor_start=None: (points, [4, 4])
        editor._ensure_roundabout_topology_preview = lambda force=False: {
            "arm_count": 5,
            "entry_gate": _gate(10.0),
        }
        messages = []
        editor._feedback = lambda message, error=False: messages.append((message, error))

        self.assertTrue(editor.confirm_vut_route())

        self.assertTrue(editor.roundabout_vut_route_confirmed)
        self.assertEqual(editor.roundabout_place_role, "vt1")
        self.assertEqual(len(editor.roundabout_history), 1)
        self.assertIn("STEP 4", messages[-1][0])
        self.assertIn("出口编号", messages[-1][0])

    def test_enter_reuses_immediately_validated_draft_without_retracing(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.is_roundabout_2b = True
        editor.ego_point = {"x": 0.0, "y": 0.0, "z": 0.0, "yaw": 0.0}
        editor.ego_route_points = [
            {"x": 10.0, "y": 0.0, "z": 0.2, "yaw": 0.0},
            {"x": 20.0, "y": 0.0, "z": 0.2, "yaw": 0.0},
        ]
        dense = [_Waypoint(x) for x in (0.0, 10.0, 20.0)]
        editor.actor_points = []
        editor.selected_agent_idx = -1
        editor.selected_mode = "ego"
        editor.roundabout_place_role = "vut"
        editor.roundabout_capable = True
        editor.roundabout_vut_route_confirmed = False
        editor.roundabout_vut_route_failure = None
        editor.roundabout_history = []
        editor.roundabout_vut_route_cache = editor._build_roundabout_route_cache(
            "vut", editor.ego_route_points, editor.ego_point,
            dense, [4, 4, 4])
        editor._densify_route = mock.Mock(
            side_effect=AssertionError("Enter must reuse the draft cache"))
        editor._ensure_roundabout_topology_preview = lambda force=False: {
            "arm_count": 5,
            "entry_gate": _gate(10.0),
        }
        editor._feedback = lambda *args, **kwargs: None

        self.assertTrue(editor.confirm_vut_route())

        editor._densify_route.assert_not_called()
        self.assertTrue(editor.roundabout_vut_route_confirmed)

    def test_step_one_topology_confirmation_accepts_operator_paired_arms(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.is_roundabout_2b = True
        editor.roundabout_branch_confirmed = True
        editor.roundabout_topology_confirmed = False
        editor.roundabout_topology_review_ready = False
        editor.roundabout_topology_seeds = [
            {
                "arm_id": "arm_{:02d}".format(index),
                "inbound": {"gate": {}, "lane": {}},
                "outbound": {"gate": {}, "lane": {}},
            }
            for index in range(1, 6)
        ]
        editor._push_roundabout_history = lambda action: None
        editor._build_roundabout_topology_review = lambda: ({
            "arm_count": 5,
            "lane_count": 12,
            "arms": [],
            "warnings": [],
        }, [])
        editor._save_roundabout_topology_cache = lambda: "/tmp/test_topology.json"
        messages = []
        editor._feedback = lambda message, error=False: messages.append((message, error))

        self.assertTrue(editor.confirm_roundabout_topology())

        self.assertFalse(editor.roundabout_topology_confirmed)
        self.assertTrue(editor.roundabout_topology_review_ready)
        self.assertIn("程序拓扑审核", messages[-1][0])
        self.assertTrue(editor.accept_roundabout_topology_review())
        self.assertTrue(editor.roundabout_topology_confirmed)
        self.assertIn("STEP 2", messages[-1][0])

    def test_step_one_p_cannot_skip_missing_arm_markers(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.is_roundabout_2b = True
        editor.roundabout_branch_confirmed = True
        editor.roundabout_topology_confirmed = False
        editor.roundabout_topology_seeds = []
        messages = []
        editor._feedback = lambda message, error=False: messages.append((message, error))

        self.assertFalse(editor.confirm_roundabout_topology())

        self.assertFalse(editor.roundabout_topology_confirmed)
        self.assertTrue(messages[-1][1])
        self.assertIn("至少标定3个完整物理arm", messages[-1][0])

    def test_step_one_right_click_alternates_inbound_and_outbound(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.is_roundabout_2b = True
        editor.roundabout_branch_confirmed = True
        editor.roundabout_topology_confirmed = False
        editor.roundabout_topology_seeds = []
        editor.roundabout_topology_mark_kind = "inbound"
        editor.roundabout_topology_preview = None
        editor.roundabout_topology_preview_errors = []
        editor.get_nearest_waypoint = lambda x, y: _Waypoint(
            x, road_id=int(x), lane_id=1)
        editor._make_gate = lambda waypoint, source: {
            "center": {"x": waypoint.transform.location.x, "y": 0.0, "z": 0.2},
            "source": source,
        }
        editor._push_roundabout_history = lambda action: None
        editor._mark_roundabout_dirty = lambda: None
        messages = []
        editor._feedback = lambda message, error=False: messages.append((message, error))

        self.assertTrue(editor.add_roundabout_topology_seed(1.0, 0.0))
        self.assertTrue(editor.add_roundabout_topology_seed(2.0, 0.0))

        self.assertEqual(len(editor.roundabout_topology_seeds), 1)
        arm = editor.roundabout_topology_seeds[0]
        self.assertIsNotNone(arm["inbound"])
        self.assertIsNotNone(arm["outbound"])
        self.assertEqual(editor.roundabout_topology_mark_kind, "inbound")
        self.assertIn("进出口配对完成", messages[-1][0])

    def test_step_one_hover_previews_the_next_colored_gate(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.roundabout_branch_confirmed = True
        editor.roundabout_topology_confirmed = False
        editor.roundabout_topology_seeds = [{
            "arm_id": "arm_01",
            "inbound": {"gate": {}, "lane": {}},
            "outbound": None,
        }]
        editor.zoom = 1.0
        editor.offset_x = 0.0
        editor.offset_y = 500.0
        waypoint = _Waypoint(20.0)
        editor.get_nearest_waypoint = lambda x, y: waypoint
        editor._make_gate = lambda selected, source: {"source": source}

        with mock.patch.object(
                EDITOR_MODULE.pygame.mouse, "get_pos", return_value=(200, 300)), \
                mock.patch.object(
                    editor, "_draw_roundabout_topology_marker") as draw_marker:
            editor._draw_roundabout_topology_hover()

        draw_marker.assert_called_once()
        _, color, label = draw_marker.call_args.args
        self.assertEqual(color, (80, 170, 255))
        self.assertEqual(label, "NEXT A01 OUT")
        self.assertTrue(draw_marker.call_args.kwargs["pending"])

    def test_operator_seed_expands_parallel_same_direction_driving_lanes(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        seed = _Waypoint(0.0, road_id=8, lane_id=-1)
        parallel = _Waypoint(0.0, road_id=8, lane_id=-2, y=3.5)
        opposite = _Waypoint(0.0, road_id=8, lane_id=1, y=7.0)
        opposite.transform.get_forward_vector = lambda: types.SimpleNamespace(
            x=-1.0, y=0.0, z=0.0)
        seed.get_left_lane = lambda: parallel
        seed.get_right_lane = lambda: None
        parallel.get_left_lane = lambda: opposite
        parallel.get_right_lane = lambda: seed
        opposite.get_left_lane = lambda: None
        opposite.get_right_lane = lambda: parallel

        lanes = editor._parallel_same_direction_lanes(seed)

        self.assertEqual(
            [editor._lane_key(waypoint) for waypoint in lanes],
            [(8, 0, -1), (8, 0, -2)])

    def test_operator_seed_finds_parallel_lane_authored_as_separate_road(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        seed = _Waypoint(0.0, road_id=177, lane_id=-1, y=0.0)
        separate_road_lane = _Waypoint(
            0.7, road_id=178, lane_id=-1, y=3.5)
        same_centreline_boundary = _Waypoint(
            1.2, road_id=999, lane_id=-1, y=0.15)
        distant_service_road = _Waypoint(
            0.0, road_id=300, lane_id=-1, y=15.0)
        opposite = _Waypoint(0.0, road_id=400, lane_id=-1, y=7.0)
        opposite.transform.get_forward_vector = lambda: types.SimpleNamespace(
            x=-1.0, y=0.0, z=0.0)
        for waypoint in (
                seed, separate_road_lane, same_centreline_boundary,
                distant_service_road, opposite):
            waypoint.get_left_lane = lambda: None
            waypoint.get_right_lane = lambda: None
        editor.waypoints = [
            seed, separate_road_lane, same_centreline_boundary,
            distant_service_road, opposite,
        ]

        lanes = editor._parallel_same_direction_lanes(seed)

        self.assertEqual(
            [editor._lane_key(waypoint) for waypoint in lanes],
            [(177, 0, -1), (178, 0, -1)])

    def test_p_stage_review_marks_all_parallel_lanes_with_same_arm(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        inbound = _Waypoint(0.0, road_id=8, lane_id=-1, y=0.0)
        inbound_parallel = _Waypoint(0.0, road_id=8, lane_id=-2, y=3.5)
        outbound = _Waypoint(10.0, road_id=9, lane_id=1, y=0.0)
        editor.roundabout_topology_seeds = [{
            "arm_id": "arm_01",
            "inbound": {"gate": {
                "center": {"x": 0.0, "y": 0.0, "z": 0.2},
                "forward": {"x": 1.0, "y": 0.0},
            }},
            "outbound": {"gate": {
                "center": {"x": 10.0, "y": 0.0, "z": 0.2},
                "forward": {"x": 1.0, "y": 0.0},
            }},
        }]
        editor._topology_seed_waypoint = lambda seed: (
            inbound if seed["gate"]["center"]["x"] == 0.0 else outbound)
        editor._parallel_same_direction_lanes = lambda waypoint: (
            [inbound, inbound_parallel] if waypoint is inbound else [outbound])
        editor._make_gate = lambda waypoint, source: {
            "center": {
                "x": waypoint.transform.location.x,
                "y": waypoint.transform.location.y,
            },
            "source": source,
        }

        review, errors = editor._build_roundabout_topology_review()

        self.assertEqual(errors, [])
        self.assertEqual(review["arm_count"], 1)
        self.assertEqual(review["lane_count"], 3)
        self.assertEqual(len(review["arms"][0]["inbound"]), 2)
        self.assertTrue(all(
            arm["arm_id"] == "arm_01" for arm in review["arms"]))

    def test_review_omits_operator_excluded_auto_cross_section(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        inbound = _Waypoint(0.0, road_id=8, lane_id=-1)
        outbound = _Waypoint(10.0, road_id=9, lane_id=-1)
        wrong_ring_lane = _Waypoint(20.0, road_id=99, lane_id=-1)
        editor.roundabout_topology_seeds = [{
            "arm_id": "arm_01",
            "inbound": {"gate": _gate(0.0), "lane": {
                "road_id": 8, "section_id": 0, "lane_id": -1,
            }},
            "outbound": {
                "gate": _gate(10.0),
                "lane": {"road_id": 9, "section_id": 0, "lane_id": -1},
                "excluded_cross_sections": [{
                    "lane": {"road_id": 99, "section_id": 0, "lane_id": -1},
                    "center": {"x": 20.0, "y": 0.0, "z": 0.2},
                }],
            },
        }]
        editor._topology_seed_waypoint = lambda seed: (
            inbound if seed["gate"]["center"]["x"] == 0.0 else outbound)
        editor._parallel_same_direction_lanes = lambda waypoint: (
            [inbound] if waypoint is inbound else [outbound, wrong_ring_lane])
        editor._make_gate = lambda waypoint, source: _gate(
            waypoint.transform.location.x, road_id=waypoint.road_id)

        review, errors = editor._build_roundabout_topology_review()

        self.assertEqual(errors, [])
        self.assertEqual(
            [item["lane"]["road_id"] for item in review["arms"][0]["outbound"]],
            [9])

    def test_delete_selected_auto_lane_persists_an_exclusion(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.roundabout_topology_seeds = [{
            "arm_id": "arm_02",
            "inbound": {"gate": _gate(0.0), "lane": {
                "road_id": 8, "section_id": 0, "lane_id": -1,
            }},
            "outbound": {"gate": _gate(10.0), "lane": {
                "road_id": 9, "section_id": 0, "lane_id": -1,
            }},
        }]
        editor.roundabout_topology_lane_target = {
            "arm_index": 0,
            "arm_id": "arm_02",
            "direction": "outbound",
            "lane": {"road_id": 99, "section_id": 0, "lane_id": -1},
            "gate": _gate(20.0, road_id=99),
            "is_operator_seed": False,
        }
        editor.roundabout_topology_confirmed = False
        editor.roundabout_topology_cache_loaded = True
        editor.roundabout_topology_edit_target = (0, "outbound")
        editor._push_roundabout_history = lambda action: None
        editor._build_roundabout_topology_review = lambda: ({
            "arms": [], "arm_count": 1, "lane_count": 2,
            "warnings": [], "diagnostics": [],
        }, [])
        editor._mark_roundabout_dirty = lambda: None
        feedback = []
        editor._feedback = lambda message, *args: feedback.append(message)

        self.assertTrue(editor.exclude_selected_roundabout_topology_lane())

        exclusions = editor.roundabout_topology_seeds[0]["outbound"][
            "excluded_cross_sections"]
        self.assertEqual(len(exclusions), 1)
        self.assertEqual(exclusions[0]["lane"]["road_id"], 99)
        self.assertIsNone(editor.roundabout_topology_lane_target)
        self.assertTrue(any("按Enter" in message for message in feedback))

    def test_same_opendrive_lane_at_distant_mouths_is_not_a_conflict(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        shared_at_first_mouth = _Waypoint(0.0, road_id=142, lane_id=-1)
        first_outbound = _Waypoint(10.0, road_id=201, lane_id=-1)
        second_inbound = _Waypoint(50.0, road_id=202, lane_id=-1)
        shared_at_second_mouth = _Waypoint(60.0, road_id=142, lane_id=-1)
        waypoint_by_seed_x = {
            0.0: shared_at_first_mouth,
            10.0: first_outbound,
            50.0: second_inbound,
            60.0: shared_at_second_mouth,
        }
        editor.roundabout_topology_seeds = [
            {
                "arm_id": "arm_01",
                "inbound": {"gate": _gate(0.0)},
                "outbound": {"gate": _gate(10.0)},
            },
            {
                "arm_id": "arm_02",
                "inbound": {"gate": _gate(50.0)},
                "outbound": {"gate": _gate(60.0)},
            },
        ]
        editor._topology_seed_waypoint = lambda seed: waypoint_by_seed_x[
            seed["gate"]["center"]["x"]]
        editor._parallel_same_direction_lanes = lambda waypoint: [waypoint]
        editor._make_gate = lambda waypoint, source: _gate(
            waypoint.transform.location.x, road_id=waypoint.road_id)

        review, errors = editor._build_roundabout_topology_review()

        self.assertEqual(errors, [])
        self.assertEqual(review["diagnostics"], [])
        self.assertEqual(review["lane_count"], 4)

    def test_same_lane_at_same_cross_section_reports_drawable_conflict(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        shared = _Waypoint(0.0, road_id=142, lane_id=-1)
        first_outbound = _Waypoint(10.0, road_id=201, lane_id=-1)
        second_inbound = _Waypoint(50.0, road_id=202, lane_id=-1)
        waypoint_by_seed_x = {
            0.0: shared,
            10.0: first_outbound,
            50.0: second_inbound,
            # Deliberately project the second OUT marker back onto the exact
            # cross-section already used by arm_01 IN.
            60.0: shared,
        }
        editor.roundabout_topology_seeds = [
            {
                "arm_id": "arm_01",
                "inbound": {"gate": _gate(0.0)},
                "outbound": {"gate": _gate(10.0)},
            },
            {
                "arm_id": "arm_02",
                "inbound": {"gate": _gate(50.0)},
                "outbound": {"gate": _gate(60.0)},
            },
        ]
        editor._topology_seed_waypoint = lambda seed: waypoint_by_seed_x[
            seed["gate"]["center"]["x"]]
        editor._parallel_same_direction_lanes = lambda waypoint: [waypoint]
        editor._make_gate = lambda waypoint, source: _gate(
            waypoint.transform.location.x, road_id=waypoint.road_id)

        review, errors = editor._build_roundabout_topology_review()

        self.assertTrue(any("同一横断面" in error for error in errors))
        self.assertEqual(len(review["diagnostics"]), 1)
        diagnostic = review["diagnostics"][0]
        self.assertEqual(diagnostic["lane"]["road_id"], 142)
        self.assertEqual(
            [(owner["arm_id"], owner["direction"])
             for owner in diagnostic["owners"]],
            [("arm_01", "inbound"), ("arm_02", "outbound")])

    def test_topology_conflict_diagnostic_is_drawn_in_red(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.roundabout_topology_review = {
            "diagnostics": [{
                "kind": "lane_cross_section_conflict",
                "owners": [
                    {"arm_id": "arm_02", "direction": "inbound",
                     "gate": _gate(10.0)},
                    {"arm_id": "arm_03", "direction": "outbound",
                     "gate": _gate(20.0)},
                ],
            }],
        }

        with mock.patch.object(
                editor, "_draw_roundabout_topology_marker") as draw_marker:
            editor._draw_roundabout_topology_diagnostics()

        self.assertEqual(draw_marker.call_count, 2)
        self.assertTrue(all(
            call.args[1] == EDITOR_MODULE.ROUNDABOUT_COLOR_TOPOLOGY_CONFLICT
            for call in draw_marker.call_args_list))
        self.assertTrue(all(
            "A02 IN / A03 OUT" in call.args[2]
            for call in draw_marker.call_args_list))

    def test_accepted_topology_keeps_colored_representative_gates(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.roundabout_topology_confirmed = True
        editor.roundabout_topology_review_ready = True
        editor.roundabout_show_all_overlays = False
        editor.roundabout_topology_edit_target = None
        editor.roundabout_topology_seeds = [{
            "arm_id": "arm_01",
            "inbound": {"gate": {"seed": "in"}},
            "outbound": {"gate": {"seed": "out"}},
        }]
        editor.roundabout_topology_review = {"arms": [{
            "arm_id": "arm_01",
            "inbound": [{"gate": {"lane": "in-1"}},
                        {"gate": {"lane": "in-2"}}],
            "outbound": [{"gate": {"lane": "out-1"}}],
        }]}

        with mock.patch.object(
                editor, "_draw_roundabout_topology_marker") as draw_marker:
            editor._draw_roundabout_topology_seeds()

        self.assertEqual(draw_marker.call_count, 2)
        self.assertEqual(
            {call.args[2] for call in draw_marker.call_args_list},
            {"A01 IN", "A01 OUT"})

        editor.roundabout_show_all_overlays = True
        with mock.patch.object(
                editor, "_draw_roundabout_topology_marker") as draw_marker:
            editor._draw_roundabout_topology_seeds()
        self.assertEqual(draw_marker.call_count, 3)

    def test_vut_start_recommends_merge_and_permitted_exits(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.roundabout_topology_confirmed = True

        def gate_at(angle, road_id):
            radius = 20.0
            x, y = radius * math.cos(angle), radius * math.sin(angle)
            return {
                "center": {"x": x, "y": y, "z": 0.2},
                "left": {"x": x - 1.0, "y": y, "z": 0.2},
                "right": {"x": x + 1.0, "y": y, "z": 0.2},
                "forward": {"x": -math.cos(angle), "y": -math.sin(angle)},
                "approach_yaw": math.degrees(angle + math.pi),
                "road_id": road_id,
                "section_id": 0,
                "lane_id": 1,
            }

        # For counter-clockwise travel each paired OUT mouth is slightly
        # clockwise of its IN mouth.  VUT starts on the west arm.
        arm_centers = [math.pi, -math.pi / 2.0, 0.0, math.pi / 2.0]
        arms = []
        for index, center_angle in enumerate(arm_centers, start=1):
            inbound_road = index * 10 + 1
            outbound_road = index * 10 + 2
            arms.append({
                "arm_id": "arm_{:02d}".format(index),
                "inbound": [{
                    "gate": gate_at(center_angle + 0.1, inbound_road),
                    "lane": {"road_id": inbound_road, "section_id": 0, "lane_id": 1},
                }],
                "outbound": [{
                    "gate": gate_at(center_angle - 0.1, outbound_road),
                    "lane": {"road_id": outbound_road, "section_id": 0, "lane_id": 1},
                }],
            })
        editor.roundabout_topology_review = {"arms": arms, "arm_count": 4}

        proposal, errors = editor._recommend_roundabout_from_vut_start(
            _Waypoint(-30.0, road_id=11, lane_id=1))

        self.assertEqual(errors, [])
        self.assertEqual(proposal["entry_arm_id"], "arm_01")
        self.assertEqual(proposal["travel_direction"], "counterclockwise")
        self.assertEqual(proposal["exit_gates"]["1"]["arm_id"], "arm_02")
        self.assertEqual(proposal["exit_gates"]["2"]["arm_id"], "arm_03")
        self.assertEqual(proposal["exit_gates"]["3"]["arm_id"], "arm_04")
        self.assertFalse(proposal["exit_gates"]["1"]["vut_allowed"])
        self.assertTrue(proposal["exit_gates"]["2"]["vut_allowed"])
        self.assertTrue(proposal["exit_gates"]["3"]["vut_allowed"])

    def test_vut_start_uses_first_reached_in_gate_not_all_downstream_arms(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.roundabout_topology_confirmed = True

        def gate_at(angle, road_id):
            radius = 20.0
            x, y = radius * math.cos(angle), radius * math.sin(angle)
            return {
                "center": {"x": x, "y": y, "z": 0.2},
                "left": {"x": x - 1.0, "y": y, "z": 0.2},
                "right": {"x": x + 1.0, "y": y, "z": 0.2},
                "forward": {"x": -math.cos(angle), "y": -math.sin(angle)},
                "approach_yaw": math.degrees(angle + math.pi),
                "road_id": road_id, "section_id": 0, "lane_id": 1,
            }

        arms = []
        for index, angle in enumerate(
                (math.pi, -math.pi / 2.0, 0.0, math.pi / 2.0), start=1):
            inbound_road = index * 10 + 1
            outbound_road = index * 10 + 2
            arms.append({
                "arm_id": "arm_{:02d}".format(index),
                "inbound": [{
                    "gate": gate_at(angle + 0.1, inbound_road),
                    "lane": {
                        "road_id": inbound_road,
                        "section_id": 0, "lane_id": 1,
                    },
                }],
                "outbound": [{
                    "gate": gate_at(angle - 0.1, outbound_road),
                    "lane": {
                        "road_id": outbound_road,
                        "section_id": 0, "lane_id": 1,
                    },
                }],
            })
        editor.roundabout_topology_review = {"arms": arms, "arm_count": 4}
        editor._topology_seed_waypoint = lambda item: _Waypoint(
            0.0, road_id=item["lane"]["road_id"], lane_id=1)
        distance_by_road = {11: 12.0, 21: 52.0, 31: 84.0, 41: 116.0}

        def trace(_start, records, **_kwargs):
            road_id = records[0]["lane_key"][0]
            return {
                "reached": True,
                "best": {"distance_m": distance_by_road[road_id]},
            }

        editor._trace_waypoint_to_records = trace

        proposal, errors = editor._recommend_roundabout_from_vut_start(
            _Waypoint(-30.0, road_id=5, lane_id=-3))

        self.assertEqual(errors, [])
        self.assertEqual(proposal["entry_arm_id"], "arm_01")

    def test_entry_event_reuses_step_two_topology_proof_across_lane_id_change(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.roundabout_vut_recommendation = {"entry_arm_id": "arm_01"}
        route = [
            _Waypoint(0.0, road_id=5, lane_id=-3),
            _Waypoint(10.0, road_id=6, lane_id=-1),
        ]
        arms = [{
            "arm_id": "arm_01",
            "inbound": [{
                "lane_key": (11, 0, -1),
                "waypoint": _Waypoint(5.0, road_id=11, lane_id=-1),
                "gate": _gate(5.0, road_id=11),
            }],
            "outbound": [],
        }]

        crossing_index, entry_arm, _record = editor._route_entry_event(
            route, arms)

        self.assertEqual(crossing_index, 1)
        self.assertEqual(entry_arm["arm_id"], "arm_01")

    def test_mature_vut_draft_is_rejected_before_enter_on_topology_error(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.is_roundabout_2b = True
        editor.ego_point = {"x": 0.0, "y": 0.0, "z": 0.0, "yaw": 0.0}
        editor.ego_route_points = []
        editor.selected_mode = "ego"
        editor.selected_agent_idx = -1
        editor.actor_points = []
        editor.roundabout_vut_route_cache = None
        editor.roundabout_vt1_route_cache = None
        editor.roundabout_topology_confirmed = True
        editor.roundabout_vut_recommendation = {
            "entry_arm_id": "arm_01",
        }
        waypoint = _Waypoint(10.0, road_id=5, lane_id=-1)
        editor._roundabout_click_waypoint_candidates = lambda x, y: [
            (waypoint, 0.2)]
        payload = editor._route_anchor_payload(waypoint)
        draft_cache = {
            "dense": [_Waypoint(0.0), waypoint],
            "options": [4, 4],
            "length_m": 10.0,
        }
        editor._build_roundabout_candidate_extension = lambda *args: (
            payload, draft_cache)
        editor._reviewed_roundabout_topology = lambda: ([{
            "arm_id": "arm_01", "inbound": [], "outbound": [],
        }], (0.0, 0.0), 1)
        editor._route_exit_arm = lambda *args, **kwargs: ({"arm_id": "arm_02"}, 1)
        editor._topology_preview_from_vut_route = mock.Mock(
            side_effect=RuntimeError("入口门线未穿越"))
        editor._set_roundabout_route_failure = lambda *args, **kwargs: None
        editor._feedback = mock.Mock()

        self.assertFalse(editor.add_active_route_point(10.0, 0.0))

        self.assertEqual(editor.ego_route_points, [])
        self.assertIn("入口门线未穿越", editor._feedback.call_args.args[0])

    def test_target_role_prompts_explain_vt1_and_vt2_lanes(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.is_roundabout_2b = True
        editor.roundabout_place_role = "vt1"
        editor.selected_mode = None
        editor.selected_agent_idx = -1
        editor.actor_points = []
        messages = []
        editor._feedback = lambda message, error=False: messages.append((message, error))

        editor.set_roundabout_role("vt1")
        self.assertIn("环形行车道", messages[-1][0])
        self.assertIn("接入道路", messages[-1][0])

        editor.set_roundabout_role("vt2")
        self.assertIn("下一个接入口", messages[-1][0])
        self.assertIn("进口车道", messages[-1][0])
        self.assertIn("不等同于VT1的出口1", messages[-1][0])

    def test_vt2_click_after_in_gate_is_moved_upstream_on_same_approach(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        clicked = _Waypoint(5.0, road_id=2, lane_id=1)
        gate_waypoint = _Waypoint(0.0, road_id=2, lane_id=1)
        placement = _Waypoint(-2.0, road_id=2, lane_id=1)
        gate_waypoint.previous = mock.Mock(return_value=[placement])
        record = {
            "lane_key": (2, 0, 1),
            "waypoint": gate_waypoint,
            "gate": _gate(0.0, road_id=2),
        }
        arm = {"arm_id": "arm_02", "inbound": [record]}

        def trace(_start, _records, maximum_distance=100.0,
                  trace_direction="forward", allow_spatial_match=True):
            return {
                "reached": trace_direction == "backward",
                "best": {"target_record": record},
            }

        editor._trace_waypoint_to_records = trace
        editor._route_reaches_records = lambda *args, **kwargs: True

        prepared, result = editor._prepare_vt2_waypoint(clicked, arm)

        self.assertIs(prepared, placement)
        self.assertTrue(result["adjusted"])
        self.assertEqual(result["arm_id"], "arm_02")
        self.assertEqual(result["lane_key"], (2, 0, 1))
        self.assertIs(result["entry_record"], record)
        self.assertEqual(result["upstream_distance_m"], 2.0)
        gate_waypoint.previous.assert_called_once_with(2.0)

    def test_vt2_click_on_unconnected_lane_is_rejected_immediately(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        clicked = _Waypoint(5.0, road_id=9, lane_id=-1)
        gate_waypoint = _Waypoint(0.0, road_id=2, lane_id=1)
        record = {
            "lane_key": (2, 0, 1),
            "waypoint": gate_waypoint,
            "gate": _gate(0.0, road_id=2),
        }
        arm = {"arm_id": "arm_02", "inbound": [record]}
        editor._trace_waypoint_to_records = lambda *args, **kwargs: {
            "reached": False,
            "best": {"target_record": record},
        }

        with self.assertRaisesRegex(RuntimeError, "不要点蓝色OUT车道"):
            editor._prepare_vt2_waypoint(clicked, arm)

    def test_downstream_gate_record_follows_vt2_lane_not_first_arm_lane(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        first_lane = {
            "lane_key": (2, 0, 1),
            "waypoint": _Waypoint(0.0, road_id=2, lane_id=1, y=0.0),
            "gate": _gate(0.0, road_id=2),
        }
        vt2_lane = {
            "lane_key": (2, 0, 2),
            "waypoint": _Waypoint(0.0, road_id=2, lane_id=2, y=4.0),
            "gate": _gate(0.0, road_id=2),
        }
        selected = editor._route_record_for_lane(
            [_Waypoint(-8.0, road_id=2, lane_id=2, y=4.0)],
            [first_lane, vt2_lane])

        self.assertIs(selected, vt2_lane)

    def test_downstream_gate_accepts_topology_proven_upstream_vt2_lane(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        gate = _gate(0.0, road_id=18)
        gate["lane_id"] = -3
        gate_record = {
            "lane_key": (18, 0, -3),
            "waypoint": _Waypoint(0.0, road_id=18, lane_id=-3),
            "gate": gate,
        }
        arm = {"arm_id": "arm_01", "inbound": [gate_record]}
        upstream_vt2 = _Waypoint(-9.5, road_id=78, lane_id=-1)

        gate = editor._downstream_gate_for_vt2(
            gate_record, arm, upstream_vt2)

        self.assertEqual(
            gate["gate_lane"],
            {"road_id": 18, "section_id": 0, "lane_id": -3})
        self.assertEqual(
            gate["selected_lane"],
            {"road_id": 78, "section_id": 0, "lane_id": -1})
        self.assertIn(gate["selected_lane"], gate["inbound_lanes"])
        self.assertEqual(
            gate["lane_membership_proof"],
            "carla_directed_topology_to_reviewed_in_gate")

    def test_editing_confirmed_vut_route_requires_reconfirmation(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.is_roundabout_2b = True
        editor.ego_point = {"x": 0.0, "y": 0.0, "z": 0.0, "yaw": 0.0}
        editor.ego_route_points = [
            {"x": 10.0, "y": 0.0, "z": 0.2, "yaw": 0.0},
            {"x": 20.0, "y": 0.0, "z": 0.2, "yaw": 0.0},
        ]
        editor.actor_points = []
        editor.selected_agent_idx = -1
        editor.selected_mode = "ego"
        editor.roundabout_place_role = "vt1"
        editor.roundabout_capable = True
        editor.roundabout_vut_route_confirmed = True
        editor.roundabout_vut_route_cache = {"stale": True}
        editor.roundabout_topology_confirmed = True
        editor.roundabout_topology_preview = {"stale": True}
        editor.roundabout_topology_preview_errors = []
        editor.roundabout_history = []
        editor.roundabout_dirty = False
        editor.roundabout_analysis = None
        editor.get_nearest_waypoint = lambda x, y: _Waypoint(x, y=y)
        editor._densify_route = lambda points, actor_start=None: (
            [actor_start] + list(points), [4] * (len(points) + 1))
        editor._feedback = lambda *args, **kwargs: None

        editor.add_active_route_point(30.0, 0.0)

        self.assertFalse(editor.roundabout_vut_route_confirmed)
        self.assertIsNotNone(editor.roundabout_vut_route_cache)
        self.assertEqual(
            editor.roundabout_vut_route_cache["payload"][-1]["x"], 30.0)
        self.assertFalse(editor.roundabout_topology_confirmed)
        self.assertIsNone(editor.roundabout_topology_preview)

    def test_bad_alt_right_candidate_is_rejected_without_route_or_history_edit(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.is_roundabout_2b = True
        editor.ego_point = {"x": 0.0, "y": 0.0, "z": 0.0, "yaw": 0.0}
        editor.ego_route_points = [
            {"x": 10.0, "y": 0.0, "z": 0.2, "yaw": 0.0},
        ]
        editor.actor_points = []
        editor.selected_agent_idx = -1
        editor.selected_mode = "ego"
        editor.roundabout_history = []
        editor.roundabout_vut_route_cache = {"existing": True}
        editor.get_nearest_waypoint = lambda x, y: _Waypoint(x, y=y)
        editor._densify_route = mock.Mock(side_effect=
            EDITOR_MODULE.RoundaboutRouteTraceError(
                "第2段落在反向车道", partial_route=[_Waypoint(10.0)],
                segment_index=2,
                segment_start={"x": 10.0, "y": 0.0, "z": 0.0, "yaw": 0.0},
                segment_target={"x": 20.0, "y": 4.0, "z": 0.0, "yaw": 0.0}))
        messages = []
        editor._feedback = lambda message, error=False: messages.append(
            (message, error))

        accepted = editor.add_active_route_point(20.0, 4.0)

        self.assertFalse(accepted)
        self.assertEqual(len(editor.ego_route_points), 1)
        self.assertEqual(editor.roundabout_history, [])
        self.assertEqual(editor.roundabout_vut_route_cache, {"existing": True})
        self.assertTrue(messages[-1][1])
        self.assertIn("候选点P2已拒绝", messages[-1][0])
        self.assertIn("无需先撤销", messages[-1][0])
        self.assertEqual(
            editor.roundabout_vut_route_failure["segment_index"], 2)

    def test_alt_right_chooses_connected_lane_over_nearest_lane(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.is_roundabout_2b = True
        editor.zoom = 10.0
        editor.ego_point = {"x": 0.0, "y": 0.0, "z": 0.0, "yaw": 0.0}
        editor.ego_route_points = []
        editor.actor_points = []
        editor.selected_agent_idx = -1
        editor.selected_mode = "ego"
        editor.roundabout_place_role = "vt1"
        editor.roundabout_capable = True
        editor.roundabout_history = []
        editor.roundabout_dirty = False
        editor.roundabout_analysis = None
        editor.roundabout_validation_attempted = False
        editor.roundabout_topology_seeds = []
        editor.roundabout_vut_route_cache = None
        editor.roundabout_vut_route_failure = None
        nearest_but_disconnected = _Waypoint(
            20.0, road_id=2, lane_id=-1, y=0.0)
        connected = _Waypoint(20.0, road_id=3, lane_id=-1, y=1.0)
        editor.waypoints = [nearest_but_disconnected, connected]
        editor.get_nearest_waypoint = lambda _x, _y: nearest_but_disconnected

        def densify(points, actor_start=None):
            if points[-1]["road_id"] == 2:
                raise EDITOR_MODULE.RoundaboutRouteTraceError(
                    "最近连接道不可达")
            return [actor_start] + list(points), [4] * (len(points) + 1)

        editor._densify_route = densify
        messages = []
        editor._feedback = lambda message, error=False: messages.append(
            (message, error))

        accepted = editor.add_active_route_point(20.0, 0.0)

        self.assertTrue(accepted)
        self.assertEqual(editor.ego_route_points[0]["road_id"], 3)
        self.assertEqual(editor.ego_route_points[0]["lane_id"], -1)
        self.assertIn("几何最近车道不可达", messages[-1][0])
        self.assertIn("road/section/lane=(3,0,-1)", messages[-1][0])

    def test_enter_confirms_selected_vt1_route_and_advances_to_vt2(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.is_roundabout_2b = True
        editor.ego_point = {"x": -10.0, "y": 0.0}
        editor.ego_route_points = [{"x": 0.0, "y": 0.0}]
        editor.actor_points = [{
            "x": 0.0, "y": 10.0, "z": 0.0, "yaw": 0.0,
            "role": "vt1", "route_points": [
                {"x": 10.0, "y": 10.0}, {"x": 20.0, "y": 10.0},
            ],
        }]
        editor.selected_agent_idx = 0
        editor.selected_mode = "agent"
        editor.roundabout_place_role = "vt1"
        editor.roundabout_capable = True
        editor.roundabout_branch_confirmed = True
        editor.roundabout_topology_confirmed = True
        editor.roundabout_vut_route_confirmed = True
        editor.roundabout_vt1_route_confirmed = False
        editor.roundabout_history = []
        editor._densify_route = lambda points, actor_start=None: (points, [4, 4])
        editor._vut_vt1_preflight_error = lambda: None
        messages = []
        editor._feedback = lambda message, error=False: messages.append((message, error))

        self.assertTrue(editor.confirm_active_roundabout_route())

        self.assertTrue(editor.roundabout_vt1_route_confirmed)
        self.assertEqual(editor.roundabout_place_role, "vt2")
        self.assertIn("STEP 6", messages[-1][0])

    def test_vt1_confirmation_rejects_final_vut_entry_clearance_early(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.is_roundabout_2b = True
        editor.actor_points = [{
            "x": 0.0, "y": 10.0, "z": 0.0, "yaw": 0.0,
            "role": "vt1", "route_points": [
                {"x": 10.0, "y": 10.0}, {"x": 20.0, "y": 10.0}],
        }]
        editor.selected_agent_idx = 0
        editor.selected_mode = "agent"
        editor.roundabout_vt1_route_confirmed = False
        editor._densify_route = lambda points, actor_start=None: (points, [4, 4])
        editor._vut_vt1_preflight_error = lambda: (
            "VUT起点距离VUT–VT1最终汇合门线只有2.3m，要求至少3.0m")
        messages = []
        editor._feedback = lambda message, error=False: messages.append(
            (message, error))

        self.assertFalse(editor.confirm_vt1_route())

        self.assertFalse(editor.roundabout_vt1_route_confirmed)
        self.assertTrue(messages[-1][1])
        self.assertIn("STEP 5", messages[-1][0])
        self.assertIn("2.3m", messages[-1][0])

    def test_step_five_preflight_rejects_vt1_upstream_timing_early(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        vt1 = {
            "x": 0.0, "y": 0.0, "z": 0.0, "yaw": 0.0,
            "role": "vt1", "route_points": [
                {"x": 10.0, "y": 0.0}, {"x": 20.0, "y": 0.0}],
        }
        editor.is_roundabout_2b = True
        editor.roundabout_vt1_route_confirmed = False
        editor._roundabout_actor = lambda role: vt1 if role == "vt1" else None
        caches = {
            "vut": {
                "dense": [_Waypoint(0.0), _Waypoint(14.5)], "payload": []},
            "vt1": {
                "dense": [_Waypoint(0.0), _Waypoint(20.0)], "payload": []},
        }
        editor._confirmed_roundabout_route = (
            lambda role, required=True: caches[role])
        editor._ensure_roundabout_topology_preview = lambda force=False: {
            "entry_index": 1,
            "arms": [{"arm_id": "arm_01"}],
            "exit_order": [],
        }
        editor._vut_vt1_merge_geometry = lambda *_args: {
            "entry_location": _Location(20.0),
            "approach_distance_m": 14.5,
            "start_gate_signed_m": -14.5,
        }

        error = editor._vut_vt1_preflight_error()

        self.assertIn("只有20.0m", error)
        self.assertIn("至少需要24.8m", error)

        enough_timing = editor._vt1_upstream_timing(
            [_Waypoint(0.0), _Waypoint(54.9)], {
                "entry_location": _Location(54.9),
                "approach_distance_m": 14.5,
            })
        self.assertAlmostEqual(enough_timing["required_m"], 24.8333333)
        self.assertIsNone(editor._vt1_upstream_timing_error(enough_timing))

        messages = []
        editor._set_roundabout_route_failure = lambda *_args, **_kwargs: None
        editor._feedback = lambda message, is_error=False: messages.append(
            (message, is_error))
        self.assertFalse(editor.confirm_vt1_route())
        self.assertIn("STEP 5", messages[-1][0])
        self.assertIn("至少需要24.8m", messages[-1][0])

    def test_path_merge_geometry_exposes_vut_start_signed_clearance(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        vut_dense = [
            _Waypoint(0.0), _Waypoint(2.3), _Waypoint(15.0),
        ]
        vt1_dense = [
            _Waypoint(2.3, y=0.5), _Waypoint(15.0, y=0.5),
        ]

        geometry = editor._vut_vt1_merge_geometry(
            vut_dense, vt1_dense, route_entry_index=1)

        self.assertEqual(geometry["entry_index"], 1)
        self.assertAlmostEqual(geometry["start_gate_signed_m"], -2.3)

    def test_reverse_topology_band_returns_only_recommended_distance(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        nodes = [_Waypoint(value) for value in (10, 8, 6, 4, 2, 0)]
        for index, node in enumerate(nodes):
            previous = [nodes[index + 1]] if index + 1 < len(nodes) else []
            node.previous = lambda _step, values=previous: values

        selected = editor._reverse_waypoint_distance_band(
            [nodes[0]], minimum_m=4.0, maximum_m=8.0)

        self.assertEqual(
            [item[0].transform.location.x for item in selected],
            [6.0, 4.0, 2.0])

    def test_reverse_topology_band_stops_at_reviewed_inbound_branch(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        start = _Waypoint(10.0, road_id=1)
        ring = _Waypoint(8.0, road_id=2)
        inbound = _Waypoint(8.0, road_id=3, y=2.0)
        inbound_upstream = _Waypoint(6.0, road_id=4, y=2.0)
        start.previous = lambda _step: [ring, inbound]
        ring.previous = lambda _step: []
        inbound.previous = lambda _step: [inbound_upstream]
        inbound_upstream.previous = lambda _step: []

        selected = editor._reverse_waypoint_distance_band(
            [start], minimum_m=0.0, maximum_m=10.0,
            blocked_lane_keys=[editor._lane_key(inbound)])

        self.assertIn(ring, [item[0] for item in selected])
        self.assertNotIn(inbound, [item[0] for item in selected])
        self.assertNotIn(inbound_upstream, [item[0] for item in selected])

    def test_vut_merge_recommendation_uses_non_vut_previous_branch(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        route = [_Waypoint(0), _Waypoint(2), _Waypoint(4), _Waypoint(6)]
        ring_predecessor = _Waypoint(3, road_id=9)
        route[1].previous = lambda _step: [route[0]]
        route[2].previous = lambda _step: [route[1], ring_predecessor]

        index, predecessors, lookback_m = editor._vut_circulation_predecessors(
            route, entry_index=0, exit_index=3)

        self.assertEqual(index, 2)
        self.assertEqual(predecessors, [ring_predecessor])
        self.assertEqual(lookback_m, 2.0)

    def test_vut_merge_recommendation_probes_beyond_two_metres(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        route = [_Waypoint(value) for value in (0, 2, 4, 6, 8)]
        ring_predecessor = _Waypoint(-2, road_id=9, y=5.0)

        def predecessors(distance):
            if distance < 12.0:
                return [route[0]]
            return [route[0], ring_predecessor]

        for waypoint in route[1:]:
            waypoint.previous = predecessors

        index, candidates, lookback_m = \
            editor._vut_circulation_predecessors(
                route, entry_index=0, exit_index=4)

        self.assertEqual(index, 1)
        self.assertEqual(candidates, [ring_predecessor])
        self.assertEqual(lookback_m, 12.0)

    def test_vt1_recommendation_can_trace_exit_one_parallel_connector(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        vut_route = [
            _Waypoint(0.0, road_id=10, y=0.0),
            _Waypoint(2.0, road_id=11, y=0.0),
            _Waypoint(4.0, road_id=11, y=0.0),
            _Waypoint(6.0, road_id=11, y=0.0),
        ]
        exit_lane = _Waypoint(8.0, road_id=20, y=0.5)
        conflict_lane = _Waypoint(4.0, road_id=21, y=0.5)
        upstream_ring = _Waypoint(0.0, road_id=22, y=4.0)
        exit_lane.previous = lambda _step: [conflict_lane]
        conflict_lane.previous = lambda _step: [upstream_ring]
        upstream_ring.previous = lambda _step: []
        preview = {
            "entry_index": 0,
            "exit_index": 3,
            "exit_order": [{
                "outbound": [{"waypoint": exit_lane}],
            }],
        }

        index, seeds, proximity_m = editor._vt1_exit1_conflict_seed(
            preview, vut_route)

        self.assertEqual(index, 2)
        self.assertEqual(seeds, [conflict_lane])
        self.assertAlmostEqual(proximity_m, 0.5)

    def test_initial_enter_explicitly_confirms_step_one_branch(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.is_roundabout_2b = True
        editor.roundabout_capable = True
        editor.roundabout_branch_confirmed = False
        editor._push_roundabout_history = lambda action: None
        messages = []
        editor._feedback = lambda message, error=False: messages.append((message, error))

        self.assertTrue(editor.confirm_active_roundabout_route())

        self.assertTrue(editor.roundabout_branch_confirmed)
        self.assertFalse(getattr(editor, "roundabout_topology_confirmed", False))
        self.assertIn("STEP 0分支已确认", messages[-1][0])
        self.assertIn("按P", messages[-1][0])

    def test_enter_on_newly_placed_vt2_advances_without_false_error(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.is_roundabout_2b = True
        editor.actor_points = [{
            "x": 10.0, "y": 5.0, "z": 0.0, "yaw": 0.0,
            "role": "vt2", "route_points": [],
        }]
        editor.selected_agent_idx = 0
        editor.selected_mode = "agent"
        editor.roundabout_branch_confirmed = True
        editor.roundabout_topology_confirmed = True
        editor.roundabout_vut_route_confirmed = True
        editor.roundabout_vt1_route_confirmed = True
        editor.roundabout_errors = []
        editor._ensure_roundabout_analysis = lambda force=False: {"valid": True}
        messages = []
        editor._feedback = lambda message, error=False: messages.append(
            (message, error))

        self.assertTrue(editor.confirm_active_roundabout_route())

        self.assertFalse(messages[-1][1])
        self.assertIn("VT2保持静止且不需要路线", messages[-1][0])
        self.assertIn("按S", messages[-1][0])

    def test_vt2_confirmation_runs_full_preflight_before_step_seven(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.is_roundabout_2b = True
        editor.actor_points = [{
            "x": 10.0, "y": 5.0, "z": 0.0, "yaw": 0.0,
            "role": "vt2", "route_points": [],
        }]
        editor.selected_agent_idx = 0
        editor.selected_mode = "agent"
        editor.roundabout_branch_confirmed = True
        editor.roundabout_topology_confirmed = True
        editor.roundabout_vut_route_confirmed = True
        editor.roundabout_vt1_route_confirmed = True
        editor.roundabout_errors = ["VUT起点余量不足"]
        editor._ensure_roundabout_analysis = lambda force=False: None
        messages = []
        editor._feedback = lambda message, error=False: messages.append(
            (message, error))

        self.assertFalse(editor.confirm_active_roundabout_route())

        self.assertTrue(messages[-1][1])
        self.assertIn("综合预检未通过", messages[-1][0])
        self.assertIn("VUT起点余量不足", messages[-1][0])

    def test_roundabout_clear_route_can_be_undone(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        editor.is_roundabout_2b = True
        editor.ego_point = {"x": 0.0, "y": 0.0, "z": 0.0, "yaw": 0.0}
        original_route = [
            {"x": 10.0, "y": 0.0, "z": 0.2, "yaw": 0.0},
            {"x": 20.0, "y": 0.0, "z": 0.2, "yaw": 0.0},
        ]
        editor.ego_route_points = list(original_route)
        editor.actor_points = []
        editor.selected_agent_idx = -1
        editor.selected_mode = "ego"
        editor.roundabout_place_role = "vt1"
        editor.roundabout_capable = True
        editor.roundabout_history = []
        editor.roundabout_dirty = False
        editor.roundabout_analysis = None
        editor._feedback = lambda *args, **kwargs: None

        editor.clear_ego_route()
        self.assertEqual(editor.ego_route_points, [])
        with mock.patch.object(EDITOR_MODULE.pygame.display, "set_caption"):
            editor.undo_roundabout_action()
        self.assertEqual(editor.ego_route_points, original_route)

    def test_save_expands_weather_and_vehicle_scenario_variants_once(self):
        with tempfile.TemporaryDirectory() as directory:
            editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
                EDITOR_MODULE.CarlaMapEditor0916)
            analysis = _analysis()
            editor._ensure_roundabout_analysis = lambda force=False: analysis
            editor.roundabout_errors = []
            editor.roundabout_capable = True
            editor.roundabout_branch_confirmed = True
            editor.roundabout_topology_confirmed = True
            editor.roundabout_vut_route_confirmed = True
            editor.roundabout_vt1_route_confirmed = True
            editor.base_seed = 41798
            editor.route_index = 0
            editor.save_dir = directory
            editor.town_name = "FakeRoundaboutMap"
            editor.ego_point = {
                "x": -5.0, "y": 0.0, "z": 0.0, "yaw": 0.0,
            }
            editor.ego_route_points = []
            vt1_actor = dict(analysis["vt1"])
            vt1_actor.update({"role": "vt1", "route_points": []})
            vt2_actor = dict(analysis["vt2"])
            vt2_actor.update({"role": "vt2", "route_points": []})
            editor.actor_points = [vt1_actor, vt2_actor]
            editor.roundabout_vut_route_cache = \
                editor._build_roundabout_route_cache(
                    "vut", editor.ego_route_points, editor.ego_point,
                    analysis["vut_dense"], analysis["vut_route_options"])
            editor.roundabout_vt1_route_cache = \
                editor._build_roundabout_route_cache(
                    "vt1", vt1_actor["route_points"], vt1_actor,
                    analysis["vt1_dense"], analysis["vt1_route_options"])
            editor.roundabout_dirty = False
            editor.roundabout_variants = {
                "weather": [
                    {"id": "clear", "parameters": {"cloudiness": 0.0}},
                    {"id": "cloudy", "parameters": {"cloudiness": 80.0}},
                ],
                "vehicles": [
                    {
                        "id": "tesla",
                        "vt1_model": "vehicle.tesla.model3",
                        "vt2_model": "vehicle.tesla.model3",
                    },
                    {
                        "id": "audi",
                        "vt1_model": "vehicle.audi.tt",
                        "vt2_model": "vehicle.audi.tt",
                    },
                ],
            }
            editor._feedback = lambda *args, **kwargs: None
            editor.clear_all_points = lambda: None

            editor.save_roundabout_trials()

            paths = sorted(pathlib.Path(directory).glob("scenario_2b_*.json"))
            self.assertEqual(len(paths), 4)
            configs = []
            for path in paths:
                with path.open("r", encoding="utf-8") as stream:
                    document = json.load(stream)
                config = document["FakeRoundaboutMap"]["route_01"][0]
                validate_roundabout_config(config, require_reproducibility=False)
                self.assertTrue(all(
                    "road_option" in point for point in config["ego_route"]))
                self.assertEqual(
                    config["roundabout_test"]["engineering"]["speed_limit_source"],
                    "fake_opendrive")
                self.assertEqual(
                    config["ego_route"],
                    editor.roundabout_vut_route_cache["payload"])
                self.assertEqual(
                    config["roundabout_test"]["vut"]["route_fingerprint"],
                    editor.roundabout_vut_route_cache["route_fingerprint"])
                self.assertEqual(
                    config["roundabout_test"]["vt1"]["route_fingerprint"],
                    editor.roundabout_vt1_route_cache["route_fingerprint"])
                configs.append(config)
            self.assertEqual(
                {item["weather"]["cloudiness"] for item in configs},
                {0.0, 80.0},
            )
            self.assertEqual(
                {actor["model"]
                 for item in configs
                 for actor in item["other_actors"]["center"]},
                {"vehicle.tesla.model3", "vehicle.audi.tt"},
            )
            self.assertTrue(all(
                "reproducibility" not in item["roundabout_test"]
                for item in configs))
            self.assertTrue(
                (pathlib.Path(directory) / "2b_scenario_manifest.json").is_file())

    def test_configured_target_models_are_checked_against_carla_library(self):
        editor = EDITOR_MODULE.CarlaMapEditor0916.__new__(
            EDITOR_MODULE.CarlaMapEditor0916)
        blueprints = [types.SimpleNamespace(id="vehicle.tesla.model3")]
        library = types.SimpleNamespace(filter=lambda _pattern: blueprints)
        editor.world = types.SimpleNamespace(
            get_blueprint_library=lambda: library)
        editor.roundabout_variants = {
            "vehicles": [{
                "id": "unavailable",
                "vt1_model": "vehicle.missing.one",
                "vt2_model": "vehicle.tesla.model3",
            }],
        }

        with self.assertRaisesRegex(ValueError, "vehicle.missing.one"):
            editor._validate_roundabout_vehicle_blueprints()


if __name__ == "__main__":
    unittest.main()
