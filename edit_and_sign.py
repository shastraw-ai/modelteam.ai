import argparse
import configparser
import datetime
import json
import os
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QTextOption
from PyQt5.QtWidgets import (QWidget, QLabel, QRadioButton, QVBoxLayout, QHBoxLayout, QScrollArea,
                             QPushButton, QButtonGroup, QMessageBox, QFrame, QApplication, QTextBrowser, QTextEdit,
                             QCheckBox)

from modelteam_utils.ai_utils import check_ollama_ready, init_ollama, rank_skills_for_profile
from modelteam_utils.constants import USER, REPO, STATS, SKILLS, RELEVANT, NOT_RELEVANT, PROFILES, \
    NR_SKILLS, TIMESTAMP, MT_PROFILE_JSON, PDF_STATS_JSON
from modelteam_utils.html_report import generate_html_report
from modelteam_utils.md_report import generate_md_report
from modelteam_utils.qt_style import APP_STYLESHEET
from modelteam_utils.skill_filter import CACHE_FILENAME, filter_profile_skills
from modelteam_utils.utils import filter_skills, get_extension_to_language_map, load_skill_config, trunc_string
from modelteam_utils.viz_utils import generate_pdf_report

display_names = {}

def get_skill_display_name(skill):
    return display_names.get(skill, skill.title())


