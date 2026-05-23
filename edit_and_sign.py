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

from modelteam_utils.constants import USER, REPO, STATS, SKILLS, RELEVANT, NOT_RELEVANT, TOP_SECRET, PROFILES, \
    NR_SKILLS, TIMESTAMP, MT_PROFILE_JSON, PDF_STATS_JSON
from modelteam_utils.crypto_utils import compress_file, generate_hc
from modelteam_utils.html_report import generate_html_report
from modelteam_utils.qt_style import APP_STYLESHEET
from modelteam_utils.utils import filter_skills, sha256_hash, load_skill_config
from modelteam_utils.utils import trunc_string
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
On the server side they will be scored further by another model.
</p>
<p style="font-size:12.5px; line-height:1.7; margin:0 0 8px 0;">
<span style="color:#a855f7;"><b>Relevant</b></span> — keep on profile.<br>
<span style="color:#06b6d4;"><b>Not Relevant</b></span> — drop from server profile (feedback to the model).<br>
<span style="color:#ef4444;"><b>Top Secret</b></span> — never even send to the server.
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
<li>I will remove any confidential skills from the profile in this step before uploading.</li>
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
        for name in [RELEVANT, NOT_RELEVANT, TOP_SECRET]:
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
        for name in [RELEVANT, NOT_RELEVANT, TOP_SECRET]:
            radio_layout = QHBoxLayout()
            radio_layout.setAlignment(Qt.AlignCenter)
            radio = QRadioButton()
            radio.setAccessibleName(name)
            if name == def_enabled:
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


def edit_profile(merged_profile, choices_file, cli_mode):
    repos = []
    skills = {}
    email = merged_profile[USER]
    for profile in merged_profile[PROFILES]:
        repos.append(profile[REPO])
        for skill in profile[STATS][SKILLS].keys():
            skills[skill] = skills.get(skill, 0) + profile[STATS][SKILLS][skill]
    avg_count = sum(skills.values()) / len(skills)
    threshold = 0.2 * avg_count
    bad_skills = [skill for skill in skills if skills[skill] < threshold]
    # print("Average count: ", avg_count, flush=True)
    # print("Bad skills: ", bad_skills, flush=True)
    for s in bad_skills:
        del skills[s]
    skill_list = sorted(skills.keys(), key=lambda x: skills[x], reverse=True)
    if not os.path.exists(choices_file):
        # mark bottom 30% as not relevant and others as relevant
        default_choices = {skill: RELEVANT if skills[skill] > 0.4 * avg_count else NOT_RELEVANT for skill in skill_list}
    else:
        with open(choices_file, 'r') as f:
            default_choices = json.load(f)
    if cli_mode:
        if display_t_and_c(merged_profile[USER]) != "y":
            print("Please accept the terms and conditions to proceed.")
            sys.exit(0)
        cli_choices(choices_file, email, repos, skill_list, default_choices)
        return 0, bad_skills
    else:
        app = QApplication(sys.argv)
        app.setStyleSheet(APP_STYLESHEET)
        ex = App(email, ",".join(repos), skill_list, choices_file, default_choices)
        return app.exec_(), bad_skills


def cli_choices(choices_file, email, repos, skills, choices_dict):
    # ANSI escape codes for text formatting
    RESET = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    RED = '\033[31m'

    print(f"Email: {BOLD}{email}{RESET}")
    print(f"Repos: {', '.join(repos)}")
    print(f"Total Skills: {BOLD}{len(skills)}{RESET}")
    print("These are the skills that our models predicted after analyzing your code contributions.")
    print("These skills will further be scored by another model on the server side.")
    print('\n')

    # Display the list of skills in 3 columns
    display_skills(BOLD, RESET, skills, choices_dict)

    # Initialize choices_dict with all skills marked as RELEVANT
    # choices_dict = {skill: RELEVANT for skill in skills}

    # Loop to get user confirmation
    print("Please select the skills you wish to remove or mark differently.\n")
    print("Options:")
    print(f"{BOLD}Relevant{RESET}: Keep the skill in your profile.")
    print(f"{BOLD}Not Relevant{RESET}: Mark as not relevant and {BOLD}remove{RESET} from profile on the server.")
    print(f"{BOLD}Top Secret{RESET}: Remove from profile and {BOLD}DON'T{RESET} even send it to the server.\n")
    while True:
        # Ask the user to enter the numbers of skills to mark as 'Relevant'
        relevant_input = input(
            f"\nEnter the numbers of skills to change to {BOLD}Relevant{RESET} (separated by commas):\n")
        if relevant_input.strip():
            relevant_numbers = set(int(num.strip()) for num in relevant_input.split(',') if num.strip().isdigit())
        else:
            relevant_numbers = set()
        # Ask the user to enter the numbers of skills to mark as 'Not Relevant'
        not_relevant_input = input(
            f"\nEnter the numbers of skills to change to {BOLD}Not Relevant{RESET} (separated by commas, or press Enter to skip):\n")
        if not_relevant_input.strip():
            not_relevant_numbers = set(
                int(num.strip()) for num in not_relevant_input.split(',') if num.strip().isdigit())
        else:
            not_relevant_numbers = set()

        # Ask the user to enter the numbers of skills to mark as 'Top Secret'
        top_secret_input = input(
            f"\nEnter the numbers of skills to mark as {BOLD}Top Secret{RESET} (separated by commas, or press Enter to skip):\n")
        if top_secret_input.strip():
            top_secret_numbers = set(int(num.strip()) for num in top_secret_input.split(',') if num.strip().isdigit())
        else:
            top_secret_numbers = set()

        for num in relevant_numbers:
            if 1 <= num <= len(skills):
                skill = skills[num - 1]
                choices_dict[skill] = RELEVANT
            else:
                print(f"Invalid skill number: {num}")

        for num in not_relevant_numbers:
            if 1 <= num <= len(skills):
                skill = skills[num - 1]
                choices_dict[skill] = NOT_RELEVANT
            else:
                print(f"Invalid skill number: {num}")

        for num in top_secret_numbers:
            if 1 <= num <= len(skills):
                skill = skills[num - 1]
                choices_dict[skill] = TOP_SECRET
            else:
                print(f"Invalid skill number: {num}")

        # Confirmation of skills marked for removal
        print("\nUpdated Status:")
        display_skills(BOLD, RESET, skills, choices_dict)
        # Ask user to confirm or re-enter selections
        confirmation = input("\nAre you satisfied with these selections? (yes/no):\n").strip().lower()
        if confirmation in ['yes', 'y']:
            break
        else:
            print("\nLet's try again.")

    # Save the choices to the file
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
        if ch == NOT_RELEVANT:
            ch = "NR"
        elif ch == TOP_SECRET:
            ch = "TS"
        else:
            ch = "R"
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


