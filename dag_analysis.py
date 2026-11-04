"""Analyze the MIL-STD-1553 message dependency DAG and generate its outputs."""

from dag_core import DirectedAcyclicGraph, MessageNode, load_dag


def load_dag_from_excel_or_csv():
    """Compatibility entry point for callers of the original analysis script."""
    return load_dag()


def generate_visualizations(dag=None):
    """Run every distinct project output generator from the single entry point."""
    import generate_perfect_trees
    import generate_schedule_timeline
    import generate_schedule_tree

    print("\n[1/3] Generating subsystem diagrams, text/Excel schedules, and HTML tree...")
    generate_perfect_trees.main()

    print("\n[2/3] Generating the complete scheduled dependency graph...")
    generate_schedule_tree.generate_schedule_tree()

    print("\n[3/3] Generating the complete cycle-by-cycle Gantt timeline...")
    generate_schedule_timeline.generate_schedule_timeline()


def main():
    print("=" * 80)
    print("   DIRECTED ACYCLIC GRAPH (DAG) ENGINE - 1553 BUS TASK SCHEDULING")
    print("=" * 80)

    dag = load_dag()
    print(f"[*] Graph initialized with {len(dag.nodes)} nodes and {len(dag.edges)} directed edges.")

    is_dag, cycle = dag.detect_cycles()
    print("\n" + "-" * 50)
    print("PROPERTY 1: ACYCLICITY VERIFICATION")
    print("-" * 50)
    if not is_dag:
        print(f"[FAIL] Cycle detected! Cycle path: {cycle}")
        raise ValueError(f"Cannot generate a schedule for cyclic dependencies: {cycle}")
    print("[SUCCESS] The graph is strictly acyclic and can be topologically scheduled.")

    topo_order = dag.topological_sort_kahn()
    print("\n" + "-" * 50)
    print("PROPERTY 2: TOPOLOGICAL ORDERING (KAHN'S ALGORITHM)")
    print("-" * 50)
    print(f"Total nodes topologically ordered: {len(topo_order)}")
    print("First 15 nodes in topological sequence:")
    for index, node_id in enumerate(topo_order[:15], 1):
        node = dag.nodes[node_id]
        print(f"  Step {index:02d}: Node {node_id:02d} - {node.name:<22} (Type: {node.type})")

    reach = dag.compute_transitive_closure()
    reach_pairs = sum(sum(row.values()) for row in reach.values())
    reduced_edges = dag.compute_transitive_reduction()
    print("\n" + "-" * 50)
    print("PROPERTY 3: REACHABILITY AND TRANSITIVE REDUCTION")
    print("-" * 50)
    print(f"Direct dependency edges: {len(dag.edges)}")
    print(f"Reachable node pairs: {reach_pairs}")
    print(f"Essential edges after reduction: {len(reduced_edges)}")
    print(f"Redundant direct edges removed: {len(dag.edges) - len(reduced_edges)}")

    print("\nSample reachability checks:")
    for parent_id, child_id in [(1, 2), (1, 3), (1, 25), (7, 25), (26, 30), (13, 17), (2, 7)]:
        if parent_id in dag.nodes and child_id in dag.nodes:
            result = "REACHABLE" if reach[parent_id][child_id] else "NOT REACHABLE"
            print(f"  {parent_id:02d} -> {child_id:02d}: {result}")

    scheduled_order, timeline = dag.priority_aware_task_schedule()
    total_duration = timeline[-1]["end_time"] if timeline else 0.0
    print("\n" + "-" * 50)
    print("PRACTICAL APPLICATION: SERIAL PRIORITY-AWARE BUS SCHEDULE")
    print("-" * 50)
    print("One task runs at a time; ready tasks are chosen by priority, duration, then ID.")
    print(f"Scheduled tasks: {len(scheduled_order)}")
    print(f"Serial execution estimate: {total_duration:.3f} ms")
    print(f"{'Seq':<4} | {'ID':<3} | {'Message Name':<22} | {'Prio':<5} | {'Time (ms)':<9} | {'Start (ms)':<10} | {'End (ms)':<10}")
    print("-" * 75)
    for index, item in enumerate(timeline[:10], 1):
        print(
            f"{index:<4} | {item['sl_no']:<3} | {item['name']:<22} | "
            f"{item['priority']:<5} | {item['cycletime']:<9.3f} | "
            f"{item['start_time']:<10.3f} | {item['end_time']:<10.3f}"
        )

    critical_path, critical_duration = dag.compute_critical_path()
    path_names = " -> ".join(
        f"{node_id}({dag.nodes[node_id].name})" for node_id in critical_path
    )
    print("\n" + "-" * 50)
    print("CRITICAL PATH ANALYSIS")
    print("-" * 50)
    print(f"Longest dependency chain: {path_names}")
    print(f"Critical-path execution duration: {critical_duration:.3f} ms")

    print("\n[Visualization] Generating tree, schedule, and diagram outputs...")
    generate_visualizations(dag)
    print("\n" + "=" * 80)
    print("DAG ANALYSIS AND OUTPUT GENERATION COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()
