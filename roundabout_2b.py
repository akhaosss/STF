"""Pure helpers for the GB/T 41798-2022 2.b roundabout scenario.

The helpers in this module deliberately do not import CARLA.  They cover the
parts of the scenario that should be deterministic and testable without a
running simulator: configuration validation, gate geometry, reproducible
three-trial metadata, aggregate verdicts, and durable result artifacts.

A gate is represented by two endpoints and an explicit downstream direction.
The preferred representation is::

    {
        "left": {"x": 1.0, "y": 2.0},
        "right": {"x": 1.0, "y": -2.0},
        "forward": {"x": 1.0, "y": 0.0}
    }

With endpoints ordered left-to-right as seen by an approaching vehicle, the
automatically derived positive normal points in the direction of travel.  A
gate may instead provide an explicit ``normal`` vector when endpoint order is
not meaningful.
"""

from __future__ import annotations

import copy
import csv
import gzip
import hashlib
import io
import json
import math
import os
import pickle
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone


SCHEMA_VERSION = "gbt41798-2b-v1"
TRIAL_COUNT = 3
STANDARD_TARGET_SPEED_KMH = 15.0
MANIFEST_FILENAME = "2b_matrix_manifest.json"


@contextmanager
def _atomic_writer(path, mode="w", **kwargs):
    """Write one artifact in-place atomically without exposing partial data."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    descriptor, temporary_path = tempfile.mkstemp(
        prefix=".{}-".format(os.path.basename(path)), dir=directory)
    os.close(descriptor)
    try:
        with open(temporary_path, mode, **kwargs) as stream:
            yield stream
        os.replace(temporary_path, path)
    except Exception:
        try:
            os.unlink(temporary_path)
        except OSError:
            pass
        raise


def canonical_hash(value):
    """Return a stable SHA-256 hash for a JSON-compatible value."""
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def roundabout_condition_payload(config):
    """Return the complete trial condition used for the matrix fingerprint.

    The three generated documents may differ only in their display name and
    reproducibility metadata.  Everything that can affect the test -- map
    geometry stored in the document, actors, weather, capability branch and
    engineering thresholds -- remains in this payload.
    """
    if not isinstance(config, dict) or not isinstance(
            config.get("roundabout_test"), dict):
        raise ValueError(
            "a full scenario config with roundabout_test is required")
    payload = copy.deepcopy(config)
    payload.pop("name", None)
    payload["roundabout_test"].pop("reproducibility", None)
    return payload


def roundabout_route_payload(config):
    """Return the manually defined geometry independently of test variants.

    Weather, vehicle blueprints and formal repetition metadata deliberately do
    not participate.  This lets one drawn route expand into many auditable
    conditions while retaining one stable route identity.
    """
    if not isinstance(config, dict) or not isinstance(
            config.get("roundabout_test"), dict):
        raise ValueError(
            "a full scenario config with roundabout_test is required")
    test = config["roundabout_test"]
    return {
        "ego_start": copy.deepcopy(config.get("ego_start")),
        "ego_route": copy.deepcopy(config.get("ego_route")),
        "planned_exit": test.get("planned_exit"),
        "roundabout_capable": test.get("roundabout_capable"),
        "entry_gate": copy.deepcopy(test.get("entry_gate")),
        "exit_gates": copy.deepcopy(test.get("exit_gates")),
        "downstream_entry": copy.deepcopy(test.get("downstream_entry")),
        "topology": copy.deepcopy(test.get("topology")),
        "vt1_route": copy.deepcopy((test.get("vt1") or {}).get("route")),
        "vt2_transform": copy.deepcopy((test.get("vt2") or {}).get("transform")),
    }


def roundabout_route_fingerprint(config):
    """Return the stable identity of one editor-drawn 2.b route."""
    return canonical_hash(roundabout_route_payload(config))


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def decode_vehicle_action(action):
    """Decode the first ``[throttle, steer, brake]`` row with safe limits.

    Plain lists/tuples and numpy-like values exposing ``tolist()`` are
    accepted.  Malformed or non-finite controller output is rejected instead
    of being silently applied to a CARLA actor.
    """
    if hasattr(action, "tolist"):
        action = action.tolist()
    if not isinstance(action, (list, tuple)) or not action:
        raise ValueError("vehicle action must contain a control row")
    first = action[0]
    row = first if isinstance(first, (list, tuple)) else action
    if len(row) < 3:
        raise ValueError("vehicle action must contain throttle, steer and brake")
    try:
        throttle, steer, brake = (float(row[index]) for index in range(3))
    except (TypeError, ValueError):
        raise ValueError("vehicle action values must be finite numbers")
    if not all(math.isfinite(value) for value in (throttle, steer, brake)):
        raise ValueError("vehicle action values must be finite numbers")
    throttle = max(0.0, min(1.0, throttle))
    steer = max(-1.0, min(1.0, steer))
    brake = max(0.0, min(1.0, brake))
    if brake > 0.05:
        throttle = 0.0
    return throttle, steer, brake


def required_vt1_initial_upstream_distance(
        vut_approach_distance_m,
        target_speed_kmh=15.0,
        vut_approach_speed_mps=15.0 / 3.6,
        stable_duration_s=1.0,
        setup_budget_s=2.0,
        entry_upstream_margin_m=3.0,
        timing_buffer_m=2.0,
        minimum_distance_m=15.0,
        vut_approach_time_budget_s=None,
        conflict_headway_target_s=0.0):
    """Return the engineering staging distance needed before the VUT entry.

    VT1 must cover its setup/stability budget and then reach the release line
    that makes it cross the shared conflict point before VUT by the requested
    lead time.  The timing buffer remains a separate, auditable engineering
    field.
    """
    values = {
        "vut_approach_distance_m": vut_approach_distance_m,
        "target_speed_kmh": target_speed_kmh,
        "vut_approach_speed_mps": vut_approach_speed_mps,
        "stable_duration_s": stable_duration_s,
        "setup_budget_s": setup_budget_s,
        "entry_upstream_margin_m": entry_upstream_margin_m,
        "timing_buffer_m": timing_buffer_m,
        "minimum_distance_m": minimum_distance_m,
        "conflict_headway_target_s": conflict_headway_target_s,
    }
    if vut_approach_time_budget_s is not None:
        values["vut_approach_time_budget_s"] = vut_approach_time_budget_s
    for name, value in values.items():
        if not _is_number(value):
            raise ValueError("{} must be a finite number".format(name))
    if target_speed_kmh <= 0:
        raise ValueError("target_speed_kmh must be positive")
    if vut_approach_speed_mps <= 0:
        raise ValueError("vut_approach_speed_mps must be positive")
    for name in (
            "vut_approach_distance_m", "stable_duration_s", "setup_budget_s",
            "entry_upstream_margin_m", "timing_buffer_m", "minimum_distance_m",
            "conflict_headway_target_s"):
        if values[name] < 0:
            raise ValueError("{} must be non-negative".format(name))
    if (vut_approach_time_budget_s is not None
            and float(vut_approach_time_budget_s) < 0.0):
        raise ValueError("vut_approach_time_budget_s must be non-negative")

    vt1_speed_mps = float(target_speed_kmh) / 3.6
    approach_time_s = float(vut_approach_distance_m) / float(vut_approach_speed_mps)
    if vut_approach_time_budget_s is not None:
        approach_time_s = max(approach_time_s, float(vut_approach_time_budget_s))
    setup_distance_m = vt1_speed_mps * (
        float(stable_duration_s) + float(setup_budget_s))
    release_remaining_m = vt1_speed_mps * max(
        0.0, approach_time_s - float(conflict_headway_target_s))
    required_distance_m = (
        setup_distance_m
        + max(float(entry_upstream_margin_m), release_remaining_m)
        + float(timing_buffer_m))
    return max(float(minimum_distance_m), required_distance_m)


def roundabout_conflict_sync_distances(
        vut_approach_distance_m,
        target_speed_kmh=15.0,
        vut_approach_speed_mps=15.0 / 3.6,
        target_headway_s=1.0,
        headway_tolerance_s=0.5,
        entry_upstream_min_distance_m=3.0):
    """Return route-normalized conflict ordering targets for VT1.

    ``target_headway_s`` is the desired time by which VT1 crosses the shared
    merge point *before* VUT.  The upstream observation plane is derived far
    enough before the gate that VT1 is still upstream there, while the release
    line is derived from the full VUT route distance to the conflict point.
    These are engineering parameters, not GB/T original distances.
    """
    values = {
        "vut_approach_distance_m": vut_approach_distance_m,
        "target_speed_kmh": target_speed_kmh,
        "vut_approach_speed_mps": vut_approach_speed_mps,
        "target_headway_s": target_headway_s,
        "headway_tolerance_s": headway_tolerance_s,
        "entry_upstream_min_distance_m": entry_upstream_min_distance_m,
    }
    for name, value in values.items():
        if not _is_number(value):
            raise ValueError("{} must be a finite number".format(name))
    if float(target_speed_kmh) <= 0.0:
        raise ValueError("target_speed_kmh must be positive")
    if float(vut_approach_speed_mps) <= 0.0:
        raise ValueError("vut_approach_speed_mps must be positive")
    for name in (
            "vut_approach_distance_m", "target_headway_s",
            "headway_tolerance_s", "entry_upstream_min_distance_m"):
        if float(values[name]) < 0.0:
            raise ValueError("{} must be non-negative".format(name))
    if float(headway_tolerance_s) > float(target_headway_s):
        raise ValueError("headway_tolerance_s must not exceed target_headway_s")

    vt1_speed_mps = float(target_speed_kmh) / 3.6
    approach_time_s = (
        float(vut_approach_distance_m) / float(vut_approach_speed_mps))
    minimum_lead_s = max(
        0.0, float(target_headway_s) - float(headway_tolerance_s))
    maximum_lead_s = float(target_headway_s) + float(headway_tolerance_s)
    # Use the latest allowed VT1 crossing (largest lead) to place the
    # observation plane.  VT1 therefore remains at least the configured
    # upstream distance at that plane for every accepted lead time.
    arrival_distance_m = float(vut_approach_speed_mps) * (
        maximum_lead_s
        + float(entry_upstream_min_distance_m) / vt1_speed_mps)
    target_gap_m = (
        float(entry_upstream_min_distance_m)
        + vt1_speed_mps * float(headway_tolerance_s))
    minimum_gap_m = float(entry_upstream_min_distance_m)
    maximum_gap_m = (
        float(entry_upstream_min_distance_m)
        + 2.0 * vt1_speed_mps * float(headway_tolerance_s))
    release_remaining_m = vt1_speed_mps * max(
        0.0, approach_time_s - float(target_headway_s))
    return {
        "vut_approach_time_s": approach_time_s,
        "target_lead_time_s": float(target_headway_s),
        "minimum_lead_time_s": minimum_lead_s,
        "maximum_lead_time_s": maximum_lead_s,
        "entry_arrival_distance_m": arrival_distance_m,
        "target_entry_gap_m": target_gap_m,
        "minimum_entry_gap_m": minimum_gap_m,
        "maximum_entry_gap_m": maximum_gap_m,
        "vt1_release_remaining_m": release_remaining_m,
    }


def _as_xy(point, name="point"):
    """Convert common JSON point representations to an ``(x, y)`` tuple."""
    if isinstance(point, dict):
        if "location" in point and not ("x" in point and "y" in point):
            point = point["location"]
        elif "transform" in point and not ("x" in point and "y" in point):
            point = point["transform"]
        try:
            x = float(point["x"])
            y = float(point["y"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("{} must contain finite numeric x/y values".format(name))
    elif isinstance(point, (list, tuple)) and len(point) >= 2:
        try:
            x = float(point[0])
            y = float(point[1])
        except (TypeError, ValueError):
            raise ValueError("{} must contain finite numeric x/y values".format(name))
    else:
        raise ValueError("{} must be an x/y mapping or a two-item sequence".format(name))
    if not math.isfinite(x) or not math.isfinite(y):
        raise ValueError("{} must contain finite numeric x/y values".format(name))
    return x, y


def _gate_geometry(gate, name="gate"):
    """Return ``(start, end, unit_normal)`` for a supported gate mapping."""
    if isinstance(gate, dict) and "gate" in gate:
        gate = gate["gate"]

    first = second = None
    if isinstance(gate, dict):
        for first_key, second_key in (
            ("left", "right"),
            ("start", "end"),
            ("p1", "p2"),
        ):
            if first_key in gate and second_key in gate:
                first, second = gate[first_key], gate[second_key]
                break
        if first is None and isinstance(gate.get("points"), (list, tuple)):
            points = gate["points"]
            if len(points) == 2:
                first, second = points

        if first is None and "center" in gate and "width_m" in gate:
            center = _as_xy(gate["center"], "{}.center".format(name))
            width = gate["width_m"]
            if not _is_number(width) or width <= 0:
                raise ValueError("{}.width_m must be positive".format(name))
            if "normal" in gate or "forward" in gate:
                normal_key = "normal" if "normal" in gate else "forward"
                normal = _as_xy(
                    gate[normal_key], "{}.{}".format(name, normal_key))
            elif _is_number(gate.get("approach_yaw")):
                yaw = math.radians(float(gate["approach_yaw"]))
                normal = math.cos(yaw), math.sin(yaw)
            else:
                raise ValueError(
                    "{} with center/width_m also needs normal or approach_yaw".format(name))
            normal_length = math.hypot(normal[0], normal[1])
            if normal_length <= 1e-12:
                raise ValueError("{}.normal must be non-zero".format(name))
            nx, ny = normal[0] / normal_length, normal[1] / normal_length
            tangent = -ny, nx
            half_width = float(width) * 0.5
            first = center[0] + tangent[0] * half_width, center[1] + tangent[1] * half_width
            second = center[0] - tangent[0] * half_width, center[1] - tangent[1] * half_width
    elif isinstance(gate, (list, tuple)) and len(gate) == 2:
        first, second = gate

    if first is None or second is None:
        raise ValueError(
            "{} must define left/right, start/end, p1/p2, points, or center/width_m".format(name))

    start = _as_xy(first, "{}.first".format(name))
    end = _as_xy(second, "{}.second".format(name))
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    if length <= 1e-9:
        raise ValueError("{} endpoints must be distinct".format(name))

    if isinstance(gate, dict) and gate.get("center") is not None:
        declared_center = _as_xy(gate["center"], "{}.center".format(name))
        endpoint_center = ((start[0] + end[0]) * 0.5, (start[1] + end[1]) * 0.5)
        if math.hypot(
                declared_center[0] - endpoint_center[0],
                declared_center[1] - endpoint_center[1]) > 1e-3:
            raise ValueError(
                "{}.center must equal the midpoint of its gate endpoints".format(name))

    explicit_normal = None
    explicit_normal_key = "normal"
    if isinstance(gate, dict):
        if gate.get("normal") is not None:
            explicit_normal = gate["normal"]
        elif gate.get("forward") is not None:
            explicit_normal = gate["forward"]
            explicit_normal_key = "forward"
    if explicit_normal is not None:
        nx, ny = _as_xy(
            explicit_normal, "{}.{}".format(name, explicit_normal_key))
        normal_length = math.hypot(nx, ny)
        if normal_length <= 1e-12:
            raise ValueError("{}.{} must be non-zero".format(
                name, explicit_normal_key))
        normal = nx / normal_length, ny / normal_length
    elif isinstance(gate, dict) and _is_number(gate.get("approach_yaw")):
        yaw = math.radians(float(gate["approach_yaw"]))
        normal = math.cos(yaw), math.sin(yaw)
    else:
        # For preferred left/right ordering, this is the direction of travel.
        normal = -dy / length, dx / length
    return start, end, normal


def route_length_2d(route):
    """Return the planar length of a route represented by JSON points."""
    if not isinstance(route, (list, tuple)):
        raise ValueError("route must be a list of points")
    points = [_as_xy(point, "route[{}]".format(index)) for index, point in enumerate(route)]
    return sum(
        math.hypot(second[0] - first[0], second[1] - first[1])
        for first, second in zip(points, points[1:])
    )


def validate_route(
    route,
    name="route",
    min_points=2,
    minimum_total_length_m=0.5,
    max_segment_length_m=None,
):
    """Validate a sparse route and return a small geometry summary.

    ``max_segment_length_m`` is optional because editor points are intentionally
    sparse.  Callers that already densified the route can opt into a stricter
    continuity check.
    """
    if not isinstance(route, (list, tuple)):
        raise ValueError("{} must be a list of points".format(name))
    if len(route) < int(min_points):
        raise ValueError("{} needs at least {} points".format(name, min_points))
    points = [_as_xy(point, "{}[{}]".format(name, index)) for index, point in enumerate(route)]
    segment_lengths = []
    for index, (first, second) in enumerate(zip(points, points[1:])):
        length = math.hypot(second[0] - first[0], second[1] - first[1])
        if length <= 1e-9:
            raise ValueError("{} has duplicate consecutive points at {} and {}".format(
                name, index, index + 1))
        if max_segment_length_m is not None:
            if not _is_number(max_segment_length_m) or max_segment_length_m <= 0:
                raise ValueError("max_segment_length_m must be positive")
            if length > float(max_segment_length_m):
                raise ValueError(
                    "{} segment {}-{} is {:.3f} m, over the {:.3f} m limit".format(
                        name, index, index + 1, length, float(max_segment_length_m)))
        segment_lengths.append(length)
    total_length = sum(segment_lengths)
    if total_length < float(minimum_total_length_m):
        raise ValueError("{} is shorter than {:.3f} m".format(
            name, float(minimum_total_length_m)))
    return {
        "point_count": len(points),
        "length_m": total_length,
        "bounds": {
            "min_x": min(point[0] for point in points),
            "min_y": min(point[1] for point in points),
            "max_x": max(point[0] for point in points),
            "max_y": max(point[1] for point in points),
        },
    }


def gate_signed_distance(point, gate):
    """Return signed perpendicular distance from ``point`` to a gate line.

    A negative-to-positive transition is a forward crossing when the gate's
    normal points downstream.
    """
    xy = _as_xy(point)
    start, end, normal = _gate_geometry(gate)
    center = (start[0] + end[0]) * 0.5, (start[1] + end[1]) * 0.5
    return (xy[0] - center[0]) * normal[0] + (xy[1] - center[1]) * normal[1]


def gate_crossing(previous_point, current_point, gate, direction="negative_to_positive",
                  tolerance=1e-7, margin_m=0.0):
    """Return whether one motion segment crosses the finite gate segment.

    ``direction`` accepts ``negative_to_positive`` (the normal driving
    direction), ``positive_to_negative``, or ``either``.  The finite segment
    check prevents a crossing of the gate's infinite line far outside the
    intended lane from being reported.
    """
    aliases = {
        "forward": "negative_to_positive",
        "reverse": "positive_to_negative",
        1: "negative_to_positive",
        -1: "positive_to_negative",
        0: "either",
    }
    direction = aliases.get(direction, direction)
    if direction not in ("negative_to_positive", "positive_to_negative", "either"):
        raise ValueError("unsupported gate crossing direction: {!r}".format(direction))
    if not _is_number(tolerance) or tolerance < 0:
        raise ValueError("tolerance must be a non-negative number")
    if not _is_number(margin_m) or margin_m < 0:
        raise ValueError("margin_m must be a non-negative number")

    previous = _as_xy(previous_point, "previous_point")
    current = _as_xy(current_point, "current_point")
    start, end, normal = _gate_geometry(gate)
    center = (start[0] + end[0]) * 0.5, (start[1] + end[1]) * 0.5

    def signed(point):
        return ((point[0] - center[0]) * normal[0]
                + (point[1] - center[1]) * normal[1])

    before, after = signed(previous), signed(current)
    forward = before < -tolerance and after >= -tolerance
    reverse = before > tolerance and after <= tolerance
    if direction == "negative_to_positive" and not forward:
        return False
    if direction == "positive_to_negative" and not reverse:
        return False
    if direction == "either" and not (forward or reverse):
        return False

    denominator = before - after
    if abs(denominator) <= 1e-12:
        return False
    ratio = before / denominator
    if ratio < -tolerance or ratio > 1.0 + tolerance:
        return False
    intersection = (
        previous[0] + ratio * (current[0] - previous[0]),
        previous[1] + ratio * (current[1] - previous[1]),
    )
    gate_dx, gate_dy = end[0] - start[0], end[1] - start[1]
    gate_length = math.hypot(gate_dx, gate_dy)
    tangent = gate_dx / gate_length, gate_dy / gate_length
    along = ((intersection[0] - center[0]) * tangent[0]
             + (intersection[1] - center[1]) * tangent[1])
    return abs(along) <= gate_length * 0.5 + float(margin_m) + tolerance


def route_crosses_gate(route, gate, direction="either", margin_m=0.0):
    """Return whether any consecutive pair in ``route`` crosses ``gate``."""
    validate_route(route)
    return any(
        gate_crossing(first, second, gate, direction=direction, margin_m=margin_m)
        for first, second in zip(route, route[1:])
    )


def generate_roundabout_trial_matrix(base_seed, route_geometry, repetitions=TRIAL_COUNT):
    """Return deterministic metadata for the required three repeated trials.

    The trial conditions remain identical; only their independently derived
    random seeds differ.  The returned tuple is ``(trials, matrix_seed,
    route_fingerprint)``.
    """
    if isinstance(base_seed, bool):
        raise ValueError("base_seed must be an integer")
    try:
        base_seed = int(base_seed)
    except (TypeError, ValueError):
        raise ValueError("base_seed must be an integer")
    if repetitions != TRIAL_COUNT:
        raise ValueError("GB/T 41798 2.b requires exactly {} trials".format(TRIAL_COUNT))

    # Historical API name retained for compatibility.  ``route_geometry`` is
    # the complete condition payload, so this value is a condition identity,
    # not the fingerprint of only the manually drawn route.
    route_fingerprint = canonical_hash(route_geometry)
    matrix_seed = int(canonical_hash({
        "schema_version": SCHEMA_VERSION,
        "base_seed": base_seed,
        "route_fingerprint": route_fingerprint,
        "trial_count": repetitions,
    })[:16], 16) % (2 ** 32)
    matrix_id = canonical_hash({
        "matrix_seed": matrix_seed,
        "route_fingerprint": route_fingerprint,
    })[:16]
    trials = []
    for trial_index in range(1, repetitions + 1):
        trial_seed = int(canonical_hash({
            "matrix_seed": matrix_seed,
            "route_fingerprint": route_fingerprint,
            "trial_index": trial_index,
        })[:16], 16) % (2 ** 32)
        trials.append({
            "schema_version": SCHEMA_VERSION,
            "generator_version": SCHEMA_VERSION,
            "matrix_id": matrix_id,
            "base_seed": base_seed,
            "matrix_seed": matrix_seed,
            "trial_seed": trial_seed,
            "trial_index": trial_index,
            "trial_count": repetitions,
            "route_fingerprint": route_fingerprint,
            "condition_fingerprint": route_fingerprint,
        })
    return trials, matrix_seed, route_fingerprint


def update_roundabout_manifest(save_dir, entries, base_seed):
    """Merge generated 2.b scenario entries into a reproducibility manifest."""
    os.makedirs(save_dir, exist_ok=True)
    path = os.path.join(save_dir, MANIFEST_FILENAME)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "base_seed": int(base_seed),
        "trial_count_per_matrix": TRIAL_COUNT,
        "entries": [],
    }
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as stream:
                current = json.load(stream)
            if current.get("schema_version") == SCHEMA_VERSION:
                manifest = current
                manifest["trial_count_per_matrix"] = TRIAL_COUNT
                previous_seed = manifest.get("base_seed")
                if isinstance(previous_seed, int) and not isinstance(previous_seed, bool):
                    for old_entry in manifest.get("entries", []):
                        if isinstance(old_entry, dict):
                            old_entry.setdefault("base_seed", previous_seed)
        except (OSError, ValueError, AttributeError):
            pass

    by_file = {}
    for entry in manifest.get("entries", []):
        if isinstance(entry, dict) and entry.get("file"):
            by_file[entry["file"]] = entry
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("file"):
            raise ValueError("every manifest entry must contain a non-empty file field")
        entry = dict(entry)
        entry.setdefault("base_seed", int(base_seed))
        by_file[entry["file"]] = entry
    manifest["entries"] = [by_file[name] for name in sorted(by_file)]
    seeds = sorted({entry.get("base_seed") for entry in manifest["entries"]
                    if isinstance(entry.get("base_seed"), int)
                    and not isinstance(entry.get("base_seed"), bool)})
    manifest["base_seed"] = seeds[0] if len(seeds) == 1 else None
    manifest["base_seeds"] = seeds

    with _atomic_writer(path, "w", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2, ensure_ascii=False, sort_keys=True)
    return path


def _section_and_outer(config):
    if not isinstance(config, dict):
        return None, None
    if "roundabout_test" in config:
        return config.get("roundabout_test"), config
    return config, None


def _exit_gate(exit_gates, number):
    if not isinstance(exit_gates, dict):
        return None
    return exit_gates.get(str(number), exit_gates.get(number))


def _add_gate_error(errors, gate, path):
    try:
        _gate_geometry(gate, path)
        return True
    except ValueError as exc:
        errors.append(str(exc))
        return False


def _add_route_error(errors, route, path):
    try:
        validate_route(route, path)
        return True
    except ValueError as exc:
        errors.append(str(exc))
        return False


def _validate_topology_summary(errors, topology):
    """Validate the editor's auditable access-arm topology summary."""
    path = "roundabout_test.topology"
    if not isinstance(topology, dict):
        errors.append("{} must be an object".format(path))
        return
    if topology.get("verified") is not True:
        errors.append("{}.verified must be true".format(path))
    operator_confirmation = topology.get("operator_confirmation")
    if (not isinstance(operator_confirmation, dict)
            or operator_confirmation.get("confirmed") is not True):
        errors.append(
            "{}.operator_confirmation.confirmed must be true".format(path))

    topology_hash = topology.get("topology_hash")
    topology_core = copy.deepcopy(topology)
    for field in ("verified", "topology_hash", "detection_method"):
        topology_core.pop(field, None)
    if (not isinstance(topology_hash, str) or len(topology_hash) != 64
            or topology_hash != canonical_hash(topology_core)):
        errors.append("{}.topology_hash must match the detected topology".format(path))

    arm_count = topology.get("arm_count")
    if (not isinstance(arm_count, int) or isinstance(arm_count, bool)
            or arm_count < 3):
        errors.append("{}.arm_count must be an integer of at least 3".format(path))

    arms = topology.get("arms")
    if not isinstance(arms, list):
        errors.append("{}.arms must enumerate every access arm".format(path))
        return
    if isinstance(arm_count, int) and not isinstance(arm_count, bool) \
            and len(arms) != arm_count:
        errors.append("{}.arms must contain exactly arm_count entries".format(path))
    if len(arms) < 3:
        errors.append("{}.arms must contain at least 3 access arms".format(path))

    arm_ids = []
    for index, arm in enumerate(arms):
        arm_path = "{}.arms[{}]".format(path, index)
        if not isinstance(arm, dict):
            errors.append("{} must be an object".format(arm_path))
            continue
        if arm.get("arm_id") in (None, ""):
            errors.append("{}.arm_id is required".format(arm_path))
        else:
            arm_ids.append(str(arm["arm_id"]))
        for field in ("inbound_lane_count", "outbound_lane_count"):
            count = arm.get(field)
            if (not isinstance(count, int) or isinstance(count, bool) or count < 1):
                errors.append("{}.{} must be an integer of at least 1".format(
                    arm_path, field))
        for direction in ("inbound", "outbound"):
            lanes_field = "{}_lanes".format(direction)
            count_field = "{}_lane_count".format(direction)
            lanes = arm.get(lanes_field)
            if not isinstance(lanes, list) or not lanes:
                errors.append("{}.{} must enumerate at least one lane".format(
                    arm_path, lanes_field))
                continue
            count = arm.get(count_field)
            if isinstance(count, int) and not isinstance(count, bool) \
                    and len(lanes) != count:
                errors.append("{}.{} length must match {}".format(
                    arm_path, lanes_field, count_field))
            identities = []
            for lane_index, lane in enumerate(lanes):
                identity = _lane_identity(lane)
                if identity is None:
                    errors.append(
                        "{}.{}[{}] must contain integer road_id, section_id "
                        "and lane_id".format(arm_path, lanes_field, lane_index))
                else:
                    identities.append(identity)
            if len(identities) != len(set(identities)):
                errors.append("{}.{} lane identities must be unique".format(
                    arm_path, lanes_field))
    if len(arm_ids) != len(set(arm_ids)):
        errors.append("{}.arms arm_id values must be unique".format(path))

    entry_arm_id = topology.get("vut_entry_arm_id")
    downstream_arm_id = topology.get("downstream_entry_arm_id")
    circulation_order = topology.get("circulation_order")
    if not entry_arm_id:
        errors.append("{}.vut_entry_arm_id is required".format(path))
    if not downstream_arm_id:
        errors.append("{}.downstream_entry_arm_id is required".format(path))
    known = set(arm_ids)
    if entry_arm_id is not None and str(entry_arm_id) not in known:
        errors.append("{}.vut_entry_arm_id must reference an enumerated arm".format(path))
    if downstream_arm_id is not None and str(downstream_arm_id) not in known:
        errors.append(
            "{}.downstream_entry_arm_id must reference an enumerated arm".format(path))
    if not isinstance(circulation_order, list) or len(circulation_order) != len(arms):
        errors.append("{}.circulation_order must enumerate every arm".format(path))
    elif len(set(str(value) for value in circulation_order)) != len(circulation_order):
        errors.append("{}.circulation_order values must be unique".format(path))
    else:
        order = [str(value) for value in circulation_order]
        if set(order) != known:
            errors.append("{}.circulation_order must contain the topology arm_ids".format(path))
        if entry_arm_id is not None and str(entry_arm_id) in order:
            entry_index = order.index(str(entry_arm_id))
            expected_downstream = order[(entry_index + 1) % len(order)]
            if (downstream_arm_id is not None
                    and str(downstream_arm_id) != expected_downstream):
                errors.append(
                    "{}.downstream_entry_arm_id must be the first arm after "
                    "vut_entry_arm_id in circulation_order".format(path))

    exit_arm_ids = topology.get("exit_arm_ids")
    if not isinstance(exit_arm_ids, dict) \
            or {str(key) for key in exit_arm_ids} != {"1", "2", "3"}:
        errors.append("{}.exit_arm_ids must map exits 1, 2 and 3 to arms".format(path))
    elif any(str(value) not in known for value in exit_arm_ids.values()):
        errors.append("{}.exit_arm_ids must reference enumerated arms".format(path))


