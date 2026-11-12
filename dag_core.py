"""Canonical data model and algorithms for the MIL-STD-1553 message DAG."""

import csv
import math
import os
import re
from collections import defaultdict, deque

import openpyxl


EXCEL_FILE = "NSSA_1553_DAG_Schedule_and_Message_Mapping.xlsx"
CSV_FILE = "dag_schedule_dataset.csv"
ROOT_PARENT_VALUES = {"", "-1", "0", "none"}
PARENT_TOKEN = re.compile(r"(\d+)(?:\.\.(\d+))?")


class MessageNode:
    """A scheduled message and its attributes from the source dataset."""

    def __init__(
        self,
        sl_no,
        nomenclature,
        msg_type="eNor",
        sampling=32,
        stated_indegree=0,
        priority=1,
        parent_raw="-1",
        cycletime=0.0,
    ):
        self.id = int(sl_no)
        self.name = str(nomenclature).strip()
        self.type = str(msg_type).strip()
        self.sampling = sampling
        self.stated_indegree = stated_indegree
        self.priority = _parse_int(priority, "priority", self.id, default=1)
        self.parent_raw = str(parent_raw if parent_raw is not None else "-1").strip()
        self.cycletime = _parse_float(cycletime, "cycle time", self.id, default=0.0)
        if self.cycletime < 0:
            raise ValueError(f"Node {self.id} has a negative cycle time: {self.cycletime}")

    def __repr__(self):
        return f"Node({self.id}: {self.name}, {self.type}, {self.cycletime}ms)"


def _parse_int(value, field, node_id, default):
    try:
        return int(float(value))
    except (ValueError, TypeError):
        if value is None or str(value).strip() == "":
            return default
        raise ValueError(f"Node {node_id} has invalid {field}: {value!r}")


def _parse_float(value, field, node_id, default):
    try:
        result = float(value)
    except (ValueError, TypeError):
        if value is None or str(value).strip() == "":
            return default
        raise ValueError(f"Node {node_id} has invalid {field}: {value!r}")
    if not math.isfinite(result):
        raise ValueError(f"Node {node_id} has non-finite {field}: {value!r}")
    return result


def parse_parent_ids(expression, child_id):
    """Parse comma/slash-separated IDs and inclusive ranges into unique parent IDs."""
    raw = str(expression if expression is not None else "-1").strip()
    if raw.lower() in ROOT_PARENT_VALUES:
        return []

    parent_ids = []
    for token in re.split(r"[,/]", raw):
        token = token.strip()
        match = PARENT_TOKEN.fullmatch(token)
        if not match:
            raise ValueError(
                f"Node {child_id} has invalid parent expression {raw!r} "
                f"(invalid item {token!r})"
            )
        start = int(match.group(1))
        end = int(match.group(2) or start)
        if end < start:
            raise ValueError(
                f"Node {child_id} has descending parent range {token!r}"
            )
        parent_ids.extend(range(start, end + 1))

    return list(dict.fromkeys(parent_ids))


