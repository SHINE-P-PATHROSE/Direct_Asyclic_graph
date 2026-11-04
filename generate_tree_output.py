"""
========================================================================================
MIL-STD-1553 BUS HIERARCHICAL TREE GENERATOR
========================================================================================
WHAT THIS FILE IS:
-----------------
This is the dedicated Hierarchical Tree Generator for the MIL-STD-1553 Bus DAG.
It transforms the dependency dataset into publication-grade tree representations:

1. 'dag_subsystem_trees.png'      - Spacious 4-panel breakdown of isolated subsystem
                                    trees (DTG, WDE, BMU/BDH, SSR) with zero overlap,
                                    full message details, and clear convergence badges.
2. 'dag_unified_tree_hierarchy.png' - High-resolution Multi-Stage Master Execution Tree
                                    (Stage 0: Bus Controller -> Stage 1: Sync Roots ->
                                     Stage 2: Commands & Telemetry -> Stage 3: Convergence).
3. 'dag_tree_structure.txt'       - Complete DAG-aware text schedule.
========================================================================================
"""

import os
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
from dag_core import load_dag, schedule_cycle_data, to_visualization_data

# Professional Color Palette & Styling Tokens
TYPE_CONFIG = {
    'eSync': {
        'bg': '#fef2f2',       # Soft red background
        'border': '#dc2626',   # Crimson border
        'header': '#dc2626',   # Crimson header
        'text': '#991b1b',
        'name': 'eSync (Bus Synchronization Root)'
    },
    'eSyncA': {
        'bg': '#fff7ed',       # Soft amber background
        'border': '#ea580c',   # Amber border
        'header': '#ea580c',   # Amber header
        'text': '#9a3412',
        'name': 'eSyncA (Sync Acknowledge Level 1)'
    },
    'eNor': {
        'bg': '#f0f9ff',       # Soft sky blue background
        'border': '#0284c7',   # Deep blue border
        'header': '#0284c7',   # Sky blue header
        'text': '#075985',
        'name': 'eNor (Normal Periodic Telemetry)'
    },
    'eAbst': {
        'bg': '#faf5ff',       # Soft purple background
        'border': '#9333ea',   # Violet border
        'header': '#9333ea',   # Violet header
        'text': '#6b21a8',
        'name': 'eAbst (Auxiliary Message)'
    },
    'BC': {
        'bg': '#f8fafc',       # Deep navy background
        'border': '#0f172a',   # Navy border
        'header': '#0f172a',   # Navy header
        'text': '#1e293b',
        'name': '1553 Bus Controller (Master Frame)'
    }
}


def save_figure_safely(fig, filename, dpi=300):
    """
    Safely saves figure to disk. Handles Windows file lock / sharing violations
    (e.g., when the user has the image currently open in Windows Photos or another viewer).
    """
    import time
    abs_path = os.path.abspath(filename)

    # 1. Try direct save (with retries in case of transient filesystem lock)
    for attempt in range(3):
        try:
            fig.savefig(abs_path, bbox_inches="tight", dpi=dpi)
            plt.close(fig)
            print(f" -> Successfully saved high-clarity {dpi} DPI '{os.path.basename(filename)}'")
            return
        except OSError:
            time.sleep(0.35)

    # 2. If locked by an active external viewer (e.g. Windows Photos app):
    # Save to a fresh copy so execution continues smoothly without crashing!
    base, ext = os.path.splitext(filename)
    fallback_name = f"{base}_updated{ext}"
    try:
        fig.savefig(fallback_name, bbox_inches="tight", dpi=dpi)
        plt.close(fig)
        print(f" [Notice] '{filename}' is open in an external image viewer (locked by Windows).")
        print(f"          Successfully saved latest version to '{fallback_name}'!")
    except OSError as e:
        plt.close(fig)
        raise OSError(f"Could not save figure to '{filename}' or '{fallback_name}'.") from e


def load_data():
    """Load the canonical graph and adapt it for the existing visual layouts."""
    return to_visualization_data(load_dag())


