"""Generate a self-contained, publicly-hostable HTML profile from a filtered
``mt_stats.json``.

The output contains only aggregate metrics, skill names, and language-level
activity. Repo names, file paths, and commit messages are never written to
the rendered HTML.
"""

import argparse
import base64
import datetime
import json
import math
import os
from collections import defaultdict

from .constants import (
    ADDED, DELETED, LANGS, NR_SKILLS, PHC, PROFILES,
    SIGNIFICANT_CONTRIBUTION, SKILLS, STATS,
    TIMESTAMP, TIME_SERIES, USER,
)
from .ai_utils import group_skills_by_keyword
from .utils import get_extension_to_language_map, yyyy_mm_to_quarter

_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
_LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "images", "modelteam_logo.png")

HTML_FILE_NAME = "modelteam_profile.html"

_PLACEHOLDER_DATA = '"__MT_DATA_JSON__"'
_PLACEHOLDER_LOGO = "__MT_LOGO_DATA_URI__"
_PLACEHOLDER_CSS = "/*__INLINE_CSS__*/"
_PLACEHOLDER_CHART = "/*__INLINE_CHARTJS__*/"
_PLACEHOLDER_APP = "/*__INLINE_APP_JS__*/"

_QUARTER_WINDOW = 8


def _rolling_quarters(now=None):
    """Return the last ``_QUARTER_WINDOW`` quarter labels in chronological order."""
    now = now or datetime.datetime.now()
    seen = []
    cursor = now
    while len(seen) < _QUARTER_WINDOW:
        label = yyyy_mm_to_quarter(int(cursor.strftime("%Y%m")))
        if not seen or seen[-1] != label:
            seen.append(label)
        # step back ~one month
        year, month = cursor.year, cursor.month - 1
        if month == 0:
            month = 12
            year -= 1
        cursor = cursor.replace(year=year, month=month, day=1)
    return list(reversed(seen))


def _build_report_data(merged_profile):
    lang_map = get_extension_to_language_map()
    quarters = _rolling_quarters()
    quarter_set = set(quarters)

    merged_skills = defaultdict(float)
    lang_qtr_added = defaultdict(lambda: defaultdict(int))
    skill_qtr_lines = defaultdict(lambda: defaultdict(int))
    total_chunks = 0
    skill_chunk_counts = defaultdict(int)

    profiles = merged_profile.get(PROFILES, []) or []
    for profile in profiles:
        nr = set(profile.get(NR_SKILLS, []) or [])
        stats = profile.get(STATS, {}) or {}
        for skill, score in (stats.get(SKILLS, {}) or {}).items():
            if skill in nr:
                continue
            merged_skills[skill] += score
        for ext, lang_block in (stats.get(LANGS, {}) or {}).items():
            disp = lang_map.get(ext, ext)
            time_series = (lang_block or {}).get(TIME_SERIES) or {}
            for yyyy_mm, cell in time_series.items():
                if not isinstance(cell, dict):
                    continue
                try:
                    qtr = yyyy_mm_to_quarter(int(yyyy_mm))
                except (TypeError, ValueError):
                    continue
                if qtr not in quarter_set:
                    continue
                lang_qtr_added[disp][qtr] += int(cell.get(ADDED, 0) or 0)
                total_chunks += int(cell.get(SIGNIFICANT_CONTRIBUTION, 0) or 0)
                for key, val in cell.items():
                    if not key.startswith("c2s::") or not isinstance(val, dict):
                        continue
                    for skill, entry in val.items():
                        if not isinstance(entry, (list, tuple)) or len(entry) < 2:
                            continue
                        try:
                            skill_chunk_counts[skill] += int(entry[0] or 0)
                        except (TypeError, ValueError):
                            pass
                        if skill in nr:
                            continue
                        try:
                            skill_qtr_lines[skill][qtr] += int(entry[1] or 0)
                        except (TypeError, ValueError):
                            continue

    # IDF weighting: downweight skills that appear in many chunks
    if total_chunks > 1:
        for skill in merged_skills:
            chunks = skill_chunk_counts.get(skill, 0)
            if chunks > 0:
                merged_skills[skill] *= math.log(total_chunks / chunks)
        for skill in skill_qtr_lines:
            chunks = skill_chunk_counts.get(skill, 0)
            if chunks > 0:
                idf = math.log(total_chunks / chunks)
                for qtr in skill_qtr_lines[skill]:
                    skill_qtr_lines[skill][qtr] = int(
                        skill_qtr_lines[skill][qtr] * idf
                    )

    active_quarters = sorted({
        q for buckets in lang_qtr_added.values() for q in buckets
    })
    if active_quarters:
        active_span = (active_quarters[0] if len(active_quarters) == 1
                       else active_quarters[0] + " → " + active_quarters[-1])
    else:
        active_span = "no recent activity"

    total_lines = sum(
        v for buckets in lang_qtr_added.values() for v in buckets.values()
    )

    return {
        "user": merged_profile.get(USER, ""),
        "git_ids": merged_profile.get("git_ids", []),
        "timestamp": merged_profile.get(TIMESTAMP, 0),
        "hc": merged_profile.get(PHC, ""),
        "merged_skills": {k: round(v, 4) for k, v in merged_skills.items()},
        "quarters": quarters,
        "lang_qtr_added": {
            lang: dict(buckets) for lang, buckets in lang_qtr_added.items()
        },
        "skill_qtr_lines": {
            skill: dict(buckets) for skill, buckets in skill_qtr_lines.items()
        },
        "total_repos": len(profiles),
        "total_lines_added": total_lines,
        "active_span": active_span,
    }


