from __future__ import annotations

from math import acos, atan2, ceil, cos, hypot, pi, sin, sqrt

from .design_profiles import BoundaryPoint, BoundarySegment, PlanBoundaryProfile, StructuralMember, StructuralNode


MAX_ARC_CHORD_M = 0.5
MAX_ARC_SAGITTA_M = 0.01
MEMBER_INTERSECTION_TOLERANCE_M = 1e-5


def _circle_from_three_points(a: tuple[float, float], m: tuple[float, float], b: tuple[float, float]) -> tuple[float, float, float]:
    ax, ay = a
    mx, my = m
    bx, by = b
    determinant = 2 * (ax * (my - by) + mx * (by - ay) + bx * (ay - my))
    if abs(determinant) < 1e-10:
        raise ValueError("圆弧三点不得共线")
    a2, m2, b2 = ax * ax + ay * ay, mx * mx + my * my, bx * bx + by * by
    cx = (a2 * (my - by) + m2 * (by - ay) + b2 * (ay - my)) / determinant
    cy = (a2 * (bx - mx) + m2 * (ax - bx) + b2 * (mx - ax)) / determinant
    return cx, cy, hypot(ax - cx, ay - cy)


def discretize_boundary_segment(
    segment: BoundarySegment,
    point_by_id: dict[str, BoundaryPoint],
) -> list[tuple[float, float]]:
    start = point_by_id[segment.start_point_id]
    end = point_by_id[segment.end_point_id]
    a = (start.x_m, start.y_m)
    b = (end.x_m, end.y_m)
    if segment.kind == "line":
        return [a, b]
    middle = (float(segment.arc_mid_x_m), float(segment.arc_mid_y_m))
    cx, cy, radius = _circle_from_three_points(a, middle, b)
    start_angle = atan2(a[1] - cy, a[0] - cx)
    middle_angle = atan2(middle[1] - cy, middle[0] - cx)
    end_angle = atan2(b[1] - cy, b[0] - cx)

    def normalized(value: float) -> float:
        return value % (2 * pi)

    counter_clockwise = normalized(middle_angle - start_angle) <= normalized(end_angle - start_angle)
    sweep = normalized(end_angle - start_angle) if counter_clockwise else -normalized(start_angle - end_angle)
    chord_angle = 2 * acos(max(-1.0, min(1.0, 1 - MAX_ARC_SAGITTA_M / radius)))
    max_angle = min(MAX_ARC_CHORD_M / radius, chord_angle) if chord_angle > 0 else MAX_ARC_CHORD_M / radius
    divisions = max(1, ceil(abs(sweep) / max_angle))
    return [
        (cx + radius * cos(start_angle + sweep * index / divisions), cy + radius * sin(start_angle + sweep * index / divisions))
        for index in range(divisions + 1)
    ]


def discretize_plan_boundary(boundary: PlanBoundaryProfile) -> list[tuple[float, float]]:
    point_by_id = {item.id: item for item in boundary.outer_points}
    segment_by_start = {item.start_point_id: item for item in boundary.outer_segments}
    current = boundary.outer_segments[0].start_point_id
    ordered: list[tuple[float, float]] = []
    visited: set[str] = set()
    while current not in visited:
        visited.add(current)
        segment = segment_by_start[current]
        points = discretize_boundary_segment(segment, point_by_id)
        ordered.extend(points[:-1])
        current = segment.end_point_id
    if current != boundary.outer_segments[0].start_point_id or len(visited) != len(boundary.outer_segments):
        raise ValueError("屋面边界必须形成单一闭合环")
    if len(ordered) > 200:
        raise ValueError("圆弧离散后超过200个边界节点，请拆分场景或减少圆弧复杂度")
    return ordered


def polygon_area(points: list[tuple[float, float]]) -> float:
    return abs(sum(points[index][0] * points[(index + 1) % len(points)][1] - points[(index + 1) % len(points)][0] * points[index][1] for index in range(len(points)))) / 2


