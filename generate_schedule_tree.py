"""Generate a standalone dependency graph annotated with the 8 ms schedule."""

import argparse
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


def generate_schedule_tree(output_path="dag_schedule_tree.png", cycle_duration=8.0, dpi=180):
    """Draw all scheduled messages by minor cycle and connect dependency edges."""
    graph = load_dag()
    _, timeline = graph.priority_aware_task_schedule(cycle_duration=cycle_duration)

    cycle_tasks = {}
    schedule_by_id = {}
    for item in timeline:
        cycle_tasks.setdefault(item["cycle"], []).append(item)
        schedule_by_id[item["sl_no"]] = item

    max_tasks = max((len(tasks) for tasks in cycle_tasks.values()), default=1)
    cycle_count = max(cycle_tasks, default=1)
    column_width = 4.0
    row_height = 1.15
    card_width = 3.45
    card_height = 0.78
    figure_width = max(12, cycle_count * column_width + 1.5)
    figure_height = max(8, max_tasks * row_height + 3.0)

    fig, ax = plt.subplots(figsize=(figure_width, figure_height))
    fig.patch.set_facecolor("#f8fafc")
    ax.set_facecolor("#f8fafc")
    ax.set_title(
        "MIL-STD-1553 Scheduled Message Dependency DAG\n"
        f"Priority-aware serial schedule, {cycle_duration:g} ms per minor cycle",
        fontsize=17,
        fontweight="bold",
        color="#0f172a",
        pad=22,
    )

    positions = {}
    for cycle, tasks in sorted(cycle_tasks.items()):
        x = (cycle - 1) * column_width
        ax.axvspan(
            x - column_width / 2,
            x + column_width / 2,
            color="#eff6ff" if cycle % 2 else "#f1f5f9",
            zorder=0,
        )
        ax.text(
            x,
            1.05,
            f"MINOR CYCLE {cycle}",
            ha="center",
            va="center",
            fontsize=10,
            fontweight="bold",
            color="#334155",
        )

        for row, item in enumerate(tasks):
            node_id = item["sl_no"]
            y = -row * row_height
            positions[node_id] = (x, y)
            node = graph.nodes[node_id]
            color = TYPE_COLORS.get(node.type, "#64748b")
            card = FancyBboxPatch(
                (x - card_width / 2, y - card_height / 2),
                card_width,
                card_height,
                boxstyle="round,pad=0.025,rounding_size=0.08",
                facecolor="#ffffff",
                edgecolor=color,
                linewidth=1.6,
                zorder=3,
            )
            ax.add_patch(card)
            ax.text(
                x,
                y,
                f"[{node_id:02d}] {node.name}\n"
                f"{node.type} | Priority {node.priority} | {item['cycletime']:.3f} ms\n"
                f"{item['start_time']:.3f}–{item['end_time']:.3f} ms",
                ha="center",
                va="center",
                fontsize=6.8,
                color="#0f172a",
                zorder=4,
            )

    for parent_id, child_id in sorted(graph.edges):
        parent = schedule_by_id[parent_id]
        child = schedule_by_id[child_id]
        parent_position = positions[parent_id]
        child_position = positions[child_id]
        ax.annotate(
            "",
            xy=child_position,
            xytext=parent_position,
            arrowprops={
                "arrowstyle": "-|>",
                "color": "#64748b",
                "linewidth": 0.9,
                "alpha": 0.75,
                "shrinkA": 30,
                "shrinkB": 30,
                "connectionstyle": "arc3,rad=0.06",
            },
            zorder=2,
        )

    legend_handles = [
        mpatches.Patch(facecolor="#ffffff", edgecolor=color, label=message_type)
        for message_type, color in TYPE_COLORS.items()
    ]
    ax.legend(
        handles=legend_handles,
        title="Message type",
        loc="upper right",
        frameon=True,
        fontsize=8,
    )
    ax.text(
        0.01,
        -0.035,
        "Arrow: prerequisite → dependent. Times are an analytical serial schedule, not a validated bus simulation.",
        transform=ax.transAxes,
        fontsize=8,
        color="#475569",
        ha="left",
        va="top",
    )

    ax.set_xlim(-column_width / 2 - 0.2, (cycle_count - 1) * column_width + column_width / 2 + 0.2)
    ax.set_ylim(-(max_tasks - 1) * row_height - 0.9, 1.5)
    ax.axis("off")
    fig.tight_layout()

    output_path = os.path.abspath(output_path)
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved scheduled dependency graph for {len(graph.nodes)} messages to '{output_path}'")
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
    args = parser.parse_args()
    generate_schedule_tree(args.output, cycle_duration=args.cycle_ms, dpi=args.dpi)


if __name__ == "__main__":
    main()
