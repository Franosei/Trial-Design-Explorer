"""
Chart service: decision-informed matplotlib visualisations for PDF reports and slides.

All functions return a BytesIO object containing a PNG image so they can be
embedded directly into ReportLab PDFs or python-pptx slides without writing
temporary files to disk.
"""

from __future__ import annotations

import io
import math
from typing import Optional

import matplotlib
matplotlib.use("Agg")  # non-interactive backend — must be set before pyplot import
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as mticker
import numpy as np

# ── Brand colours matching the report ─────────────────────────────────────────
C_COMPLETED = "#1F5B7A"   # dark teal  – successful precedent
C_DISRUPTED = "#C0563D"   # muted red  – risk / disrupted precedent
C_PROTOCOL  = "#F5A623"   # amber      – the current draft
C_NEUTRAL   = "#8AA0AF"   # slate grey – reference / neutral
C_HEADER    = "#15324A"   # navy       – axes / titles
C_SOFT      = "#EDF3F7"   # light blue-grey – backgrounds


def _save(fig) -> io.BytesIO:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf


# ── 1. Radar / spider chart — design alignment across domains ─────────────────

def generate_radar_chart(metrics: dict, width_in: float = 5.5, height_in: float = 5.0) -> io.BytesIO:
    """
    Radar chart comparing protocol alignment with completed vs disrupted precedent
    across all design domains.  Each axis is a 0–100% alignment score.
    """
    rows = metrics.get("alignment_by_domain", [])
    if not rows:
        return _empty_chart("No alignment data available", width_in, height_in)

    labels = [r["Domain"] for r in rows]
    completed_vals = [float(r.get("Completed Match (%)") or 0) for r in rows]
    disrupted_vals = [float(r.get("Disrupted Match (%)") or 0) for r in rows]

    n = len(labels)
    angles = [2 * math.pi * i / n for i in range(n)] + [0]
    completed_vals_c = completed_vals + [completed_vals[0]]
    disrupted_vals_c = disrupted_vals + [disrupted_vals[0]]

    fig, ax = plt.subplots(figsize=(width_in, height_in),
                           subplot_kw={"polar": True}, facecolor="white")
    ax.set_facecolor(C_SOFT)

    ax.plot(angles, completed_vals_c, color=C_COMPLETED, linewidth=2, label="Completed precedent")
    ax.fill(angles, completed_vals_c, color=C_COMPLETED, alpha=0.15)
    ax.plot(angles, disrupted_vals_c, color=C_DISRUPTED, linewidth=2,
            linestyle="--", label="Disrupted precedent")
    ax.fill(angles, disrupted_vals_c, color=C_DISRUPTED, alpha=0.10)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, size=8, color=C_HEADER)
    ax.set_yticks([20, 40, 60, 80, 100])
    ax.set_yticklabels(["20%", "40%", "60%", "80%", "100%"], size=6, color=C_NEUTRAL)
    ax.set_ylim(0, 100)
    ax.set_title("Design Domain Alignment: Completed vs Disrupted Precedent",
                 size=10, color=C_HEADER, pad=14, fontweight="bold")
    ax.legend(loc="lower right", bbox_to_anchor=(1.35, -0.05), fontsize=8,
              framealpha=0.9, edgecolor=C_NEUTRAL)
    ax.grid(color=C_NEUTRAL, linestyle="--", linewidth=0.5, alpha=0.5)
    fig.tight_layout()
    return _save(fig)


# ── 2. Enrollment benchmark — box-and-whisker with protocol target line ────────

