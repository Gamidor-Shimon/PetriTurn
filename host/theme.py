"""
Gamidor Diagnostics - Qt/PySide6 design tokens.

Lifted verbatim from decapper_qt.py (DeCapper Control Center v2.0).
Copy this file into a new project, or import it, and the app already looks
like the rest of the family.

Usage:
    self.setStyleSheet(QSS.format(**(DARK if dark else LIGHT)))
"""

from PySide6 import QtWidgets
from PySide6.QtCore import Qt


LIGHT = {
    "bg": "#f4f6f9", "surface": "#ffffff", "surface2": "#eceff3",
    "text": "#1b2733", "muted": "#6b7785", "border": "#dde2e8",
    "accent": "#e8563f", "accent_hi": "#f2704f", "info": "#0b6fb4",
    "ok": "#10893e", "warn": "#b07d00", "err": "#c0261a",
    "sidebar": "#ffffff", "sidebar_sel": "#fdeeea",
    "console_bg": "#141a21", "console_fg": "#d7dee6",
    "shadow": "rgba(0,0,0,0.06)",
}
DARK = {
    "bg": "#14181d", "surface": "#1c2128", "surface2": "#232b34",
    "text": "#e6edf3", "muted": "#8b98a5", "border": "#2d353e",
    "accent": "#ff6b52", "accent_hi": "#ff8570", "info": "#4aa3e0",
    "ok": "#3fb950", "warn": "#d29922", "err": "#f85149",
    "sidebar": "#181d23", "sidebar_sel": "#2a1f1d",
    "console_bg": "#0d1117", "console_fg": "#c9d1d9",
    "shadow": "rgba(0,0,0,0.35)",
}

QSS = """
* {{ font-family: "Segoe UI", "Inter", sans-serif; font-size: 13px; }}
QWidget#Root {{ background: {bg}; }}

/* ---------- sidebar ---------- */
QFrame#Sidebar {{ background: {sidebar}; border-right: 1px solid {border}; }}
QPushButton#Nav {{
    background: transparent; border: none; border-radius: 8px;
    padding: 11px 14px; text-align: left; color: {muted};
    font-size: 13px; font-weight: 600;
}}
QPushButton#Nav:hover {{ background: {surface2}; color: {text}; }}
QPushButton#Nav:checked {{ background: {sidebar_sel}; color: {accent}; }}
QLabel#Brand {{ color: {muted}; font-size: 10px; letter-spacing: 1px; }}

/* ---------- cards ---------- */
QFrame#Card {{
    background: {surface}; border: 1px solid {border}; border-radius: 10px;
}}
QLabel#CardTitle {{
    color: {muted}; font-size: 10px; font-weight: 700; letter-spacing: 1.1px;
}}
QLabel#H1 {{ color: {text}; font-size: 22px; font-weight: 700; }}
QLabel#H2 {{ color: {text}; font-size: 15px; font-weight: 600; }}
QLabel#Muted {{ color: {muted}; font-size: 11px; min-height: 14px; }}
QLabel {{ color: {text}; background: transparent; }}

QLabel#Readout {{
    color: {ok}; font-family: "Consolas", monospace;
    font-size: 20px; font-weight: 700;
    min-height: 26px;
}}
QLabel#BigNum {{
    color: {info}; font-family: "Consolas", monospace;
    font-size: 32px; font-weight: 700;
    min-height: 42px;
}}
QLabel#TypeNum {{
    color: {accent}; font-family: "Consolas", monospace;
    font-size: 26px; font-weight: 700;
    min-height: 34px; min-width: 30px;
}}

/* ---------- buttons ---------- */
QPushButton {{
    background: {surface2}; color: {text}; border: 1px solid {border};
    border-radius: 7px; padding: 7px 13px; font-weight: 600;
}}
QPushButton:hover {{ border-color: {accent}; }}
QPushButton:pressed {{ background: {border}; }}
QPushButton:disabled {{ color: {muted}; border-color: {border};
                        background: {surface}; }}
QPushButton#Primary {{
    background: {accent}; color: #ffffff; border: none; padding: 9px 16px;
}}
QPushButton#Primary:hover {{ background: {accent_hi}; }}
QPushButton#Primary:disabled {{ background: {border}; color: {muted}; }}
QPushButton#Ghost {{ background: transparent; }}
QPushButton#Chip {{
    background: {surface2}; border: 1px solid {border}; border-radius: 6px;
    padding: 5px 9px; font-family: "Consolas", monospace; font-weight: 600;
}}
QPushButton#Chip:hover {{ border-color: {accent}; color: {accent}; }}

/* ---------- inputs ---------- */
QLineEdit, QComboBox, QSpinBox {{
    background: {surface}; color: {text}; border: 1px solid {border};
    border-radius: 7px; padding: 6px 9px; selection-background-color: {accent};
}}
QLineEdit:focus, QComboBox:focus {{ border-color: {accent}; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
/* The spin arrows need explicit geometry. Styling QSpinBox's border and
   padding without styling the sub-controls left them drawn but with a broken
   hit area, so clicking them did nothing. */
QSpinBox {{ padding-right: 22px; }}
QSpinBox::up-button, QSpinBox::down-button {{
    subcontrol-origin: border; width: 20px; border: none;
    background: {surface2};
}}
QSpinBox::up-button {{ subcontrol-position: top right; height: 50%; }}
QSpinBox::down-button {{ subcontrol-position: bottom right; height: 50%; }}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background: {border}; }}
QSpinBox::up-arrow {{
    image: none; width: 7px; height: 7px; border-left: 4px solid transparent;
    border-right: 4px solid transparent; border-bottom: 5px solid {text};
}}
QSpinBox::down-arrow {{
    image: none; width: 7px; height: 7px; border-left: 4px solid transparent;
    border-right: 4px solid transparent; border-top: 5px solid {text};
}}
QComboBox QAbstractItemView {{
    background: {surface}; color: {text}; border: 1px solid {border};
    selection-background-color: {accent}; selection-color: #ffffff;
    outline: none;
}}
QCheckBox {{ color: {text}; spacing: 7px; }}
QCheckBox::indicator {{
    width: 15px; height: 15px; border-radius: 4px;
    border: 1px solid {border}; background: {surface};
}}
QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; }}

/* ---------- table ---------- */
QTableWidget {{
    background: {surface}; color: {text}; border: 1px solid {border};
    border-radius: 8px; gridline-color: {border};
    selection-background-color: {sidebar_sel}; selection-color: {text};
}}
QHeaderView::section {{
    background: {surface2}; color: {muted}; border: none;
    border-bottom: 1px solid {border}; padding: 7px; font-weight: 700;
    font-size: 11px;
}}
QTableWidget::item {{ padding: 5px; }}

QListWidget {{
    background: {surface}; color: {text}; border: 1px solid {border};
    border-radius: 8px; font-family: "Consolas", monospace;
}}
QListWidget::item:selected {{ background: {sidebar_sel}; color: {text}; }}

/* ---------- console ---------- */
QPlainTextEdit#Console {{
    background: {console_bg}; color: {console_fg};
    border: 1px solid {border}; border-radius: 8px;
    font-family: "Consolas", monospace; font-size: 12px;
}}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {border}; border-radius: 5px;
                               min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: {muted}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {border}; border-radius: 5px;
                                 min-width: 24px; }}

QFrame#Sep {{ background: {border}; max-height: 1px; border: none; }}
QToolTip {{
    background: {surface}; color: {text}; border: 1px solid {border};
    padding: 5px;
}}
"""