def draw_node_card(ax, x, y, width, height, nid, name, ntype, ntime, nprio=None,
                   badge_text=None, badge_color="#dc2626", is_highlight=False):
    """
    Draw a clean, detailed, CAD-grade node card with subtle drop-shadow,
    high-contrast header, and perfectly aligned text.
    """
    cfg = TYPE_CONFIG.get(ntype, TYPE_CONFIG['eNor'])

    # Drop shadow
    shadow = FancyBboxPatch((x - width / 2 + 0.03, y - height / 2 - 0.03), width, height,
                            boxstyle="round,pad=0.02,rounding_size=0.12",
                            facecolor="#cbd5e1", edgecolor="none", alpha=0.5, zorder=2)
    ax.add_patch(shadow)

    # Main Card Box
    border_color = "#b91c1c" if is_highlight else cfg['border']
    border_w = 2.4 if is_highlight else 1.6
    card = FancyBboxPatch((x - width / 2, y - height / 2), width, height,
                          boxstyle="round,pad=0.02,rounding_size=0.12",
                          facecolor=cfg['bg'], edgecolor=border_color,
                          linewidth=border_w, zorder=3)
    ax.add_patch(card)

    # Header Bar
    header_h = height * 0.42
    header = FancyBboxPatch((x - width / 2, y + height / 2 - header_h), width, header_h,
                            boxstyle="round,pad=0.01,rounding_size=0.10",
                            facecolor=cfg['header'], edgecolor="none", zorder=4)
    ax.add_patch(header)

    # Header Text: Node ID and Message Name
    id_str = f"[{nid:02d}]" if nid > 0 else "[BC]"
    title_text = f"{id_str} {name}"
    if len(title_text) > 22:
        title_text = title_text[:21] + "…"

    ax.text(x, y + height / 2 - header_h / 2, title_text,
            color="#ffffff", fontsize=8.0, fontweight="bold",
            ha="center", va="center", zorder=5)

    # Body Details
    prio_str = f" | Prio {nprio}" if nprio is not None else ""
    body_text = f"{ntype} | {ntime:.3f} ms{prio_str}" if ntime > 0 else f"{ntype}{prio_str}"
    ax.text(x, y - height * 0.16, body_text,
            color="#334155", fontsize=7.2, fontweight="normal",
            ha="center", va="center", zorder=5)

    # Pill Badge (e.g. Convergence, Critical Path)
    if badge_text:
        badge_w = width * 0.75
        badge_h = height * 0.22
        bp = FancyBboxPatch((x - badge_w / 2, y + height / 2 + 0.02), badge_w, badge_h,
                            boxstyle="round,pad=0.01,rounding_size=0.08",
                            facecolor=badge_color, edgecolor="#ffffff", linewidth=0.8, zorder=6)
        ax.add_patch(bp)
        ax.text(x, y + height / 2 + 0.02 + badge_h / 2, badge_text,
                color="#ffffff", fontsize=6.5, fontweight="bold",
                ha="center", va="center", zorder=7)


def draw_arrow(ax, start_pt, end_pt, color="#475569", lw=1.5, style="straight", rad=0.0):
    """Draw clean directed arrow connecting cards with generous arrowhead."""
    if style == "straight":
        ax.annotate('', xy=end_pt, xytext=start_pt,
                    arrowprops=dict(arrowstyle="-|>", color=color, lw=lw,
                                    mutation_scale=13, shrinkA=2, shrinkB=2),
                    zorder=2)
    elif style == "curved":
        conn = f"arc3,rad={rad}"
        ax.annotate('', xy=end_pt, xytext=start_pt,
                    arrowprops=dict(arrowstyle="-|>", color=color, lw=lw,
                                    connectionstyle=conn, mutation_scale=13,
                                    shrinkA=2, shrinkB=2),
                    zorder=2)