class App(QWidget):
    def __init__(self, email, repocsv, skills, choice_file, default_choices):
        super().__init__()

        self.email = email
        self.repocsv = repocsv
        self.skills = skills
        self.choice_file = choice_file
        self.default_choices = default_choices
        self.choices = {}
        self.init_ui()


    def enable_save_button(self):
        if self.t_n_c_checkbox.isChecked():
            self.save_button.setEnabled(True)
        else:
            self.save_button.setEnabled(False)

    def init_ui(self):
        self.setWindowTitle("modelteam · edit skills")
        self.setGeometry(100, 100, 880, 860)
        layout = QVBoxLayout()
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        # Header: logo + title
        pixmap = QPixmap(os.path.join("images", "modelteam_logo.png"))
        if not pixmap.isNull():
            pixmap = pixmap.scaledToHeight(48, Qt.SmoothTransformation)
        logo_label = QLabel()
        logo_label.setPixmap(pixmap)

        title_label = QLabel("Edit Skills")
        title_label.setStyleSheet(
            "font-size: 22px; font-weight: 600; color: #e6edf3; padding-left: 12px;"
        )
        subtitle_label = QLabel(f"{self.email} · {len(self.skills)} predicted skills")
        subtitle_label.setProperty("hint", True)
        subtitle_label.setStyleSheet("color: #8b949e; font-size: 13px; padding-left: 12px;")

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title_box.addWidget(title_label)
        title_box.addWidget(subtitle_label)

        header_layout = QHBoxLayout()
        header_layout.addWidget(logo_label)
        header_layout.addLayout(title_box, 1)
        layout.addLayout(header_layout)

        explanation = (
            f"""<html><body style="color:#e6edf3;">
<p style="font-size:12.5px; line-height:1.6; margin:0 0 8px 0;">
These are the skills our models predicted after analyzing your code contributions.
Pick which ones belong on your HTML profile.
</p>
<p style="font-size:12.5px; line-height:1.7; margin:0 0 8px 0;">
<span style="color:#a855f7;"><b>Relevant</b></span> — keep on profile.<br>
<span style="color:#06b6d4;"><b>Not Relevant</b></span> — remove from profile.
</p>
<p style="font-size:12.5px; margin:0;">
<span style="color:#8b949e;">Repos analyzed: {self.repocsv}</span>
</p>
</body></html>"""
        )
        repo_csv_label = QTextBrowser()
        repo_csv_label.setMaximumHeight(200)
        repo_csv_label.setHtml(explanation)
        repo_csv_label.setWordWrapMode(QTextOption.WordWrap)
        layout.addWidget(repo_csv_label)

        # Scroll area for skills
        self.add_choice_header(layout)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(2, 2, 2, 2)
        scroll_layout.setSpacing(3)
        scroll_area.setWidget(scroll_content)

        toggle = False
        for skill in self.skills:
            self.add_choice_widget(scroll_layout, skill, self.default_choices.get(skill, RELEVANT), toggle)
            toggle = not toggle
        scroll_layout.addStretch(1)
        layout.addWidget(scroll_area, 1)

        t_n_c_text = f"""<html><body style="color:#e6edf3;">
<p style="font-size:13px; font-weight:600; margin:0 0 6px 0;">Terms and conditions</p>
<ul style="font-size:12.5px; margin:0 0 0 16px; padding:0;">
<li>I am the owner of the id <span style="color:#06b6d4;">{self.email}</span> associated with this profile.</li>
<li>I own the code contributions associated with this id.</li>
<li>I will remove any confidential skills from the profile in this step.</li>
</ul>
</body></html>"""
        self.t_n_c_label = QTextBrowser()
        self.t_n_c_label.setMaximumHeight(120)
        self.t_n_c_label.setHtml(t_n_c_text)
        self.t_n_c_checkbox = QCheckBox("I accept the terms and conditions")
        self.t_n_c_checkbox.stateChanged.connect(self.enable_save_button)
        layout.addWidget(self.t_n_c_label)
        layout.addWidget(self.t_n_c_checkbox)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)
        button_layout.setContentsMargins(0, 8, 0, 0)
        button_layout.addStretch(1)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setProperty("secondary", True)
        self.cancel_button.setMinimumWidth(140)
        self.cancel_button.clicked.connect(self.close_window)
        button_layout.addWidget(self.cancel_button)
        self.save_button = QPushButton("Save Choices")
        self.save_button.setMinimumWidth(160)
        self.save_button.clicked.connect(self.save_choices)
        self.save_button.setEnabled(False)
        button_layout.addWidget(self.save_button)
        layout.addLayout(button_layout)

        self.setLayout(layout)
        self.show()

    def add_choice_header(self, layout):
        frame = QFrame()
        frame_layout = QHBoxLayout(frame)
        frame_layout.setContentsMargins(10, 4, 10, 4)
        label = QLabel("Skill")
        label.setProperty("heading", True)
        label.setStyleSheet(
            "font-size: 11px; font-weight: 600; letter-spacing: 0.12em; color: #6e7681;"
        )
        label.setFixedWidth(220)
        frame_layout.addWidget(label)
        for name in [RELEVANT, NOT_RELEVANT]:
            header_layout = QHBoxLayout()
            header_layout.setAlignment(Qt.AlignCenter)
            header_label = QLabel(name.upper())
            header_label.setStyleSheet(
                "font-size: 11px; font-weight: 600; letter-spacing: 0.12em; color: #6e7681;"
            )
            header_layout.addWidget(header_label)
            frame_layout.addLayout(header_layout)
        layout.addWidget(frame)

    def add_choice_widget(self, layout, skill, def_enabled, toggle_bg_color):
        frame = QFrame()
        if toggle_bg_color:
            frame.setProperty("alt", True)
        frame_layout = QHBoxLayout(frame)
        frame_layout.setContentsMargins(10, 4, 10, 4)

        label = QLabel(get_skill_display_name(skill))
        label.setFixedWidth(220)
        label.setWordWrap(True)
        frame_layout.addWidget(label)

        button_group = QButtonGroup()
        # Fall back to Relevant if def_enabled is an unknown / legacy value (e.g. "Top Secret").
        normalized_default = def_enabled if def_enabled in (RELEVANT, NOT_RELEVANT) else RELEVANT
        for name in [RELEVANT, NOT_RELEVANT]:
            radio_layout = QHBoxLayout()
            radio_layout.setAlignment(Qt.AlignCenter)
            radio = QRadioButton()
            radio.setAccessibleName(name)
            if name == normalized_default:
                radio.setChecked(True)
            button_group.addButton(radio)
            radio_layout.addWidget(radio)
            frame_layout.addLayout(radio_layout)
        self.choices[skill] = button_group
        layout.addWidget(frame)

    def save_choices(self):
        choices_dict = {item: group.checkedButton().accessibleName() for item, group in self.choices.items()}
        with open(self.choice_file, 'w') as f:
            json.dump(choices_dict, f)
        self.close()

    def close_window(self):
        # cleanup choice file
        if os.path.exists(self.choice_file):
            os.remove(self.choice_file)
        self.close()