def _actor_role(actor):
    if not isinstance(actor, dict):
        return ""
    role = str(actor.get("role", actor.get("rolename", ""))).strip().lower()
    role = role.replace("_", "").replace("-", "")
    return {
        "vt1": "vt1", "target1": "vt1", "targetvehicle1": "vt1",
        "vt2": "vt2", "target2": "vt2", "targetvehicle2": "vt2",
    }.get(role, role)


def _lane_identity(value):
    """Return a strict CARLA ``(road, section, lane)`` identity or ``None``."""
    if not isinstance(value, dict):
        return None
    identity = []
    for field in ("road_id", "section_id", "lane_id"):
        item = value.get(field)
        if not isinstance(item, int) or isinstance(item, bool):
            return None
        identity.append(item)
    return tuple(identity)


def _gate_lane_identities(gate):
    if not isinstance(gate, dict):
        return set()
    values = gate.get("allowed_lanes")
    if not isinstance(values, list):
        values = [gate]
    return {identity for identity in (_lane_identity(value) for value in values)
            if identity is not None}


def _topology_arm(topology, arm_id):
    if not isinstance(topology, dict):
        return None
    return next((arm for arm in topology.get("arms", [])
                 if isinstance(arm, dict)
                 and str(arm.get("arm_id")) == str(arm_id)), None)


