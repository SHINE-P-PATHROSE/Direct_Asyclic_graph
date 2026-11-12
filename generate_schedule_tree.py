"""Generate a standalone dependency graph annotated with the 8 ms schedule."""

import argparse
import math
import os

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch

from dag_core import load_dag


TYPE_COLORS = {
    "eSync": "#dc2626",
    "eSyncA": "#ea580c",
    "eNor": "#0284c7",
    "eAbst": "#9333ea",
}


def generate_schedule_tree(
    output_path="dag_schedule_tree.png",
    cycle_duration=8.0,
    dpi=180,
    horizon_cycles=64,
    max_tasks_per_cycle=20,
):
    """Draw the periodic schedule as a compact 8-by-8 cycle overview."""
    graph = load_dag()
    _, timeline = graph.priority_aware_task_schedule(
        cycle_duration=cycle_duration,
        horizon_cycles=horizon_cycles,
        max_tasks_per_cycle=max_tasks_per_cycle,
    )
    cycle_tasks = {cycle: [] for cycle in range(1, horizon_cycles + 1)}
    for item in timeline:
        cycle_tasks[item["cycle"]].append(item)

    grid_columns = min(8, horizon_cycles)
    grid_rows = math.ceil(horizon_cycles / grid_columns)
    fig, axes = plt.subplots(
        grid_rows,
        grid_columns,
        figsize=(grid_columns * 4.0, grid_rows * 5.0),
        squeeze=False,
    )
    fig.patch.set_facecolor("#f8fafc")
    fig.suptitle(
        "MIL-STD-1553 Periodic Message Schedule\n"
        f"{horizon_cycles} cycles | {cycle_duration:g} ms per cycle | "
        f"maximum {max_tasks_per_cycle} executions per cycle",
        fontsize=18,
        fontweight="bold",
        color="#0f172a",
        y=0.995,
    )

    for cycle in range(1, grid_rows * grid_columns + 1):
        ax = axes[(cycle - 1) // grid_columns][(cycle - 1) % grid_columns]
        ax.set_facecolor("#ffffff")
        if cycle > horizon_cycles:
            ax.axis("off")
            continue
        tasks = cycle_tasks[cycle]
        busy = sum(item["cycletime"] for item in tasks)
        ax.set_title(
            f"Cycle {cycle}: {len(tasks)} tasks, {busy:.2f}/{cycle_duration:g} ms",
            fontsize=9,
            fontweight="bold",
            color="#0f172a",
        )
        ax.set_xlim(0, 1)
        ax.set_ylim(max_tasks_per_cycle, 0)
        ax.set_xticks([])
        ax.set_yticks([])
        for row, item in enumerate(tasks):
            node = graph.nodes[item["sl_no"]]
            color = TYPE_COLORS.get(node.type, "#64748b")
            parents = ",".join(map(str, sorted(graph.in_edges[item["sl_no"]]))) or "root"
            card = FancyBboxPatch(
                (0.02, row + 0.08),
                0.96,
                0.82,
                boxstyle="round,pad=0.015,rounding_size=0.04",
                facecolor="#ffffff",
                edgecolor=color,
                linewidth=1.1,
            )
            ax.add_patch(card)
            ax.text(
                0.05,
                row + 0.49,
                f'[{item["sl_no"]:02d}] #{item["occurrence"]} {node.name} '
                f'({item["start_time"]:.2f}-{item["end_time"]:.2f} ms; '
                f'parents: {parents})',
                ha="left",
                va="center",
                fontsize=5.1,
                color="#0f172a",
                clip_on=True,
            )
        ax.spines[["top", "right", "left", "bottom"]].set_color("#cbd5e1")

    legend_handles = [
        mpatches.Patch(facecolor="#ffffff", edgecolor=color, label=message_type)
        for message_type, color in TYPE_COLORS.items()
    ]
    fig.legend(
        handles=legend_handles,
        title="Message type",
        loc="lower center",
        ncol=len(legend_handles),
        frameon=False,
        fontsize=8,
    )
    fig.text(
        0.5,
        0.008,
        "Sampling-based schedule; listed parent IDs are prerequisites. "
        "Analytical estimate, not a validated bus simulation.",
        ha="center",
        fontsize=8,
        color="#475569",
    )
    fig.tight_layout(rect=(0.01, 0.03, 0.99, 0.98))

    output_path = os.path.abspath(output_path)
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    print(
        f"Saved {len(timeline)} scheduled executions across "
        f"{horizon_cycles} cycles to '{output_path}'"
    )
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Draw the complete dependency DAG annotated with its minor-cycle schedule."
    )
    parser.add_argument(
        "--output",
        default="dag_schedule_tree.png",
        help="PNG output path (default: dag_schedule_tree.png)",
    )
    parser.add_argument(
        "--cycle-ms",
        type=float,
        default=8.0,
        help="Minor-cycle duration in milliseconds (default: 8)",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=180,
        help="PNG resolution in DPI (default: 180)",
    )
    parser.add_argument("--cycles", type=int, default=64, help="Number of minor cycles.")
    parser.add_argument(
        "--max-tasks",
        type=int,
        default=20,
        help="Maximum executions per minor cycle.",
    )
    args = parser.parse_args()
    generate_schedule_tree(
        args.output,
        cycle_duration=args.cycle_ms,
        dpi=args.dpi,
        horizon_cycles=args.cycles,
        max_tasks_per_cycle=args.max_tasks,
    )


if __name__ == "__main__":
    main()
