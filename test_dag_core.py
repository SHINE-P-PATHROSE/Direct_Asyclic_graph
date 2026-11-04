import contextlib
import io
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dag_core import (
    DirectedAcyclicGraph,
    MessageNode,
    load_dag,
    parse_parent_ids,
    schedule_cycle_data,
    to_visualization_data,
)


def make_node(node_id, parents="-1", duration=1.0, priority=1):
    return MessageNode(
        node_id,
        f"message-{node_id}",
        priority=priority,
        parent_raw=parents,
        cycletime=duration,
    )


class ParentParsingTests(unittest.TestCase):
    def test_parse_comma_slash_and_ranges(self):
        self.assertEqual(parse_parent_ids("1, 3..4/3", 9), [1, 3, 4])
        self.assertEqual(parse_parent_ids("-1", 9), [])

    def test_reject_malformed_or_descending_parent_ranges(self):
        for expression in ("1,,2", "1..x", "4..2"):
            with self.subTest(expression=expression):
                with self.assertRaises(ValueError):
                    parse_parent_ids(expression, 9)

    def test_reject_unknown_parent(self):
        graph = DirectedAcyclicGraph()
        graph.add_node(make_node(2, "1"))
        with self.assertRaisesRegex(ValueError, "unknown parent node 1"):
            graph.parse_parents()


class DagAlgorithmTests(unittest.TestCase):
    def test_cycle_is_detected_and_topological_sort_rejects_it(self):
        graph = DirectedAcyclicGraph()
        graph.add_node(make_node(1, "2"))
        graph.add_node(make_node(2, "1"))
        graph.parse_parents()

        self.assertFalse(graph.detect_cycles()[0])
        with self.assertRaisesRegex(ValueError, "contains a cycle"):
            graph.topological_sort_kahn()

    def test_closure_and_reduction_preserve_dependencies(self):
        graph = DirectedAcyclicGraph()
        for node in (make_node(1), make_node(2, "1"), make_node(3, "1,2")):
            graph.add_node(node)
        graph.parse_parents()

        self.assertTrue(graph.compute_transitive_closure()[1][3])
        self.assertEqual(graph.compute_transitive_reduction(), {(1, 2), (2, 3)})

    def test_critical_path_sums_node_durations(self):
        graph = DirectedAcyclicGraph()
        for node in (
            make_node(1, duration=2),
            make_node(2, "1", duration=3),
            make_node(3, duration=4),
        ):
            graph.add_node(node)
        graph.parse_parents()

        self.assertEqual(graph.compute_critical_path(), ([1, 2], 5.0))

    def test_empty_critical_path(self):
        self.assertEqual(DirectedAcyclicGraph().compute_critical_path(), ([], 0.0))