def generate_subsystem_trees_image(nodes, adj):
    """
    Generate clean, spacious 4-panel subsystem trees with cards and zero overlap.
    DPI=300 for pristine print/publication quality.
    """
    fig, axes = plt.subplots(2, 2, figsize=(28, 22), dpi=300)
    fig.patch.set_facecolor("#f8fafc")
    fig.suptitle("MIL-STD-1553 Bus Subsystem Dependency Trees (Detailed Architectural Hierarchy)",
                 fontsize=22, fontweight="bold", color="#0f172a", y=0.985)

    card_w = 2.5
    card_h = 0.78

    # -------------------------------------------------------------------------
    # Panel 1: DTG Subsystem (Gyros 1 & 2 Execution Tree)
    # -------------------------------------------------------------------------
    ax1 = axes[0, 0]
    ax1.set_facecolor("#ffffff")
    ax1.set_title("(A) DTG Subsystem (Dynamic Tuned Gyros 1 & 2 Execution Tree)",
                  fontsize=14, fontweight="bold", color="#1e293b", pad=14)

    dtg_positions = {
        # DTG1 Sync Root & Branches
        1:  (4.5, 9.2),
        2:  (1.6, 6.8),   # Rate Telemetry
        4:  (4.5, 6.8),   # Temp 1
        5:  (7.4, 6.8),   # Temp 2
        6:  (10.3, 6.8),  # VStatus
        3:  (1.6, 4.4),   # Secondary Rate TM (from 2)
        # DTG1 Cross Gyro Telemetry Group
        9:  (3.0, 2.0),
        10: (5.8, 2.0),
        11: (8.6, 2.0),
        12: (11.4, 2.0),
        # DTG2 Sync Root & Branches
        7:  (14.5, 9.2),
        8:  (14.5, 6.8),  # DTG2 VStatus
        # Dual Convergence Node
        25: (14.5, 3.2)
    }

    # Arrows for DTG1
    for child in [2, 4, 5, 6]:
        draw_arrow(ax1, (4.5, 9.2 - card_h/2), (dtg_positions[child][0], 6.8 + card_h/2), color="#64748b", lw=1.6)
    # 2 -> 3
    draw_arrow(ax1, (1.6, 6.8 - card_h/2), (1.6, 4.4 + card_h/2), color="#0284c7", lw=1.8)
    # 1 -> Cross Gyros
    for c in [9, 10, 11, 12]:
        draw_arrow(ax1, (4.5, 9.2 - card_h/2), (dtg_positions[c][0], 2.0 + card_h/2),
                   color="#94a3b8", lw=1.3, style="curved", rad=-0.12)
    # 7 -> 8
    draw_arrow(ax1, (14.5, 9.2 - card_h/2), (14.5, 6.8 + card_h/2), color="#64748b", lw=1.6)
    # Convergence: 1 -> 25 and 7 -> 25
    draw_arrow(ax1, (4.5, 9.2 - card_h/2), (14.5 - card_w/2, 3.2), color="#dc2626", lw=2.0, style="curved", rad=0.15)
    draw_arrow(ax1, (14.5, 6.8 - card_h/2), (14.5, 3.2 + card_h/2), color="#dc2626", lw=2.0)

    for nid, (x, y) in dtg_positions.items():
        n = nodes[nid]
        badge = "DUAL CONVERGENCE" if nid == 25 else ("CRITICAL ROOT" if nid in [1, 7] else None)
        draw_node_card(ax1, x, y, card_w, card_h, nid, n['name'], n['type'], n['time'], n['priority'],
                       badge_text=badge, badge_color="#dc2626" if nid == 25 else "#0284c7")

    ax1.set_xlim(0.0, 16.5)
    ax1.set_ylim(0.5, 10.5)
    ax1.axis("off")

    # -------------------------------------------------------------------------
    # Panel 2: WDE Subsystem (Wheel Drive Electronics 1 & 2)
    # -------------------------------------------------------------------------
    ax2 = axes[0, 1]
    ax2.set_facecolor("#ffffff")
    ax2.set_title("(B) WDE Subsystem (Wheel Drive Electronics 1 & 2 Command & Telemetry)",
                  fontsize=14, fontweight="bold", color="#1e293b", pad=14)

    wde_positions = {
        # WDE1 Tree (Left)
        13: (4.0, 9.0),
        14: (1.8, 6.0),
        15: (4.0, 6.0),
        16: (1.8, 3.0),
        17: (4.0, 3.0),
        # WDE2 Tree (Right)
        19: (11.0, 9.0),
        20: (8.8, 6.0),
        21: (11.0, 6.0),
        22: (8.8, 3.0),
        23: (11.0, 3.0)
    }

    for child in [14, 15, 16, 17]:
        draw_arrow(ax2, (4.0, 9.0 - card_h/2), (wde_positions[child][0], wde_positions[child][1] + card_h/2), color="#64748b", lw=1.6)
    for child in [20, 21, 22, 23]:
        draw_arrow(ax2, (11.0, 9.0 - card_h/2), (wde_positions[child][0], wde_positions[child][1] + card_h/2), color="#64748b", lw=1.6)

    for nid, (x, y) in wde_positions.items():
        n = nodes[nid]
        badge = "WDE1 SYNC ROOT" if nid == 13 else ("WDE2 SYNC ROOT" if nid == 19 else None)
        draw_node_card(ax2, x, y, card_w, card_h, nid, n['name'], n['type'], n['time'], n['priority'],
                       badge_text=badge, badge_color="#ea580c")

    ax2.set_xlim(0.0, 14.0)
    ax2.set_ylim(1.5, 10.5)
    ax2.axis("off")

    # -------------------------------------------------------------------------
    # Panel 3: BMU & BDH Subsystems (Convergence & Critical Path)
    # -------------------------------------------------------------------------
    ax3 = axes[1, 0]
    ax3.set_facecolor("#ffffff")
    ax3.set_title("(C) BMU & BDH Subsystems (4-Way Fan-in Convergence & Critical Path Latency)",
                  fontsize=14, fontweight="bold", color="#1e293b", pad=14)

    bmu_positions = {
        26: (1.6, 8.5),
        27: (4.4, 8.5),
        28: (7.2, 8.5),
        29: (10.0, 8.5),
        30: (5.8, 4.2),
        80: (13.5, 8.5),
        81: (13.5, 4.2)
    }

    for p in [26, 27, 28, 29]:
        draw_arrow(ax3, (bmu_positions[p][0], 8.5 - card_h/2), (5.8, 4.2 + card_h/2), color="#64748b", lw=1.8)
    draw_arrow(ax3, (13.5, 8.5 - card_h/2), (13.5, 4.2 + card_h/2), color="#dc2626", lw=2.4)

    cp_box = FancyBboxPatch((11.8, 2.0), 3.4, 1.2,
                            boxstyle="round,pad=0.04,rounding_size=0.15",
                            facecolor="#fef2f2", edgecolor="#dc2626", linewidth=1.8, zorder=3)
    ax3.add_patch(cp_box)
    ax3.text(13.5, 2.7, "CRITICAL PATH CHAIN\n80 (0.715ms) -> 81 (0.715ms)\nTotal Duration: 1.430 ms",
             color="#991b1b", fontsize=7.8, fontweight="bold", ha="center", va="center", zorder=4)

    for nid, (x, y) in bmu_positions.items():
        n = nodes[nid]
        badge = "4-WAY CONVERGENCE" if nid == 30 else ("CRITICAL PATH" if nid in [80, 81] else None)
        draw_node_card(ax3, x, y, card_w, card_h, nid, n['name'], n['type'], n['time'], n['priority'],
                       badge_text=badge, badge_color="#dc2626" if nid in [30, 80, 81] else "#0284c7",
                       is_highlight=(nid in [80, 81]))

    ax3.set_xlim(0.0, 16.0)
    ax3.set_ylim(1.0, 10.0)
    ax3.axis("off")

    # -------------------------------------------------------------------------
    # Panel 4: SSR Subsystems (Solid State Recorders Dual Chains)
    # -------------------------------------------------------------------------
    ax4 = axes[1, 1]
    ax4.set_facecolor("#ffffff")
    ax4.set_title("(D) SSR Subsystems (Solid State Recorders 1 & 2 Independent Dual Telemetry)",
                  fontsize=14, fontweight="bold", color="#1e293b", pad=14)

    ssr_positions = {
        82: (4.0, 8.5),
        83: (4.0, 4.2),
        86: (10.0, 8.5),
        87: (10.0, 4.2)
    }

    draw_arrow(ax4, (4.0, 8.5 - card_h/2), (4.0, 4.2 + card_h/2), color="#0284c7", lw=2.0)
    draw_arrow(ax4, (10.0, 8.5 - card_h/2), (10.0, 4.2 + card_h/2), color="#0284c7", lw=2.0)

    box_ssr1 = FancyBboxPatch((2.2, 1.8), 3.6, 1.2,
                              boxstyle="round,pad=0.03,rounding_size=0.12",
                              facecolor="#f0f9ff", edgecolor="#0284c7", linewidth=1.4)
    ax4.add_patch(box_ssr1)
    ax4.text(4.0, 2.4, "SSR-1 Channel\nSequential Telemetry Link\n0.320 ms Execution",
             color="#0369a1", fontsize=7.8, fontweight="bold", ha="center", va="center")

    box_ssr2 = FancyBboxPatch((8.2, 1.8), 3.6, 1.2,
                              boxstyle="round,pad=0.03,rounding_size=0.12",
                              facecolor="#f0f9ff", edgecolor="#0284c7", linewidth=1.4)
    ax4.add_patch(box_ssr2)
    ax4.text(10.0, 2.4, "SSR-2 Channel\nSequential Telemetry Link\n0.320 ms Execution",
             color="#0369a1", fontsize=7.8, fontweight="bold", ha="center", va="center")

    for nid, (x, y) in ssr_positions.items():
        n = nodes[nid]
        badge = "SSR1 ROOT" if nid == 82 else ("SSR2 ROOT" if nid == 86 else "TELEMETRY LEAF")
        draw_node_card(ax4, x, y, card_w, card_h, nid, n['name'], n['type'], n['time'], n['priority'],
                       badge_text=badge, badge_color="#0284c7")

    ax4.set_xlim(0.0, 14.0)
    ax4.set_ylim(1.0, 10.0)
    ax4.axis("off")

    # Common Legend
    legend_elements = [
        mpatches.Patch(facecolor=TYPE_CONFIG['eSync']['header'], edgecolor=TYPE_CONFIG['eSync']['border'],
                       label='eSync (Bus Sync Root)'),
        mpatches.Patch(facecolor=TYPE_CONFIG['eSyncA']['header'], edgecolor=TYPE_CONFIG['eSyncA']['border'],
                       label='eSyncA (Sync Acknowledge Level 1)'),
        mpatches.Patch(facecolor=TYPE_CONFIG['eNor']['header'], edgecolor=TYPE_CONFIG['eNor']['border'],
                       label='eNor (Normal Periodic Telemetry)'),
        mpatches.Patch(facecolor=TYPE_CONFIG['eAbst']['header'], edgecolor=TYPE_CONFIG['eAbst']['border'],
                       label='eAbst (Auxiliary Message)'),
        mpatches.Patch(facecolor='#dc2626', edgecolor='#ffffff',
                       label='Critical Path / Convergence Link')
    ]
    fig.legend(handles=legend_elements, loc='lower center', ncol=5, frameon=True,
               fontsize=11.5, facecolor="#ffffff", edgecolor="#cbd5e1", bbox_to_anchor=(0.5, 0.012))

    plt.tight_layout(rect=[0, 0.04, 1, 0.97])
    save_figure_safely(fig, "dag_subsystem_trees.png", dpi=300)


