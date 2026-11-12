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


def _validate_schedule(
    graph,
    timeline,
    cycle_duration,
    horizon_cycles,
    max_tasks_per_cycle,
):
    """Reject periodic schedules that exceed cycle limits or violate dependencies."""
    by_instance = {}
    cycle_counts = {}
    cycle_loads = {}
    for item in timeline:
        key = (item["sl_no"], item["occurrence"])
        if key in by_instance:
            raise ValueError(f"Schedule contains duplicate execution {key}.")
        by_instance[key] = item
        cycle_counts[item["cycle"]] = cycle_counts.get(item["cycle"], 0) + 1
        cycle_loads[item["cycle"]] = (
            cycle_loads.get(item["cycle"], 0.0) + item["cycletime"]
        )

    if any(cycle < 1 or cycle > horizon_cycles for cycle in cycle_counts):
        raise ValueError("Schedule contains a cycle outside the configured frame.")
    if any(count > max_tasks_per_cycle for count in cycle_counts.values()):
        raise ValueError(
            f"Schedule exceeds the {max_tasks_per_cycle}-task per-cycle limit."
        )
    if any(load > cycle_duration + 1e-9 for load in cycle_loads.values()):
        raise ValueError("Schedule exceeds the configured cycle duration.")

    absolute_times = {
        key: (
            (item["cycle"] - 1) * cycle_duration + item["start_time"],
            (item["cycle"] - 1) * cycle_duration + item["end_time"],
        )
        for key, item in by_instance.items()
    }
    for parent_id, child_id in graph.edges:
        parent_ends = [
            times[1]
            for key, times in absolute_times.items()
            if key[0] == parent_id
        ]
        child_starts = [
            times[0]
            for key, times in absolute_times.items()
            if key[0] == child_id
        ]
        if any(
            not any(parent_end <= child_start + 1e-9 for parent_end in parent_ends)
            for child_start in child_starts
        ):
            raise ValueError(f"Schedule violates dependency {parent_id} -> {child_id}.")


def generate_schedule_timeline(
    output_path="dag_scheduling_timeline1.png",
    cycle_duration=8.0,
    dpi=220,
    horizon_cycles=64,
    max_tasks_per_cycle=20,
):
    """Schedule periodic message executions and save a detailed per-cycle Gantt chart."""
    graph = load_dag()
    _, timeline = graph.priority_aware_task_schedule(
        cycle_duration=cycle_duration,
        horizon_cycles=horizon_cycles,
        max_tasks_per_cycle=max_tasks_per_cycle,
    )
    _validate_schedule(
        graph,
        timeline,
        cycle_duration,
        horizon_cycles,
        max_tasks_per_cycle,
    )

    cycles = {}
    for item in timeline:
        cycles.setdefault(item["cycle"], []).append(item)
    for cycle in range(1, horizon_cycles + 1):
        cycles.setdefault(cycle, [])

    cycle_summaries = []
    for cycle, items in sorted(cycles.items()):
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

    row_height = 0.11
    panel_header_height = 0.32
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
        f"{len(timeline)} executions | {len(cycles)} cycles | "
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
                f'#{item["occurrence"]} P{item["priority"]} | {item["cycletime"]:.3f} ms | '
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
            f"Cycle {cycle}: {len(items)} executions | "
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
        f"Sampling-based schedule: up to {max_tasks_per_cycle} executions per cycle; "
        "dependencies are enforced before dispatch. "
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
        f"Saved {len(timeline)} scheduled executions across {len(cycles)} cycles "
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
    parser.add_argument("--cycles", type=int, default=64, help="Number of minor cycles.")
    parser.add_argument(
        "--max-tasks",
        type=int,
        default=20,
        help="Maximum executions per minor cycle.",
    )
    args = parser.parse_args()
    generate_schedule_timeline(
        args.output,
        cycle_duration=args.cycle_ms,
        dpi=args.dpi,
        horizon_cycles=args.cycles,
        max_tasks_per_cycle=args.max_tasks,
    )


if __name__ == "__main__":
    main()
