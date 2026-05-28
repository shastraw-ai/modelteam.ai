"""Generate a GitHub profile folder (README.md + image charts) from a filtered
mt_stats.json.

Output structure::

    {output_dir}/
        README.md
        images/
            skills.png        — horizontal bar chart of top skills
            languages.png     — donut chart with total in center
            activity.png      — rounded-cell heatmap of skill × quarter
"""

import argparse
import datetime
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.patches import FancyBboxPatch
import numpy as np

try:
    from wordcloud import WordCloud
except ImportError:
    WordCloud = None

from .html_report import _build_report_data

MD_FILE_NAME = "README.md"
IMAGES_DIR = "images"

# ── Palette ──────────────────────────────────────────────────────────────────

_LANG_COLORS = [
    "#6366f1", "#06b6d4", "#f59e0b", "#ef4444", "#10b981",
    "#8b5cf6", "#ec4899", "#64748b",
]
_HEATMAP_STOPS = ["#eef2ff", "#a5b4fc", "#6366f1", "#4338ca", "#312e81"]
_BAR_GRADIENT = ("#a5b4fc", "#4f46e5")  # light indigo → deep indigo

_BG = "#ffffff"
_TEXT = "#1e293b"
_MUTED = "#64748b"
_EMPTY_CELL = "#f1f5f9"


def _setup():
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica Neue", "Arial", "DejaVu Sans"],
        "font.size": 11,
        "figure.facecolor": _BG,
        "axes.facecolor": _BG,
        "text.color": _TEXT,
    })


def _save(fig, path):
    fig.savefig(path, dpi=180, bbox_inches="tight", facecolor=_BG, pad_inches=0.25)
    plt.close(fig)


# ── Chart: Top Skills (horizontal bar) ──────────────────────────────────────

def _chart_skills(skill_scores, path, limit=12):
    if not skill_scores:
        return False

    items = sorted(skill_scores.items(), key=lambda x: x[1], reverse=True)[:limit]
    items.reverse()
    names = [i[0] for i in items]
    scores = [i[1] for i in items]
    n = len(names)
    max_val = max(scores) if scores else 1

    cmap = mcolors.LinearSegmentedColormap.from_list("bar", [_BAR_GRADIENT[0], _BAR_GRADIENT[1]])
    colors = [cmap(0.25 + 0.75 * i / max(n - 1, 1)) for i in range(n)]

    fig, ax = plt.subplots(figsize=(8, max(2.5, n * 0.42 + 0.8)))
    bars = ax.barh(range(n), scores, height=0.62, color=colors, edgecolor="none", zorder=3)

    ax.set_yticks(range(n))
    ax.set_yticklabels(names, fontsize=11, color=_TEXT)
    ax.set_xlim(0, max_val * 1.18)
    ax.tick_params(left=False, bottom=False)
    ax.xaxis.set_visible(False)

    for spine in ax.spines.values():
        spine.set_visible(False)

    for i, v in enumerate(scores):
        ax.text(v + max_val * 0.02, i, f"{v:,.0f}", va="center", fontsize=9, color=_MUTED)

    ax.set_title("Top Skills", fontsize=15, fontweight="bold", color=_TEXT, pad=14, loc="left")
    ax.text(1.0, 1.06, "lines of code", transform=ax.transAxes,
            ha="right", fontsize=9, color=_MUTED, style="italic")

    _save(fig, path)
    return True


# ── Chart: Languages (donut) ────────────────────────────────────────────────