def _read_asset(name):
    with open(os.path.join(_ASSETS_DIR, name), "r", encoding="utf-8") as f:
        return f.read()


def _logo_data_uri():
    with open(_LOGO_PATH, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("ascii")
    return "data:image/png;base64," + encoded


def _render_html(report_data):
    template = _read_asset("template.html")
    css = _read_asset("styles.css")
    chartjs = _read_asset("chart.min.js")
    appjs = _read_asset("app.js")
    logo = _logo_data_uri()

    data_json = json.dumps(report_data, ensure_ascii=False).replace("</", "<\\/")

    return (template
            .replace(_PLACEHOLDER_CSS, css)
            .replace(_PLACEHOLDER_CHART, chartjs)
            .replace(_PLACEHOLDER_APP, appjs)
            .replace(_PLACEHOLDER_LOGO, logo)
            .replace(_PLACEHOLDER_DATA, data_json))


def generate_html_report(profile_json, output_dir, skill_groups=None):
    """Read the filtered ``mt_stats.json`` and write ``modelteam_profile.html``.

    ``skill_groups`` (a list of ``{"name", "skills"}`` dicts) drives the grouped
    skill charts; when omitted the page falls back to a single default group.

    Returns the absolute path to the written HTML file.
    """
    with open(profile_json, "r", encoding="utf-8") as f:
        merged_profile = json.load(f)
    report_data = _build_report_data(merged_profile)
    if not skill_groups:
        merged_skills = report_data.get("merged_skills", {})
        if merged_skills:
            skill_names = [s for s, _ in sorted(merged_skills.items(),
                                                key=lambda x: x[1], reverse=True)]
            skill_groups = group_skills_by_keyword(skill_names)
    report_data["skill_groups"] = skill_groups or []
    html = _render_html(report_data)
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, HTML_FILE_NAME)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path


def _main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--profile_json", required=True,
                   help="Path to mt_stats.json (filtered profile)")
    p.add_argument("--output_dir", required=True,
                   help="Directory to write modelteam_profile.html into")
    args = p.parse_args()
    out = generate_html_report(args.profile_json, args.output_dir)
    print(out)


if __name__ == "__main__":
    _main()