def _point_lateral_distance(point, gate):
    xy = _as_xy(point)
    start, end, _ = _gate_geometry(gate)
    center = ((start[0] + end[0]) * 0.5, (start[1] + end[1]) * 0.5)
    length = math.hypot(end[0] - start[0], end[1] - start[1])
    tangent = ((end[0] - start[0]) / length, (end[1] - start[1]) / length)
    return abs((xy[0] - center[0]) * tangent[0]
               + (xy[1] - center[1]) * tangent[1]), length * 0.5


def roundabout_config_errors(config, require_reproducibility=True):
    """Return human-readable errors for one full or inner 2.b config.

    Unknown fields are intentionally ignored so controllers and topology
    analyzers can add metadata without requiring a schema bump.
    """
    errors = []
    section, outer = _section_and_outer(config)
    if not isinstance(section, dict):
        return ["roundabout_test must be an object"]

    if section.get("schema_version") != SCHEMA_VERSION:
        errors.append("roundabout_test.schema_version must be {}".format(SCHEMA_VERSION))

    if not isinstance(section.get("roundabout_capable"), bool):
        errors.append("roundabout_test.roundabout_capable must be a boolean")

    planned_exit = section.get("planned_exit")
    if isinstance(planned_exit, bool) or planned_exit not in (2, 3):
        errors.append("roundabout_test.planned_exit must be 2 or 3")

    topology = section.get("topology")
    _validate_topology_summary(errors, topology)
    if isinstance(topology, dict):
        nested_topology_hash = topology.get("topology_hash")
        if section.get("topology_hash") != nested_topology_hash:
            errors.append(
                "roundabout_test.topology_hash must match topology.topology_hash")

    entry_gate_valid = _add_gate_error(
        errors, section.get("entry_gate"), "roundabout_test.entry_gate")

    exit_gates = section.get("exit_gates")
    exit_gate_validity = {}
    if not isinstance(exit_gates, dict):
        errors.append("roundabout_test.exit_gates must be an object keyed by 1, 2 and 3")
    else:
        for number in (1, 2, 3):
            exit_gate_validity[number] = _add_gate_error(
                errors, _exit_gate(exit_gates, number),
                "roundabout_test.exit_gates.{}".format(number))

    downstream_entry = section.get("downstream_entry")
    downstream_gate_valid = _add_gate_error(
        errors, downstream_entry, "roundabout_test.downstream_entry")

    if isinstance(topology, dict):
        entry_arm = _topology_arm(topology, topology.get("vut_entry_arm_id"))
        entry_lanes = {
            identity for identity in (
                _lane_identity(item) for item in (entry_arm or {}).get("inbound_lanes", []))
            if identity is not None}
        if entry_gate_valid and not (_gate_lane_identities(section.get("entry_gate"))
                                     & entry_lanes):
            errors.append(
                "roundabout_test.entry_gate lane must belong to the VUT inbound arm")

        exit_arm_ids = topology.get("exit_arm_ids", {})
        for number in (1, 2, 3):
            arm = _topology_arm(topology, exit_arm_ids.get(str(number)))
            outbound_lanes = {
                identity for identity in (
                    _lane_identity(item) for item in (arm or {}).get("outbound_lanes", []))
                if identity is not None}
            gate = _exit_gate(exit_gates, number)
            if exit_gate_validity.get(number) and not (
                    _gate_lane_identities(gate) & outbound_lanes):
                errors.append(
                    "roundabout_test.exit_gates.{} lanes must belong to its topology arm".format(
                        number))

    vut = section.get("vut", {})
    vut_route = vut.get("route") if isinstance(vut, dict) else None
    vut_route_valid = _add_route_error(errors, vut_route, "VUT route")
    if outer is not None and canonical_hash(outer.get("ego_route")) != canonical_hash(vut_route):
        errors.append("ego_route must exactly match roundabout_test.vut.route")

    vt1 = section.get("vt1")
    vt1_route = None
    vt1_route_valid = False
    if not isinstance(vt1, dict):
        errors.append("roundabout_test.vt1 must be an object")
    else:
        speed = vt1.get("target_speed_kmh")
        if not _is_number(speed) or not math.isclose(
                float(speed), STANDARD_TARGET_SPEED_KMH, rel_tol=0.0, abs_tol=1e-9):
            errors.append("roundabout_test.vt1.target_speed_kmh must be 15")
        vt1_route = vt1.get("route")
        vt1_route_valid = _add_route_error(errors, vt1_route, "VT1 route")

    vt2 = section.get("vt2")
    if not isinstance(vt2, dict):
        errors.append("roundabout_test.vt2 must be an object")
    else:
        if str(vt2.get("motion", "")).lower() != "stationary":
            errors.append("roundabout_test.vt2.motion must be stationary")
        if vt2.get("route"):
            errors.append("roundabout_test.vt2 must not have a moving route")
        try:
            _as_xy(vt2.get("transform"), "roundabout_test.vt2.transform")
        except ValueError as exc:
            errors.append(str(exc))
        if isinstance(topology, dict):
            expected_arm = topology.get("downstream_entry_arm_id")
            if expected_arm is not None and str(vt2.get("arm_id")) != str(expected_arm):
                errors.append(
                    "roundabout_test.vt2.arm_id must match the first downstream entry arm")
        if isinstance(downstream_entry, dict):
            gate_arm = downstream_entry.get("arm_id")
            if gate_arm is not None and str(vt2.get("arm_id")) != str(gate_arm):
                errors.append(
                    "roundabout_test.vt2.arm_id must match downstream_entry.arm_id")
            vt2_lane = _lane_identity(vt2)
            if vt2_lane is None:
                errors.append(
                    "roundabout_test.vt2 road_id/section_id/lane_id must be integers")
            inbound_lanes = downstream_entry.get("inbound_lanes")
            if not isinstance(inbound_lanes, list) or not inbound_lanes:
                errors.append(
                    "roundabout_test.downstream_entry.inbound_lanes must be a non-empty list")
            else:
                inbound_identities = [_lane_identity(item) for item in inbound_lanes]
                if any(identity is None for identity in inbound_identities):
                    errors.append(
                        "roundabout_test.downstream_entry.inbound_lanes must contain "
                        "integer road_id/section_id/lane_id values")
                elif vt2_lane is not None and vt2_lane not in set(inbound_identities):
                    errors.append(
                        "roundabout_test.vt2 road_id/section_id/lane_id must match "
                        "a downstream_entry inbound lane")

    if outer is not None:
        actors = outer.get("other_actors", {}).get("center", []) \
            if isinstance(outer.get("other_actors"), dict) else None
        if not isinstance(actors, list):
            errors.append("other_actors.center must be a list containing VT1 and VT2")
        else:
            role_actors = {
                role: [actor for actor in actors if _actor_role(actor) == role]
                for role in ("vt1", "vt2")
            }
            for role in ("vt1", "vt2"):
                if len(role_actors[role]) != 1:
                    errors.append(
                        "other_actors.center must contain exactly one {}".format(
                            role.upper()))
            unassigned_actors = [
                actor for actor in actors
                if isinstance(actor, dict)
                and _actor_role(actor) not in ("vt1", "vt2")
            ]
            if unassigned_actors or len(actors) != 2:
                errors.append("2.b other_actors.center must contain only VT1 and VT2")
            for role in ("vt1", "vt2"):
                if len(role_actors[role]) != 1:
                    continue
                actor = role_actors[role][0]
                if not str(actor.get("model", "")).startswith("vehicle."):
                    errors.append("{} actor model must be vehicle.*".format(role.upper()))
                if actor.get("autopilot") is not False:
                    errors.append("{} actor autopilot must be false".format(role.upper()))
                try:
                    _as_xy(actor.get("transform"), "{} actor transform".format(role.upper()))
                except ValueError as exc:
                    errors.append(str(exc))
                if role == "vt1" and isinstance(vt1, dict):
                    if canonical_hash(actor.get("route")) != canonical_hash(vt1.get("route")):
                        errors.append("VT1 actor route must match roundabout_test.vt1.route")
                    if str(actor.get("motion", "")).lower() != "route_follow":
                        errors.append("VT1 actor motion must be route_follow")
                    speed = actor.get("target_speed_kmh", STANDARD_TARGET_SPEED_KMH)
                    if not _is_number(speed) or not math.isclose(
                            float(speed), STANDARD_TARGET_SPEED_KMH,
                            rel_tol=0.0, abs_tol=1e-9):
                        errors.append("VT1 actor target_speed_kmh must be 15")
                    try:
                        actor_xy = _as_xy(actor.get("transform"))
                        route_xy = _as_xy(vt1.get("route", [None])[0])
                        if math.hypot(
                                actor_xy[0] - route_xy[0],
                                actor_xy[1] - route_xy[1]) > 3.0:
                            errors.append("VT1 actor transform must be at the start of its route")
                    except (IndexError, TypeError, ValueError):
                        pass
                if role == "vt2" and isinstance(vt2, dict):
                    if actor.get("route"):
                        errors.append("VT2 actor must not have a moving route")
                    if str(actor.get("motion", "")).lower() != "stationary":
                        errors.append("VT2 actor motion must be stationary")
                    if canonical_hash(actor.get("transform")) != canonical_hash(
                            vt2.get("transform")):
                        errors.append(
                            "VT2 actor transform must match roundabout_test.vt2.transform")

    engineering = section.get("engineering")
    if not isinstance(engineering, dict):
        errors.append("roundabout_test.engineering must be an object")
    else:
        positive_fields = (
            "vt1_speed_tolerance_kmh",
            "vt1_stable_duration_s",
            "vt1_stabilization_timeout_s",
            "vt1_upstream_max_distance_m",
            "vt1_conflict_max_offset_m",
            "vt1_speed_continuity_duration_s",
            "vt1_exit_observation_timeout_s",
            "speed_limit_unobservable_duration_s",
            "stop_duration_s",
            "emergency_brake_deceleration_mps2",
            "emergency_brake_duration_s",
            "route_completion_distance_m",
            "incapable_observation_s",
            "lane_direction_violation_duration_s",
            "lane_guidance_violation_duration_s",
            "off_road_violation_duration_s",
            "sut_readiness_timeout_s",
            "scenario_timeout_s",
            "timeout_s",
            "vt2_downstream_entry_max_distance_m",
            "camera_frame_timeout_s",
            "vut_approach_time_budget_s",
            "vt1_conflict_headway_target_s",
            "vt1_release_remaining_m",
            "vt1_conflict_entry_gap_target_m",
            "vt1_conflict_entry_gap_min_m",
            "vt1_conflict_entry_gap_max_m",
            "lane_guidance_corridor_min_half_width_m",
            "lane_guidance_corridor_max_half_width_m",
        )
        non_negative_fields = (
            "vt1_initial_upstream_min_distance_m",
            "vt1_entry_upstream_min_distance_m",
            "vt1_setup_distance_budget_s",
            "vt1_timing_buffer_m",
            "vut_approach_distance_m",
            "vut_sync_approach_distance_m",
            "stop_speed_threshold_mps",
            "vt2_stationary_speed_threshold_mps",
            "exit_completion_distance_m",
            "gate_margin_m",
            "speed_limit_tolerance_kmh",
            "timeline_sample_interval_s",
            "indicator_lookback_s",
            "vut_start_entry_gate_margin_m",
            "entry_arrival_distance_m",
            "vt1_conflict_headway_tolerance_s",
            "lane_guidance_corridor_extra_m",
        )
        for field in positive_fields:
            if field in engineering and (
                    not _is_number(engineering[field]) or engineering[field] <= 0):
                errors.append("roundabout_test.engineering.{} must be positive".format(field))
        for field in non_negative_fields:
            if field in engineering and (
                    not _is_number(engineering[field]) or engineering[field] < 0):
                errors.append(
                    "roundabout_test.engineering.{} must be non-negative".format(field))
        target_headway = engineering.get("vt1_conflict_headway_target_s")
        headway_tolerance = engineering.get("vt1_conflict_headway_tolerance_s")
        if (_is_number(target_headway) and _is_number(headway_tolerance)
                and float(headway_tolerance) > float(target_headway)):
            errors.append(
                "roundabout_test.engineering.vt1_conflict_headway_tolerance_s "
                "must not exceed vt1_conflict_headway_target_s")
        corridor_min = engineering.get("lane_guidance_corridor_min_half_width_m")
        corridor_max = engineering.get("lane_guidance_corridor_max_half_width_m")
        if (_is_number(corridor_min) and _is_number(corridor_max)
                and float(corridor_min) > float(corridor_max)):
            errors.append(
                "roundabout_test.engineering lane corridor minimum must not exceed maximum")
        gap_min = engineering.get("vt1_conflict_entry_gap_min_m")
        gap_target = engineering.get("vt1_conflict_entry_gap_target_m")
        gap_max = engineering.get("vt1_conflict_entry_gap_max_m")
        if all(_is_number(value) for value in (gap_min, gap_target, gap_max)) \
                and not float(gap_min) <= float(gap_target) <= float(gap_max):
            errors.append(
                "roundabout_test.engineering conflict entry gap must satisfy min <= target <= max")
        if "vut_approach_speed_assumption_kmh" in engineering and (
                not _is_number(engineering["vut_approach_speed_assumption_kmh"])
                or engineering["vut_approach_speed_assumption_kmh"] <= 0):
            errors.append(
                "roundabout_test.engineering.vut_approach_speed_assumption_kmh "
                "must be positive")
        if "speed_limit_kmh" in engineering and (
                not _is_number(engineering["speed_limit_kmh"])
                or engineering["speed_limit_kmh"] <= 0):
            errors.append("roundabout_test.engineering.speed_limit_kmh must be positive")
        speed_limits_by_road = engineering.get("speed_limit_by_road_id")
        if speed_limits_by_road is not None:
            if not isinstance(speed_limits_by_road, dict) or not speed_limits_by_road:
                errors.append(
                    "roundabout_test.engineering.speed_limit_by_road_id must be a non-empty object")
            else:
                for road_id, value in speed_limits_by_road.items():
                    try:
                        int(road_id)
                    except (TypeError, ValueError):
                        errors.append(
                            "roundabout_test.engineering.speed_limit_by_road_id keys "
                            "must be road IDs")
                    if not _is_number(value) or value <= 0:
                        errors.append(
                            "roundabout_test.engineering.speed_limit_by_road_id values "
                            "must be positive")
        if (not _is_number(engineering.get("speed_limit_kmh"))
                and not isinstance(speed_limits_by_road, dict)):
            errors.append(
                "roundabout_test.engineering must provide an auditable speed_limit_kmh "
                "or speed_limit_by_road_id fallback")
        for field in ("emergency_brake_threshold",):
            if field in engineering and (
                    not _is_number(engineering[field])
                    or not 0.0 <= engineering[field] <= 1.0):
                errors.append(
                    "roundabout_test.engineering.{} must be between 0 and 1".format(
                        field))
        if "max_timeline_samples" in engineering and (
                not isinstance(engineering["max_timeline_samples"], int)
                or isinstance(engineering["max_timeline_samples"], bool)
                or engineering["max_timeline_samples"] < 1):
            errors.append(
                "roundabout_test.engineering.max_timeline_samples must be a positive integer")
        for field in ("allow_config_odd_alert_debug", "formal_hmi_evidence_required"):
            if field in engineering and not isinstance(engineering[field], bool):
                errors.append(
                    "roundabout_test.engineering.{} must be a boolean".format(field))

    if (isinstance(vt2, dict) and downstream_gate_valid
            and isinstance(vt2.get("transform"), (dict, list, tuple))):
        maximum_distance = 100.0
        lateral_margin = 1.0
        if isinstance(engineering, dict):
            configured_maximum = engineering.get(
                "vt2_downstream_entry_max_distance_m", 100.0)
            if _is_number(configured_maximum) and configured_maximum > 0:
                maximum_distance = float(configured_maximum)
            configured_margin = engineering.get("gate_margin_m", 1.0)
            if _is_number(configured_margin) and configured_margin >= 0:
                lateral_margin = float(configured_margin)
        try:
            signed_distance = gate_signed_distance(vt2["transform"], downstream_entry)
            lateral_distance, half_width = _point_lateral_distance(
                vt2["transform"], downstream_entry)
            if signed_distance > lateral_margin or signed_distance < -maximum_distance:
                errors.append(
                    "roundabout_test.vt2.transform must be upstream of and within "
                    "{:.1f} m of downstream_entry".format(maximum_distance))
            # A long approach may curve relative to the gate tangent.  The
            # editor proves CARLA lane connectivity/arm membership; use the
            # finite-width check only in the locally linear gate vicinity.
            local_gate_span = max(10.0, half_width * 3.0)
            if (abs(signed_distance) <= local_gate_span
                    and lateral_distance > half_width + lateral_margin):
                errors.append(
                    "roundabout_test.vt2.transform must lie on the downstream entry lane")
        except (TypeError, ValueError):
            pass

    if outer is not None and entry_gate_valid:
        start_margin = 3.0
        if isinstance(engineering, dict):
            configured_margin = engineering.get(
                "vut_start_entry_gate_margin_m", start_margin)
            if _is_number(configured_margin) and configured_margin >= 0:
                start_margin = float(configured_margin)
        try:
            start_distance = gate_signed_distance(
                outer.get("ego_start"), section["entry_gate"])
            if start_distance >= 0.0 or -start_distance < start_margin:
                errors.append(
                    "ego_start must be upstream of roundabout_test.entry_gate "
                    "with at least {:.1f} m center margin".format(start_margin))
        except (TypeError, ValueError) as exc:
            errors.append("ego_start is invalid: {}".format(exc))

    reproducibility = section.get("reproducibility")
    if require_reproducibility:
        if not isinstance(reproducibility, dict):
            errors.append("roundabout_test.reproducibility must be an object")
        else:
            trial_index = reproducibility.get("trial_index")
            if isinstance(trial_index, bool) or trial_index not in (1, 2, 3):
                errors.append("roundabout_test.reproducibility.trial_index must be 1, 2 or 3")
            if reproducibility.get("trial_count", TRIAL_COUNT) != TRIAL_COUNT:
                errors.append("roundabout_test.reproducibility.trial_count must be 3")
            for field in ("base_seed", "matrix_seed", "trial_seed"):
                value = reproducibility.get(field)
                if not isinstance(value, int) or isinstance(value, bool):
                    errors.append(
                        "roundabout_test.reproducibility.{} must be an integer".format(field))
            fingerprint = reproducibility.get("route_fingerprint")
            if not isinstance(fingerprint, str) or len(fingerprint) != 64:
                errors.append(
                    "roundabout_test.reproducibility.route_fingerprint must be a SHA-256 hex string")
            else:
                try:
                    int(fingerprint, 16)
                except ValueError:
                    errors.append(
                        "roundabout_test.reproducibility.route_fingerprint must be a SHA-256 hex string")
            reproduction_topology_hash = reproducibility.get("topology_hash")
            if (reproduction_topology_hash is not None
                    and isinstance(topology, dict)
                    and reproduction_topology_hash != topology.get("topology_hash")):
                errors.append(
                    "roundabout_test.reproducibility.topology_hash must match "
                    "topology.topology_hash")

            # A full scenario document is what the editor and run.py use.
            # Recompute every derived value so three files cannot claim the
            # same matrix while silently changing a test condition.
            if outer is not None:
                try:
                    condition_payload = roundabout_condition_payload(outer)
                    expected_trials, expected_matrix_seed, expected_fingerprint = \
                        generate_roundabout_trial_matrix(
                            reproducibility.get("base_seed"), condition_payload)
                    expected_by_index = {
                        item["trial_index"]: item for item in expected_trials
                    }
                    expected = expected_by_index.get(trial_index)
                    if fingerprint != expected_fingerprint:
                        errors.append(
                            "roundabout_test.reproducibility.route_fingerprint "
                            "does not match the complete trial condition")
                    if reproducibility.get("matrix_seed") != expected_matrix_seed:
                        errors.append(
                            "roundabout_test.reproducibility.matrix_seed "
                            "does not match the complete trial condition")
                    if expected is not None:
                        for field in ("matrix_id", "trial_seed"):
                            if reproducibility.get(field) != expected[field]:
                                errors.append(
                                    "roundabout_test.reproducibility.{} is invalid".format(
                                        field))
                except (TypeError, ValueError) as exc:
                    errors.append(
                        "roundabout_test.reproducibility cannot be verified: {}".format(
                            exc))

    margin = 0.0
    if isinstance(engineering, dict) and _is_number(engineering.get("gate_margin_m")):
        margin = max(0.0, float(engineering["gate_margin_m"]))
    if entry_gate_valid and vut_route_valid:
        try:
            if not route_crosses_gate(
                    vut_route, section["entry_gate"],
                    direction="negative_to_positive", margin_m=margin):
                errors.append(
                    "VUT route does not cross roundabout_test.entry_gate in its forward direction")
        except ValueError:
            pass
    if planned_exit in (2, 3) and vut_route_valid and exit_gate_validity.get(planned_exit):
        try:
            if not route_crosses_gate(
                    vut_route, _exit_gate(exit_gates, planned_exit),
                    direction="negative_to_positive", margin_m=margin):
                errors.append(
                    "VUT route does not cross planned exit {} gate in its forward direction".format(
                        planned_exit))
        except ValueError:
            pass
    if vt1_route_valid and exit_gate_validity.get(1):
        try:
            if not route_crosses_gate(
                    vt1_route, _exit_gate(exit_gates, 1),
                    direction="negative_to_positive", margin_m=margin):
                errors.append("VT1 route does not cross exit 1 gate in its forward direction")
        except ValueError:
            pass
    return errors


