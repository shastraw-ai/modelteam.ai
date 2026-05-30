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

from .ai_utils import group_skills_for_report
from .html_report import _build_report_data

MD_FILE_NAME = "README.md"
IMAGES_DIR = "images"

# ── Palette ──────────────────────────────────────────────────────────────────

_LANG_COLORS = [
    "#6366f1", "#06b6d4", "#f59e0b", "#ef4444", "#10b981",
    "#8b5cf6", "#ec4899", "#64748b",
]
_HEATMAP_STOPS = ["#eef2ff", "#a5b4fc", "#6366f1", "#4338ca", "#312e81"]
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



# ── Chart: Languages (line chart over time) ────────────────────────────────

def _chart_languages(lang_qtr_added, quarters, path):
    if not lang_qtr_added:
        return False

    display_quarters = quarters[-8:]
    if not display_quarters:
        return False

    lang_totals = {lang: sum(qtrs.get(q, 0) for q in display_quarters)
                   for lang, qtrs in lang_qtr_added.items()}
    items = sorted(lang_totals.items(), key=lambda x: x[1], reverse=True)[:7]
    items = [i for i in items if i[1] > 0]
    if not items:
        return False

    qtr_labels = [f"{q[4:]}'{q[2:4]}" for q in display_quarters]
    x = np.arange(len(display_quarters))
    colors = _LANG_COLORS[:len(items)]

    fig, ax = plt.subplots(figsize=(8, 4))
    for i, (lang, _) in enumerate(items):
        values = [lang_qtr_added[lang].get(q, 0) for q in display_quarters]
        ax.plot(x, values, '-o', label=lang, color=colors[i],
                linewidth=2, markersize=4)

    ax.set_xlim(0, len(display_quarters) - 1)
    ax.set_xticks(x)
    ax.set_xticklabels(qtr_labels, fontsize=10, color=_MUTED)
    ax.tick_params(left=False, bottom=False)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(
        lambda v, _: f"{v / 1000:.0f}K" if v >= 1000 else f"{v:.0f}"
    ))
    ax.tick_params(axis="y", labelsize=9, labelcolor=_MUTED)

    for spine in ax.spines.values():
        spine.set_visible(False)

    ax.set_title("Languages", fontsize=15, fontweight="bold",
                 color=_TEXT, pad=14, loc="left")
    ax.text(1.0, 1.06, "lines of code per quarter", transform=ax.transAxes,
            ha="right", fontsize=9, color=_MUTED, style="italic")

    ax.legend(frameon=False, fontsize=10, labelcolor=_TEXT, loc="upper left",
              bbox_to_anchor=(1.02, 1.0))

    _save(fig, path)
    return True


# ── Chart: Activity (grouped small multiples) ─────────────────────────────

_AREA_COLORS = [
    "#6366f1", "#06b6d4", "#f59e0b", "#10b981", "#8b5cf6",
    "#ec4899", "#ef4444", "#0ea5e9", "#64748b", "#84cc16",
]

def _chart_activity(skill_qtr_lines, sorted_skills, quarters, path, groups=None):
    display_quarters = quarters[-8:]
    if not display_quarters:
        return False

    active_skills = set()
    for skill, _ in sorted_skills:
        if skill in skill_qtr_lines:
            total = sum(skill_qtr_lines[skill].get(q, 0) for q in display_quarters)
            if total > 0:
                active_skills.add(skill)

    if not active_skills:
        return False

    if not groups:
        ordered = [s for s, _ in sorted_skills if s in active_skills][:8]
        groups = [{"name": "Skills", "skills": ordered}]

    groups = [
        {"name": g["name"], "skills": [s for s in g["skills"] if s in active_skills]}
        for g in groups
    ]
    groups = [g for g in groups if g["skills"]]
    if not groups:
        return False

    n_groups = len(groups)
    n_qt = len(display_quarters)
    qtr_labels = [f"{q[4:]}'{q[2:4]}" for q in display_quarters]
    x = np.arange(n_qt)

    ncols = 2 if n_groups >= 4 else 1
    nrows = (n_groups + ncols - 1) // ncols
    fig_w = 5.5 * ncols
    fig_h = 3.0 * nrows + 0.8

    fig, axes = plt.subplots(nrows, ncols, figsize=(fig_w, fig_h),
                             squeeze=False)

    color_idx = 0
    for g_idx, group in enumerate(groups):
        row, col = g_idx // ncols, g_idx % ncols
        ax = axes[row][col]

        for skill in group["skills"]:
            values = [skill_qtr_lines.get(skill, {}).get(q, 0) for q in display_quarters]
            color = _AREA_COLORS[color_idx % len(_AREA_COLORS)]
            ax.plot(x, values, '-o', label=skill, color=color,
                    linewidth=2, markersize=4)
            color_idx += 1

        ax.set_title(group["name"], fontsize=12, fontweight="bold",
                     color=_TEXT, loc="left", pad=8)
        ax.set_xlim(0, n_qt - 1)
        ax.set_xticks(x)
        ax.set_xticklabels(qtr_labels, fontsize=8, color=_MUTED)
        ax.tick_params(left=False, bottom=False, labelsize=8, labelcolor=_MUTED)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(
            lambda v, _: f"{v / 1000:.0f}K" if v >= 1000 else f"{v:.0f}"
        ))

        for spine in ax.spines.values():
            spine.set_visible(False)

        ax.legend(fontsize=8, frameon=False, loc="upper left", labelcolor=_TEXT)

    for g_idx in range(n_groups, nrows * ncols):
        axes[g_idx // ncols][g_idx % ncols].set_visible(False)

    fig.suptitle("Skill Activity", fontsize=15, fontweight="bold",
                 color=_TEXT, x=0.03, ha="left", y=0.99)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
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

    # ── Languages line chart ──
    if has.get("langs"):
        md.append(f'<p align="center"><img src="{img}/languages.png" alt="Languages" /></p>\n')
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

def generate_md_report(profile_json, output_dir, model_data=None):
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

    groups = None
    if model_data and merged_skills:
        skill_names = [s for s, _ in sorted_skills]
        print("  Grouping skills for activity chart...", flush=True)
        groups = group_skills_for_report(model_data, skill_names)

    has = {
        "langs":    _chart_languages(lang_qtr_added, quarters, os.path.join(images_dir, "languages.png")),
        "activity": _chart_activity(skill_qtr_lines, sorted_skills, quarters,
                                    os.path.join(images_dir, "activity.png"), groups=groups),
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