def _chart_languages(lang_totals, path):
    if not lang_totals:
        return False

    items = sorted(lang_totals.items(), key=lambda x: x[1], reverse=True)[:7]
    labels = [i[0] for i in items]
    values = [i[1] for i in items]
    total = sum(values)
    colors = _LANG_COLORS[: len(labels)]

    fig, ax = plt.subplots(figsize=(5.5, 5.5))
    wedges, texts, autotexts = ax.pie(
        values,
        labels=None,
        autopct=lambda p: f"{p:.0f}%" if p >= 5 else "",
        colors=colors,
        pctdistance=0.78,
        startangle=90,
        wedgeprops=dict(width=0.34, edgecolor=_BG, linewidth=3),
    )
    for t in autotexts:
        t.set_fontsize(10)
        t.set_fontweight("bold")
        t.set_color("white")

    # center text: total lines
    if total >= 10_000:
        center_num = f"{total / 1000:.1f}K"
    elif total >= 1_000_000:
        center_num = f"{total / 1_000_000:.1f}M"
    else:
        center_num = f"{total:,}"
    ax.text(0, 0.06, center_num, ha="center", va="center",
            fontsize=22, fontweight="bold", color=_TEXT)
    ax.text(0, -0.14, "lines", ha="center", va="center",
            fontsize=11, color=_MUTED)

    # legend on the right
    ax.legend(
        wedges, labels,
        loc="center left", bbox_to_anchor=(1.02, 0.5),
        frameon=False, fontsize=11, labelcolor=_TEXT,
    )

    _save(fig, path)
    return True


# ── Chart: Activity (rounded-cell heatmap) ──────────────────────────────────

def _chart_activity(skill_qtr_lines, sorted_skills, quarters, path):
    display_quarters = quarters[-8:]

    timeline_skills = []
    for skill, _ in sorted_skills:
        if skill in skill_qtr_lines:
            if any(skill_qtr_lines[skill].get(q, 0) > 0 for q in display_quarters):
                timeline_skills.append(skill)
        if len(timeline_skills) >= 12:
            break

    if not timeline_skills or not display_quarters:
        return False

    n_sk = len(timeline_skills)
    n_qt = len(display_quarters)

    raw = np.zeros((n_sk, n_qt))
    for i, skill in enumerate(timeline_skills):
        for j, q in enumerate(display_quarters):
            raw[i, j] = skill_qtr_lines.get(skill, {}).get(q, 0)

    normed = np.zeros_like(raw)
    for i in range(n_sk):
        mx = raw[i].max()
        if mx > 0:
            normed[i] = raw[i] / mx

    cmap = mcolors.LinearSegmentedColormap.from_list("hm", _HEATMAP_STOPS)

    cell_w, cell_h = 0.82, 0.82
    rounding = 0.12
    fig, ax = plt.subplots(figsize=(max(5.5, n_qt * 0.9 + 3), max(3, n_sk * 0.54 + 1.2)))

    for i in range(n_sk):
        for j in range(n_qt):
            v = normed[i, j]
            fc = cmap(v) if raw[i, j] > 0 else _EMPTY_CELL
            rect = FancyBboxPatch(
                (j - cell_w / 2, i - cell_h / 2), cell_w, cell_h,
                boxstyle=f"round,pad=0,rounding_size={rounding}",
                facecolor=fc, edgecolor="none", zorder=2,
            )
            ax.add_patch(rect)

    ax.set_xlim(-0.5, n_qt - 0.5)
    ax.set_ylim(n_sk - 0.5, -0.5)

    qtr_labels = []
    for q in display_quarters:
        yr = q[2:4]
        qp = q[4:]
        qtr_labels.append(f"{qp}\n'{yr}")
    ax.set_xticks(range(n_qt))
    ax.set_xticklabels(qtr_labels, fontsize=9, color=_MUTED, ha="center")
    ax.set_yticks(range(n_sk))
    ax.set_yticklabels(timeline_skills, fontsize=10, color=_TEXT)

    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)

    ax.set_title("Activity Timeline", fontsize=15, fontweight="bold",
                 color=_TEXT, pad=16, loc="left")

    # legend: 5 small rounded squares
    legend_y = -1.0
    legend_labels = ["", "Low", "", "Med", "", "High"]
    n_legend = 5
    x_start = n_qt - n_legend - 0.2
    for k in range(n_legend):
        c = cmap(k / (n_legend - 1))
        r = FancyBboxPatch(
            (x_start + k * 0.7, n_sk + 0.15), 0.5, 0.4,
            boxstyle=f"round,pad=0,rounding_size=0.08",
            facecolor=c, edgecolor="none", zorder=2,
            clip_on=False,
        )
        ax.add_patch(r)

    ax.text(x_start - 0.1, n_sk + 0.35, "Less", fontsize=8, color=_MUTED,
            ha="right", va="center", clip_on=False)
    ax.text(x_start + n_legend * 0.7 + 0.1, n_sk + 0.35, "More", fontsize=8, color=_MUTED,
            ha="left", va="center", clip_on=False)

    fig.subplots_adjust(bottom=0.12)
    _save(fig, path)
    return True


