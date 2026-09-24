"""
PetriPlatter Control Center — create, edit and test dish-rotation programs and store them
on the PetriPlatter controller (XIAO ESP32-C3 + TMC2209). Gamidor instrument-console design
(see theme.py, copied verbatim from the gamidor-ui-design skill).

The robot then runs a stored program with:   platter.exe run <slot>
Disconnect (or close) this window before the robot uses the port: only one program can hold
a COM port at a time.

Run:
    .venv\\Scripts\\python host\\platter_gui.py
Build the exe (from the project root):
    .venv\\Scripts\\pyinstaller --onefile --windowed --name platter_gui --icon host\\assets\\app.ico ^
        --add-data "host\\assets;assets" host\\platter_gui.py
"""

from __future__ import annotations

import ctypes
import datetime
import html
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import serial
from PySide6 import QtGui, QtWidgets
from PySide6.QtCore import QObject, QPoint, QSettings, Qt, QThread, QTimer, Signal, Slot

from platter_link import (DEFAULT_LIMITS, Config, ConfigError, PlatterError, PlatterLink, Program,
                          Step, list_ports, load_config, save_port)
from theme import DARK, LIGHT, QSS, Pill, card, hsep, muted

APP_NAME = "PetriPlatter Control Center"
APP_VERSION = "1.0"
COMPANY = "Gamidor Diagnostics"
AUTHOR = "Shimon Yeshayahu"

PAGE_MIN_WIDTH = 1030

# Same tokens as theme.py; rules theme.py does not cover (double spin boxes, the STOP button,
# an inline error line) are built from its palette only. The spin buttons get no "height: 50%":
# stylesheets do not support percentages, and with it both buttons collapse into one.
EXTRA_QSS = """
QDoubleSpinBox {{
    background: {surface}; color: {text}; border: 1px solid {border};
    border-radius: 7px; padding: 6px 9px; padding-right: 22px;
    selection-background-color: {accent};
}}
QDoubleSpinBox:focus {{ border-color: {accent}; }}
QDoubleSpinBox:disabled, QSpinBox:disabled, QLineEdit:disabled, QComboBox:disabled {{
    color: {muted}; background: {surface2};
}}
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border; width: 20px; border: none; background: {surface2};
}}
QDoubleSpinBox::up-button {{ subcontrol-position: top right; }}
QDoubleSpinBox::down-button {{ subcontrol-position: bottom right; }}
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{ background: {border}; }}
QDoubleSpinBox::up-arrow {{ image: url({arrow_up}); width: 9px; height: 6px; }}
QDoubleSpinBox::down-arrow {{ image: url({arrow_down}); width: 9px; height: 6px; }}
QComboBox::down-arrow {{ image: url({arrow_down}); width: 9px; height: 6px; }}
QPushButton#Danger {{
    background: {err}; color: #ffffff; border: none; padding: 9px 16px; font-weight: 700;
}}
QPushButton#Danger:disabled {{ background: {border}; color: {muted}; }}
QLabel#MutedErr {{ color: {err}; font-size: 11px; }}
QScrollArea {{ background: transparent; border: none; }}
QTableWidget {{ outline: 0; }}
QTableWidget::item:selected {{ background: {sidebar_sel}; color: {text}; border: none; }}
QSplitter::handle {{ background: {bg}; }}
QListWidget::item {{ padding: 4px 6px; }}
QWidget#Page {{ background: {bg}; }}
"""

CONSOLE_COLOURS = {"err": "#ff7b6b", "warn": "#ffc061", "ok": "#5fd68a",
                   "tx": "#5aa9f0", "gui": "#9aa5b1"}

ACTIONS = (("Rotate", "ROT"), ("Wait", "WAIT"), ("Hold dish", "HOLD"), ("Release dish", "RELEASE"))
ACTION_LABEL = {kind: label for label, kind in ACTIONS}

ERROR_HINTS = {
    "DRIVER": "The motor driver is not responding, so the motor was not moved.",
    "EMPTY_SLOT": "This slot has no program.",
    "STOPPED": "The motion was stopped.",
    "BUSY": "The controller is still running a program.",
}
ERROR_DETAIL = {
    "DRIVER": "Check that the 24V supply is on and reaches VM, and that the D4/D5 wires "
              "to the driver's USART pin are in place.",
}


def asset(name: str) -> str:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return str(base / "assets" / name)


def data_dir() -> Path:
    """Next to the exe when frozen, next to this file otherwise."""
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent


def fmt(x: float) -> str:
    return f"{x:g}"


def arrow_images(colour: str) -> dict[str, str]:
    """Spin-box / combo arrows as small PNGs in the theme's text colour. Stylesheet triangles
    made of borders render as bars on Windows, so they are drawn once per theme instead."""
    out = {}
    folder = Path(tempfile.gettempdir()) / "petriplatter_gui"
    folder.mkdir(exist_ok=True)
    for name, points in (("up", ((0, 5), (4, 0), (8, 5))), ("down", ((0, 0), (4, 5), (8, 0)))):
        pm = QtGui.QPixmap(9, 6)
        pm.fill(Qt.GlobalColor.transparent)
        p = QtGui.QPainter(pm)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QColor(colour))
        p.drawPolygon(QtGui.QPolygon([QPoint(x, y) for x, y in points]))
        p.end()
        path = folder / f"arrow_{name}_{colour.lstrip('#')}.png"
        pm.save(str(path))
        out[f"arrow_{name}"] = path.as_posix()
    return out


# ------------------------------------------------------------------------------------
# Serial I/O runs on a worker thread; the GUI never blocks.

@dataclass(eq=False)
class Job:
    label: str                              # shown in the busy label and the console
    fn: Callable[[], object]                # runs on the worker thread
    on_done: Callable[[object], None] | None = None
    tx: str | None = None                   # the raw command, printed as "sent"
    quiet: bool = False                     # status polling: no console lines on success
    motion: bool = False                    # STOP has to interrupt this one