def validate_roundabout_config(config, require_reproducibility=True):
    """Validate one 2.b configuration, raising ``ValueError`` on failure."""
    errors = roundabout_config_errors(config, require_reproducibility=require_reproducibility)
    if errors:
        raise ValueError("invalid 2.b roundabout config: " + "; ".join(errors))
    section, outer = _section_and_outer(config)
    vut_route = section.get("vut", {}).get("route")
    if vut_route is None and outer is not None:
        vut_route = outer.get("ego_route")
    return {
        "planned_exit": section["planned_exit"],
        "vut_route": validate_route(vut_route, "VUT route"),
        "vt1_route": validate_route(section["vt1"]["route"], "VT1 route"),
        "exit_gate_count": len(section["exit_gates"]),
        "trial_index": section.get("reproducibility", {}).get("trial_index"),
    }


def validate_roundabout_matrix(configs):
    """Validate complete, reproducible three-trial 2.b matrices."""
    if not isinstance(configs, (list, tuple)) or not configs:
        raise ValueError("invalid 2.b test matrix: no configurations found")
    errors = []
    groups = {}
    for position, config in enumerate(configs):
        config_errors = roundabout_config_errors(config, require_reproducibility=True)
        if config_errors:
            errors.extend("config {}: {}".format(position + 1, error) for error in config_errors)
            continue
        section, _ = _section_and_outer(config)
        reproducibility = section["reproducibility"]
        group_key = reproducibility.get("matrix_id") or reproducibility["route_fingerprint"]
        groups.setdefault(group_key, []).append(section)

    for matrix_id, group in groups.items():
        label = str(matrix_id)[:16]
        if len(group) != TRIAL_COUNT:
            errors.append("matrix {} has {} trials, expected {}".format(
                label, len(group), TRIAL_COUNT))
        reproductions = [item["reproducibility"] for item in group]
        indexes = {item.get("trial_index") for item in reproductions}
        if indexes != {1, 2, 3}:
            errors.append("matrix {} trial indexes are not 1/2/3".format(label))
        trial_seeds = [item.get("trial_seed") for item in reproductions]
        if len(set(trial_seeds)) != len(trial_seeds):
            errors.append("matrix {} trial seeds are not unique".format(label))
        for field in ("base_seed", "matrix_seed", "route_fingerprint"):
            if len({item.get(field) for item in reproductions}) != 1:
                errors.append("matrix {} has inconsistent {} values".format(label, field))
        if len({item.get("planned_exit") for item in group}) != 1:
            errors.append("matrix {} has inconsistent planned_exit values".format(label))

    if not groups:
        errors.append("no valid 2.b matrix configurations found")
    if errors:
        raise ValueError("invalid 2.b test matrix: " + "; ".join(errors))
    return {
        "matrix_count": len(groups),
        "trial_count": sum(len(group) for group in groups.values()),
        "planned_exits": sorted({group[0]["planned_exit"] for group in groups.values()}),
    }