class DirectedAcyclicGraph:
    """Directed graph of message prerequisites with DAG analysis and scheduling."""

    def __init__(self):
        self.nodes = {}
        self.adj = defaultdict(list)
        self.in_edges = defaultdict(list)
        self.edges = set()

    def add_node(self, node):
        if node.id in self.nodes:
            raise ValueError(f"Duplicate node ID: {node.id}")
        self.nodes[node.id] = node

    def add_edge(self, parent_id, child_id):
        if parent_id not in self.nodes:
            raise ValueError(f"Dependency references unknown parent node {parent_id}")
        if child_id not in self.nodes:
            raise ValueError(f"Dependency references unknown child node {child_id}")
        if (parent_id, child_id) not in self.edges:
            self.edges.add((parent_id, child_id))
            self.adj[parent_id].append(child_id)
            self.in_edges[child_id].append(parent_id)

    def parse_parents(self):
        """Build parent-to-child edges from each node's parent expression."""
        self.adj = defaultdict(list)
        self.in_edges = defaultdict(list)
        self.edges = set()
        for child_id, node in self.nodes.items():
            for parent_id in parse_parent_ids(node.parent_raw, child_id):
                self.add_edge(parent_id, child_id)

    def detect_cycles(self):
        """Return (is_acyclic, cycle_path) using DFS three-color marking."""
        color = {node_id: 0 for node_id in self.nodes}
        parent = {}

        def visit(node_id):
            color[node_id] = 1
            for child_id in self.adj[node_id]:
                if color[child_id] == 1:
                    cycle = [child_id]
                    current = node_id
                    while current != child_id:
                        cycle.append(current)
                        current = parent[current]
                    cycle.append(child_id)
                    cycle.reverse()
                    return cycle
                if color[child_id] == 0:
                    parent[child_id] = node_id
                    cycle = visit(child_id)
                    if cycle:
                        return cycle
            color[node_id] = 2
            return None

        for node_id in sorted(self.nodes):
            if color[node_id] == 0:
                cycle = visit(node_id)
                if cycle:
                    return False, cycle
        return True, []

    def topological_sort_kahn(self):
        """Return a topological ordering or raise if dependencies contain a cycle."""
        indegree = {node_id: len(self.in_edges[node_id]) for node_id in self.nodes}
        ready = deque(node_id for node_id in sorted(self.nodes) if indegree[node_id] == 0)
        order = []

        while ready:
            node_id = ready.popleft()
            order.append(node_id)
            for child_id in self.adj[node_id]:
                indegree[child_id] -= 1
                if indegree[child_id] == 0:
                    ready.append(child_id)

        if len(order) != len(self.nodes):
            raise ValueError("Graph contains a cycle; topological sorting is impossible.")
        return order

    def compute_transitive_closure(self):
        """Return reach[u][v], true when a directed path leads from u to v."""
        node_ids = sorted(self.nodes)
        reach = {u: {v: False for v in node_ids} for u in node_ids}
        for parent_id, child_id in self.edges:
            reach[parent_id][child_id] = True
        for intermediate in node_ids:
            for start in node_ids:
                if reach[start][intermediate]:
                    for end in node_ids:
                        if reach[intermediate][end]:
                            reach[start][end] = True
        return reach

    def compute_transitive_reduction(self):
        """Return the essential edges of this DAG, preserving reachability."""
        reach = self.compute_transitive_closure()
        return {
            (parent_id, child_id)
            for parent_id, child_id in self.edges
            if not any(
                middle != parent_id
                and middle != child_id
                and reach[parent_id][middle]
                and reach[middle][child_id]
                for middle in self.nodes
            )
        }

    def priority_aware_task_schedule(
        self,
        cycle_duration=None,
        horizon_cycles=None,
        max_tasks_per_cycle=20,
    ):
        """Schedule tasks once, or periodically across a fixed cycle horizon."""
        if cycle_duration is not None:
            cycle_duration = float(cycle_duration)
            if not math.isfinite(cycle_duration) or cycle_duration <= 0:
                raise ValueError("Cycle duration must be a positive finite number.")

        if horizon_cycles is not None:
            if cycle_duration is None:
                raise ValueError("Cycle duration is required for a periodic schedule.")
            if (
                isinstance(horizon_cycles, bool)
                or not isinstance(horizon_cycles, int)
                or horizon_cycles <= 0
            ):
                raise ValueError("Cycle horizon must be a positive integer.")
            if (
                isinstance(max_tasks_per_cycle, bool)
                or not isinstance(max_tasks_per_cycle, int)
                or max_tasks_per_cycle <= 0
            ):
                raise ValueError("Maximum tasks per cycle must be a positive integer.")
            return self._periodic_task_schedule(
                cycle_duration,
                horizon_cycles,
                max_tasks_per_cycle,
            )

        indegree = {node_id: len(self.in_edges[node_id]) for node_id in self.nodes}
        ready = [node_id for node_id in self.nodes if indegree[node_id] == 0]
        timeline = []
        current_cycle = 1
        cycle_time = 0.0
        elapsed_time = 0.0

        while ready:
            ready.sort(
                key=lambda node_id: (
                    self.nodes[node_id].priority,
                    self.nodes[node_id].cycletime,
                    node_id,
                )
            )
            node_id = ready.pop(0)
            node = self.nodes[node_id]
            duration = node.cycletime

            if cycle_duration is not None:
                if duration > cycle_duration:
                    raise ValueError(
                        f"Node {node_id} duration ({duration} ms) exceeds "
                        f"the cycle duration ({cycle_duration} ms)."
                    )
                if cycle_time + duration > cycle_duration + 1e-9 and cycle_time > 0:
                    current_cycle += 1
                    cycle_time = 0.0

            start_time = cycle_time if cycle_duration is not None else elapsed_time
            end_time = start_time + duration
            timeline.append(
                {
                    "sl_no": node_id,
                    "name": node.name,
                    "type": node.type,
                    "priority": node.priority,
                    "cycletime": duration,
                    "start_time": start_time,
                    "end_time": end_time,
                    "cycle": current_cycle,
                }
            )
            elapsed_time += duration
            cycle_time = end_time

            for child_id in self.adj[node_id]:
                indegree[child_id] -= 1
                if indegree[child_id] == 0:
                    ready.append(child_id)

        if len(timeline) != len(self.nodes):
            raise ValueError("Graph contains a cycle; tasks could not all be scheduled.")
        return [item["sl_no"] for item in timeline], timeline

    def _periodic_task_schedule(
        self,
        cycle_duration,
        horizon_cycles,
        max_tasks_per_cycle,
    ):
        """Balance periodic executions across cycles while preserving dependencies.

        Sampling values are treated as millisecond intervals. Missing values default
        to one execution per frame.
        """
        frame_duration = cycle_duration * horizon_cycles
        periods = {}
        for node_id, node in self.nodes.items():
            sampling = _parse_float(
                node.sampling,
                "sampling interval",
                node_id,
                default=frame_duration,
            )
            if sampling <= 0:
                raise ValueError(
                    f"Node {node_id} has a non-positive sampling interval: {sampling}"
                )
            periods[node_id] = min(
                horizon_cycles,
                max(1, math.ceil(sampling / cycle_duration - 1e-12)),
            )

        order = self.topological_sort_kahn()
        phase_limit = {}
        for node_id in reversed(order):
            child_limits = [phase_limit[child] for child in self.adj[node_id]]
            phase_limit[node_id] = min(
                [periods[node_id] - 1, *child_limits]
            )

        total_instances = sum(
            len(range(0, horizon_cycles, periods[node_id]))
            for node_id in self.nodes
        )
        total_duration = sum(
            self.nodes[node_id].cycletime
            * len(range(0, horizon_cycles, periods[node_id]))
            for node_id in self.nodes
        )
        target_count = total_instances / horizon_cycles
        target_duration = total_duration / horizon_cycles
        cycle_counts = [0] * horizon_cycles
        cycle_loads = [0.0] * horizon_cycles
        phases = {}

        for node_id in order:
            node = self.nodes[node_id]
            earliest_phase = max(
                (phases[parent] for parent in self.in_edges[node_id]),
                default=0,
            )
            latest_phase = phase_limit[node_id]
            candidates = []
            if earliest_phase <= latest_phase:
                for phase in range(earliest_phase, latest_phase + 1):
                    cycles = list(range(phase, horizon_cycles, periods[node_id]))
                    if not cycles:
                        cycles = [phase]
                    if any(
                        cycle_counts[cycle] >= max_tasks_per_cycle
                        or cycle_loads[cycle] + node.cycletime
                        > cycle_duration + 1e-9
                        for cycle in cycles
                    ):
                        continue

                    count_score = sum(
                        (
                            (cycle_counts[cycle] + 1 - target_count)
                            / max(target_count, 1.0)
                        ) ** 2
                        - (
                            (cycle_counts[cycle] - target_count)
                            / max(target_count, 1.0)
                        ) ** 2
                        for cycle in cycles
                    )
                    load_score = sum(
                        (
                            (cycle_loads[cycle] + node.cycletime - target_duration)
                            / max(target_duration, 1e-9)
                        ) ** 2
                        - (
                            (cycle_loads[cycle] - target_duration)
                            / max(target_duration, 1e-9)
                        ) ** 2
                        for cycle in cycles
                    )
                    candidates.append(
                        (count_score + load_score, max(cycle_loads[c] for c in cycles), phase, cycles)
                    )

            if not candidates:
                raise ValueError(
                    f"Cannot place periodic executions for node {node_id} "
                    f"within {horizon_cycles} cycles while respecting dependencies, "
                    f"the {max_tasks_per_cycle}-task limit, and cycle duration."
                )

            _, _, phase, cycles = min(candidates)
            phases[node_id] = phase
            for cycle in cycles:
                cycle_counts[cycle] += 1
                cycle_loads[cycle] += node.cycletime

        def balance_score(counts, loads):
            count_error = sum(
                ((count - target_count) / max(target_count, 1.0)) ** 2
                for count in counts
            )
            load_error = sum(
                ((load - target_duration) / max(target_duration, 1e-9)) ** 2
                for load in loads
            )
            return count_error + load_error

        for _ in range(4):
            changed = False
            for node_id in reversed(order):
                node = self.nodes[node_id]
                lower = max((phases[parent] for parent in self.in_edges[node_id]), default=0)
                upper = min(
                    [phase_limit[node_id]]
                    + [phases[child] for child in self.adj[node_id]]
                )
                old_phase = phases[node_id]
                old_cycles = list(range(old_phase, horizon_cycles, periods[node_id]))
                best_phase = old_phase
                best_score = balance_score(cycle_counts, cycle_loads)

                for phase in range(lower, upper + 1):
                    candidate_cycles = list(
                        range(phase, horizon_cycles, periods[node_id])
                    )
                    candidate_counts = cycle_counts.copy()
                    candidate_loads = cycle_loads.copy()
                    for cycle in old_cycles:
                        candidate_counts[cycle] -= 1
                        candidate_loads[cycle] -= node.cycletime
                    for cycle in candidate_cycles:
                        candidate_counts[cycle] += 1
                        candidate_loads[cycle] += node.cycletime
                    if any(
                        candidate_counts[cycle] > max_tasks_per_cycle
                        or candidate_loads[cycle] > cycle_duration + 1e-9
                        for cycle in candidate_cycles
                    ):
                        continue
                    score = balance_score(candidate_counts, candidate_loads)
                    if score < best_score - 1e-12:
                        best_phase = phase
                        best_score = score

                if best_phase != old_phase:
                    for cycle in old_cycles:
                        cycle_counts[cycle] -= 1
                        cycle_loads[cycle] -= node.cycletime
                    for cycle in range(best_phase, horizon_cycles, periods[node_id]):
                        cycle_counts[cycle] += 1
                        cycle_loads[cycle] += node.cycletime
                    phases[node_id] = best_phase
                    changed = True
            if not changed:
                break

        timeline = []
        occurrence_counts = defaultdict(int)
        scheduled_cycles = {
            node_id: {
                cycle
                for cycle in range(horizon_cycles)
                if cycle >= phases[node_id]
                and (cycle - phases[node_id]) % periods[node_id] == 0
            }
            for node_id in self.nodes
        }

        for cycle in range(horizon_cycles):
            timeline_start = len(timeline)
            in_cycle = {
                node_id
                for node_id in self.nodes
                if cycle in scheduled_cycles[node_id]
            }
            indegree = {
                node_id: sum(parent in in_cycle for parent in self.in_edges[node_id])
                for node_id in in_cycle
            }
            ready = [node_id for node_id in in_cycle if indegree[node_id] == 0]
            cycle_time = 0.0
            while ready:
                ready.sort(
                    key=lambda current_id: (
                        self.nodes[current_id].priority,
                        self.nodes[current_id].cycletime,
                        current_id,
                    )
                )
                node_id = ready.pop(0)
                node = self.nodes[node_id]
                start_time = cycle_time
                end_time = start_time + node.cycletime
                occurrence_counts[node_id] += 1
                timeline.append(
                    {
                        "sl_no": node_id,
                        "name": node.name,
                        "type": node.type,
                        "priority": node.priority,
                        "cycletime": node.cycletime,
                        "start_time": start_time,
                        "end_time": end_time,
                        "cycle": cycle + 1,
                        "occurrence": occurrence_counts[node_id],
                    }
                )
                cycle_time = end_time

                for child_id in self.adj[node_id]:
                    if child_id in indegree:
                        indegree[child_id] -= 1
                        if indegree[child_id] == 0:
                            ready.append(child_id)

            if len(timeline) - timeline_start != len(in_cycle):
                raise ValueError(
                    f"Dependencies prevent scheduling all tasks in cycle {cycle + 1}."
                )

        timeline_counts = defaultdict(int)
        for item in timeline:
            timeline_counts[item["sl_no"]] += 1
        for node_id, period in periods.items():
            expected = len(range(phases[node_id], horizon_cycles, period))
            if timeline_counts[node_id] != expected:
                raise ValueError(
                    f"Node {node_id} was scheduled {timeline_counts[node_id]} times; "
                    f"expected {expected} executions in the frame."
                )

        return [item["sl_no"] for item in timeline], timeline

    def compute_critical_path(self):
        """Return the longest weighted dependency path and its duration."""
        if not self.nodes:
            return [], 0.0
        order = self.topological_sort_kahn()
        distance = {node_id: self.nodes[node_id].cycletime for node_id in self.nodes}
        predecessor = {node_id: None for node_id in self.nodes}

        for parent_id in order:
            for child_id in self.adj[parent_id]:
                candidate = distance[parent_id] + self.nodes[child_id].cycletime
                if candidate > distance[child_id]:
                    distance[child_id] = candidate
                    predecessor[child_id] = parent_id

        end_id = max(distance, key=distance.get)
        path = []
        while end_id is not None:
            path.append(end_id)
            end_id = predecessor[end_id]
        path.reverse()
        return path, distance[path[-1]]