def edit_profile(merged_profile, choices_file, cli_mode, model_data=None, cache_path=None):
    repos = []
    skills = {}
    email = merged_profile[USER]
    for profile in merged_profile[PROFILES]:
        repos.append(profile[REPO])
        for skill in profile[STATS][SKILLS].keys():
            skills[skill] = skills.get(skill, 0) + profile[STATS][SKILLS][skill]
    print(f"Found {len(skills)} predicted skills across {len(repos)} repos.", flush=True)

    pre_filter_drops = set()
    canonical_map = {}
    if model_data:
        lang_drops, llm_drops, canonical_map, surviving_scores = filter_profile_skills(
            skills, model_data, cache_path
        )
        pre_filter_drops = lang_drops | llm_drops
        skills = surviving_scores
        print(f"  Dropped {len(lang_drops)} language names "
              f"and {len(llm_drops)} non-marketable skills; "
              f"merged into {len(skills)} canonical skills.", flush=True)
    else:
        print("  Ollama not reachable — skipping LLM relevance filter.", flush=True)

    if not skills:
        print("No skills survived filtering. Nothing to edit.", flush=True)
        return 0, list(pre_filter_drops), canonical_map

    bad_skills = list(pre_filter_drops)
    skill_list = sorted(skills.keys(), key=lambda x: skills[x], reverse=True)
    if not os.path.exists(choices_file):
        if model_data:
            lang_map = get_extension_to_language_map()
            languages = set()
            for profile in merged_profile[PROFILES]:
                for ext in (profile.get(STATS, {}).get("langs", {}) or {}).keys():
                    languages.add(lang_map.get(ext, ext))
            print("  Ranking skills for profile relevance...", flush=True)
            relevant_set = rank_skills_for_profile(model_data, skills, languages)
            default_choices = {
                skill: RELEVANT if skill in relevant_set else NOT_RELEVANT
                for skill in skill_list
            }
            rel_count = sum(1 for v in default_choices.values() if v == RELEVANT)
            print(f"  LLM marked {rel_count}/{len(skill_list)} skills as relevant.", flush=True)
        else:
            default_choices = {skill: RELEVANT for skill in skill_list}
    else:
        with open(choices_file, 'r') as f:
            default_choices = json.load(f)
        # Back-compat: older choices files may contain "Top Secret" (now merged into Not Relevant).
        default_choices = {k: (NOT_RELEVANT if v == "Top Secret" else v) for k, v in default_choices.items()}
    if cli_mode:
        if display_t_and_c(merged_profile[USER]) != "y":
            print("Please accept the terms and conditions to proceed.")
            sys.exit(0)
        cli_choices(choices_file, email, repos, skill_list, default_choices)
        return 0, bad_skills, canonical_map
    else:
        app = QApplication(sys.argv)
        app.setStyleSheet(APP_STYLESHEET)
        ex = App(email, ",".join(repos), skill_list, choices_file, default_choices)
        return app.exec_(), bad_skills, canonical_map


