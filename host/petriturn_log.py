"""
Audit log for PetriTurn: every action of the robot CLI and the GUI is written to text files in a
"logs" folder next to the programs. Nothing is ever deleted or overwritten.

Files:  logs/2026-09-26_robot_001.log, logs/2026-09-26_gui_001.log, ...
        - a new file every day, per program (robot = petriturn.exe, gui = petriturn_gui.exe);
        - when a file reaches the size limit (petriturn.ini [logs] max_mb, default 5 MB) the next
          part starts: _002, _003, ...
Line:   2026-09-26 14:03:12.345 [pid 4812] [tx] ROT 90 10
        (the pid tells apart two robot calls that ran close together)

Opening, appending and closing the file for every line keeps it readable by other programs
while the GUI is open, and nothing is lost if a program is killed.
"""

from __future__ import annotations

import datetime
import getpass
import os
import platform
import sys
from pathlib import Path

DEFAULT_MAX_MB = 5.0


def program_dir() -> Path:
    """Next to the exe when frozen, next to the scripts otherwise."""
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent


class AuditLog:
    def __init__(self, source: str, max_mb: float = DEFAULT_MAX_MB, folder: Path | None = None):
        self.source = source                       # "robot" or "gui"
        self.max_bytes = int(max_mb * 1024 * 1024)
        self.folder = folder or program_dir() / "logs"
        self.pid = os.getpid()
        self.error: str | None = None              # last write error, None while all is well
        self.path: Path | None = None

    def _file_for(self, day: str, extra: int) -> Path:
        """Today's current part: the last one that still has room for `extra` bytes."""
        part = 1
        while True:
            path = self.folder / f"{day}_{self.source}_{part:03d}.log"
            if not path.exists() or path.stat().st_size + extra <= self.max_bytes:
                return path
            part += 1

    def write(self, tag: str, text: str) -> bool:
        """Append one line. Returns False (and keeps the reason in .error) if it could not."""
        now = datetime.datetime.now()
        line = f"{now:%Y-%m-%d %H:%M:%S}.{now.microsecond // 1000:03d} [pid {self.pid}] [{tag}] {text}\n"
        data = line.encode("utf-8")
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            self.path = self._file_for(f"{now:%Y-%m-%d}", len(data))
            with open(self.path, "ab") as fh:
                fh.write(data)
            self.error = None
            return True
        except OSError as e:
            self.error = f"cannot write the log in {self.folder}: {e}"
            return False

    def session_start(self, what: str) -> bool:
        """First line of a program run: who, where, which version."""
        try:
            user = getpass.getuser()
        except Exception:                          # no user name available (service account)
            user = "?"
        return self.write("start", f"{what} | user {user} | PC {platform.node()}")