class SchedulingTests(unittest.TestCase):
    def test_priority_schedule_respects_dependencies_and_cycle_capacity(self):
        graph = DirectedAcyclicGraph()
        for node in (
            make_node(1, duration=3, priority=2),
            make_node(2, "1", duration=2, priority=1),
            make_node(3, duration=2, priority=1),
        ):
            graph.add_node(node)
        graph.parse_parents()
        _, timeline = graph.priority_aware_task_schedule(cycle_duration=4)
        scheduled = {item["sl_no"]: item for item in timeline}

        self.assertLess(scheduled[1]["cycle"], scheduled[2]["cycle"])
        self.assertTrue(all(item["end_time"] <= 4 for item in timeline))
        self.assertEqual(scheduled[3]["cycle"], 1)

    def test_task_longer_than_cycle_is_rejected(self):
        graph = DirectedAcyclicGraph()
        graph.add_node(make_node(1, duration=8.1))
        with self.assertRaisesRegex(ValueError, "exceeds the cycle duration"):
            graph.priority_aware_task_schedule(cycle_duration=8)

    def test_all_loaded_dataset_nodes_are_scheduled_in_topological_order(self):
        graph = load_dag()
        order, timeline = graph.priority_aware_task_schedule()
        positions = {node_id: index for index, node_id in enumerate(order)}

        self.assertEqual(len(graph.nodes), 87)
        self.assertEqual(len(order), len(graph.nodes))
        self.assertTrue(all(positions[parent] < positions[child] for parent, child in graph.edges))
        self.assertEqual(len(timeline), len(graph.nodes))

    def test_renderer_adapter_uses_computed_degrees_and_shared_scheduler(self):
        graph = load_dag()
        nodes, adj, in_edges, in_degree = to_visualization_data(graph)
        schedule, ordered, summaries = schedule_cycle_data(
            nodes, adj, in_edges, in_degree, cycle_duration=8
        )

        self.assertEqual(len(schedule), len(graph.nodes))
        self.assertEqual(len(ordered), len(graph.nodes))
        self.assertEqual(sum(item["task_count"] for item in summaries), len(graph.nodes))
        self.assertEqual(in_degree[39], len(in_edges[39]))
        for parent_id, child_id in graph.edges:
            parent = schedule[parent_id]
            child = schedule[child_id]
            self.assertTrue(
                parent["cycle"] < child["cycle"]
                or (
                    parent["cycle"] == child["cycle"]
                    and parent["end_time"] <= child["start_time"]
                ),
                f"Dependency {parent_id}->{child_id} is not scheduled in order.",
            )
        self.assertTrue(
            all(item["end_time"] <= 8 for item in ordered)
        )

    def test_csv_fallback_matches_primary_workbook(self):
        primary = load_dag()
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_workbook = Path(temp_dir) / "missing-workbook.xlsx"
            fallback = load_dag(
                excel_path=str(missing_workbook),
                csv_path=str(Path(__file__).with_name("dag_schedule_dataset.csv")),
            )
        self.assertEqual(primary.edges, fallback.edges)
        self.assertEqual(
            {
                node_id: (
                    node.name,
                    node.type,
                    node.parent_raw,
                    node.priority,
                    node.cycletime,
                )
                for node_id, node in primary.nodes.items()
            },
            {
                node_id: (
                    node.name,
                    node.type,
                    node.parent_raw,
                    node.priority,
                    node.cycletime,
                )
                for node_id, node in fallback.nodes.items()
            },
        )


class GeneratedTreeTests(unittest.TestCase):
    def test_analysis_entry_point_runs_each_distinct_generator_once(self):
        import generate_perfect_trees
        import generate_schedule_timeline
        import generate_schedule_tree
        from dag_analysis import generate_visualizations

        with (
            patch.object(generate_perfect_trees, "main") as trees,
            patch.object(generate_schedule_tree, "generate_schedule_tree") as graph,
            patch.object(
                generate_schedule_timeline, "generate_schedule_timeline"
            ) as timeline,
        ):
            generate_visualizations()

        trees.assert_called_once_with()
        graph.assert_called_once_with()
        timeline.assert_called_once_with()

    def test_text_and_html_trees_represent_every_graph_node(self):
        import generate_perfect_trees

        graph = load_dag()
        nodes, adj, in_edges, in_degree = to_visualization_data(graph)
        original_dir = os.getcwd()
        with tempfile.TemporaryDirectory() as output_dir:
            try:
                os.chdir(output_dir)
                with contextlib.redirect_stdout(io.StringIO()):
                    generate_perfect_trees.generate_text_tree(
                        nodes, adj, in_edges, in_degree
                    )
                    text = Path("dag_tree_structure.txt").read_text(encoding="utf-8")
                    generate_perfect_trees.generate_interactive_html(
                        nodes, adj, in_degree
                    )
                text_ids = {int(value) for value in re.findall(r"\[(\d{2})\]", text)}
                html = Path("dag_tree_view.html").read_text(encoding="utf-8")
                html_node_count = html.count('<button class="node"')
            finally:
                os.chdir(original_dir)

        self.assertTrue(set(graph.nodes).issubset(text_ids))
        self.assertEqual(html_node_count, len(graph.nodes))

    def test_schedule_graph_generates_a_standalone_image(self):
        import generate_schedule_tree

        with tempfile.TemporaryDirectory() as output_dir:
            output_path = Path(output_dir) / "schedule.png"
            generate_schedule_tree.generate_schedule_tree(
                str(output_path), cycle_duration=8, dpi=40
            )
            self.assertTrue(output_path.is_file())
            self.assertGreater(output_path.stat().st_size, 0)

    def test_schedule_timeline_generates_a_full_sized_image(self):
        import generate_schedule_timeline

        with tempfile.TemporaryDirectory() as output_dir:
            output_path = Path(output_dir) / "timeline.png"
            generate_schedule_timeline.generate_schedule_timeline(
                str(output_path), cycle_duration=8, dpi=50
            )
            self.assertTrue(output_path.is_file())
            self.assertGreater(output_path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