def generate_enrollment_benchmark_chart(metrics: dict,
                                         width_in: float = 6.0,
                                         height_in: float = 4.0) -> io.BytesIO:
    """
    Box-and-whisker plot showing completed and disrupted enrollment distributions,
    with the protocol's planned enrollment as a vertical reference line.
    """
    c_med = metrics.get("completed_enrollment_median")
    c_p25 = metrics.get("completed_enrollment_p25")
    c_p75 = metrics.get("completed_enrollment_p75")
    d_med = metrics.get("disrupted_enrollment_median")
    d_p25 = metrics.get("disrupted_enrollment_p25")
    d_p75 = metrics.get("disrupted_enrollment_p75")
    target = metrics.get("enrollment_target")

    if c_med is None and d_med is None:
        return _empty_chart("Enrollment benchmark data not available", width_in, height_in)

    fig, ax = plt.subplots(figsize=(width_in, height_in), facecolor="white")
    ax.set_facecolor(C_SOFT)

    def draw_box(y: float, median: float, p25: float, p75: float,
                 color: str, label: str) -> None:
        # IQR box
        ax.barh(y, p75 - p25, left=p25, height=0.4, color=color, alpha=0.6,
                label=label)
        # median line
        ax.plot([median, median], [y - 0.2, y + 0.2], color=color,
                linewidth=2.5, zorder=3)
        ax.text(median, y + 0.28, f"{median:,.0f}", ha="center", va="bottom",
                fontsize=8, color=color, fontweight="bold")

    y_pos = []
    y_labels = []
    y = 0
    if c_med is not None and c_p25 is not None and c_p75 is not None:
        draw_box(y, c_med, c_p25, c_p75, C_COMPLETED, "Completed precedent IQR")
        y_pos.append(y)
        y_labels.append("Completed")
        y += 1
    if d_med is not None and d_p25 is not None and d_p75 is not None:
        draw_box(y, d_med, d_p25, d_p75, C_DISRUPTED, "Disrupted precedent IQR")
        y_pos.append(y)
        y_labels.append("Disrupted")
        y += 1

    if target is not None:
        ax.axvline(target, color=C_PROTOCOL, linewidth=2, linestyle="--",
                   label=f"Protocol target ({target:,})", zorder=4)

    ax.set_yticks(y_pos)
    ax.set_yticklabels(y_labels, fontsize=9, color=C_HEADER)
    ax.set_xlabel("Enrollment (participants)", fontsize=9, color=C_HEADER)
    ax.set_title("Enrollment Benchmark: Protocol Target vs Precedent Cohorts",
                 fontsize=10, color=C_HEADER, fontweight="bold", pad=10)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    ax.tick_params(axis="x", labelsize=8)
    ax.legend(fontsize=8, loc="lower right", framealpha=0.9, edgecolor=C_NEUTRAL)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return _save(fig)


# ── 3. Duration comparison — stacked reference ranges ─────────────────────────

def generate_duration_comparison_chart(metrics: dict,
                                        width_in: float = 6.0,
                                        height_in: float = 3.5) -> io.BytesIO:
    """
    Horizontal range bar showing completed vs disrupted median trial duration
    with the protocol's planned duration as a marker.
    """
    c_med = metrics.get("completed_duration_median_months")
    c_p25 = metrics.get("completed_duration_p25_months")
    c_p75 = metrics.get("completed_duration_p75_months")
    d_med = metrics.get("disrupted_duration_median_months")
    d_p25 = metrics.get("disrupted_duration_p25_months")
    d_p75 = metrics.get("disrupted_duration_p75_months")
    proto = metrics.get("protocol_duration_months")

    if c_med is None and d_med is None:
        return _empty_chart("Duration data not available", width_in, height_in)

    fig, ax = plt.subplots(figsize=(width_in, height_in), facecolor="white")
    ax.set_facecolor(C_SOFT)

    def draw_range(y, median, p25, p75, color, label):
        if p25 is not None and p75 is not None:
            ax.barh(y, p75 - p25, left=p25, height=0.35, color=color, alpha=0.55, label=label)
        ax.plot([median, median], [y - 0.2, y + 0.2], color=color, linewidth=2.5, zorder=3)
        ax.text(median, y + 0.26, f"{median:.0f} mo", ha="center", va="bottom",
                fontsize=8, color=color, fontweight="bold")

    y_pos, y_labels = [], []
    y = 0
    if c_med is not None:
        draw_range(y, c_med, c_p25, c_p75, C_COMPLETED, "Completed precedent IQR")
        y_pos.append(y); y_labels.append("Completed"); y += 1
    if d_med is not None:
        draw_range(y, d_med, d_p25, d_p75, C_DISRUPTED, "Disrupted precedent IQR")
        y_pos.append(y); y_labels.append("Disrupted"); y += 1

    if proto is not None:
        ax.axvline(proto, color=C_PROTOCOL, linewidth=2, linestyle="--",
                   label=f"Protocol plan ({proto:.0f} mo)", zorder=4)

    ax.set_yticks(y_pos)
    ax.set_yticklabels(y_labels, fontsize=9, color=C_HEADER)
    ax.set_xlabel("Duration (months)", fontsize=9, color=C_HEADER)
    ax.set_title("Planned Duration vs Precedent Cohort Ranges",
                 fontsize=10, color=C_HEADER, fontweight="bold", pad=10)
    ax.tick_params(axis="x", labelsize=8)
    ax.legend(fontsize=8, loc="lower right", framealpha=0.9, edgecolor=C_NEUTRAL)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return _save(fig)