def cli_choices(choices_file, email, repos, skills, choices_dict):
    RESET = '\033[0m'
    BOLD = '\033[1m'

    print(f"Email: {BOLD}{email}{RESET}")
    print(f"Repos: {', '.join(repos)}")
    print(f"Total Skills: {BOLD}{len(skills)}{RESET}")
    print("These are the skills our models predicted after analyzing your code contributions.")
    print("Pick which ones belong on your HTML profile.")
    print('\n')

    display_skills(BOLD, RESET, skills, choices_dict)

    print("Options:")
    print(f"{BOLD}Relevant{RESET}: Keep the skill on your profile.")
    print(f"{BOLD}Not Relevant{RESET}: Remove the skill from your profile.\n")
    while True:
        relevant_input = input(
            f"\nEnter the numbers of skills to change to {BOLD}Relevant{RESET} (separated by commas, or press Enter to skip):\n")
        relevant_numbers = set(int(n.strip()) for n in relevant_input.split(',') if n.strip().isdigit())

        not_relevant_input = input(
            f"\nEnter the numbers of skills to change to {BOLD}Not Relevant{RESET} (separated by commas, or press Enter to skip):\n")
        not_relevant_numbers = set(int(n.strip()) for n in not_relevant_input.split(',') if n.strip().isdigit())

        for num in relevant_numbers:
            if 1 <= num <= len(skills):
                choices_dict[skills[num - 1]] = RELEVANT
            else:
                print(f"Invalid skill number: {num}")

        for num in not_relevant_numbers:
            if 1 <= num <= len(skills):
                choices_dict[skills[num - 1]] = NOT_RELEVANT
            else:
                print(f"Invalid skill number: {num}")

        print("\nUpdated Status:")
        display_skills(BOLD, RESET, skills, choices_dict)
        confirmation = input("\nAre you satisfied with these selections? (yes/no):\n").strip().lower()
        if confirmation in ['yes', 'y']:
            break
        print("\nLet's try again.")

    with open(choices_file, 'w') as f:
        json.dump(choices_dict, f)


def display_skills(BOLD, RESET, skills, choices):
    print("Skills:")
    number_of_columns = 3
    total_skills = len(skills)
    number_of_rows = (total_skills + number_of_columns - 1) // number_of_columns  # Ceiling division
    # Arrange skills into columns
    columns = [[] for _ in range(number_of_columns)]
    for idx, skill in enumerate(skills):
        column_index = idx % number_of_columns
        skill_number = idx + 1
        ch = choices.get(skill, RELEVANT)
        ch = "NR" if ch == NOT_RELEVANT else "R"
        display_name = f"{BOLD}{skill_number}{RESET}. {trunc_string(get_skill_display_name(skill), 40)} ({ch})"
        columns[column_index].append(display_name)
    # Pad columns to have equal length
    max_col_length = max(len(col) for col in columns)
    for col in columns:
        while len(col) < max_col_length:
            col.append('')
    # Print the columns side by side
    for row in range(max_col_length):
        for col in columns:
            print(f"{col[row]:<45}", end='')
        print()


def _apply_canonical_map(stats, canonical_map):
    """Rename skill keys per canonical_map across stats[skills] and the per-month c2s blocks."""
    new_skills = {}
    for s, v in stats.get(SKILLS, {}).items():
        canon = canonical_map.get(s, s)
        new_skills[canon] = new_skills.get(canon, 0) + v
    stats[SKILLS] = new_skills

    for lang_block in (stats.get("langs", {}) or {}).values():
        time_series = (lang_block or {}).get("yyyymm", {}) or {}
        for month_data in time_series.values():
            if not isinstance(month_data, dict):
                continue
            for key, val in list(month_data.items()):
                if not key.startswith("c2s::") or not isinstance(val, dict):
                    continue
                new_c2s = {}
                for s, entry in val.items():
                    canon = canonical_map.get(s, s)
                    if not isinstance(entry, (list, tuple)) or len(entry) < 2:
                        continue
                    if canon in new_c2s:
                        new_c2s[canon] = [new_c2s[canon][0] + entry[0],
                                          new_c2s[canon][1] + entry[1]]
                    else:
                        new_c2s[canon] = [entry[0], entry[1]]
                month_data[key] = new_c2s


