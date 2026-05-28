import os
import subprocess
import sys
from datetime import datetime, timedelta

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QApplication, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog, \
    QListWidget, QLabel, QComboBox, QTextEdit, QListWidgetItem, QSpinBox, QDialog, QCheckBox

from edit_skills import run_edit_and_sign
from modelteam_utils.qt_style import APP_STYLESHEET
from setup_utils import run_model_team_git_parser, get_profile_path_file_name


class GitHelperTool(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('modelteam · profile builder')
        self.setGeometry(100, 100, 880, 860)

        # Initialize variables
        self.git_repos = []
        self.selected_repos = []
        self.current_user = self.get_git_user_email()
        self.input_path = os.path.expanduser("~")
        self.num_years = 5

        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(28, 24, 28, 24)
        self.layout.setSpacing(14)
        self.setLayout(self.layout)

        # Logo header
        pixmap = QPixmap(os.path.join("images", "modelteam_logo.png"))
        if not pixmap.isNull():
            pixmap = pixmap.scaledToHeight(48, Qt.SmoothTransformation)
        logo_label = QLabel()
        logo_label.setPixmap(pixmap)

        title_label = QLabel("Profile Builder")
        title_label.setProperty("heading", True)
        title_label.setStyleSheet(
            "font-size: 22px; font-weight: 600; color: #e6edf3; padding-left: 12px;"
        )
        subtitle_label = QLabel("Extract skills from your local Git history")
        subtitle_label.setProperty("hint", True)
        subtitle_label.setStyleSheet("color: #8b949e; font-size: 13px; padding-left: 12px;")

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title_box.addWidget(title_label)
        title_box.addWidget(subtitle_label)

        header_layout = QHBoxLayout()
        header_layout.addWidget(logo_label)
        header_layout.addLayout(title_box, 1)
        self.layout.addLayout(header_layout)

        # Step 1 — Directory
        self.path_label = QLabel(
            "Step 1 — Parent directory to scan for Git repos\n"
            "Pick the folder that contains your repos (use home to scan everything)."
        )
        self.path_label.setProperty("heading", True)
        self.path_input = QLabel(self)
        self.path_input.setProperty("mono", True)

        self.browse_button = QPushButton('Browse', self)
        self.browse_button.clicked.connect(self.browse_directory)
        self.browse_button.setMaximumWidth(140)

        # Step 2 — Repos
        self.repo_list_label = QLabel("Step 2 — Pick the repos to include")
        self.repo_list_label.setProperty("heading", True)
        self.repo_list = QListWidget(self)
        self.repo_list.setMinimumHeight(180)

        self.scan_authors_button = QPushButton('Scan Git Email IDs', self)
        self.scan_authors_button.clicked.connect(self.scan_for_authors)
        self.scan_authors_button.setMaximumWidth(220)
        self.scan_authors_button.setEnabled(False)

        # Step 3 — Author / years
        self.author_label = QLabel("Step 3 — Select your author email")
        self.author_label.setProperty("heading", True)
        self.author_combo = QComboBox(self)
        self.author_note = QLabel(
            "If you have multiple git email IDs, run this tool once per email to build a complete profile."
        )
        self.author_note.setProperty("hint", True)
        self.author_note.setWordWrap(True)

        self.num_years_label = QLabel("History window (years)")
        self.num_years_input = QSpinBox(self)
        self.num_years_input.setRange(1, 100)
        self.num_years_input.setValue(self.num_years)
        self.num_years_input.setMaximumWidth(120)
        self.num_years_input.valueChanged.connect(lambda x: setattr(self, 'num_years', x))

        # Step 4 — Run
        self.run_button = QPushButton('Generate User Git Stats', self)
        self.run_button.setMaximumWidth(260)
        self.run_button.clicked.connect(self.run_git_command)
        self.run_button.setEnabled(False)

        self.force_rerun = QCheckBox("Cleanup and force re-run  (needs CLI confirmation)", self)
        self.force_rerun.setChecked(False)

        self.run_label = QLabel("Continues in the terminal once started.")
        self.run_label.setProperty("hint", True)

        self.output_terminal = QTextEdit(self)
        self.output_terminal.setReadOnly(True)
        self.output_terminal.setMinimumHeight(160)

        # Layout assembly
        self.layout.addSpacing(6)
        self.layout.addWidget(self.path_label)
        path_row = QHBoxLayout()
        path_row.addWidget(self.browse_button)
        path_row.addWidget(self.path_input, 1)
        self.layout.addLayout(path_row)

        self.layout.addSpacing(4)
        self.layout.addWidget(self.repo_list_label)
        self.layout.addWidget(self.repo_list)
        self.layout.addWidget(self.scan_authors_button)

        self.layout.addSpacing(4)
        self.layout.addWidget(self.author_label)
        author_row = QHBoxLayout()
        author_row.addWidget(self.author_combo, 1)
        self.layout.addLayout(author_row)
        self.layout.addWidget(self.author_note)

        years_row = QHBoxLayout()
        years_row.addWidget(self.num_years_label)
        years_row.addWidget(self.num_years_input)
        years_row.addStretch(1)
        self.layout.addLayout(years_row)

        self.layout.addSpacing(4)
        run_row = QHBoxLayout()
        run_row.addWidget(self.run_button)
        run_row.addWidget(self.run_label, 1)
        run_row.addWidget(self.force_rerun)
        self.layout.addLayout(run_row)

        self.layout.addWidget(self.output_terminal)

    def browse_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Directory", directory=self.input_path)
        if directory:
            self.path_input.setText(f"({directory})")
            self.input_path = directory
            self.find_git_repos()

    def find_git_repos(self):
        """Find all Git repositories in the provided path."""
        self.git_repos = []
        self.selected_repos = []
        self.author_combo.clear()
        self.repo_list.clear()

        for root, dirs, files in os.walk(self.input_path):
            print("Scanning for Git repositories in " + root)
            if '.git' in dirs:
                repo_path = root
                self.git_repos.append(repo_path)
                item = QListWidgetItem(repo_path)  # Create a list item for the repo
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)  # Make it checkable
                item.setCheckState(Qt.Checked)  # Default to checked
                self.repo_list.addItem(item)  # Add item to the list
                dirs[:] = []  # Don't recurse into subdirectories
            else:
                dirs[:] = [d for d in dirs if not d.startswith('.')]

        if not self.git_repos:
            self.output_terminal.append("No Git repositories found.")
        else:
            self.scan_authors_button.setEnabled(True)

    def scan_for_authors(self):
        selected_repos = self.get_selected_repos()

        if not selected_repos:
            self.output_terminal.append("Please select at least one repository.")
            return

        authors = self.find_authors()

        self.author_combo.clear()
        self.author_combo.addItems(authors[:20])  # Display only the first 10 authors
        self.run_button.setEnabled(True)

    def get_selected_repos(self):
        """Scan the selected repositories and populate the authors combo box."""
        selected_repos = []
        for i in range(self.repo_list.count()):
            item = self.repo_list.item(i)
            if item.checkState() == Qt.Checked:
                selected_repos.append(item.text())
        self.selected_repos = selected_repos
        return selected_repos

    def find_authors(self):
        """Find authors from the selected repositories."""
        authors = {}
        since_date = (datetime.now() - timedelta(days=365 * self.num_years)).strftime('%Y-%m-%d')

        for repo in self.selected_repos:
            try:
                # Change directory to the repository and get the authors' emails
                result = subprocess.check_output(
                    ['git', 'log', '--since', since_date, '--pretty=format:%ae', '--abbrev-commit'], cwd=repo)
                author_list = result.decode("utf-8").splitlines()
                deduped_authors = list(set(author_list))
                for author in deduped_authors:
                    if not author:
                        continue
                    author = author.strip().lower()
                    if author in authors:
                        authors[author] += 1
                    else:
                        authors[author] = 1
            except subprocess.CalledProcessError:
                continue
        authors.pop(self.current_user, None)  # Remove the current user from the list
        sorted_authors = sorted(authors.keys(), key=lambda x: (-authors[x], x.lower()))
        if self.current_user:
            sorted_authors.insert(0, self.current_user)
        return sorted_authors

    def get_git_user_email(self):
        """Get the current Git user email."""
        try:
            result = subprocess.check_output(["git", "config", "--global", "user.email"], stderr=subprocess.STDOUT)
            return result.decode("utf-8").strip().lower()
        except subprocess.CalledProcessError:
            return ""

    def run_git_command(self):
        """Run the Git command using the selected repos and author."""
        selected_author = self.author_combo.currentText()
        selected_repos = self.get_selected_repos()

        if not selected_repos or not selected_author:
            self.output_terminal.append("Please select at least one repository and an author.")
            return
        self.accept()

    def get_selected_data(self):
        selected_author = self.author_combo.currentText()
        return self.selected_repos, selected_author, self.num_years, self.force_rerun.isChecked()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLESHEET)
    window = GitHelperTool()
    if window.exec_() == QDialog.Accepted:
        selected_repos, selected_author, num_years, force_rerun = window.get_selected_data()
        tmp_repo_file_name = os.path.join(os.getcwd(), "repo_list_autogen.txt")
        with open(tmp_repo_file_name, "w") as f:
            for repo in selected_repos:
                f.write(repo + "\n")
        profile_path_file = get_profile_path_file_name(selected_author)
        if os.path.exists(profile_path_file):
            os.remove(profile_path_file)
        output_path = run_model_team_git_parser(tmp_repo_file_name, selected_author, int(num_years), False, None,
                                                force_rerun)
        with open(profile_path_file, "w") as f:
            f.write(output_path)
        if output_path:
            run_edit_and_sign(output_path, False, False)
    else:
        print("Dialog closed... error")