# ── Chart: Word cloud (optional) ────────────────────────────────────────────

def _chart_wordcloud(skill_scores, path):
    if not skill_scores or WordCloud is None:
        return False
    top = dict(sorted(skill_scores.items(), key=lambda x: x[1], reverse=True)[:30])

    def color_func(word, **kwargs):
        idx = list(top.keys()).index(word) if word in top else 0
        palette = ["#6366f1", "#8b5cf6", "#06b6d4", "#0ea5e9", "#4f46e5",
                    "#7c3aed", "#2563eb", "#0891b2", "#6d28d9", "#3b82f6"]
        return palette[idx % len(palette)]

    wc = WordCloud(
        width=1000, height=420,
        background_color=_BG,
        color_func=color_func,
        prefer_horizontal=0.80,
        max_words=30,
        min_font_size=13,
        margin=10,
        relative_scaling=0.55,
    ).generate_from_frequencies(top)

    fig, ax = plt.subplots(figsize=(10, 4.2))
    ax.imshow(wc, interpolation="bilinear")
    ax.axis("off")
    _save(fig, path)
    return True


# ── Markdown ─────────────────────────────────────────────────────────────────

def _fmt(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 10_000:
        return f"{n / 1_000:.1f}K"
    return f"{n:,}"


def _render_markdown(report_data, has):
    user = report_data.get("user", "Developer")
    display_name = user.split("@")[0] if "@" in user else user
    git_ids = report_data.get("git_ids", [])

    merged_skills = report_data.get("merged_skills", {})
    lang_qtr_added = report_data.get("lang_qtr_added", {})
    total_repos = report_data.get("total_repos", 0)
    total_lines = report_data.get("total_lines_added", 0)
    active_span = report_data.get("active_span", "")
    timestamp = report_data.get("timestamp", 0)

    sorted_skills = sorted(merged_skills.items(), key=lambda x: x[1], reverse=True)
    lang_totals = {l: sum(q.values()) for l, q in lang_qtr_added.items()}
    sorted_langs = sorted(lang_totals.items(), key=lambda x: x[1], reverse=True)

    top_langs = [l[0] for l in sorted_langs[:2]]
    tagline = " & ".join(top_langs) + " Developer" if top_langs else "Software Developer"

    date_str = (
        datetime.datetime.fromtimestamp(timestamp).strftime("%B %d, %Y")
        if timestamp
        else datetime.datetime.now().strftime("%B %d, %Y")
    )
    repo_word = "repository" if total_repos == 1 else "repositories"
    img = IMAGES_DIR
    md = []

    # ── Header ──
    md.append('<div align="center">\n')
    md.append(f"# {display_name}\n")
    md.append(f"#### {tagline}\n")
    md.append(
        f"**{total_repos}** {repo_word} analyzed &nbsp;·&nbsp; "
        f"**{_fmt(total_lines)}** lines authored &nbsp;·&nbsp; "
        f"**{len(sorted_skills)}** skills identified"
    )
    if active_span and active_span != "no recent activity":
        md.append(f"  \n*Active: {active_span}*")
    if git_ids:
        md.append(f"  \n*Git IDs: {', '.join(git_ids)}*")
    md.append("\n\n</div>\n")

    # ── Word cloud hero ──
    if has.get("cloud"):
        md.append(f'<p align="center"><img src="{img}/wordcloud.png" alt="Skills Cloud" /></p>\n')

    md.append("---\n")

    # ── Skills ──
    if sorted_skills:
        md.append("### &nbsp;&nbsp;Skills\n")
        md.append("&nbsp;&nbsp;" + " &nbsp;".join(f"`{s[0]}`" for s in sorted_skills[:25]))
        if len(sorted_skills) > 25:
            md.append(f"&nbsp; *+{len(sorted_skills) - 25} more*")
        md.append("\n")
        md.append("---\n")

    # ── Side-by-side: Languages donut + Skills bar ──
    has_left = has.get("langs")
    has_right = has.get("skills")
    if has_left and has_right:
        md.append("<table><tr>")
        md.append(f'<td align="center" width="42%"><img src="{img}/languages.png" alt="Languages" width="100%"/></td>')
        md.append(f'<td align="center" width="58%"><img src="{img}/skills.png" alt="Top Skills" width="100%"/></td>')
        md.append("</tr></table>\n")
        md.append("---\n")
    elif has_left:
        md.append(f'<p align="center"><img src="{img}/languages.png" alt="Languages" width="420"/></p>\n')
        md.append("---\n")
    elif has_right:
        md.append(f'<p align="center"><img src="{img}/skills.png" alt="Top Skills" width="600"/></p>\n')
        md.append("---\n")

    # ── Activity heatmap (full width) ──
    if has.get("activity"):
        md.append(f'<p align="center"><img src="{img}/activity.png" alt="Activity Timeline" /></p>\n')
        md.append("---\n")

    # ── Footer ──
    md.append(
        '<div align="center">\n<sub>'
        'Generated with <a href="https://modelteam.ai">modelteam.ai</a>'
        f" · Updated {date_str}"
        "</sub>\n</div>\n"
    )

    return "\n".join(md)


# ── Public API ───────────────────────────────────────────────────────────────

def generate_md_report(profile_json, output_dir):
    """Generate a GitHub-profile-ready folder with README.md and charts.

    Returns the absolute path to the written README.md.
    """
    with open(profile_json, "r", encoding="utf-8") as f:
        merged_profile = json.load(f)
    report_data = _build_report_data(merged_profile)

    images_dir = os.path.join(output_dir, IMAGES_DIR)
    os.makedirs(images_dir, exist_ok=True)

    _setup()

    merged_skills = report_data.get("merged_skills", {})
    lang_qtr_added = report_data.get("lang_qtr_added", {})
    skill_qtr_lines = report_data.get("skill_qtr_lines", {})
    quarters = report_data.get("quarters", [])

    sorted_skills = sorted(merged_skills.items(), key=lambda x: x[1], reverse=True)
    lang_totals = {lang: sum(qtrs.values()) for lang, qtrs in lang_qtr_added.items()}

    has = {
        "skills":   _chart_skills(merged_skills, os.path.join(images_dir, "skills.png")),
        "langs":    _chart_languages(lang_totals, os.path.join(images_dir, "languages.png")),
        "activity": _chart_activity(skill_qtr_lines, sorted_skills, quarters,
                                    os.path.join(images_dir, "activity.png")),
        "cloud":    _chart_wordcloud(merged_skills, os.path.join(images_dir, "wordcloud.png")),
    }

    md = _render_markdown(report_data, has)
    out_path = os.path.join(output_dir, MD_FILE_NAME)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)
    return out_path


def _main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--profile_json", required=True,
                   help="Path to mt_stats.json (filtered profile)")
    p.add_argument("--output_dir", required=True,
                   help="Directory to write README.md and images/ into")
    args = p.parse_args()
    out = generate_md_report(args.profile_json, args.output_dir)
    print(f"Generated: {out}")
    print(f"Images:    {os.path.join(args.output_dir, IMAGES_DIR)}/")


if __name__ == "__main__":
    _main()