# ── 4. Risk signal heatmap — alignment score colour table ─────────────────────

def generate_alignment_heatmap(metrics: dict,
                                width_in: float = 7.0,
                                height_in: float = 3.5) -> io.BytesIO:
    """
    Colour-coded heatmap table of alignment scores per design domain.
    Green = strong completed alignment; red = closer to disrupted precedent.
    """
    rows = metrics.get("alignment_by_domain", [])
    if not rows:
        return _empty_chart("No alignment data available", width_in, height_in)

    domains = [r["Domain"] for r in rows]
    completed = [float(r.get("Completed Match (%)") or 0) for r in rows]
    disrupted = [float(r.get("Disrupted Match (%)") or 0) for r in rows]
    gap = [c - d for c, d in zip(completed, disrupted)]

    fig, ax = plt.subplots(figsize=(width_in, height_in), facecolor="white")
    ax.set_facecolor("white")
    ax.axis("off")

    col_labels = ["Domain", "Completed %", "Disrupted %", "Gap (C–D)", "Signal"]
    table_data = []
    cell_colors = []

    for i, domain in enumerate(domains):
        g = gap[i]
        if g >= 15:
            signal = "Closer to Completed"
            sig_color = "#C8E6C9"
        elif g <= -15:
            signal = "Closer to Disrupted"
            sig_color = "#FFCDD2"
        else:
            signal = "Mixed"
            sig_color = "#FFF9C4"

        c_color = _pct_to_color(completed[i], reverse=False)
        d_color = _pct_to_color(disrupted[i], reverse=True)

        table_data.append([
            domain,
            f"{completed[i]:.1f}%",
            f"{disrupted[i]:.1f}%",
            f"{g:+.1f}%",
            signal,
        ])
        cell_colors.append(["#EDF3F7", c_color, d_color, _gap_color(g), sig_color])

    header_colors = [["#15324A"] * len(col_labels)]
    all_data = [col_labels] + table_data
    all_colors = header_colors + cell_colors

    tbl = ax.table(
        cellText=all_data,
        cellColours=all_colors,
        cellLoc="center",
        loc="center",
        bbox=[0, 0, 1, 1],
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(8)
    for (row, col), cell in tbl.get_celld().items():
        cell.set_edgecolor("#D5DCE3")
        cell.set_linewidth(0.5)
        if row == 0:
            cell.set_text_props(color="white", fontweight="bold")
        cell.set_height(0.12)

    ax.set_title("Design Alignment Risk Signal Summary",
                 fontsize=10, color=C_HEADER, fontweight="bold", pad=12)
    fig.tight_layout()
    return _save(fig)


def _pct_to_color(value: float, reverse: bool = False) -> str:
    """Map 0–100 percentage to a green/red gradient."""
    norm = max(0, min(100, value)) / 100
    if reverse:
        norm = 1 - norm
    r = int(255 * (1 - norm * 0.6))
    g = int(200 + norm * 55)
    b = int(200 - norm * 100)
    return f"#{r:02X}{g:02X}{b:02X}"


def _gap_color(gap: float) -> str:
    if gap >= 15:
        return "#C8E6C9"
    if gap <= -15:
        return "#FFCDD2"
    return "#FFF9C4"


# ── 5. Endpoint distribution — grouped bar completed vs disrupted ──────────────

def generate_endpoint_distribution_chart(metrics: dict,
                                          width_in: float = 6.5,
                                          height_in: float = 4.0) -> io.BytesIO:
    """
    Grouped bar chart showing endpoint category distribution in completed vs
    disrupted trials.  Protocol's endpoint focus is highlighted.
    """
    c_dist = metrics.get("completed_endpoint_distribution", {})
    d_dist = metrics.get("disrupted_endpoint_distribution", {})
    if not c_dist and not d_dist:
        return _empty_chart("Endpoint distribution data not available", width_in, height_in)

    all_cats = sorted(set(c_dist) | set(d_dist))
    c_vals = [c_dist.get(cat, 0) for cat in all_cats]
    d_vals = [d_dist.get(cat, 0) for cat in all_cats]

    x = np.arange(len(all_cats))
    w = 0.35

    fig, ax = plt.subplots(figsize=(width_in, height_in), facecolor="white")
    ax.set_facecolor(C_SOFT)

    bars_c = ax.bar(x - w / 2, c_vals, w, color=C_COMPLETED, alpha=0.8, label="Completed precedent")
    bars_d = ax.bar(x + w / 2, d_vals, w, color=C_DISRUPTED, alpha=0.8, label="Disrupted precedent")

    proto_focus = metrics.get("protocol_endpoint_focus", "")
    if proto_focus and proto_focus in all_cats:
        idx = all_cats.index(proto_focus)
        ax.axvspan(idx - 0.5, idx + 0.5, color=C_PROTOCOL, alpha=0.12,
                   label=f"Protocol focus: {proto_focus}")

    ax.set_xticks(x)
    ax.set_xticklabels(all_cats, rotation=20, ha="right", fontsize=8, color=C_HEADER)
    ax.set_ylabel("Share of comparator cohort (%)", fontsize=9, color=C_HEADER)
    ax.set_title("Endpoint Category Distribution: Completed vs Disrupted Precedent",
                 fontsize=10, color=C_HEADER, fontweight="bold", pad=10)
    ax.tick_params(axis="y", labelsize=8)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.0f}%"))
    ax.legend(fontsize=8, framealpha=0.9, edgecolor=C_NEUTRAL)
    ax.spines[["top", "right"]].set_visible(False)

    for bar in list(bars_c) + list(bars_d):
        h = bar.get_height()
        if h > 1:
            ax.text(bar.get_x() + bar.get_width() / 2, h + 0.5,
                    f"{h:.0f}%", ha="center", va="bottom", fontsize=6.5, color=C_HEADER)
    fig.tight_layout()
    return _save(fig)


