"""Shared PyQt5 stylesheet for the helper and skill-filter dialogs.

Matches the dark-dashboard palette used by the HTML profile output.

Dynamic-property hooks used by widgets:
  - QLabel  ``heading="true"``    section heading
  - QLabel  ``hint="true"``       dim secondary text
  - QLabel  ``mono="true"``       monospace dim text (paths, hashes)
  - QPushButton ``secondary="true"``  outline / cancel-style button
  - QFrame  ``alt="true"``        alternating row background (skill list)
"""

APP_STYLESHEET = """
QDialog, QWidget {
    background-color: #0d1117;
    color: #e6edf3;
    font-family: "Helvetica Neue", "Segoe UI", "Inter", Arial, sans-serif;
    font-size: 13px;
}
QLabel { background: transparent; color: #e6edf3; font-size: 13px; }
QLabel[heading="true"] { font-size: 15px; font-weight: 600; color: #e6edf3; padding-top: 4px; }
QLabel[hint="true"] { color: #8b949e; font-size: 12px; }
QLabel[mono="true"] {
    font-family: Menlo, "JetBrains Mono", Consolas, "Courier New", monospace;
    color: #8b949e;
    font-size: 12px;
}

QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #a855f7, stop:1 #06b6d4);
    color: white;
    border: 0;
    border-radius: 8px;
    padding: 10px 22px;
    font-size: 13px;
    font-weight: 600;
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #b97afa, stop:1 #22cae3);
}
QPushButton:pressed {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #913aea, stop:1 #0494b4);
}
QPushButton:disabled {
    background: #21262d;
    color: #6e7681;
}
QPushButton[secondary="true"] {
    background: transparent;
    color: #e6edf3;
    border: 1px solid #30363d;
}
QPushButton[secondary="true"]:hover {
    border-color: #06b6d4;
    color: #06b6d4;
}
QPushButton[secondary="true"]:pressed {
    color: #a855f7;
    border-color: #a855f7;
}

QListWidget, QTextEdit, QTextBrowser {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 10px;
    padding: 6px;
    color: #e6edf3;
    font-size: 12.5px;
    selection-background-color: rgba(168, 85, 247, 0.22);
    selection-color: #e6edf3;
}
QTextEdit { font-family: Menlo, "JetBrains Mono", Consolas, "Courier New", monospace; }
QTextBrowser { padding: 12px; }
QListWidget::item { padding: 5px 8px; border-radius: 4px; }
QListWidget::item:hover { background-color: #21262d; }
QListWidget::item:selected { background-color: rgba(168, 85, 247, 0.18); color: #e6edf3; }
QListWidget::indicator, QCheckBox::indicator {
    width: 14px; height: 14px;
    border: 1px solid #30363d;
    border-radius: 3px;
    background: #0d1117;
}
QListWidget::indicator:checked, QCheckBox::indicator:checked {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #a855f7, stop:1 #06b6d4);
    border: 1px solid transparent;
    image: none;
}

QRadioButton { color: #e6edf3; spacing: 8px; }
QRadioButton::indicator {
    width: 14px; height: 14px;
    border: 1px solid #30363d;
    border-radius: 7px;
    background: #0d1117;
}
QRadioButton::indicator:hover { border-color: #484f58; }
QRadioButton::indicator:checked {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #a855f7, stop:1 #06b6d4);
    border: 1px solid transparent;
}

QSpinBox, QComboBox {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 6px 10px;
    color: #e6edf3;
    font-size: 13px;
    min-height: 22px;
}
QSpinBox:focus, QComboBox:focus, QListWidget:focus, QTextEdit:focus, QTextBrowser:focus {
    border: 1px solid #06b6d4;
}
QComboBox::drop-down { border: 0; width: 24px; }
QComboBox QAbstractItemView {
    background-color: #161b22;
    border: 1px solid #30363d;
    selection-background-color: rgba(168, 85, 247, 0.22);
    selection-color: #e6edf3;
    color: #e6edf3;
    padding: 4px;
    outline: 0;
}

QCheckBox { color: #e6edf3; spacing: 8px; }

QFrame { background: transparent; }
QFrame[alt="true"] { background-color: #11161d; border-radius: 6px; }

QScrollArea { background: transparent; border: 0; }
QScrollArea > QWidget > QWidget { background: transparent; }

QScrollBar:vertical { background: #0d1117; width: 10px; border: 0; margin: 0; }
QScrollBar::handle:vertical { background: #30363d; border-radius: 5px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: #484f58; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""
