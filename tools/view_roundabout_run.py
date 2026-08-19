#!/usr/bin/env python3
"""Interactive 2.b planned-route versus executed-trajectory viewer."""

import argparse
import csv
import gzip
import json
import math
import pickle
from pathlib import Path

import carla
import pygame


SCREEN_SIZE = (1200, 800)
BACKGROUND = (0, 0, 0)
MAP_ARROW = (0, 215, 45)
PLAN_VUT = (0, 220, 255)
ACTUAL_VUT = (245, 245, 245)
PLAN_VT1 = (255, 145, 20)
ACTUAL_VT1 = (255, 225, 70)
VT2 = (220, 80, 255)
ENTRY = (0, 220, 255)
EXITS = {"1": (255, 225, 70), "2": (255, 150, 30), "3": (255, 70, 70)}
ZOOM_MIN = 0.2
ZOOM_MAX = 100.0
ZOOM_SPEED = 1.2


def _load_result(path, record_index=-1):
    path = Path(path)
    if path.name in ("telemetry.csv.gz", "summary.json"):
        attempt_dir = path.parent
        summary_path = attempt_dir / "summary.json"
        telemetry_path = attempt_dir / "telemetry.csv.gz"
        if not summary_path.is_file() or not telemetry_path.is_file():
            raise ValueError(
                "结构化结果需要同一attempt目录中的summary.json和telemetry.csv.gz")
        record = json.loads(summary_path.read_text(encoding="utf-8"))
        samples = []
        with gzip.open(telemetry_path, "rt", encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream):
                sample = {
                    "frame": row.get("frame"),
                    "sim_time": row.get("sim_time_s"),
                    "trial_time": row.get("trial_time_s"),
                    "phase": row.get("phase"),
                }
                for role in ("vut", "vt1", "vt2"):
                    try:
                        x = float(row["{}_position_x".format(role)])
                        y = float(row["{}_position_y".format(role)])
                        z = float(row.get("{}_position_z".format(role)) or 0.0)
                    except (KeyError, TypeError, ValueError):
                        continue
                    sample[role] = {"location": {"x": x, "y": y, "z": z}}
                samples.append(sample)
        if not samples:
            raise ValueError("telemetry.csv.gz中没有可回放的轨迹")
        record["timeline_samples"] = samples
        return record
    with Path(path).open("rb") as stream:
        payload = pickle.load(stream)
    records = payload if isinstance(payload, list) else [payload]
    if not records:
        raise ValueError("结果文件没有试验记录")
    try:
        record = records[record_index]
    except IndexError as exc:
        raise ValueError(
            "record-index超出范围；结果中共有{}条记录".format(len(records))) from exc
    if not isinstance(record, dict):
        raise ValueError("选中的结果记录不是对象")
    samples = record.get("timeline_samples")
    if not isinstance(samples, list) or not samples:
        raise ValueError(
            "结果没有timeline_samples；新版结果请传入attempt目录的telemetry.csv.gz")
    return record


def _scenario_candidates(document):
    candidates = []

    def visit(value):
        if isinstance(value, dict):
            if isinstance(value.get("ego_route"), list) \
                    and isinstance(value.get("roundabout_test"), dict):
                candidates.append(value)
            else:
                for child in value.values():
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(document)
    return candidates


def _load_scenario(path, scenario_name=None):
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    candidates = _scenario_candidates(document)
    if not candidates:
        raise ValueError("场景JSON中没有2.b配置")
    if scenario_name:
        matches = [item for item in candidates if item.get("name") == scenario_name]
        if matches:
            return matches[0]
    if len(candidates) != 1:
        raise ValueError("场景JSON包含多条记录，请提供与结果名称匹配的文件")
    return candidates[0]


def _find_scenario_path(record, explicit_path=None):
    candidates = []
    if explicit_path:
        candidates.append(Path(explicit_path))
    input_file = record.get("input_file")
    if input_file:
        candidates.append(Path(input_file))
    scenario_name = record.get("scenario")
    if scenario_name:
        candidates.append(
            Path("save_scenarios/2b/definitions") / (scenario_name + ".json"))
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(
        "找不到本次结果对应的场景JSON；请使用--scenario-config明确指定")