def load_dag(excel_path=None, csv_path=None):
    """Load the canonical DAG from the workbook, falling back to the CSV if absent."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    excel_path = excel_path or os.path.join(base_dir, EXCEL_FILE)
    csv_path = csv_path or os.path.join(base_dir, CSV_FILE)
    graph = DirectedAcyclicGraph()

    if os.path.exists(excel_path):
        workbook = openpyxl.load_workbook(excel_path, data_only=True, read_only=True)
        if "SchTril" not in workbook.sheetnames:
            workbook.close()
            raise ValueError(f"Workbook {excel_path!r} does not contain a 'SchTril' sheet.")
        try:
            rows = workbook["SchTril"].iter_rows(values_only=True)
            for row in list(rows)[3:]:
                if row[0] is None:
                    continue
                graph.add_node(
                    MessageNode(
                        sl_no=row[0],
                        nomenclature=row[1],
                        msg_type=row[2] or "eNor",
                        sampling=row[3],
                        stated_indegree=row[4] if row[4] is not None else 0,
                        priority=row[5] if row[5] is not None else 1,
                        parent_raw=row[6],
                        cycletime=row[9] if len(row) > 9 else 0.0,
                    )
                )
        finally:
            workbook.close()
    elif os.path.exists(csv_path):
        with open(csv_path, "r", encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                graph.add_node(
                    MessageNode(
                        sl_no=row["sl_no"],
                        nomenclature=row["nomenclature"],
                        msg_type=row.get("type") or "eNor",
                        sampling=row.get("sampling") or None,
                        stated_indegree=row.get("indegree", 0),
                        priority=row.get("priority", 1),
                        parent_raw=row.get("parent_raw", "-1"),
                        cycletime=row.get("cycletime_ms", row.get("cycletime", 0.0)),
                    )
                )
    else:
        raise FileNotFoundError(
            f"Neither workbook {excel_path!r} nor CSV dataset {csv_path!r} exists."
        )

    graph.parse_parents()
    return graph


def to_visualization_data(graph):
    """Adapt the canonical graph to the dictionary shape used by existing renderers."""
    nodes = {
        node_id: {
            "id": node.id,
            "name": node.name,
            "type": node.type,
            "sampling": node.sampling,
            "stated_indegree": node.stated_indegree,
            "priority": node.priority,
            "parent_raw": node.parent_raw,
            "time": node.cycletime,
        }
        for node_id, node in graph.nodes.items()
    }
    adj = defaultdict(list, {node_id: list(children) for node_id, children in graph.adj.items()})
    in_edges = defaultdict(list, {node_id: list(parents) for node_id, parents in graph.in_edges.items()})
    in_degree = defaultdict(int, {node_id: len(in_edges[node_id]) for node_id in graph.nodes})
    return nodes, adj, in_edges, in_degree


def schedule_cycle_data(
    nodes,
    adj,
    in_edges,
    in_degree,
    cycle_duration=8.0,
    horizon_cycles=64,
    max_tasks_per_cycle=20,
):
    """Compatibility adapter that uses the canonical priority/cycle scheduler."""
    graph = DirectedAcyclicGraph()
    for node_id, data in nodes.items():
        graph.add_node(
            MessageNode(
                sl_no=node_id,
                nomenclature=data["name"],
                msg_type=data["type"],
                sampling=data.get("sampling", 32),
                stated_indegree=data.get("stated_indegree", 0),
                priority=data.get("priority", 1),
                parent_raw=data.get("parent_raw", "-1"),
                cycletime=data.get("time", 0.0),
            )
        )
    for parent_id, children in adj.items():
        for child_id in children:
            graph.add_edge(parent_id, child_id)

    _, timeline = graph.priority_aware_task_schedule(
        cycle_duration=cycle_duration,
        horizon_cycles=horizon_cycles,
        max_tasks_per_cycle=max_tasks_per_cycle,
    )
    schedule_by_id = {}
    for sequence, item in enumerate(timeline, start=1):
        node_id = item["sl_no"]
        parents = sorted(in_edges[node_id])
        cycle_end = item["end_time"]
        schedule_by_id.setdefault(node_id, {
            "seq": sequence,
            "id": node_id,
            "name": item["name"],
            "type": item["type"],
            "priority": item["priority"],
            "cycle": item["cycle"],
            "occurrence": item["occurrence"],
            "exec_time": item["cycletime"],
            "start_time": round(item["start_time"], 4),
            "end_time": round(cycle_end, 4),
            "time_left": max(0.0, round(cycle_duration - cycle_end, 4)),
            "parents_str": ", ".join(map(str, parents)) if parents else "Bus Controller / Root",
        })
    ordered = []
    for sequence, item in enumerate(timeline, start=1):
        node_id = item["sl_no"]
        parents = sorted(in_edges[node_id])
        ordered.append(
            {
                "seq": sequence,
                "id": node_id,
                "name": item["name"],
                "type": item["type"],
                "priority": item["priority"],
                "cycle": item["cycle"],
                "occurrence": item["occurrence"],
                "exec_time": item["cycletime"],
                "start_time": round(item["start_time"], 4),
                "end_time": round(item["end_time"], 4),
                "time_left": max(0.0, round(cycle_duration - item["end_time"], 4)),
                "parents_str": ", ".join(map(str, parents)) if parents else "Bus Controller / Root",
            }
        )
    summaries = []
    for cycle in range(1, horizon_cycles + 1):
        tasks = [item for item in ordered if item["cycle"] == cycle]
        used = sum(item["exec_time"] for item in tasks)
        summaries.append(
            {
                "cycle": cycle,
                "task_count": len(tasks),
                "used_time": round(used, 3),
                "slack": round(max(0.0, cycle_duration - used), 3),
                "utilization": round((used / cycle_duration) * 100, 1),
            }
        )
    return schedule_by_id, ordered, summaries