def apply_choices(merged_profile, choices_file, edited_file, bad_skills):
    utc_now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    with open(edited_file, "w") as f2:
        with open(choices_file, 'r') as f3:
            choices_dict = json.load(f3)
        non_relevant_skills = [skill for skill in choices_dict if choices_dict[skill] == NOT_RELEVANT]
        top_secret_set = {skill for skill in choices_dict if choices_dict[skill] == TOP_SECRET}
        skills_to_remove = top_secret_set.union(bad_skills)
        for profile in merged_profile[PROFILES]:
            stats = profile[STATS]
            filter_skills(stats, 0, skills_to_remove)
            profile[NR_SKILLS] = non_relevant_skills
            profile[TIMESTAMP] = utc_now
        merged_profile[TIMESTAMP] = utc_now
        f2.write(json.dumps(merged_profile, indent=2))


def display_t_and_c(email_id):
    t_and_c = ["\nI certify that,",
               f"\t1. I am the owner of the id {email_id} associated with this profile",
               "\t2. I own the code contributions associated with this id",
               "\t3. I will remove any confidential skills from the profile in this step before uploading"]
    res = input("\n".join(t_and_c) + "\nEnter \"Y\" to proceed: \n")
    return res.lower()


def print_file_tree(currentDir, fullPath):
    relative_path = os.path.relpath(fullPath, currentDir)
    parts = relative_path.split(os.sep)
    print(currentDir)
    for i, part in enumerate(parts):
        prefix = "   ├── " if i < len(parts) - 1 else "   └── "
        print("   " * i + prefix + part)


def print_message(pdf_file, html_file, final_output_file):
    star_line = "*" * 80
    blue_text = "\033[94m"
    reset_text = "\033[0m"

    print("📄 PDF Report Generated!")
    print("⚠️ This is for your personal use only and is NOT needed by modelteam.ai.")
    print(f"📂 Saved at: {pdf_file}")
    print()
    print("🌐 HTML Profile Generated!")
    print("✅ Safe to host publicly — contains no repo names, file paths, or commit messages.")
    print(f"📂 Saved at: {html_file}")
    print(f"   Open in browser: file://{os.path.abspath(html_file)}")
    print()
    print(star_line)
    print(f"📂 \033[1mFinal Output:\033[0m{final_output_file}")
    print_file_tree(os.getcwd(), final_output_file)
    print("🔹 Please note:")
    print(
        "The final profile will be generated on the server-side using another ML model that processes the JSON file you upload.")
    print(f"🚀 \033[1;91m\033[1mDon't forget to upload the file:\033[0m")
    print(f"🔗 {blue_text}https://app.modelteam.ai/experience{reset_text}")
    print(star_line)


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("--profile_path", type=str, required=True)
    arg_parser.add_argument("--user_key", type=str, required=True)
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
    skill_list = config["modelteam.ai"]["skill_list"]
    display_names = load_skill_config(skill_list, only_keys=False)
    with open(profile_json, "r") as f:
        merged_profile = json.load(f)
    result, bad_skills = edit_profile(merged_profile, choices_file, args.cli_mode)
    if result == 0 and os.path.exists(choices_file):
        print("Changes were saved. Applying changes...")
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        edited_file = os.path.join(args.profile_path, f"mt_stats_{today}.json")
        print(f"Edited file: {edited_file}")
        apply_choices(merged_profile, choices_file, edited_file, bad_skills)
        hc = sha256_hash(generate_hc(edited_file) + args.user_key)
        final_output_file = os.path.join(args.profile_path, f"mt_stats_{today}_{hc}.json.gz")
        compress_file(edited_file, final_output_file)
        pdf_file = generate_pdf_report(edited_file, pdf_stats_json, pdf_path)
        html_file = generate_html_report(edited_file, args.profile_path)
        print_message(pdf_file, html_file, final_output_file)
    else:
        print("Changes were NOT SAVED. Exiting... Please run the script again.")
        sys.exit(0)
