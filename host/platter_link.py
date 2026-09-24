"""
Serial link to the PetriPlatter ESP32 + the program model. Shared by platter.py (robot CLI)
and platter_gui.py (program editor). Protocol is documented at the top of PetriPlatter.ino.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

import serial
import serial.tools.list_ports

BAUD = 115200
SHORT_TIMEOUT_S = 3.0     # commands that reply immediately
RUN_MARGIN_S = 10.0       # extra time on top of the estimated program duration

# Fallback limits, used until INFO is read from the controller (must match the firmware).
DEFAULT_LIMITS = {
    "SLOTS": 20, "MAX_STEPS": 32, "MIN_RPM": 0.1, "MAX_RPM": 120.0,
    "MAX_DEG": 36000.0, "MAX_WAIT_MS": 600000, "ACCEL": 1.0,
}
MAX_NAME = 24
NAME_FORBIDDEN = set("|,=\r\n")

# Firmware reasons that mean "the request was wrong", as opposed to a device failure.
BAD_REQUEST_REASONS = {
    "BAD_ARGS", "BAD_STEP", "BAD_NAME", "BAD_SLOT", "EMPTY_SLOT", "NO_STEPS",
    "TOO_MANY_STEPS", "DEG_RANGE", "RPM_RANGE", "WAIT_RANGE", "UNKNOWN_CMD", "LINE_TOO_LONG",
}


class PlatterError(Exception):
    """The controller answered ERR <reason>."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


# ------------------------------------------------------------------------------------
# Program model

STEP_KINDS = ("ROT", "WAIT", "HOLD", "RELEASE")


@dataclass
class Step:
    kind: str            # one of STEP_KINDS
    deg: float = 0.0     # ROT: degrees, negative = reverse
    rpm: float = 0.0     # ROT
    ms: int = 0          # WAIT

    def to_text(self) -> str:
        if self.kind == "WAIT":
            return f"WAIT {int(self.ms)}"
        if self.kind == "ROT":
            return f"ROT {self.deg:g} {self.rpm:g}"
        return self.kind

    @classmethod
    def from_text(cls, text: str) -> "Step":
        parts = text.split()
        if parts and parts[0] == "ROT" and len(parts) == 3:
            return cls("ROT", deg=float(parts[1]), rpm=float(parts[2]))
        if parts and parts[0] == "WAIT" and len(parts) == 2:
            return cls("WAIT", ms=int(float(parts[1])))
        if parts and parts[0] in ("HOLD", "RELEASE") and len(parts) == 1:
            return cls(parts[0])
        raise ValueError(f"bad step: {text!r}")

    def seconds(self, accel_rev_s2: float) -> float:
        """Upper bound on the step duration (trapezoid profile, ramp up + down)."""
        if self.kind == "WAIT":
            return self.ms / 1000.0
        if self.kind != "ROT" or self.rpm <= 0:
            return 0.0
        rev_s = self.rpm / 60.0
        return abs(self.deg) / 360.0 / rev_s + rev_s / accel_rev_s2


@dataclass
class Program:
    name: str
    steps: list[Step] = field(default_factory=list)

    def to_text(self) -> str:
        return "|".join([self.name] + [s.to_text() for s in self.steps])

    @classmethod
    def from_text(cls, text: str) -> "Program":
        name, *steps = text.split("|")
        return cls(name, [Step.from_text(s) for s in steps])

    def seconds(self, accel_rev_s2: float) -> float:
        return sum(s.seconds(accel_rev_s2) for s in self.steps)

    def validate(self, limits: dict) -> list[str]:
        """Human-readable problems; empty list = OK to save."""
        errors = []
        # the firmware limit is in bytes (UTF-8), so a Hebrew name gets ~12 letters
        if not self.name or len(self.name.encode("utf-8")) > MAX_NAME or NAME_FORBIDDEN & set(self.name):
            errors.append(f"Name must be 1-{MAX_NAME} bytes (Hebrew ≈ {MAX_NAME // 2} letters), without | , =")
        if not self.steps:
            errors.append("Program has no steps")
        if len(self.steps) > limits["MAX_STEPS"]:
            errors.append(f"Too many steps (max {limits['MAX_STEPS']})")
        for i, s in enumerate(self.steps, 1):
            if s.kind == "ROT":
                if abs(s.deg) > limits["MAX_DEG"]:
                    errors.append(f"Step {i}: max {limits['MAX_DEG'] / 360:g} turns")
                if not limits["MIN_RPM"] <= s.rpm <= limits["MAX_RPM"]:
                    errors.append(f"Step {i}: RPM must be {limits['MIN_RPM']:g}-{limits['MAX_RPM']:g}")
            elif s.kind == "WAIT" and not 0 <= s.ms <= limits["MAX_WAIT_MS"]:
                errors.append(f"Step {i}: wait must be 0-{limits['MAX_WAIT_MS'] / 1000:g} s")
        return errors