# ── 6. Precedent posture gauge — single-metric visual ─────────────────────────

def generate_posture_gauge(metrics: dict,
                            width_in: float = 5.0,
                            height_in: float = 3.0) -> io.BytesIO:
    """
    Half-donut gauge showing the net precedent gap (completed fit – disrupted fit).
    Positive = closer to completed (green); negative = closer to disrupted (red).
    """
    c_fit = metrics.get("completed_design_fit_pct")
    d_fit = metrics.get("disrupted_design_fit_pct")

    if c_fit is None or d_fit is None:
        return _empty_chart("Posture data not available", width_in, height_in)

    gap = c_fit - d_fit
    posture = metrics.get("precedent_posture", "Mixed")

    # Clamp to [-40, 40] for display
    display_gap = max(-40, min(40, gap))
    norm = (display_gap + 40) / 80  # 0 = full disrupted, 1 = full completed

    fig, ax = plt.subplots(figsize=(width_in, height_in), facecolor="white")
    ax.set_aspect("equal")
    ax.axis("off")

    # Background arc (grey)
    theta = np.linspace(np.pi, 0, 200)
    ax.plot(np.cos(theta), np.sin(theta), lw=18, color="#E0E0E0", solid_capstyle="round")

    # Filled arc
    fill_end = np.pi - norm * np.pi
    theta_fill = np.linspace(np.pi, fill_end, 200)
    fill_color = C_COMPLETED if gap >= 0 else C_DISRUPTED
    ax.plot(np.cos(theta_fill), np.sin(theta_fill), lw=18, color=fill_color,
            solid_capstyle="round", alpha=0.85)

    ax.text(0, -0.05, f"{gap:+.1f}%", ha="center", va="center",
            fontsize=22, color=fill_color, fontweight="bold")
    ax.text(0, -0.38, "Net Precedent Gap (Completed – Disrupted)",
            ha="center", va="center", fontsize=7.5, color=C_NEUTRAL)
    ax.text(0, 0.42, posture, ha="center", va="center",
            fontsize=9, color=C_HEADER, fontweight="bold")

    ax.text(-1.05, -0.15, "Disrupted", ha="center", fontsize=7.5, color=C_DISRUPTED)
    ax.text(1.05, -0.15, "Completed", ha="center", fontsize=7.5, color=C_COMPLETED)

    ax.set_xlim(-1.4, 1.4)
    ax.set_ylim(-0.6, 1.1)
    ax.set_title("Overall Precedent Posture", fontsize=10, color=C_HEADER,
                 fontweight="bold", pad=4)
    fig.tight_layout()
    return _save(fig)