def _points(route):
    result = []
    for point in route or []:
        if not isinstance(point, dict):
            continue
        try:
            x, y = float(point["x"]), float(point["y"])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(x) and math.isfinite(y):
            result.append((x, y))
    return result


def _sample_points(samples, role):
    result = []
    for sample in samples:
        actor = sample.get(role, {}) if isinstance(sample, dict) else {}
        location = actor.get("location", {}) if isinstance(actor, dict) else {}
        try:
            result.append((float(location["x"]), float(location["y"])))
        except (KeyError, TypeError, ValueError):
            result.append(None)
    return result


class RoundaboutRunViewer:
    def __init__(self, carla_map, record, scenario, result_path, scenario_path):
        self.map = carla_map
        self.record = record
        self.scenario = scenario
        self.result_path = Path(result_path).resolve()
        self.scenario_path = Path(scenario_path).resolve()
        self.samples = record["timeline_samples"]
        self.planned_vut = _points(scenario.get("ego_route"))
        roundabout = scenario["roundabout_test"]
        self.planned_vt1 = _points(roundabout.get("vt1", {}).get("route"))
        self.actual_vut = _sample_points(self.samples, "vut")
        self.actual_vt1 = _sample_points(self.samples, "vt1")
        self.actual_vt2 = _sample_points(self.samples, "vt2")
        self.entry_gate = roundabout.get("entry_gate")
        self.exit_gates = roundabout.get("exit_gates", {})
        self.planned_exit = str(roundabout.get("planned_exit", "?"))
        self.map_waypoints = carla_map.generate_waypoints(2.0)
        self.index = len(self.samples) - 1
        self.playing = False
        self.show_labels = False
        self.dragging = False
        self.last_mouse = (0, 0)
        self.zoom = 10.0
        self.offset_x = SCREEN_SIZE[0] / 2
        self.offset_y = SCREEN_SIZE[1] / 2

        pygame.init()
        self.screen = pygame.display.set_mode(SCREEN_SIZE, pygame.RESIZABLE)
        pygame.display.set_caption(
            "CARLA 2.b 规划路线 / 实际轨迹对比 | {}".format(
                record.get("scenario", "unknown")))
        self.clock = pygame.time.Clock()
        self.font = self._font(16)
        self.small_font = self._font(14)
        self._fit_view()

    @staticmethod
    def _font(size):
        for path in (
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf"):
            if Path(path).is_file():
                return pygame.font.Font(path, size)
        return pygame.font.SysFont(None, size)

    def world_to_screen(self, point):
        return (
            int(round(self.offset_x + point[0] * self.zoom)),
            int(round(self.offset_y - point[1] * self.zoom)),
        )

    def screen_to_world(self, point):
        return (
            (point[0] - self.offset_x) / self.zoom,
            (self.offset_y - point[1]) / self.zoom,
        )

    def _fit_view(self):
        points = self.planned_vut + self.planned_vt1
        points += [point for point in self.actual_vut if point]
        points += [point for point in self.actual_vt1 if point]
        if not points:
            return
        min_x = min(point[0] for point in points)
        max_x = max(point[0] for point in points)
        min_y = min(point[1] for point in points)
        max_y = max(point[1] for point in points)
        width, height = self.screen.get_size()
        usable_width = max(100.0, width - 80.0)
        usable_height = max(100.0, height - 160.0)
        self.zoom = max(ZOOM_MIN, min(
            ZOOM_MAX,
            usable_width / max(1.0, max_x - min_x),
            usable_height / max(1.0, max_y - min_y)))
        center_x = (min_x + max_x) / 2.0
        center_y = (min_y + max_y) / 2.0
        self.offset_x = width / 2.0 - center_x * self.zoom
        self.offset_y = (height + 60.0) / 2.0 + center_y * self.zoom

    def _zoom_at(self, position, steps):
        world = self.screen_to_world(position)
        self.zoom = max(
            ZOOM_MIN, min(ZOOM_MAX, self.zoom * (ZOOM_SPEED ** steps)))
        self.offset_x = position[0] - world[0] * self.zoom
        self.offset_y = position[1] + world[1] * self.zoom

    def _draw_segment(self, color, first, second, width=1):
        rect = self.screen.get_rect()
        clipped = rect.clipline(self.world_to_screen(first), self.world_to_screen(second))
        if clipped:
            pygame.draw.line(self.screen, color, clipped[0], clipped[1], width)

    def _draw_polyline(self, points, color, width=2, dashed=False):
        clean = [point for point in points if point is not None]
        for index, (first, second) in enumerate(zip(clean, clean[1:])):
            if dashed and index % 2:
                continue
            self._draw_segment(color, first, second, width)

    def _draw_map(self):
        width, height = self.screen.get_size()
        for waypoint in self.map_waypoints:
            location = waypoint.transform.location
            center = self.world_to_screen((location.x, location.y))
            if not (-12 <= center[0] <= width + 12 and -12 <= center[1] <= height + 12):
                continue
            yaw = math.radians(waypoint.transform.rotation.yaw)
            end = (
                center[0] + math.cos(yaw) * 7.0,
                center[1] - math.sin(yaw) * 7.0,
            )
            pygame.draw.line(self.screen, MAP_ARROW, center, end, 1)
            wing = 2.5
            for angle in (yaw + 2.55, yaw - 2.55):
                tip = (end[0] + math.cos(angle) * wing,
                       end[1] - math.sin(angle) * wing)
                pygame.draw.line(self.screen, MAP_ARROW, end, tip, 1)

    def _draw_gate(self, gate, color, label):
        if not isinstance(gate, dict):
            return
        try:
            first = (float(gate["left"]["x"]), float(gate["left"]["y"]))
            second = (float(gate["right"]["x"]), float(gate["right"]["y"]))
            center = (float(gate["center"]["x"]), float(gate["center"]["y"]))
        except (KeyError, TypeError, ValueError):
            return
        self._draw_segment(color, first, second, 4)
        if self.show_labels:
            position = self.world_to_screen(center)
            self.screen.blit(self.small_font.render(label, True, color),
                             (position[0] + 10, position[1] + 8))

    @staticmethod
    def _actor_location(sample, role):
        actor = sample.get(role, {})
        location = actor.get("location", {})
        try:
            return float(location["x"]), float(location["y"])
        except (KeyError, TypeError, ValueError):
            return None

    def _draw_current_actor(self, role, color, radius):
        point = self._actor_location(self.samples[self.index], role)
        if point is None:
            return
        center = self.world_to_screen(point)
        pygame.draw.circle(self.screen, (0, 0, 0), center, radius + 3)
        pygame.draw.circle(self.screen, color, center, radius)
        if self.show_labels:
            self.screen.blit(self.small_font.render(role.upper(), True, color),
                             (center[0] + radius + 5, center[1] - radius))

    def _draw_panel(self):
        sample = self.samples[self.index]
        vut = sample.get("vut", {})
        result_text = "PASS" if self.record.get("pass") is True else (
            "FAIL" if self.record.get("pass") is False else "INVALID")
        trial_time = sample.get("trial_time")
        rows = [
            "2.b运行轨迹对比 | {} | {} | 计划出口{}".format(
                self.record.get("scenario", "unknown"), result_text,
                self.planned_exit),
            "帧 {}/{} | 试验时间 {} | 阶段 {} | {}".format(
                self.index + 1, len(self.samples),
                "--" if trial_time is None else "{:.2f}s".format(trial_time),
                sample.get("phase", "--"),
                "播放" if self.playing else "暂停"),
            "VUT road/lane={}/{}  speed={:.1f}km/h".format(
                vut.get("road_id", "--"), vut.get("lane_id", "--"),
                float(vut.get("speed_mps", 0.0)) * 3.6),
            "青虚线=规划VUT | 白实线=实际VUT | 橙虚线=规划VT1 | 黄实线=实际VT1 | 紫=VT2",
            "Space播放/暂停  ←/→逐帧  Home/End首尾  F全图  H标签  中键拖动  滚轮缩放  Q退出",
        ]
        row_height = self.font.get_linesize() + 2
        panel_width = min(self.screen.get_width() - 16, 920)
        panel = pygame.Surface((panel_width, row_height * len(rows) + 10), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 210))
        self.screen.blit(panel, (8, 8))
        colors = ((230, 230, 230), (255, 225, 90), (180, 225, 255),
                  (205, 205, 205), (175, 175, 175))
        for index, row in enumerate(rows):
            self.screen.blit(self.font.render(row, True, colors[index]),
                             (16, 13 + index * row_height))

    def draw(self):
        self.screen.fill(BACKGROUND)
        self._draw_map()
        self._draw_gate(self.entry_gate, ENTRY, "VUT ENTRY")
        for number, gate in sorted(self.exit_gates.items()):
            self._draw_gate(gate, EXITS.get(str(number), (180, 180, 180)),
                            "EXIT {}".format(number))
        self._draw_polyline(self.planned_vut, PLAN_VUT, 2, dashed=True)
        self._draw_polyline(self.planned_vt1, PLAN_VT1, 2, dashed=True)
        self._draw_polyline(self.actual_vut[:self.index + 1], ACTUAL_VUT, 3)
        self._draw_polyline(self.actual_vt1[:self.index + 1], ACTUAL_VT1, 3)
        self._draw_current_actor("vut", ACTUAL_VUT, 7)
        self._draw_current_actor("vt1", ACTUAL_VT1, 6)
        self._draw_current_actor("vt2", VT2, 6)
        self._draw_panel()

    def run(self):
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_q:
                        running = False
                    elif event.key == pygame.K_SPACE:
                        if self.index >= len(self.samples) - 1:
                            self.index = 0
                        self.playing = not self.playing
                    elif event.key == pygame.K_LEFT:
                        self.playing = False
                        self.index = max(0, self.index - 1)
                    elif event.key == pygame.K_RIGHT:
                        self.playing = False
                        self.index = min(len(self.samples) - 1, self.index + 1)
                    elif event.key == pygame.K_HOME:
                        self.playing = False
                        self.index = 0
                    elif event.key == pygame.K_END:
                        self.playing = False
                        self.index = len(self.samples) - 1
                    elif event.key == pygame.K_f:
                        self._fit_view()
                    elif event.key == pygame.K_h:
                        self.show_labels = not self.show_labels
                elif event.type == pygame.MOUSEWHEEL:
                    self._zoom_at(pygame.mouse.get_pos(), event.y)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 2:
                    self.dragging = True
                    self.last_mouse = event.pos
                elif event.type == pygame.MOUSEBUTTONUP and event.button == 2:
                    self.dragging = False
                elif event.type == pygame.MOUSEMOTION and self.dragging:
                    self.offset_x += event.pos[0] - self.last_mouse[0]
                    self.offset_y += event.pos[1] - self.last_mouse[1]
                    self.last_mouse = event.pos
                elif event.type == pygame.VIDEORESIZE:
                    self._fit_view()
            if self.playing:
                self.index += 1
                if self.index >= len(self.samples):
                    self.index = len(self.samples) - 1
                    self.playing = False
            self.draw()
            pygame.display.flip()
            self.clock.tick(20)
        pygame.quit()


def main():
    parser = argparse.ArgumentParser(
        description="在CARLA编辑器风格地图中对比2.b规划路线和实际运行轨迹")
    parser.add_argument("result", help="包含timeline_samples的2b_result.pkl")
    parser.add_argument("--scenario-config", help="对应场景JSON；默认自动寻找")
    parser.add_argument("--record-index", type=int, default=-1,
                        help="PKL记录索引，默认最后一条")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2000)
    args = parser.parse_args()

    record = _load_result(args.result, args.record_index)
    scenario_path = _find_scenario_path(record, args.scenario_config)
    scenario = _load_scenario(scenario_path, record.get("scenario"))
    client = carla.Client(args.host, args.port)
    client.set_timeout(20.0)
    carla_map = client.get_world().get_map()
    expected_map = str(carla_map.name).rstrip("/").rsplit("/", 1)[-1]
    if expected_map not in scenario_path.read_text(encoding="utf-8")[:500]:
        raise RuntimeError(
            "当前CARLA地图{}与场景JSON不一致".format(carla_map.name))
    viewer = RoundaboutRunViewer(
        carla_map, record, scenario, args.result, scenario_path)
    viewer.run()


if __name__ == "__main__":
    main()