def _record_trial_index(record):
    value = record.get("trial_index")
    if value is None and isinstance(record.get("reproducibility"), dict):
        value = record["reproducibility"].get("trial_index")
    if not isinstance(value, int) or isinstance(value, bool) or value not in (1, 2, 3):
        return None
    return value


def _record_is_valid(record):
    values = [record[key] for key in ("trial_valid", "precondition_valid", "valid")
              if key in record]
    return bool(values) and all(value is True for value in values)


ROUNDABOUT_QUANTITATIVE_METRICS = {
    "trial_duration_s": "s",
    "driven_distance_m": "m",
    "average_speed_mps": "m/s",
    "max_speed_kmh": "km/h",
    "max_deceleration_mps2": "m/s^2",
    "minimum_ttc_s": "s",
    "minimum_vut_vt1_distance_m": "m",
    "minimum_vut_vt2_distance_m": "m",
    "vt1_speed_mean_kmh": "km/h",
    "vt1_speed_std_kmh": "km/h",
    "vt1_speed_at_entry_kmh": "km/h",
    "vt1_lead_time_at_vut_entry_s": "s",
}


def _finite_metric(record, name):
    value = record.get(name)
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _quantitative_statistics(records):
    """Summarise numeric trial metrics without changing the 3/3 verdict."""
    statistics = {}
    for name, unit in ROUNDABOUT_QUANTITATIVE_METRICS.items():
        values = [_finite_metric(record, name) for record in records]
        values = [value for value in values if value is not None]
        if not values:
            continue
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        statistics[name] = {
            "unit": unit,
            "count": len(values),
            "mean": round(mean, 6),
            "std": round(math.sqrt(variance), 6),
            "min": round(min(values), 6),
            "max": round(max(values), 6),
        }
    return statistics