# ==========================================================================
#  Building blocks - every screen is made of these four
# ==========================================================================
def card(title=None):
    f = QtWidgets.QFrame()
    f.setObjectName("Card")
    # Preferred vertically: a card reports the height its contents need and is
    # not shrunk below it, which is what clipped the text before.
    f.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred,
                    QtWidgets.QSizePolicy.Policy.Maximum)
    lay = QtWidgets.QVBoxLayout(f)
    lay.setContentsMargins(16, 14, 16, 14)
    lay.setSpacing(10)
    if title:
        lb = QtWidgets.QLabel(title.upper())
        lb.setObjectName("CardTitle")
        lay.addWidget(lb)
    return f, lay


def muted(text, wrap=False):
    lb = QtWidgets.QLabel(text)
    lb.setObjectName("Muted")
    if wrap:
        lb.setWordWrap(True)
        # A wrapped label reports a multi-line sizeHint; Minimum keeps the
        # layout from shrinking it back to one line and clipping the rest.
        lb.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred,
                         QtWidgets.QSizePolicy.Policy.Minimum)
    return lb


def hsep():
    f = QtWidgets.QFrame()
    f.setObjectName("Sep")
    f.setFixedHeight(1)
    return f


class Pill(QtWidgets.QLabel):
    """Small rounded status badge."""

    def __init__(self, text="--"):
        super().__init__(text)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumWidth(96)
        self._colour = "#888888"
        self._paint()

    def set_state(self, text, colour):
        if text == self.text() and colour == self._colour:
            return                      # avoid a needless restyle + repaint
        self.setText(text)
        self._colour = colour
        self._paint()

    def _paint(self):
        self.setStyleSheet(
            f"background:{self._colour}22; color:{self._colour};"
            f"border:1px solid {self._colour}66; border-radius:11px;"
            f"padding:4px 10px; font-weight:700; font-size:11px;")


# ==========================================================================
#  Main window