def apply_choices(merged_profile, choices_file, edited_file, bad_skills, canonical_map=None):
    utc_now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    with open(edited_file, "w") as f2:
        with open(choices_file, 'r') as f3:
            choices_dict = json.load(f3)
        not_relevant = {s for s, c in choices_dict.items() if c == NOT_RELEVANT}
        skills_to_remove = set(bad_skills)
        for profile in merged_profile[PROFILES]:
            filter_skills(profile[STATS], 0, skills_to_remove)
            if canonical_map:
                _apply_canonical_map(profile[STATS], canonical_map)
            # Choices use canonical names; remove any selected as Not Relevant.
            if not_relevant:
                filter_skills(profile[STATS], 0, not_relevant)
            profile[NR_SKILLS] = []
            profile[TIMESTAMP] = utc_now
        merged_profile[TIMESTAMP] = utc_now
        f2.write(json.dumps(merged_profile, indent=2))


def display_t_and_c(email_id):
    t_and_c = ["\nI certify that,",
               f"\t1. I am the owner of the id {email_id} associated with this profile",
               "\t2. I own the code contributions associated with this id",
               "\t3. I will remove any confidential skills from the profile in this step"]
    res = input("\n".join(t_and_c) + "\nEnter \"Y\" to proceed: \n")
    return res.lower()


def print_message(pdf_file, html_file, md_file=None):
    print("📄 PDF Report Generated!")
    print(f"📂 Saved at: {pdf_file}")
    print()
    print("🌐 HTML Profile Generated!")
    print("✅ Safe to host publicly — contains no repo names, file paths, or commit messages.")
    print(f"📂 Saved at: {html_file}")
    print(f"   Open in browser: file://{os.path.abspath(html_file)}")
    if md_file:
        print()
        print("📝 GitHub Profile README Generated!")
        print(f"📂 Saved at: {md_file}")
        print("   Copy to your GitHub profile repo (username/username) as README.md")


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("--profile_path", type=str, required=True)
    arg_parser.add_argument("--cli_mode", action="store_true", default=False)
    arg_parser.add_argument("--config", type=str, required=False, default="config.ini")

    args = arg_parser.parse_args()
    profile_json = os.path.join(args.profile_path, MT_PROFILE_JSON)
    pdf_stats_json = os.path.join(args.profile_path, "tmp-stats", PDF_STATS_JSON)
    file_name_without_extension = profile_json.replace(".json", "")
    choices_file = f"{file_name_without_extension}_choices.json"
    pdf_path = os.path.join(args.profile_path, "pdf")
    config_file = args.config
    config = configparser.ConfigParser()
    config.read(config_file)
    skill_list_path = config["modelteam.ai"].get("skill_list", "")
    if skill_list_path and os.path.exists(skill_list_path):
        display_names = load_skill_config(skill_list_path, only_keys=False)
    else:
        display_names = {}
    with open(profile_json, "r") as f:
        merged_profile = json.load(f)
    model_data = init_ollama(config) if check_ollama_ready(config) else None
    cache_path = os.path.join(args.profile_path, CACHE_FILENAME)
    result, bad_skills, canonical_map = edit_profile(
        merged_profile, choices_file, args.cli_mode,
        model_data=model_data, cache_path=cache_path,
    )
    if result == 0 and os.path.exists(choices_file):
        print("Changes were saved. Applying changes...")
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        edited_file = os.path.join(args.profile_path, f"mt_stats_{today}.json")
        print(f"Edited file: {edited_file}")
        apply_choices(merged_profile, choices_file, edited_file, bad_skills, canonical_map)
        pdf_file = generate_pdf_report(edited_file, pdf_stats_json, pdf_path)
        html_file = generate_html_report(edited_file, args.profile_path)
        md_file = generate_md_report(edited_file, args.profile_path, model_data=model_data)
        print_message(pdf_file, html_file, md_file)
    else:
        print("Changes were NOT SAVED. Exiting... Please run the script again.")
        sys.exit(0)