# ── 7. Sponsor type donut ─────────────────────────────────────────────────────

def generate_sponsor_donut(metrics: dict,
                            width_in: float = 4.0,
                            height_in: float = 3.5) -> io.BytesIO:
    """Donut chart showing industry vs academic sponsor split in the cohort."""
    dist = metrics.get("sponsor_type_distribution", {})
    if not dist:
        return _empty_chart("Sponsor data not available", width_in, height_in)

    labels = list(dist.keys())
    values = [float(v) for v in dist.values()]
    colours = [C_COMPLETED if l == "Industry" else C_NEUTRAL for l in labels]

    fig, ax = plt.subplots(figsize=(width_in, height_in), facecolor="white")
    wedges, texts, autotexts = ax.pie(
        values, labels=labels, colors=colours, autopct="%1.0f%%",
        startangle=90, pctdistance=0.75,
        wedgeprops={"width": 0.5, "edgecolor": "white", "linewidth": 2},
    )
    for text in texts:
        text.set_fontsize(9)
        text.set_color(C_HEADER)
    for autotext in autotexts:
        autotext.set_fontsize(8)
        autotext.set_color("white")
        autotext.set_fontweight("bold")
    ax.set_title("Sponsor Type Distribution", fontsize=10, color=C_HEADER,
                 fontweight="bold", pad=10)
    fig.tight_layout()
    return _save(fig)


# ── Helper ────────────────────────────────────────────────────────────────────

def _empty_chart(message: str, width_in: float, height_in: float) -> io.BytesIO:
    fig, ax = plt.subplots(figsize=(width_in, height_in), facecolor="white")
    ax.axis("off")
    ax.text(0.5, 0.5, message, ha="center", va="center",
            fontsize=10, color=C_NEUTRAL, transform=ax.transAxes)
    return _save(fig)