def generate_unified_tree_image(nodes, adj, in_degree):
    """
    Generate a stunning, zero-overlap Left-to-Right Hierarchical Master Tree.
    Every node is placed on its own horizontal slot so text NEVER overlaps.
    DPI=300 for crisp rendering.
    """
    fig, ax = plt.subplots(figsize=(28, 24), dpi=300)
    fig.patch.set_facecolor("#f8fafc")
    ax.set_facecolor("#f8fafc")
    ax.set_title("MIL-STD-1553 Bus Hierarchical Master Execution Tree\n(Zero-Overlap Multi-Stage Architecture)",
                 fontsize=22, fontweight="bold", color="#0f172a", pad=28)

    card_w = 2.7
    card_h = 0.72

    # Vertical rows (Y: 28 down to -5)
    tree_layout = [
        # STAGE 0: Root BC
        (0, 0.0, 14.0),

        # DTG1 Sub-tree
        (1,  4.2, 23.5),
        (2,  8.8, 27.0),
        (3, 13.2, 27.0),
        (4,  8.8, 25.5),
        (5,  8.8, 24.0),
        (6,  8.8, 22.5),
        (9,  8.8, 21.0),
        (10, 8.8, 19.5),
        (11, 8.8, 18.0),
        (12, 8.8, 16.5),

        # DTG2 Sub-tree & Convergence 25
        (7,  4.2, 14.5),
        (8,  8.8, 14.5),
        (25, 13.2, 19.0),

        # WDE1 Sub-tree
        (13, 4.2, 11.5),
        (14, 8.8, 12.8),
        (15, 8.8, 11.5),
        (16, 8.8, 10.2),
        (17, 8.8,  8.9),

        # WDE2 Sub-tree
        (19, 4.2,  6.5),
        (20, 8.8,  7.8),
        (21, 8.8,  6.5),
        (22, 8.8,  5.2),
        (23, 8.8,  3.9),

        # BMU Sub-tree & Convergence 30
        (26, 4.2,  2.2),
        (27, 4.2,  1.0),
        (28, 4.2, -0.2),
        (29, 4.2, -1.4),
        (30, 8.8,  0.4),

        # BDH & SSR Pairs
        (80, 4.2, -2.8),
        (81, 8.8, -2.8),
        (82, 4.2, -4.2),
        (83, 8.8, -4.2),
        (86, 4.2, -5.6),
        (87, 8.8, -5.6)
    ]

    coords = {nid: (x, y) for (nid, x, y) in tree_layout}

    # Stage 0 -> Stage 1 Roots
    for r in [1, 7, 13, 19, 26, 27, 28, 29, 80, 82, 86]:
        draw_arrow(ax, (0.0 + card_w/2, 14.0), (4.2 - card_w/2, coords[r][1]),
                   color="#94a3b8", lw=1.3, style="curved", rad=0.06)

    # 1 -> children
    for c in [2, 4, 5, 6, 9, 10, 11, 12]:
        draw_arrow(ax, (4.2 + card_w/2, coords[1][1]), (8.8 - card_w/2, coords[c][1]), color="#64748b", lw=1.5)
    # 2 -> 3
    draw_arrow(ax, (8.8 + card_w/2, coords[2][1]), (13.2 - card_w/2, coords[3][1]), color="#0284c7", lw=1.8)
    # 7 -> 8
    draw_arrow(ax, (4.2 + card_w/2, coords[7][1]), (8.8 - card_w/2, coords[8][1]), color="#64748b", lw=1.5)
    # Convergence: 1 -> 25 and 7 -> 25
    draw_arrow(ax, (4.2 + card_w/2, coords[1][1]), (13.2 - card_w/2, coords[25][1]),
               color="#dc2626", lw=2.0, style="curved", rad=-0.12)
    draw_arrow(ax, (4.2 + card_w/2, coords[7][1]), (13.2 - card_w/2, coords[25][1]),
               color="#dc2626", lw=2.0, style="curved", rad=0.12)

    # 13 -> children
    for c in [14, 15, 16, 17]:
        draw_arrow(ax, (4.2 + card_w/2, coords[13][1]), (8.8 - card_w/2, coords[c][1]), color="#64748b", lw=1.5)

    # 19 -> children
    for c in [20, 21, 22, 23]:
        draw_arrow(ax, (4.2 + card_w/2, coords[19][1]), (8.8 - card_w/2, coords[c][1]), color="#64748b", lw=1.5)

    # BMU Convergence into 30
    for p in [26, 27, 28, 29]:
        draw_arrow(ax, (4.2 + card_w/2, coords[p][1]), (8.8 - card_w/2, coords[30][1]), color="#64748b", lw=1.5)

    # 80 -> 81 (Critical Path)
    draw_arrow(ax, (4.2 + card_w/2, coords[80][1]), (8.8 - card_w/2, coords[81][1]), color="#dc2626", lw=2.4)
    # 82 -> 83, 86 -> 87
    draw_arrow(ax, (4.2 + card_w/2, coords[82][1]), (8.8 - card_w/2, coords[83][1]), color="#64748b", lw=1.5)
    draw_arrow(ax, (4.2 + card_w/2, coords[86][1]), (8.8 - card_w/2, coords[87][1]), color="#64748b", lw=1.5)

    # Draw Cards
    for nid, (x, y) in coords.items():
        if nid == 0:
            draw_node_card(ax, x, y, card_w * 1.15, card_h * 1.15, 0, "1553 Bus Controller", "BC", 0.0,
                           badge_text="BUS MASTER", badge_color="#0f172a")
        else:
            n = nodes[nid]
            badge = None
            if nid in [1, 7, 13, 19]:
                badge = "SYNC ROOT"
            elif nid in [25, 30]:
                badge = "CONVERGENCE"
            elif nid in [80, 81]:
                badge = "CRITICAL PATH"
            draw_node_card(ax, x, y, card_w, card_h, nid, n['name'], n['type'], n['time'], n['priority'],
                           badge_text=badge, badge_color="#dc2626" if nid in [25, 30, 80, 81] else "#0284c7",
                           is_highlight=(nid in [80, 81]))

    # Column Headers
    col_headers = [
        (0.0, "STAGE 0\n1553 Bus Controller Root", "#0f172a"),
        (4.2, "STAGE 1\nSubsystem Synchronization (Level 1)", "#0284c7"),
        (8.8, "STAGE 2\nCommands & Telemetry (Level 2)", "#ea580c"),
        (13.2, "STAGE 3\nResponses & Convergence (Level 3)", "#dc2626")
    ]
    for col_x, h_text, h_col in col_headers:
        ax.text(col_x, 28.5, h_text, fontsize=11.5, fontweight="bold", color=h_col, ha="center")
        ax.axvline(col_x, color="#e2e8f0", linestyle="--", lw=1.4, zorder=1)

    ax.set_xlim(-1.8, 15.0)
    ax.set_ylim(-7.0, 30.0)
    ax.axis("off")

    # Legend
    legend_elements = [
        mpatches.Patch(facecolor=TYPE_CONFIG['BC']['header'], edgecolor=TYPE_CONFIG['BC']['border'],
                       label='Level 0: 1553 Bus Controller (BC Frame Master)'),
        mpatches.Patch(facecolor=TYPE_CONFIG['eSync']['header'], edgecolor=TYPE_CONFIG['eSync']['border'],
                       label='eSync (Bus Synchronization Root)'),
        mpatches.Patch(facecolor=TYPE_CONFIG['eSyncA']['header'], edgecolor=TYPE_CONFIG['eSyncA']['border'],
                       label='eSyncA (Sync Acknowledge Level 1)'),
        mpatches.Patch(facecolor=TYPE_CONFIG['eNor']['header'], edgecolor=TYPE_CONFIG['eNor']['border'],
                       label='eNor (Normal Telemetry Transfer)'),
        mpatches.Patch(facecolor='#dc2626', edgecolor='#ffffff',
                       label='Critical Path / Convergence Link')
    ]
    fig.legend(handles=legend_elements, loc='lower center', ncol=5, frameon=True,
               fontsize=11.5, facecolor="#ffffff", edgecolor="#cbd5e1", bbox_to_anchor=(0.5, 0.012))

    plt.tight_layout(rect=[0, 0.04, 1, 0.97])
    save_figure_safely(fig, "dag_unified_tree_hierarchy.png", dpi=300)