# ------------------------------------------------------------------------------------
# Serial link

def list_ports() -> list[str]:
    return [p.device for p in serial.tools.list_ports.comports()]


class PlatterLink:
    def __init__(self, port: str):
        # DTR/RTS must be low BEFORE open(), otherwise the ESP32 resets and drops the dish.
        self.ser = serial.Serial()
        self.ser.port = port
        self.ser.baudrate = BAUD
        self.ser.dtr = False
        self.ser.rts = False
        self.ser.timeout = 0.2
        self.ser.open()
        self.ser.reset_input_buffer()   # drop stale lines (e.g. boot banner)
        self._cmd_lock = threading.Lock()
        self._write_lock = threading.Lock()

    def close(self) -> None:
        self.ser.close()

    def _write(self, line: str) -> None:
        with self._write_lock:
            self.ser.write((line + "\n").encode("utf-8"))
            self.ser.flush()

    def command(self, cmd: str, timeout_s: float = SHORT_TIMEOUT_S) -> str:
        """Send one command; return the text after 'OK'. Raises PlatterError / TimeoutError."""
        with self._cmd_lock:
            self.ser.reset_input_buffer()
            self._write(cmd)
            deadline = time.monotonic() + timeout_s
            while time.monotonic() < deadline:
                raw = self.ser.readline()
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="replace").strip()
                if line == "OK" or line.startswith("OK "):
                    return line[3:]
                if line.startswith("ERR"):
                    raise PlatterError(line[4:] or "UNKNOWN")
                # anything else (e.g. '# ...' info lines) is ignored
            raise TimeoutError(f"no reply to {cmd.split()[0]} after {timeout_s:.1f}s")

    def send_stop(self) -> None:
        """Safe to call from another thread while RUN/ROT is waiting for its reply."""
        self._write("STOP")

    # --- convenience wrappers ---

    def ping(self) -> None:
        self.command("PING")

    def info(self) -> dict:
        limits = dict(DEFAULT_LIMITS)
        for kv in self.command("INFO").split():
            key, _, val = kv.partition("=")
            if key in limits:
                limits[key] = type(limits[key])(float(val))
        return limits

    def status(self) -> dict[str, str]:
        return dict(kv.partition("=")[::2] for kv in self.command("STATUS").split())

    def list_programs(self) -> dict[int, str]:
        text = self.command("PLIST")
        result = {}
        for item in filter(None, text.split(",")):
            slot, _, name = item.partition("=")
            result[int(slot)] = name
        return result

    def get_program(self, slot: int) -> Program:
        return Program.from_text(self.command(f"PGET {slot}"))

    def set_program(self, slot: int, program: Program) -> None:
        self.command(f"PSET {slot} {program.to_text()}")

    def delete_program(self, slot: int) -> None:
        self.command(f"PDEL {slot}")

    def run_program(self, slot: int, limits: dict | None = None) -> None:
        """Blocks until the program ends."""
        limits = limits or self.info()
        duration = self.get_program(slot).seconds(limits["ACCEL"])
        self.command(f"RUN {slot}", duration + RUN_MARGIN_S)

    def rotate(self, deg: float, rpm: float, limits: dict | None = None) -> None:
        limits = limits or self.info()
        duration = Step("ROT", deg=deg, rpm=rpm).seconds(limits["ACCEL"])
        self.command(f"ROT {deg:g} {rpm:g}", duration + RUN_MARGIN_S)

    def enable(self) -> None:
        self.command("EN")

    def disable(self) -> None:
        self.command("DIS")