def aggregate_three_trial_verdict(records):
    """Aggregate one required set of three trials into PASS/FAIL/incomplete.

    A ledger may contain retries for the same ``trial_index``.  For each index
    the latest valid attempt is authoritative; when no valid attempt exists,
    the latest attempt remains selected and the matrix is incomplete.  Invalid
    preconditions therefore never become a tested-system failure.
    """
    records = list(records or [])
    attempts_by_index = {index: [] for index in (1, 2, 3)}
    all_attempts_indexed = True
    for record in records:
        index = _record_trial_index(record)
        if index not in attempts_by_index:
            all_attempts_indexed = False
            continue
        attempts_by_index[index].append(record)

    selected_by_index = {}
    for index, attempts in attempts_by_index.items():
        if not attempts:
            continue
        selected_by_index[index] = next(
            (record for record in reversed(attempts) if _record_is_valid(record)),
            attempts[-1],
        )
    selected_records = [selected_by_index[index]
                        for index in (1, 2, 3) if index in selected_by_index]
    valid_records = [record for record in selected_records if _record_is_valid(record)]
    invalid_records = [record for record in selected_records if not _record_is_valid(record)]
    passed = [record for record in valid_records if record.get("pass") is True]
    failed = [record for record in valid_records if record.get("pass") is False]
    undecided = [record for record in valid_records if record.get("pass") not in (True, False)]

    complete_shape = (
        all_attempts_indexed
        and set(selected_by_index) == {1, 2, 3}
    )
    complete = complete_shape and not invalid_records and not undecided
    if complete and len(passed) == TRIAL_COUNT:
        status, verdict = "pass", True
    elif complete and failed:
        status, verdict = "fail", False
    else:
        status, verdict = "incomplete", None

    reasons = []
    if not complete_shape:
        reasons.append("three distinct trials with indexes 1/2/3 are required")
    for record in invalid_records:
        index = _record_trial_index(record)
        reason = record.get("invalid_reason") or record.get("invalid_reasons") \
            or record.get("failure_reasons") or "invalid precondition"
        if isinstance(reason, (list, tuple)):
            reason = ", ".join(str(item) for item in reason)
        reasons.append("trial {} invalid: {}".format(index if index is not None else "?", reason))
    for record in undecided:
        reasons.append("trial {} has no PASS/FAIL verdict".format(
            _record_trial_index(record) if _record_trial_index(record) is not None else "?"))
    for record in failed:
        failure_reasons = record.get("failure_reasons") or ["failed"]
        if not isinstance(failure_reasons, (list, tuple)):
            failure_reasons = [failure_reasons]
        reasons.extend(
            "trial {}: {}".format(_record_trial_index(record), reason)
            for reason in failure_reasons
        )

    return {
        "status": status,
        "pass": verdict,
        "complete": complete,
        "expected_trial_count": TRIAL_COUNT,
        "trial_count": len(selected_records),
        "attempt_count": len(records),
        "valid_trial_count": len(valid_records),
        "invalid_trial_count": len(invalid_records),
        "pass_count": len(passed),
        "fail_count": len(failed),
        "failure_reasons": reasons,
        # Numeric values are descriptive statistics only.  GB/T 41798-2022
        # still requires all three selected trials to pass.
        "quantitative_statistics": _quantitative_statistics(valid_records),
        "selected_trials": [
            {
                "trial_index": _record_trial_index(record),
                "attempt_index": record.get("attempt_index"),
                "valid": _record_is_valid(record),
                "pass": record.get("pass"),
            }
            for record in selected_records
        ],
    }