def compute_priority_schedule(nodes, adj, in_edges, in_degree, total_cycle_time=8.000):
    """Schedule tasks through the shared DAG scheduler and pack them into cycles."""
    return schedule_cycle_data(nodes, adj, in_edges, in_degree, total_cycle_time)


def generate_text_tree(nodes, adj, in_edges, in_degree):
    """Generate hierarchical dependency tree annotated with topological cycle schedule."""

    TOTAL_CYCLE_TIME = 8.000
    schedule_by_id, schedule_ordered_list, cycle_summaries = compute_priority_schedule(
        nodes, adj, in_edges, in_degree, TOTAL_CYCLE_TIME
    )

    tree_lines = []
    tree_lines.append("=" * 116)
    tree_lines.append("MIL-STD-1553 BUS HIERARCHICAL TASK DEPENDENCY TREE & FRAME SCHEDULE")
    tree_lines.append(f"Bus Minor Cycle Duration: {TOTAL_CYCLE_TIME:.3f} ms | Priority-Aware Topological Precedence Schedule")
    tree_lines.append("=" * 116)
    tree_lines.append("[00] 1553 Bus Controller (Master Frame Schedule Root)")

    major_roots = sorted(
        node_id for node_id in nodes
        if in_degree[node_id] == 0 and adj.get(node_id)
    )
    visited = set()

    def build_tree_text(u, prefix="", is_last=True, visited=None):
        if visited is None:
            visited = set()

        n = nodes[u]
        sch = schedule_by_id[u]

        node_str = (
            f"[{u:02d}] {n['name']} "
            f"({n['type']}, "
            f"Cycle {sch['cycle']} [{sch['start_time']:.3f}-{sch['end_time']:.3f} ms], "
            f"Margin Left: {sch['time_left']:.3f} ms, "
            f"Prio {n['priority']})"
        )

        connector = "+-- " if is_last else "|-- "
        tree_lines.append(prefix + connector + node_str)

        visited.add(u)

        children = adj.get(u, [])

        for idx, child in enumerate(children):
            child_is_last = idx == len(children) - 1
            next_prefix = prefix + ("    " if is_last else "|   ")

            if child in visited:
                c_sch = schedule_by_id[child]
                tree_lines.append(
                    next_prefix
                    + ("\\-- " if child_is_last else "|-- ")
                    + f"[{child:02d}] {nodes[child]['name']} "
                    + f"[DAG Convergence Link; scheduled in Cycle {c_sch['cycle']} at {c_sch['start_time']:.3f}-{c_sch['end_time']:.3f} ms]"
                )
            else:
                build_tree_text(
                    child,
                    next_prefix,
                    child_is_last,
                    visited
                )

    for idx, root in enumerate(major_roots):
        if root in visited:
            continue
        is_last_root = idx == len(major_roots) - 1
        build_tree_text(root, prefix="|   ", is_last=is_last_root, visited=visited)

    standalone_roots = [
        nid for nid in nodes
        if in_degree[nid] == 0 and not adj.get(nid)
    ]

    tree_lines.append("\n" + "-" * 116)
    tree_lines.append(f"Independent Standalone Broadcast Messages ({len(standalone_roots)} messages):")
    tree_lines.append("-" * 116)

    for nid in standalone_roots:
        n = nodes[nid]
        sch = schedule_by_id[nid]
        tree_lines.append(
            f"  * [{nid:02d}] {n['name']} "
            f"({n['type']}, "
            f"Cycle {sch['cycle']} [{sch['start_time']:.3f}-{sch['end_time']:.3f} ms], "
            f"Margin Left: {sch['time_left']:.3f} ms, "
            f"Prio {n['priority']})"
        )

    tree_lines.append("\n" + "=" * 116)
    tree_lines.append("SCHEDULE SUMMARY ACROSS MINOR CYCLES (8.000 ms each):")
    tree_lines.append("-" * 116)
    for cs in cycle_summaries:
        tree_lines.append(
            f"  * Minor Cycle {cs['cycle']}: {cs['task_count']:2d} tasks scheduled | "
            f"Busy Time: {cs['used_time']:5.3f} ms | "
            f"Remaining Margin: {cs['slack']:5.3f} ms | "
            f"Bus Utilization: {cs['utilization']:5.1f}%"
        )
    total_exec = sum(cs['used_time'] for cs in cycle_summaries)
    tree_lines.append("-" * 116)
    tree_lines.append(
        f"Total Messages: {len(nodes)} | Total Bus Duration: {total_exec:.3f} ms | "
        f"Total Minor Cycles Required: {len(cycle_summaries)}"
    )
    tree_lines.append("=" * 116)

    content = "\n".join(tree_lines)
    with open("dag_tree_structure.txt", "w", encoding="utf-8") as f:
        f.write(content)

    print(
        f" -> Saved true topological multi-cycle tree ({len(cycle_summaries)} cycles) "
        "to 'dag_tree_structure.txt'"
    )
    return content


def main():
    print("=" * 80)
    print("GENERATING 1553 BUS TREE-STRUCTURED OUTPUTS (HIGH CLARITY & RESOLUTION)")
    print("=" * 80)
    nodes, adj, in_edges, in_degree = load_data()
    print(f"Loaded {len(nodes)} nodes and {sum(len(v) for v in adj.values())} dependency links.")

    # 1. Text Tree
    generate_text_tree(nodes, adj, in_edges, in_degree)

    # 2. Subsystem Isolated Trees Diagram (300 DPI)
    generate_subsystem_trees_image(nodes, adj)

    # 3. Unified Multi-Stage Master Tree Diagram (300 DPI)
    generate_unified_tree_image(nodes, adj, in_degree)

    print("\n" + "=" * 80)
    print("ALL TREE OUTPUTS GENERATED SUCCESSFULLY!")
    print("=" * 80)


if __name__ == "__main__":
    main()