class Worker(QObject):
    finished = Signal(object, object, object)   # job, result, error

    @Slot(object)
    def run(self, job: Job):
        try:
            result, error = job.fn(), None
        except Exception as e:      # reported by the GUI, never kills the thread
            result, error = None, e
        self.finished.emit(job, result, error)


# ------------------------------------------------------------------------------------

class MainWindow(QtWidgets.QMainWindow):
    submit_job = Signal(object)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QtGui.QIcon(asset("app.ico")))
        self.settings = QSettings("GamidorDiagnostics", "PetriPlatter")
        try:
            self.cfg, self.cfg_error = load_config(), None     # platter.ini, shared with the robot
        except ConfigError as e:
            self.cfg, self.cfg_error = Config(), str(e)
        self.dark = self.settings.value("dark", False, type=bool)

        self.link: PlatterLink | None = None
        self.limits = dict(DEFAULT_LIMITS)
        self.status: dict[str, str] = {}
        self.last_up: int | None = None
        self.pending: list[Job] = []
        self.slot_names: dict[int, str] = {}
        self.current_slot: int | None = None
        self.steps: list[Step] = []
        self.dirty = False
        self._loading = False
        self._gate_cache = None

        # widgets gated by state (see _update_gating)
        self._conn_idle_widgets: list[QtWidgets.QWidget] = []   # connected and idle
        self._motion_widgets: list[QtWidgets.QWidget] = []      # + driver answering
        self._offline_widgets: list[QtWidgets.QWidget] = []     # only while disconnected

        log_dir = data_dir() / "logs"
        log_dir.mkdir(exist_ok=True)
        self.log_path = log_dir / f"platter_{datetime.date.today():%Y-%m-%d}.log"

        self._build_ui()
        self._start_worker()
        self._apply_limits()
        self.apply_theme()
        self.refresh_ports()
        self.show_page(0)
        self._refresh_slot_list()
        self._refresh_steps()
        self._update_gating(force=True)

        geo = self.settings.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        else:
            self.resize(1320, 880)
        split = self.settings.value("splitter")
        if split is not None:
            self.splitter.restoreState(split)

        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.poll_status)
        self.poll_timer.start(self.cfg.poll_ms)
        self.log("gui", f"{APP_NAME} {APP_VERSION} started. Log file: {self.log_path}")
        if self.cfg_error:
            self.log("err", f"{self.cfg_error} — running on the default settings")
        else:
            self.log("gui", f"settings: {self.cfg.path} (port {self.cfg.port}, {self.cfg.baudrate} baud)")

    # ================================================================ layout

    def _build_ui(self):
        root = QtWidgets.QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        outer = QtWidgets.QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_sidebar())

        main = QtWidgets.QVBoxLayout()
        main.setContentsMargins(14, 14, 14, 14)
        main.setSpacing(12)
        outer.addLayout(main, 1)
        main.addWidget(self._build_topbar())

        self.stack = QtWidgets.QStackedWidget()
        for build in (self._build_programs_page, self._build_manual_page, self._build_info_page):
            self.stack.addWidget(self._scroll_page(build()))

        self.splitter = QtWidgets.QSplitter(Qt.Orientation.Vertical)
        self.splitter.addWidget(self.stack)
        self.splitter.addWidget(self._build_console())
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)
        main.addWidget(self.splitter, 1)

    def _scroll_page(self, page: QtWidgets.QWidget) -> QtWidgets.QScrollArea:
        page.setObjectName("Page")
        page.setMinimumWidth(PAGE_MIN_WIDTH)
        area = QtWidgets.QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        area.setWidget(page)
        return area

    def _build_sidebar(self) -> QtWidgets.QFrame:
        bar = QtWidgets.QFrame()
        bar.setObjectName("Sidebar")
        bar.setFixedWidth(216)
        lay = QtWidgets.QVBoxLayout(bar)
        lay.setContentsMargins(15, 20, 15, 16)
        lay.setSpacing(6)

        self.side_logo = QtWidgets.QLabel()
        self.side_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.side_logo)
        lay.addSpacing(18)

        self.nav_buttons = []
        for i, (text, tip) in enumerate((
                ("Programs", "Create, edit, store and test rotation programs"),
                ("Manual control", "Hold, release and rotate the dish by hand, live status"),
                ("Info", "About this software and the robot command line"))):
            b = QtWidgets.QPushButton(text)
            b.setObjectName("Nav")
            b.setCheckable(True)
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False, i=i: self.show_page(i))
            lay.addWidget(b)
            self.nav_buttons.append(b)
        lay.addStretch(1)

        self.theme_btn = QtWidgets.QPushButton()
        self.theme_btn.setObjectName("Ghost")
        self.theme_btn.setToolTip("Switch between the light and dark theme")
        self.theme_btn.clicked.connect(self.toggle_theme)
        lay.addWidget(self.theme_btn)
        lay.addSpacing(8)
        brand = QtWidgets.QLabel((f"{AUTHOR.upper()}\n" if AUTHOR else "") + COMPANY.upper())
        brand.setObjectName("Brand")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(brand)
        return bar

    def _build_topbar(self) -> QtWidgets.QFrame:
        f, cl = card()
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(10)
        cl.addLayout(row)

        row.addWidget(QtWidgets.QLabel("Port"))
        self.port_box = QtWidgets.QComboBox()
        self.port_box.setMinimumWidth(110)
        self.port_box.setToolTip("USB serial port of the PetriPlatter controller")
        row.addWidget(self.port_box)
        refresh = QtWidgets.QPushButton("↻")
        refresh.setObjectName("Chip")
        refresh.setToolTip("Scan again for serial ports")
        refresh.clicked.connect(self.refresh_ports)
        row.addWidget(refresh)
        self._offline_widgets += [self.port_box, refresh]

        self.connect_btn = QtWidgets.QPushButton("Connect")
        self.connect_btn.setObjectName("Primary")
        self.connect_btn.setFixedWidth(118)
        self.connect_btn.setToolTip("Open the port. Does not reset the controller and does not "
                                    "move the motor.")
        self.connect_btn.clicked.connect(self.toggle_connection)
        row.addWidget(self.connect_btn)
        row.addSpacing(8)

        self.pill_conn = Pill("DISCONNECTED")
        self.pill_driver = Pill("DRIVER --")
        self.pill_motor = Pill("MOTOR --")
        self.pill_activity = Pill("--")
        self.pill_conn.setToolTip("USB link to the controller")
        self.pill_driver.setToolTip("Does the TMC2209 driver answer? It needs the 24V supply.")
        self.pill_motor.setToolTip("HELD = motor energised, the dish is locked. "
                                   "FREE = the dish turns by hand.")
        self.pill_activity.setToolTip("IDLE, or RUNNING while a rotation or program executes")
        for p in (self.pill_conn, self.pill_driver, self.pill_motor, self.pill_activity):
            row.addWidget(p)

        self.busy_label = muted("")
        row.addWidget(self.busy_label, 1)

        self.stop_btn = QtWidgets.QPushButton("STOP")
        self.stop_btn.setObjectName("Danger")
        self.stop_btn.setFixedWidth(118)
        self.stop_btn.setToolTip("Decelerate and stop the motor now. The dish stays held.")
        self.stop_btn.clicked.connect(self.stop)
        row.addWidget(self.stop_btn)
        return f

    # ---------------------------------------------------------------- programs page

    def _build_programs_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 4, 0)
        lay.setSpacing(12)
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(12)
        lay.addLayout(row)

        # stored programs
        f, cl = card("stored programs")
        f.setMinimumWidth(270)
        self.slot_list = QtWidgets.QListWidget()
        self.slot_list.setMinimumHeight(340)
        self.slot_list.currentRowChanged.connect(self.on_slot_selected)
        cl.addWidget(self.slot_list)
        btns = QtWidgets.QHBoxLayout()
        cl.addLayout(btns)
        for text, slot, tip in (
                ("Reload", self.reload_list, "Read the program list from the controller again"),
                ("Delete", self.delete_slot, "Erase the selected program from the controller")):
            b = QtWidgets.QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            btns.addWidget(b)
            self._conn_idle_widgets.append(b)
        cl.addWidget(muted("Programs live in the controller's flash and survive power-off. "
                           "The robot runs one with  platter.exe run <slot>.", wrap=True))
        row.addWidget(f, 1, Qt.AlignmentFlag.AlignTop)

        # editor
        f, cl = card("program")
        f.setMinimumWidth(700)
        head = QtWidgets.QHBoxLayout()
        head.setSpacing(10)
        cl.addLayout(head)
        head.addWidget(QtWidgets.QLabel("Slot"))
        self.slot_num = QtWidgets.QLabel("--")
        self.slot_num.setObjectName("TypeNum")
        head.addWidget(self.slot_num)
        head.addSpacing(10)
        head.addWidget(QtWidgets.QLabel("Name"))
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setPlaceholderText("e.g. Streak 4 quadrants")
        self.name_edit.setToolTip("Up to 24 bytes (about 12 Hebrew letters), without | , =")
        self.name_edit.textChanged.connect(self.mark_dirty)
        head.addWidget(self.name_edit, 1)

        self.table = QtWidgets.QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["#", "ACTION", "TURNS", "RPM", "WAIT [S]", "≈ TIME [S]"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setMinimumHeight(250)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 44)
        self.table.itemSelectionChanged.connect(self.on_step_selected)
        cl.addWidget(self.table)

        # step form
        form = QtWidgets.QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(4)
        cl.addLayout(form)
        self.action_box = QtWidgets.QComboBox()
        for label, kind in ACTIONS:
            self.action_box.addItem(label, kind)
        self.action_box.setToolTip("Rotate the dish, wait, or lock / free it")
        self.action_box.currentIndexChanged.connect(self.update_form_fields)
        self.turns_spin = QtWidgets.QDoubleSpinBox()
        self.turns_spin.setDecimals(3)
        self.turns_spin.setSingleStep(0.25)
        self.turns_spin.setValue(1)
        self.turns_spin.setToolTip("Dish revolutions. Negative turns the other way.")
        self.rpm_spin = QtWidgets.QDoubleSpinBox()
        self.rpm_spin.setDecimals(1)
        self.rpm_spin.setValue(20)
        self.rpm_spin.setToolTip("Dish speed, revolutions per minute")
        self.wait_spin = QtWidgets.QDoubleSpinBox()
        self.wait_spin.setDecimals(1)
        self.wait_spin.setSingleStep(0.5)
        self.wait_spin.setValue(1)
        self.wait_spin.setToolTip("Pause, in seconds. The dish stays as it is (held or free).")
        for col, (title, w) in enumerate((("action", self.action_box), ("turns", self.turns_spin),
                                          ("rpm", self.rpm_spin), ("wait [s]", self.wait_spin))):
            form.addWidget(muted(title), 0, col)
            form.addWidget(w, 1, col)
        for c in range(4):
            form.setColumnStretch(c, 1)

        step_btns = QtWidgets.QHBoxLayout()
        cl.addLayout(step_btns)
        for text, slot, tip in (
                ("Add", self.add_step, "Insert this step after the selected one"),
                ("Replace", self.replace_step, "Overwrite the selected step with these values"),
                ("Remove", self.remove_step, "Delete the selected step"),
                ("▲", lambda: self.move_step(-1), "Move the selected step up"),
                ("▼", lambda: self.move_step(1), "Move the selected step down")):
            b = QtWidgets.QPushButton(text)
            b.setToolTip(tip)
            if len(text) == 1:
                b.setObjectName("Chip")
            b.clicked.connect(slot)
            step_btns.addWidget(b)
        step_btns.addStretch(1)
        new_btn = QtWidgets.QPushButton("New / clear")
        new_btn.setObjectName("Ghost")
        new_btn.setToolTip("Empty the editor. Nothing is erased on the controller.")
        new_btn.clicked.connect(self.clear_editor)
        step_btns.addWidget(new_btn)
        cl.addWidget(muted("A rotation always runs with the motor holding, even after a "
                           "“Release dish” step. Use “Hold dish” at the end to keep the dish "
                           "locked, or “Release dish” to leave it free.", wrap=True))

        cl.addWidget(hsep())
        bottom = QtWidgets.QHBoxLayout()
        cl.addLayout(bottom)
        self.total_label = QtWidgets.QLabel("--")
        self.total_label.setObjectName("H2")
        bottom.addWidget(self.total_label)
        bottom.addStretch(1)
        self.save_btn = QtWidgets.QPushButton("Save to controller")
        self.save_btn.setObjectName("Primary")
        self.save_btn.setToolTip("Write this program into the selected slot of the controller")
        self.save_btn.clicked.connect(self.save_slot)
        bottom.addWidget(self.save_btn)
        self.run_btn = QtWidgets.QPushButton("Run on controller")
        self.run_btn.setObjectName("Primary")
        self.run_btn.setToolTip("Run the stored program now — the dish will turn")
        self.run_btn.clicked.connect(self.run_slot)
        bottom.addWidget(self.run_btn)
        self.editor_note = QtWidgets.QLabel("")
        self.editor_note.setWordWrap(True)
        cl.addWidget(self.editor_note)
        row.addWidget(f, 3, Qt.AlignmentFlag.AlignTop)

        lay.addStretch(1)
        return page

    # ---------------------------------------------------------------- manual page

    def _build_manual_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 4, 0)
        lay.setSpacing(12)
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(12)
        lay.addLayout(row)

        # dish
        f, cl = card("dish")
        f.setMinimumWidth(280)
        for text, cmd, tip, needs_driver in (
                ("Hold dish", "EN", "Energise the motor: the dish is locked in place", True),
                ("Release dish", "DIS", "De-energise the motor: the dish turns freely by hand", False),
                ("Zero position", "ZERO", "Call the current angle 0°. Does not move the motor.", False)):
            b = QtWidgets.QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False, c=cmd, t=text: self.simple_command(c, t))
            cl.addWidget(b)
            (self._motion_widgets if needs_driver else self._conn_idle_widgets).append(b)
        cl.addWidget(muted("Release the dish before switching the 24V off.", wrap=True))
        row.addWidget(f, 2, Qt.AlignmentFlag.AlignTop)

        # rotate
        f, cl = card("rotate")
        f.setMinimumWidth(320)
        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(10)
        cl.addLayout(grid)
        self.man_turns = QtWidgets.QDoubleSpinBox()
        self.man_turns.setDecimals(3)
        self.man_turns.setSingleStep(0.25)
        self.man_turns.setValue(1)
        self.man_turns.setToolTip("Dish revolutions. Negative turns the other way.")
        self.man_rpm = QtWidgets.QDoubleSpinBox()
        self.man_rpm.setDecimals(1)
        self.man_rpm.setValue(20)
        self.man_rpm.setToolTip("Dish speed, revolutions per minute")
        grid.addWidget(muted("turns"), 0, 0)
        grid.addWidget(self.man_turns, 1, 0)
        grid.addWidget(muted("rpm"), 0, 1)
        grid.addWidget(self.man_rpm, 1, 1)
        go = QtWidgets.QPushButton("Go")
        go.setObjectName("Primary")
        go.setToolTip("Rotate the dish now by this amount")
        go.clicked.connect(self.manual_rotate)
        grid.addWidget(go, 1, 2)
        self._motion_widgets.append(go)
        cl.addWidget(muted("+ and − are the two directions of the dish. If + turns the wrong "
                           "way, set INVERT_DIR in the firmware.", wrap=True))
        row.addWidget(f, 3, Qt.AlignmentFlag.AlignTop)

        # live status
        f, cl = card("live status")
        f.setMinimumWidth(300)
        grid = QtWidgets.QGridLayout()
        grid.setVerticalSpacing(8)
        cl.addLayout(grid)
        self.readouts = {}
        for i, (key, title) in enumerate((("POS", "position [°]"), ("DRV", "driver"),
                                          ("CUR", "current [mA]"), ("UP", "up time [s]"),
                                          ("STEP", "program step"), ("URX", "link restarts"))):
            k = QtWidgets.QLabel(title)
            k.setObjectName("H2")
            grid.addWidget(k, i, 0)
            v = QtWidgets.QLabel("--")
            v.setObjectName("Readout")
            v.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(v, i, 1)
            self.readouts[key] = v
        grid.setColumnStretch(1, 1)
        self.auto_refresh = QtWidgets.QCheckBox("auto refresh")
        self.auto_refresh.setChecked(True)
        self.auto_refresh.setToolTip(f"Read STATUS every {self.cfg.poll_ms / 1000:g} s while idle (poll_ms in platter.ini)")
        cl.addWidget(self.auto_refresh)
        row.addWidget(f, 3, Qt.AlignmentFlag.AlignTop)

        # legend
        f, cl = card("what the numbers mean")
        for key, text, col in (
                ("DRV 0x21", "the driver answers — ready to move", "ok"),
                ("DRV 0x00", "the driver is silent — 24V off, or the D4/D5 → USART wiring", "err"),
                ("UP drops", "the controller restarted (USB replugged, or the Arduino serial "
                             "monitor opened the port)", "warn"),
                ("URX > 0", "the link to the driver froze and was restarted automatically — "
                            "note when it happened", "warn"),
                ("CUR", "motor current set in software, ≈ 560 mA", "info"),
                ("POS", "angle since power-up or ZERO; one dish turn = 360°", "info")):
            rr = QtWidgets.QHBoxLayout()
            cl.addLayout(rr)
            k = QtWidgets.QLabel(key)
            k.setFixedWidth(110)
            k.setProperty("legend", col)
            rr.addWidget(k)
            rr.addWidget(muted(text, wrap=True), 1)
        self.legend_keys = [w for w in f.findChildren(QtWidgets.QLabel) if w.property("legend")]
        lay.addWidget(f)
        lay.addStretch(1)
        return page

    # ---------------------------------------------------------------- info page

    def _build_info_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 4, 0)
        lay.setSpacing(12)
        f, cl = card()
        self.info_logo = QtWidgets.QLabel()
        cl.addWidget(self.info_logo)
        title = QtWidgets.QLabel(APP_NAME)
        title.setObjectName("H1")
        cl.addWidget(title)
        cl.addWidget(muted(f"Version {APP_VERSION} · " + (f"{AUTHOR} · " if AUTHOR else "") + COMPANY))
        cl.addWidget(muted("Rotates a petri dish during streaking. Programs are written here and "
                           "stored in the controller; the robot runs them by slot number.",
                           wrap=True))
        lay.addWidget(f)

        f, cl = card("robot command line")
        usage = QtWidgets.QLabel(
            "platter.exe run <slot>          run a stored program, exit when it ends\n"
            "platter.exe rotate <deg> <rpm>  one-off rotation\n"
            "platter.exe enable | disable    hold / release the dish\n"
            "platter.exe status | list\n\n"
            "exit 0 = OK   1 = timeout, device error or stopped   2 = bad command or empty slot")
        usage.setStyleSheet("font-family: Consolas, monospace;")
        cl.addWidget(usage)
        cl.addWidget(muted("The port, baud rate and timeouts are in platter.ini next to the programs; "
                           "Connect here writes the port there, so the robot uses the same one. "
                           "Close this window first — only one program can hold the port.",
                           wrap=True))
        lay.addWidget(f)
        lay.addStretch(1)
        return page

    # ---------------------------------------------------------------- console

    def _build_console(self) -> QtWidgets.QFrame:
        f, cl = card("console")
        f.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred,
                        QtWidgets.QSizePolicy.Policy.Expanding)
        bar = QtWidgets.QHBoxLayout()
        cl.addLayout(bar)
        for text, slot, tip in (("Copy", self.copy_console, "Copy the console text"),
                                ("Save…", self.save_console, "Save the console text to a file"),
                                ("Clear", lambda: self.console.clear(), "Clear the console pane")):
            b = QtWidgets.QPushButton(text)
            b.setObjectName("Ghost")
            b.setToolTip(tip)
            b.clicked.connect(slot)
            bar.addWidget(b)
        bar.addWidget(muted(f"auto-saved to {self.log_path}"), 1)
        self.console = QtWidgets.QPlainTextEdit()
        self.console.setObjectName("Console")
        self.console.setReadOnly(True)
        self.console.setMaximumBlockCount(4000)
        self.console.setMinimumHeight(110)
        cl.addWidget(self.console, 1)
        return f

    # ================================================================ theme, pages, console

    def palette_colors(self) -> dict:
        return DARK if self.dark else LIGHT

    def apply_theme(self):
        c = self.palette_colors()
        self.setStyleSheet(QSS.format(**c) + EXTRA_QSS.format(**c, **arrow_images(c["text"])))
        wide = QtGui.QPixmap(asset("logo_wide_dark.png" if self.dark else "logo_wide.png"))
        dpr = self.devicePixelRatioF()
        for label, width in ((self.side_logo, 186), (self.info_logo, 540)):
            pm = wide.scaledToWidth(int(width * dpr), Qt.TransformationMode.SmoothTransformation)
            pm.setDevicePixelRatio(dpr)
            label.setPixmap(pm)
        self.theme_btn.setText("Light mode" if self.dark else "Dark mode")
        for k in self.legend_keys:
            k.setStyleSheet(f"font-family: Consolas; font-weight: 700; color: {c[k.property('legend')]};")
        self._update_pills()
        self._update_editor_note()

    def toggle_theme(self):
        self.dark = not self.dark
        self.settings.setValue("dark", self.dark)
        self.apply_theme()

    def show_page(self, i: int):
        self.stack.setCurrentIndex(i)
        for j, b in enumerate(self.nav_buttons):
            b.setChecked(i == j)

    def log(self, tag: str, text: str):
        stamp = datetime.datetime.now().strftime("%H:%M:%S")
        colour = CONSOLE_COLOURS.get(tag, CONSOLE_COLOURS["gui"])
        prefix = {"tx": "→", "ok": "←", "err": "✖", "warn": "!", "gui": "·"}.get(tag, "·")
        self.console.appendHtml(f'<span style="color:{colour}">{stamp} {prefix} '
                                f'{html.escape(text)}</span>')
        self.console.verticalScrollBar().setValue(self.console.verticalScrollBar().maximum())
        try:
            with open(self.log_path, "a", encoding="utf-8") as fh:
                fh.write(f"{stamp} [{tag}] {text}\n")
        except OSError:
            pass

    def copy_console(self):
        QtWidgets.QApplication.clipboard().setText(self.console.toPlainText())

    def save_console(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save console", "platter_console.txt",
                                                        "Text files (*.txt)")
        if path:
            Path(path).write_text(self.console.toPlainText(), encoding="utf-8")
            self.log("gui", f"console saved to {path}")

    def confirm(self, title: str, text: str, detail: str = "") -> bool:
        m = QtWidgets.QMessageBox(self)
        m.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        m.setWindowTitle(title)
        m.setText(text)
        if detail:
            m.setInformativeText(detail)
        m.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Ok |
                             QtWidgets.QMessageBox.StandardButton.Cancel)
        m.setDefaultButton(QtWidgets.QMessageBox.StandardButton.Cancel)
        return m.exec() == QtWidgets.QMessageBox.StandardButton.Ok

    # ================================================================ worker + state

    def _start_worker(self):
        self.thread = QThread(self)
        self.worker = Worker()
        self.worker.moveToThread(self.thread)
        self.submit_job.connect(self.worker.run)
        self.worker.finished.connect(self._job_finished)
        self.thread.start()

    def submit(self, job: Job):
        if not self.link:
            return
        self.pending.append(job)
        if job.tx and not job.quiet:
            self.log("tx", job.tx)
        self._update_gating()
        self.submit_job.emit(job)

    @Slot(object, object, object)
    def _job_finished(self, job: Job, result, error):
        if job not in self.pending:        # finished after a disconnect: stale
            return
        self.pending.remove(job)
        if error is None:
            if job.on_done:
                job.on_done(result)
        elif isinstance(error, PlatterError):
            self.log("warn" if error.reason == "STOPPED" else "err",
                     f"{job.label}: controller replied ERR {error.reason}")
            hint = ERROR_HINTS.get(error.reason)
            if hint and error.reason != "STOPPED" and not job.quiet:
                box = QtWidgets.QMessageBox(self)
                box.setIcon(QtWidgets.QMessageBox.Icon.Warning)
                box.setWindowTitle(job.label)
                box.setText(hint)
                box.setInformativeText(ERROR_DETAIL.get(error.reason, ""))
                box.exec()
        elif isinstance(error, TimeoutError):
            self.log("err", f"{job.label}: {error}")
        else:
            self.log("err", f"{job.label}: connection lost ({error})")
            self.disconnect_port()
        self._update_gating()
        if job.motion and self.link:
            self.poll_status(force=True)

    def _driver_ok(self) -> bool:
        return self.status.get("DRV", "").upper() == "0X21"

    def _update_gating(self, force: bool = False):
        conn = self.link is not None
        idle = not self.pending
        drv = self._driver_ok()
        running = any(j.motion for j in self.pending)
        busy_text = ", ".join(j.label for j in self.pending if not j.quiet)
        self.busy_label.setText(f"busy: {busy_text}…" if busy_text else "")
        self.connect_btn.setText("Disconnect" if conn else "Connect")
        self._update_pills()
        self._update_editor_note()

        state = (conn, idle, drv, running)
        if state == self._gate_cache and not force:
            return
        self._gate_cache = state
        for group, target in ((self._conn_idle_widgets, conn and idle),
                              (self._motion_widgets, conn and idle and drv),
                              (self._offline_widgets, not conn)):
            for w in group:
                if w.isEnabled() != target:     # compare first, or the window flickers
                    w.setEnabled(target)
        self.connect_btn.setEnabled(idle or not conn)
        self.stop_btn.setEnabled(conn)

    def _update_pills(self):
        c = self.palette_colors()
        conn = self.link is not None
        self.pill_conn.set_state("CONNECTED" if conn else "DISCONNECTED", c["ok"] if conn else c["muted"])
        if not conn or not self.status:
            self.pill_driver.set_state("DRIVER --", c["muted"])
            self.pill_motor.set_state("MOTOR --", c["muted"])
        else:
            drv = self._driver_ok()
            self.pill_driver.set_state("DRIVER OK" if drv else "NO DRIVER", c["ok"] if drv else c["err"])
            held = self.status.get("EN") == "1"
            self.pill_motor.set_state("HELD" if held else "FREE", c["info"] if held else c["warn"])
        running = conn and (any(j.motion for j in self.pending) or self.status.get("BUSY") == "1")
        self.pill_activity.set_state("RUNNING" if running else ("IDLE" if conn else "--"),
                                     c["accent"] if running else (c["ok"] if conn else c["muted"]))

    # ================================================================ connection + status

    def refresh_ports(self):
        current = self.port_box.currentText() or self.cfg.port
        self.port_box.clear()
        ports = list_ports()
        self.port_box.addItems(ports)
        if current in ports:
            self.port_box.setCurrentText(current)

    def toggle_connection(self):
        if self.link:
            self.disconnect_port()
            return
        port = self.port_box.currentText().strip()
        if not port:
            self.log("warn", "choose a serial port first")
            return
        try:
            self.link = PlatterLink.from_config(self.cfg, port)
        except serial.SerialException as e:
            self.log("err", f"cannot open {port}: {e}")
            if "Access is denied" in str(e) or "PermissionError" in str(e):
                self.log("warn", "the port is held by another program — close the Arduino serial "
                                 "monitor or a running platter.exe")
            return
        self.log("gui", f"opened {port}")
        link = self.link

        def work():
            return link.info(), link.status(), link.list_programs()

        def done(res):
            self.limits, status, self.slot_names = res
            self._apply_limits()
            self._apply_status(status)
            self._refresh_slot_list()
            self.log("ok", f"controller ready — {len(self.slot_names)} program(s) stored, "
                           f"driver {status.get('DRV', '?')}")
            if port != self.cfg.port and not self.cfg_error:
                try:
                    save_port(port, self.cfg.path)
                    self.cfg.port = port
                    self.log("gui", f"port {port} saved to {self.cfg.path.name} — the robot uses it too")
                except OSError as e:
                    self.log("warn", f"could not save the port to platter.ini: {e}")
            if not self._driver_ok():
                self.log("warn", "the driver does not answer: is the 24V on? Motion is disabled "
                                 "until it does.")

        self.submit(Job("connecting", work, done, tx="INFO · STATUS · PLIST"))

    def disconnect_port(self):
        if self.link:
            try:
                if any(j.motion for j in self.pending):
                    self.link.send_stop()
                self.link.close()
            except serial.SerialException:
                pass
            self.log("gui", "port closed")
        self.link = None
        self.pending.clear()
        self.status = {}
        self.last_up = None
        for v in self.readouts.values():
            v.setText("--")
        self._update_gating(force=True)

    def poll_status(self, force: bool = False):
        if not self.link or self.pending:
            return
        if not force and not self.auto_refresh.isChecked():
            return
        link = self.link
        self.submit(Job("status", link.status, self._apply_status, tx="STATUS", quiet=True))

    def _apply_status(self, st: dict):
        up = int(st.get("UP", "0") or 0)
        first = self.last_up is None
        if not first and up < self.last_up:
            self.log("warn", f"the controller restarted (up time {self.last_up} s → {up} s). "
                             "The motor was released during the restart.")
        self.last_up = up
        urx = int(st.get("URX", "0") or 0)
        if urx > int(self.status.get("URX", "0") or 0) and not first:
            self.log("warn", f"the link to the driver froze and was restarted by the controller "
                             f"(total {urx} since power-up)")
        was_ok = self._driver_ok()
        self.status = st
        if self._driver_ok() != was_ok and not first:
            self.log("ok" if self._driver_ok() else "warn",
                     "driver answers again" if self._driver_ok() else "driver stopped answering (24V?)")
        for key, label in self.readouts.items():
            label.setText(st.get(key, "--"))
        self._update_gating()

    def _apply_limits(self):
        lim = self.limits
        max_turns = lim["MAX_DEG"] / 360
        for spin in (self.turns_spin, self.man_turns):
            spin.setRange(-max_turns, max_turns)
        for spin in (self.rpm_spin, self.man_rpm):
            spin.setRange(lim["MIN_RPM"], lim["MAX_RPM"])
        self.wait_spin.setRange(0.1, lim["MAX_WAIT_MS"] / 1000)
        self._refresh_slot_list()
        self._refresh_steps()

    # ================================================================ commands

    def simple_command(self, cmd: str, label: str):
        link = self.link
        self.submit(Job(label, lambda: link.command(cmd), lambda _: self.log("ok", f"{label}: OK"),
                        tx=cmd, motion=False))
        self.poll_status_soon()

    def poll_status_soon(self):
        QTimer.singleShot(150, lambda: self.poll_status(force=True))

    def manual_rotate(self):
        turns, rpm = self.man_turns.value(), self.man_rpm.value()
        if turns == 0:
            self.log("warn", "0 turns — nothing to do")
            return
        link, limits, deg = self.link, dict(self.limits), round(turns * 360, 3)
        self.submit(Job(f"rotate {fmt(turns)} turns", lambda: link.rotate(deg, rpm, limits),
                        lambda _: self.log("ok", "rotation finished"),
                        tx=f"ROT {fmt(deg)} {fmt(rpm)}", motion=True))

    def stop(self):
        if not self.link:
            return
        try:
            if any(j.motion for j in self.pending):
                self.link.send_stop()     # the running command ends with ERR STOPPED
                self.log("tx", "STOP")
            else:
                link = self.link
                self.submit(Job("stop", lambda: link.command("STOP"), tx="STOP"))
        except serial.SerialException as e:
            self.log("err", f"STOP failed: {e}")

    # ================================================================ slot list

    def _refresh_slot_list(self):
        self.slot_list.blockSignals(True)
        self.slot_list.clear()
        c = self.palette_colors()
        for slot in range(1, int(self.limits["SLOTS"]) + 1):
            name = self.slot_names.get(slot)
            item = QtWidgets.QListWidgetItem(f"{slot:>2}  {name}" if name else f"{slot:>2}  (empty)")
            if not name:
                item.setForeground(QtGui.QColor(c["muted"]))
            self.slot_list.addItem(item)
        if self.current_slot:
            self.slot_list.setCurrentRow(self.current_slot - 1)
        self.slot_list.blockSignals(False)

    def reload_list(self):
        link = self.link

        def done(names):
            self.slot_names = names
            self._refresh_slot_list()
            self.log("ok", f"{len(names)} program(s) stored")
        self.submit(Job("reading program list", link.list_programs, done, tx="PLIST"))

    def on_slot_selected(self, row: int):
        slot = row + 1
        if row < 0 or slot == self.current_slot:
            return
        if self.dirty and not self.confirm("Unsaved changes",
                                           "Discard the changes to the current program?"):
            self.slot_list.blockSignals(True)
            self.slot_list.setCurrentRow((self.current_slot or 1) - 1)
            self.slot_list.blockSignals(False)
            return
        self.current_slot = slot
        self.slot_num.setText(str(slot))
        if slot not in self.slot_names or not self.link:
            self.load_program(Program("", []))
            return
        link = self.link
        self.submit(Job(f"loading slot {slot}", lambda: link.get_program(slot), self.load_program,
                        tx=f"PGET {slot}"))

    def delete_slot(self):
        slot = self.current_slot
        if not slot or slot not in self.slot_names:
            self.log("warn", "choose a stored program to delete")
            return
        if not self.confirm("Delete program", f"Erase program {slot} “{self.slot_names[slot]}” "
                                              "from the controller?",
                            "The robot will get ERR EMPTY_SLOT if it runs this slot."):
            return
        link = self.link

        def done(_):
            self.slot_names.pop(slot, None)
            self._refresh_slot_list()
            self.load_program(Program("", []))
            self.log("ok", f"slot {slot} erased")
        self.submit(Job(f"deleting slot {slot}", lambda: link.delete_program(slot), done,
                        tx=f"PDEL {slot}"))

    # ================================================================ editor

    def load_program(self, program: Program):
        self._loading = True
        self.name_edit.setText(program.name)
        self.steps = list(program.steps)
        self._loading = False
        self.dirty = False
        self._refresh_steps()

    def clear_editor(self):
        if self.dirty and not self.confirm("Unsaved changes", "Discard the changes?"):
            return
        self.load_program(Program("", []))

    def mark_dirty(self):
        if not self._loading:
            self.dirty = True
            self._update_editor_note()

    def _refresh_steps(self, select: int | None = None):
        accel = self.limits["ACCEL"]
        mono = QtGui.QFont("Consolas")
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.steps))
        for i, s in enumerate(self.steps):
            turns = fmt(round(s.deg / 360, 4)) if s.kind == "ROT" else ""
            rpm = fmt(s.rpm) if s.kind == "ROT" else ""
            wait = fmt(s.ms / 1000) if s.kind == "WAIT" else ""
            secs = f"{s.seconds(accel):.1f}" if s.kind in ("ROT", "WAIT") else "0"
            for col, text in enumerate((str(i + 1), ACTION_LABEL[s.kind], turns, rpm, wait, secs)):
                item = QtWidgets.QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col != 1:
                    item.setFont(mono)
                self.table.setItem(i, col, item)
        self.table.blockSignals(False)
        if select is not None and 0 <= select < len(self.steps):
            self.table.selectRow(select)
        total = sum(s.seconds(accel) for s in self.steps)
        self.total_label.setText(f"{len(self.steps)} steps · ≈ {total:.1f} s")
        self._update_editor_note()

    def update_form_fields(self):
        kind = self.action_box.currentData()
        self.turns_spin.setEnabled(kind == "ROT")
        self.rpm_spin.setEnabled(kind == "ROT")
        self.wait_spin.setEnabled(kind == "WAIT")

    def selected_index(self) -> int | None:
        rows = self.table.selectionModel().selectedRows()
        return rows[0].row() if rows else None

    def on_step_selected(self):
        i = self.selected_index()
        if i is None:
            return
        s = self.steps[i]
        self.action_box.setCurrentIndex([k for _, k in ACTIONS].index(s.kind))
        if s.kind == "ROT":
            self.turns_spin.setValue(s.deg / 360)
            self.rpm_spin.setValue(s.rpm)
        elif s.kind == "WAIT":
            self.wait_spin.setValue(s.ms / 1000)

    def step_from_form(self) -> Step | None:
        kind = self.action_box.currentData()
        if kind == "ROT":
            if self.turns_spin.value() == 0:
                self.log("warn", "a rotation of 0 turns does nothing")
                return None
            return Step("ROT", deg=round(self.turns_spin.value() * 360, 3), rpm=self.rpm_spin.value())
        if kind == "WAIT":
            return Step("WAIT", ms=round(self.wait_spin.value() * 1000))
        return Step(kind)

    def add_step(self):
        if len(self.steps) >= self.limits["MAX_STEPS"]:
            self.log("warn", f"a program holds at most {self.limits['MAX_STEPS']} steps")
            return
        step = self.step_from_form()
        if step:
            i = self.selected_index()
            pos = len(self.steps) if i is None else i + 1
            self.steps.insert(pos, step)
            self.mark_dirty()
            self._refresh_steps(select=pos)

    def replace_step(self):
        i = self.selected_index()
        step = self.step_from_form() if i is not None else None
        if step:
            self.steps[i] = step
            self.mark_dirty()
            self._refresh_steps(select=i)

    def remove_step(self):
        i = self.selected_index()
        if i is not None:
            del self.steps[i]
            self.mark_dirty()
            self._refresh_steps(select=min(i, len(self.steps) - 1))

    def move_step(self, delta: int):
        i = self.selected_index()
        if i is None or not 0 <= i + delta < len(self.steps):
            return
        self.steps[i], self.steps[i + delta] = self.steps[i + delta], self.steps[i]
        self.mark_dirty()
        self._refresh_steps(select=i + delta)

    def current_program(self) -> Program:
        return Program(self.name_edit.text().strip(), list(self.steps))

    def _update_editor_note(self):
        """Refuse rather than fail: Save / Run are only enabled when they can succeed,
        and the line under them says why not."""
        if not hasattr(self, "run_btn"):
            return
        conn, idle = self.link is not None, not self.pending
        errors = self.current_program().validate(self.limits) if self.current_slot else []
        slot = self.current_slot
        if not slot:
            reason, is_err = "Choose a slot in the list.", False
        elif not self.steps and not self.name_edit.text().strip():
            reason, is_err = "Name the program and add steps.", False
        elif errors:
            reason, is_err = errors[0], True
        elif not conn:
            reason, is_err = "Connect to save or run.", False
        elif self.dirty:
            reason, is_err = "Unsaved changes — save before running.", False
        elif slot not in self.slot_names:
            reason, is_err = "This slot is empty on the controller.", False
        elif not self._driver_ok():
            reason, is_err = "The driver does not answer (24V off?) — cannot run.", True
        else:
            reason, is_err = f"The robot runs this program with  platter.exe run {slot}", False
        self.editor_note.setObjectName("MutedErr" if is_err else "Muted")
        self.editor_note.setText(reason)
        self.editor_note.style().unpolish(self.editor_note)
        self.editor_note.style().polish(self.editor_note)

        can_save = conn and idle and bool(slot) and not errors
        can_run = (conn and idle and bool(slot) and not self.dirty and slot in self.slot_names
                   and self._driver_ok())
        for btn, target in ((self.save_btn, can_save), (self.run_btn, can_run)):
            if btn.isEnabled() != target:
                btn.setEnabled(target)

    def save_slot(self):
        slot, program = self.current_slot, self.current_program()
        link = self.link

        def done(_):
            self.slot_names[slot] = program.name
            self._refresh_slot_list()
            self.dirty = False
            self.log("ok", f"slot {slot} saved “{program.name}” — robot: platter.exe run {slot}")
            self._update_editor_note()
        self.submit(Job(f"saving slot {slot}", lambda: link.set_program(slot, program), done,
                        tx=f"PSET {slot} {program.to_text()}"))

    def run_slot(self):
        slot = self.current_slot
        link, limits = self.link, dict(self.limits)
        self.submit(Job(f"running slot {slot}", lambda: link.run_program(slot, limits),
                        lambda _: self.log("ok", f"program {slot} finished"),
                        tx=f"RUN {slot}", motion=True))

    # ================================================================ shutdown

    def closeEvent(self, event: QtGui.QCloseEvent):
        if self.dirty and not self.confirm("Unsaved changes", "Quit without saving the program?"):
            event.ignore()
            return
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("splitter", self.splitter.saveState())
        self.poll_timer.stop()
        self.disconnect_port()
        self.thread.quit()
        self.thread.wait(2000)
        event.accept()


def main():
    if sys.platform == "win32":
        # own taskbar group + icon instead of python.exe's
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("GamidorDiagnostics.PetriPlatter")
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")    # honours the stylesheet's sub-controls; the Windows 11 style does not
    app.setWindowIcon(QtGui.QIcon(asset("app.ico")))
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