def _json_safe(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item"):
        return _json_safe(value.item())
    return str(value)


def roundabout_record_summary(record):
    """Return the lightweight ledger representation of one attempt.

    High-frequency samples and exact snapshots live in the structured
    condition/attempt artifacts.  Keeping them out of the batch ledger avoids
    quadratic rewrites and multi-gigabyte index files for large expansions.
    """
    summary = copy.deepcopy(_json_safe(record))
    for bulky in (
            "timeline_samples", "timeline_events", "phase_history",
            "collision_events", "lane_invasion_events", "fixture_collision_events",
            "scenario_snapshot", "runtime_environment"):
        summary.pop(bulky, None)
    return summary


def _markdown_cell(value):
    if isinstance(value, (dict, list, tuple)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if value is None:
        return "—"
    return str(value).replace("|", "\\|").replace("\n", " ")


def load_existing_roundabout_records(output_dir, scenario_code="2b"):
    """Load the durable 2.b ledger created by the result writer."""
    path = os.path.join(output_dir, "{}_result.json".format(scenario_code))
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as stream:
            payload = json.load(stream)
        records = payload.get("records", []) if isinstance(payload, dict) else []
        if not isinstance(records, list):
            raise RuntimeError("2.b result ledger records must be a list: {}".format(path))
        return records
    except (OSError, ValueError) as exc:
        raise RuntimeError("cannot read existing 2.b result ledger {}: {}".format(
            path, exc))


def _safe_path_component(value, fallback):
    value = str(value or "").strip().lower()
    cleaned = []
    for character in value:
        cleaned.append(character if character.isalnum() or character in "-_" else "-")
    value = "".join(cleaned).strip("-_")
    return value or fallback


def _record_condition_identity(record):
    generation = record.get("generation") or {}
    route_fingerprint = (
        record.get("route_definition_fingerprint")
        or generation.get("route_fingerprint")
        or record.get("topology_hash")
        or record.get("route_fingerprint")
        or "unknown")
    condition_fingerprint = (
        record.get("condition_fingerprint")
        or generation.get("condition_fingerprint")
        or record.get("route_fingerprint")
        or record.get("matrix_id")
        or "unknown")
    route_id = (
        record.get("drawn_route_id")
        or generation.get("route_id")
        or "route_{}".format(str(route_fingerprint)[:10]))
    capability = "capable" if record.get("roundabout_capable", True) else "incapable"
    planned_exit = record.get("planned_exit")
    route_directory = "{}_exit{}_{}".format(
        _safe_path_component(route_id, "route_unknown"),
        planned_exit if planned_exit is not None else "unknown",
        capability)
    condition_id = (
        record.get("condition_id")
        or generation.get("condition_id")
        or "condition")
    condition_directory = "{}__c_{}".format(
        _safe_path_component(condition_id, "condition"),
        str(condition_fingerprint)[:10])
    return {
        "route_id": route_id,
        "route_fingerprint": route_fingerprint,
        "route_directory": route_directory,
        "condition_id": condition_id,
        "condition_fingerprint": condition_fingerprint,
        "condition_directory": condition_directory,
    }


def _artifact_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _flatten_telemetry_sample(sample):
    row = {
        "frame": sample.get("frame"),
        "sim_time_s": sample.get("sim_time"),
        "trial_time_s": sample.get("trial_time"),
        "phase": sample.get("phase"),
    }
    for role in ("vut", "vt1", "vt2"):
        actor = sample.get(role) or {}
        for section, prefix in (
                (actor.get("location") or {}, "position"),
                (actor.get("rotation") or {}, "rotation"),
                (actor.get("velocity") or {}, "velocity"),
                (actor.get("acceleration") or {}, "acceleration"),
                (actor.get("angular_velocity") or {}, "angular_velocity"),
                (actor.get("applied_control") or actor.get("control") or {},
                 "applied_control"),
                (actor.get("requested_control") or {}, "requested_control")):
            for key, value in section.items():
                row["{}_{}_{}".format(role, prefix, key)] = value
        for key in (
                "actor_id", "type_id", "speed_mps", "longitudinal_velocity_mps",
                "lateral_velocity_mps", "longitudinal_acceleration_mps2",
                "lateral_acceleration_mps2", "road_id", "section_id", "lane_id",
                "light_state_raw", "light_state"):
            row["{}_{}".format(role, key)] = actor.get(key)
    relative = sample.get("relative_metrics") or {}
    for key, value in relative.items():
        row[key] = value
    route = sample.get("route_metrics") or {}
    for key, value in route.items():
        row["route_{}".format(key)] = value
    row["ads_active"] = sample.get("ads_active")
    row["ads_control_source"] = sample.get("ads_control_source")
    return row


def _write_gzip_csv(path, rows):
    rows = list(rows)
    fieldnames = sorted({key for row in rows for key in row})
    with _atomic_writer(path, "wb") as binary_stream:
        with gzip.GzipFile(fileobj=binary_stream, mode="wb", mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as text_stream:
                writer = csv.DictWriter(text_stream, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)


def _write_structured_roundabout_artifacts(records, output_dir, aggregates):
    """Write condition/trial artifacts while retaining the legacy ledger."""
    aggregate_lookup = {
        (str(item.get("matrix_id")), str(item.get("run_id") or "")): item
        for item in aggregates
    }
    for record in records:
        identity = _record_condition_identity(record)
        condition_dir = os.path.join(
            output_dir, identity["route_directory"], identity["condition_directory"])
        execution_mode = record.get("execution_mode") or "formal"
        if execution_mode == "screening":
            attempt_dir = os.path.join(
                condition_dir, "screening", "attempt_{:02d}".format(
                    int(record.get("attempt_index") or 1)))
        else:
            trial_index = record.get("trial_index")
            attempt_dir = os.path.join(
                condition_dir,
                "trial_{:02d}".format(int(trial_index or 0)),
                "attempt_{:02d}".format(int(record.get("attempt_index") or 1)))
        os.makedirs(attempt_dir, exist_ok=True)

        timeline = list(record.get("timeline_samples") or [])
        events = {
            "phase_history": record.get("phase_history") or [],
            "timeline_events": record.get("timeline_events") or [],
            "collision_events": record.get("collision_events") or [],
            "lane_invasion_events": record.get("lane_invasion_events") or [],
            "fixture_collision_events": record.get("fixture_collision_events") or [],
        }
        summary = copy.deepcopy(record)
        for bulky in (
                "timeline_samples", "timeline_events", "phase_history",
                "collision_events", "lane_invasion_events", "fixture_collision_events",
                "scenario_snapshot"):
            summary.pop(bulky, None)
        summary["identity"] = identity
        summary["artifact_files"] = {
            "telemetry": "telemetry.csv.gz",
            "events": "events.json",
            "video": record.get("video_path"),
        }
        summary_path = os.path.join(attempt_dir, "summary.json")
        events_path = os.path.join(attempt_dir, "events.json")
        telemetry_path = os.path.join(attempt_dir, "telemetry.csv.gz")
        with _atomic_writer(summary_path, "w", encoding="utf-8") as stream:
            json.dump(summary, stream, indent=2, ensure_ascii=False, sort_keys=True)
        with _atomic_writer(events_path, "w", encoding="utf-8") as stream:
            json.dump(events, stream, indent=2, ensure_ascii=False, sort_keys=True)
        _write_gzip_csv(
            telemetry_path,
            [_flatten_telemetry_sample(sample) for sample in timeline])

        condition_payload = {
            "schema_version": SCHEMA_VERSION,
            "identity": identity,
            "standard_clause": record.get("standard_clause"),
            "evidence_profile": record.get("evidence_profile"),
            "parameter_correspondence": record.get("parameter_correspondence"),
            "scenario_snapshot": record.get("scenario_snapshot"),
            "runtime_environment": record.get("runtime_environment"),
        }
        condition_path = os.path.join(condition_dir, "condition.json")
        with _atomic_writer(condition_path, "w", encoding="utf-8") as stream:
            json.dump(condition_payload, stream, indent=2,
                      ensure_ascii=False, sort_keys=True)

        matrix_id = record.get("matrix_id") or record.get("route_fingerprint")
        aggregate = aggregate_lookup.get(
            (str(matrix_id), str(record.get("run_id") or "")))
        if aggregate is not None:
            aggregate_path = os.path.join(condition_dir, "aggregate.json")
            with _atomic_writer(aggregate_path, "w", encoding="utf-8") as stream:
                json.dump(aggregate, stream, indent=2,
                          ensure_ascii=False, sort_keys=True)

        artifact_paths = [summary_path, events_path, telemetry_path, condition_path]
        video_path = record.get("video_path")
        if video_path and os.path.isfile(video_path):
            artifact_paths.append(video_path)
        manifest = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "files": [
                {
                    "path": os.path.relpath(path, condition_dir),
                    "sha256": _artifact_sha256(path),
                    "size_bytes": os.path.getsize(path),
                }
                for path in artifact_paths
            ],
        }
        with _atomic_writer(
                os.path.join(attempt_dir, "artifact_manifest.json"),
                "w", encoding="utf-8") as stream:
            json.dump(manifest, stream, indent=2,
                      ensure_ascii=False, sort_keys=True)


def _matrix_aggregates(records):
    groups = {}
    for record in records:
        reproducibility = record.get("reproducibility", {})
        matrix_id = record.get("matrix_id") or reproducibility.get("matrix_id") \
            or record.get("route_fingerprint") or reproducibility.get("route_fingerprint")
        if not matrix_id:
            continue
        run_id = str(record.get("run_id") or "")
        groups.setdefault((str(matrix_id), run_id), []).append(record)
    aggregates = []
    for (matrix_id, run_id), group in sorted(groups.items()):
        aggregate = aggregate_three_trial_verdict(group)
        aggregate.update({
            "matrix_id": matrix_id,
            "run_id": run_id or None,
            "run_ids": [run_id] if run_id else [],
            "planned_exit": next(
                (record.get("planned_exit") for record in reversed(group)
                 if record.get("planned_exit") is not None), None),
        })
        aggregates.append(aggregate)
    return aggregates


def write_roundabout_result_artifacts(
        records, output_dir, scenario_code="2b", metadata=None):
    """Persist 2.b trial results as Markdown, JSON, CSV, and pickle files."""
    os.makedirs(output_dir, exist_ok=True)
    prefix = os.path.join(output_dir, "{}_result".format(scenario_code))
    safe_records = [_json_safe(record) for record in records]
    ledger_records = [roundabout_record_summary(record) for record in safe_records]
    safe_metadata = _json_safe(metadata or {})
    aggregates = _matrix_aggregates(ledger_records)
    generated_at = datetime.now(timezone.utc).isoformat()

    payload = {
        "schema_version": SCHEMA_VERSION,
        "scenario_code": scenario_code,
        "generated_at_utc": generated_at,
        "metadata": safe_metadata,
        "records": ledger_records,
        "aggregates": aggregates,
    }
    with _atomic_writer(prefix + ".json", "w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, ensure_ascii=False, sort_keys=True)

    preferred_columns = [
        "run_id", "scenario", "drawn_route_id", "route_definition_fingerprint",
        "condition_id", "condition_fingerprint", "matrix_id", "trial_index",
        "attempt_index", "execution_mode",
        "planned_exit",
        "trial_valid", "vt1_speed_at_entry_kmh", "vt1_upstream_at_entry",
        "vt1_upstream_remaining_at_entry_m", "vt1_conflict_ttc_at_entry_s",
        "vt1_conflict_gap_target_m", "vt1_conflict_gap_window_m",
        "vt1_speed_maintained", "vt1_exit1_crossed", "vt2_stationary",
        "correct_exit_crossed", "correct_exit_lane",
        "collision", "collision_vt1", "collision_vt2",
        "infrastructure_collision", "other_collision",
        "emergency_braking", "stopped_in_roundabout",
        "speed_limit_observed", "speed_limit_exceeded", "solid_line_invasion",
        "lane_direction_violation", "lane_guidance_violation", "off_road",
        "exit_indicator_observed", "exit_indicator_evidence_source", "route_complete",
        "trial_duration_s", "driven_distance_m", "average_speed_mps",
        "minimum_ttc_s", "minimum_vut_vt1_distance_m",
        "minimum_vut_vt2_distance_m", "vt1_speed_mean_kmh",
        "vt1_speed_std_kmh", "max_deceleration_mps2",
        "pass", "failure_reasons",
    ]
    all_fields = {key for record in ledger_records for key in record}
    fieldnames = preferred_columns + sorted(all_fields - set(preferred_columns))
    with _atomic_writer(
            prefix + ".csv", "w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for record in ledger_records:
            writer.writerow({
                key: json.dumps(value, ensure_ascii=False, sort_keys=True)
                if isinstance(value, (dict, list)) else value
                for key, value in record.items()
            })

    with _atomic_writer(prefix + ".pkl", "wb") as stream:
        pickle.dump(ledger_records, stream)

    pass_count = sum(record.get("pass") is True for record in ledger_records)
    fail_count = sum(record.get("pass") is False for record in ledger_records)
    aggregate_counts = {
        status: sum(item["status"] == status for item in aggregates)
        for status in ("pass", "fail", "incomplete")
    }
    with _atomic_writer(prefix + ".md", "w", encoding="utf-8") as stream:
        stream.write("# GB/T 41798—2022 环形路口（2.b）测试结果\n\n")
        stream.write("- 生成时间（UTC）：{}\n".format(generated_at))
        stream.write("- 已记录尝试：{}；其中通过：{}；失败：{}\n".format(
            len(ledger_records), pass_count, fail_count))
        stream.write("- 三次试验矩阵：通过 {}；失败 {}；待补测 {}\n".format(
            aggregate_counts["pass"], aggregate_counts["fail"],
            aggregate_counts["incomplete"]))
        for key in sorted(safe_metadata):
            stream.write("- {}：{}\n".format(key, _markdown_cell(safe_metadata[key])))

        stream.write("\n## 三次试验汇总\n\n")
        aggregate_columns = [
            "run_id", "matrix_id", "planned_exit", "status", "attempt_count", "trial_count",
            "valid_trial_count", "pass_count", "fail_count", "failure_reasons",
        ]
        stream.write("| " + " | ".join(aggregate_columns) + " |\n")
        stream.write("| " + " | ".join(["---"] * len(aggregate_columns)) + " |\n")
        for aggregate in aggregates:
            stream.write("| " + " | ".join(
                _markdown_cell(aggregate.get(column)) for column in aggregate_columns
            ) + " |\n")

        stream.write("\n## 逐次结果\n\n")
        stream.write("| " + " | ".join(preferred_columns) + " |\n")
        stream.write("| " + " | ".join(["---"] * len(preferred_columns)) + " |\n")
        for record in ledger_records:
            stream.write("| " + " | ".join(
                _markdown_cell(record.get(column)) for column in preferred_columns
            ) + " |\n")

        stream.write("\n## 判定说明\n\n")
        stream.write(
            "同一矩阵按索引 1、2、3 分别选择最后一次有效尝试；若某索引从未有效，"
            "则保留其最后一次无效尝试并标记为待补测。三个索引的选中尝试均有效且"
            "全部通过时，矩阵才判定为通过。\n"
        )

    # ``run.py`` intentionally replaces completed attempts in its in-memory
    # batch list with lightweight ledger records after their high-frequency
    # evidence has been materialised.  The final batch-level persist therefore
    # must not overwrite an existing attempt directory with empty telemetry and
    # event arrays.  A fresh full record always carries at least one of these
    # fields, including setup/INVALID attempts through scenario_snapshot.
    structured_evidence_fields = {
        "timeline_samples", "timeline_events", "phase_history",
        "collision_events", "lane_invasion_events", "fixture_collision_events",
        "scenario_snapshot", "runtime_environment",
    }
    if (safe_records
            and structured_evidence_fields.intersection(safe_records[-1])):
        _write_structured_roundabout_artifacts(
            [safe_records[-1]], output_dir, aggregates)

    return {
        "markdown": prefix + ".md",
        "json": prefix + ".json",
        "csv": prefix + ".csv",
        "pickle": prefix + ".pkl",
    }
