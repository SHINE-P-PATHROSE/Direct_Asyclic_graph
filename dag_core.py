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

    def priority_aware_task_schedule(self, cycle_duration=None):
        """Schedule one serial bus task at a time, optionally packing fixed cycles."""
        if cycle_duration is not None:
            cycle_duration = float(cycle_duration)
            if not math.isfinite(cycle_duration) or cycle_duration <= 0:
                raise ValueError("Cycle duration must be a positive finite number.")

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
                        sampling=row[3] if row[3] is not None else 32,
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
                        sampling=row.get("sampling", 32),
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


def schedule_cycle_data(nodes, adj, in_edges, in_degree, cycle_duration=8.0):
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

    _, timeline = graph.priority_aware_task_schedule(cycle_duration=cycle_duration)
    schedule_by_id = {}
    for sequence, item in enumerate(timeline, start=1):
        node_id = item["sl_no"]
        parents = sorted(in_edges[node_id])
        cycle_end = item["end_time"]
        schedule_by_id[node_id] = {
            "seq": sequence,
            "id": node_id,
            "name": item["name"],
            "type": item["type"],
            "priority": item["priority"],
            "cycle": item["cycle"],
            "exec_time": item["cycletime"],
            "start_time": round(item["start_time"], 4),
            "end_time": round(cycle_end, 4),
            "time_left": max(0.0, round(cycle_duration - cycle_end, 4)),
            "parents_str": ", ".join(map(str, parents)) if parents else "Bus Controller / Root",
        }

    ordered = list(schedule_by_id.values())
    summaries = []
    for cycle in range(1, max((item["cycle"] for item in ordered), default=0) + 1):
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
