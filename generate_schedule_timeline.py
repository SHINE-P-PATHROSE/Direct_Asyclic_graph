"""Generate a complete cycle-by-cycle Gantt chart for scheduled DAG messages."""

import argparse
import os

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from dag_core import load_dag


TYPE_COLORS = {
    "eSync": "#dc2626",
    "eSyncA": "#ea580c",
    "eNor": "#0284c7",
    "eAbst": "#9333ea",
}


def _validate_schedule(graph, timeline, cycle_duration):
    """Reject schedules that omit tasks, violate dependencies, or overflow cycles."""
    if len(timeline) != len(graph.nodes):
        raise ValueError(
            f"Schedule contains {len(timeline)} tasks, expected {len(graph.nodes)}."
        )

    by_id = {item["sl_no"]: item for item in timeline}
    if len(by_id) != len(graph.nodes):
        raise ValueError("Schedule contains duplicate or missing message IDs.")

    absolute_times = {
        node_id: (
            (item["cycle"] - 1) * cycle_duration + item["start_time"],
            (item["cycle"] - 1) * cycle_duration + item["end_time"],
        )
        for node_id, item in by_id.items()
    }

    for parent_id, child_id in graph.edges:
        if absolute_times[parent_id][1] > absolute_times[child_id][0] + 1e-9:
            raise ValueError(
                f"Schedule violates dependency {parent_id} -> {child_id}."
            )

    for item in timeline:
        if item["start_time"] < -1e-9 or item["end_time"] > cycle_duration + 1e-9:
            raise ValueError(
                f"Message {item['sl_no']} does not fit in cycle {item['cycle']}."
            )


def generate_schedule_timeline(
    output_path="dag_scheduling_timeline1.png",
    cycle_duration=8.0,
    dpi=220,
):
    """Schedule every message once and save a detailed per-cycle Gantt chart."""
    graph = load_dag()
    _, timeline = graph.priority_aware_task_schedule(cycle_duration=cycle_duration)
    _validate_schedule(graph, timeline, cycle_duration)

    cycles = {}
    for item in timeline:
        cycles.setdefault(item["cycle"], []).append(item)

    cycle_summaries = []
    for cycle, items in cycles.items():
        busy_time = sum(item["cycletime"] for item in items)
        cycle_summaries.append(
            {
                "cycle": cycle,
                "items": items,
                "busy": busy_time,
                "slack": max(0.0, cycle_duration - busy_time),
                "utilization": busy_time / cycle_duration * 100,
            }
        )

    row_height = 0.23
    panel_header_height = 0.75
    figure_height = max(
        10,
        row_height * len(timeline) + panel_header_height * len(cycles) + 2.2,
    )
    fig, axes = plt.subplots(
        len(cycle_summaries),
        1,
        figsize=(22, figure_height),
        sharex=True,
        gridspec_kw={
            "height_ratios": [max(1, len(summary["items"])) for summary in cycle_summaries]
        },
        squeeze=False,
    )
    fig.patch.set_facecolor("#f8fafc")
    fig.suptitle(
        "MIL-STD-1553 Message Scheduling Timeline\n"
        f"All {len(timeline)} messages | {len(cycles)} cycles | "
        f"{sum(item['cycletime'] for item in timeline):.3f} ms total execution | "
        f"{cycle_duration:g} ms minor cycles",
        fontsize=19,
        fontweight="bold",
        color="#0f172a",
        y=0.998,
    )

    legend_handles = [
        mpatches.Patch(facecolor=color, label=message_type)
        for message_type, color in TYPE_COLORS.items()
    ]

    for ax, summary in zip(axes[:, 0], cycle_summaries):
        cycle = summary["cycle"]
        items = summary["items"]
        y_values = list(range(len(items)))
        ax.set_facecolor("#ffffff")
        ax.barh(
            y_values,
            [item["cycletime"] for item in items],
            left=[item["start_time"] for item in items],
            height=0.68,
            color=[
                TYPE_COLORS.get(graph.nodes[item["sl_no"]].type, "#64748b")
                for item in items
            ],
            edgecolor="#ffffff",
            linewidth=0.6,
            zorder=3,
        )
        ax.set_yticks(y_values)
        ax.set_yticklabels(
            [
                f'[{item["sl_no"]:02d}] {item["name"]}   '
                f'P{item["priority"]} | {item["cycletime"]:.3f} ms | '
                f'{item["start_time"]:.3f}–{item["end_time"]:.3f} ms'
                for item in items
            ],
            fontsize=7.2,
            color="#1e293b",
        )
        ax.invert_yaxis()
        ax.set_xlim(0, cycle_duration)
        ax.set_xticks(
            [
                tick
                for tick in range(int(cycle_duration) + 1)
                if tick <= cycle_duration
            ]
        )
        ax.grid(axis="x", linestyle="--", linewidth=0.7, color="#cbd5e1", zorder=0)
        ax.tick_params(axis="y", length=0, pad=8)
        ax.tick_params(axis="x", labelsize=8, colors="#475569")
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.spines["bottom"].set_color("#94a3b8")
        ax.set_title(
            f"Cycle {cycle}: {len(items)} messages | "
            f"busy {summary['busy']:.3f} ms | "
            f"slack {summary['slack']:.3f} ms | "
            f"utilization {summary['utilization']:.1f}%",
            loc="left",
            fontsize=10,
            fontweight="bold",
            color="#0f172a",
            pad=7,
        )

    axes[-1, 0].set_xlabel("Time within minor cycle (ms)", fontsize=10, labelpad=8)
    fig.legend(
        handles=legend_handles,
        title="Message type",
        loc="upper right",
        bbox_to_anchor=(0.985, 0.965),
        ncol=len(legend_handles),
        fontsize=8,
        title_fontsize=8,
        frameon=False,
    )
    fig.text(
        0.5,
        0.003,
        "Each message is scheduled once; arrows/dependencies are enforced before dispatch. "
        "Computed estimates, not the incomplete planned-cycle entries in the workbook "
        "or a validated MIL-STD-1553 bus simulation.",
        ha="center",
        fontsize=8,
        color="#475569",
    )
    fig.subplots_adjust(left=0.36, right=0.985, top=0.925, bottom=0.025, hspace=0.6)

    output_path = os.path.abspath(output_path)
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    try:
        fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
    finally:
        plt.close(fig)

    total_time = sum(item["cycletime"] for item in timeline)
    print(
        f"Saved {len(timeline)} scheduled messages across {len(cycles)} cycles "
        f"({total_time:.3f} ms total execution) to '{output_path}'"
    )
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Generate a complete DAG-aware message scheduling timeline."
    )
    parser.add_argument(
        "--output",
        default="dag_scheduling_timeline1.png",
        help="PNG path (default: dag_scheduling_timeline1.png)",
    )
    parser.add_argument(
        "--cycle-ms",
        type=float,
        default=8.0,
        help="Minor-cycle duration in milliseconds (default: 8)",
    )
    parser.add_argument("--dpi", type=int, default=220, help="PNG resolution (default: 220)")
    args = parser.parse_args()
    generate_schedule_timeline(
        args.output,
        cycle_duration=args.cycle_ms,
        dpi=args.dpi,
    )


if __name__ == "__main__":
    main()