def _orientation(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def has_self_intersection(points: list[tuple[float, float]]) -> bool:
    count = len(points)
    for first in range(count):
        a, b = points[first], points[(first + 1) % count]
        for second in range(first + 1, count):
            if second in {first, (first + 1) % count} or (second + 1) % count == first:
                continue
            c, d = points[second], points[(second + 1) % count]
            if _orientation(a, b, c) * _orientation(a, b, d) < 0 and _orientation(c, d, a) * _orientation(c, d, b) < 0:
                return True
    return False


def validate_plan_boundary(boundary: PlanBoundaryProfile) -> tuple[list[tuple[float, float]], float]:
    points = discretize_plan_boundary(boundary)
    if has_self_intersection(points):
        raise ValueError("屋面边界存在自交，不能生成荷载分区")
    area = polygon_area(points)
    if area < 0.01:
        raise ValueError("屋面边界面积过小")
    return points, area


def find_member_topology_conflicts(
    nodes: list[StructuralNode], members: list[StructuralMember]
) -> list[dict[str, object]]:
    """Find coincident members and interior 3D crossings without a shared node.

    This is a topology pre-check, not a finite-element connectivity repair.  It
    deliberately reports the involved member IDs so the editor can locate and
    split the members explicitly instead of silently changing the model.
    """

    node_by_id = {node.id: node for node in nodes}
    conflicts: list[dict[str, object]] = []

    def vector(node: StructuralNode) -> tuple[float, float, float]:
        return node.x_m, node.y_m, node.z_m

    def subtract(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
        return a[0] - b[0], a[1] - b[1], a[2] - b[2]

    def add_scaled(a: tuple[float, float, float], direction: tuple[float, float, float], scale: float) -> tuple[float, float, float]:
        return a[0] + direction[0] * scale, a[1] + direction[1] * scale, a[2] + direction[2] * scale

    def dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
        return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]

    for first_index, first in enumerate(members):
        first_start = vector(node_by_id[first.start_node_id])
        first_end = vector(node_by_id[first.end_node_id])
        first_endpoints = {first.start_node_id, first.end_node_id}
        for second in members[first_index + 1:]:
            if first_endpoints & {second.start_node_id, second.end_node_id}:
                continue
            second_start = vector(node_by_id[second.start_node_id])
            second_end = vector(node_by_id[second.end_node_id])
            same_geometry = (
                (first_start == second_start and first_end == second_end)
                or (first_start == second_end and first_end == second_start)
            )
            if same_geometry:
                conflicts.append({
                    "code": "overlapping_members",
                    "member_ids": (first.id, second.id),
                    "location": tuple((first_start[index] + first_end[index]) / 2 for index in range(3)),
                })
                continue

            u = subtract(first_end, first_start)
            v = subtract(second_end, second_start)
            w = subtract(first_start, second_start)
            a, b, c, d, e = dot(u, u), dot(u, v), dot(v, v), dot(u, w), dot(v, w)
            denominator = a * c - b * b
            if a <= 1e-12 or c <= 1e-12 or abs(denominator) <= 1e-12:
                continue
            first_parameter = (b * e - c * d) / denominator
            second_parameter = (a * e - b * d) / denominator
            if not (1e-6 < first_parameter < 1 - 1e-6 and 1e-6 < second_parameter < 1 - 1e-6):
                continue
            first_point = add_scaled(first_start, u, first_parameter)
            second_point = add_scaled(second_start, v, second_parameter)
            distance = sqrt(sum((first_point[index] - second_point[index]) ** 2 for index in range(3)))
            if distance <= MEMBER_INTERSECTION_TOLERANCE_M:
                conflicts.append({
                    "code": "unconnected_member_crossing",
                    "member_ids": (first.id, second.id),
                    "location": tuple((first_point[index] + second_point[index]) / 2 for index in range(3)),
                })
    return conflicts
