"""
petriturn — command-line bridge between the robot and the PetriTurn ESP32.

Usage:
    petriturn run <slot>                    run a stored program, block until it ends
    petriturn rotate <turns> <rpm> cw|ccw   rotate without a program, block until it ends
    petriturn hold                          lock the dish (motor energised)
    petriturn release                       free the dish (turns by hand)
    petriturn stop                          decelerate and stop a motion
    petriturn status                        print driver/motor status
    petriturn list                          list stored programs
    petriturn ping
    petriturn ports                         list the serial ports on this PC

    cw / ccw = clockwise / counter-clockwise, looking down at the dish.
    enable / disable are kept as aliases of hold / release.

Options:
    --port COM6                    serial port for this call only (default: petriturn.ini)

Settings (port, baud rate, timeouts) live in petriturn.ini, and every call is logged (command,
all serial traffic, result, exit code) to logs/<date>_robot_001.log - a new part every day or
every [logs] max_mb. Both in C:\\ProgramData\\PetriTurn once installed.

Exit codes:
    0 = OK
    1 = timeout / no reply / port error / device error / stopped
    2 = bad command, bad arguments or empty slot

Programs are created with petriturn_gui.

Build the exe (from the project root, with the project's .venv):
    .venv\\Scripts\\pyinstaller --onefile --name petriturn host\\petriturn.py
"""

from __future__ import annotations

import argparse
import sys
import time

import serial

from petriturn_link import (BAD_REQUEST_REASONS, ConfigError, PetriTurnError, PetriTurnLink, list_ports,
                          load_config)
from petriturn_log import DEFAULT_MAX_MB, AuditLog

VERSION = "1.1"

EXIT_OK, EXIT_FAIL, EXIT_BAD_CMD = 0, 1, 2


class _Parser(argparse.ArgumentParser):
    log: AuditLog | None = None

    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"ERR {message}", file=sys.stderr)
        if _Parser.log:
            _Parser.log.write("error", f"ERR {message}")
        sys.exit(EXIT_BAD_CMD)


def parse_args():
    p = _Parser(prog="petriturn")
    p.add_argument("--port", help="serial port for this call only (default: petriturn.ini)")
    sub = p.add_subparsers(dest="action", required=True)
    run = sub.add_parser("run")
    run.add_argument("slot", type=int)
    rot = sub.add_parser("rotate")
    rot.add_argument("turns", type=positive_float, help="dish revolutions, e.g. 2 or 0.25")
    rot.add_argument("rpm", type=positive_float, help="speed, revolutions per minute")
    rot.add_argument("direction", type=str.lower, choices=("cw", "ccw"),
                     help="cw = clockwise, ccw = counter-clockwise (looking down at the dish)")
    for name in ("hold", "release", "enable", "disable", "stop", "list", "status", "ping", "ports"):
        sub.add_parser(name)
    return p.parse_args()


def positive_float(text: str) -> float:
    value = float(text)
    if not value > 0:
        raise argparse.ArgumentTypeError(f"must be greater than 0: {text}")
    return value


def execute(link: PetriTurnLink, args) -> str:
    """Runs the action; returns the text to print."""
    if args.action == "run":
        link.run_program(args.slot)
        return "OK"
    if args.action == "rotate":
        # firmware convention: positive degrees = clockwise seen from above
        deg = round(args.turns * 360, 3) * (1 if args.direction == "cw" else -1)
        link.rotate(deg, args.rpm)
        return "OK"
    if args.action == "list":
        programs = link.list_programs()
        return "\n".join(f"{slot}\t{name}" for slot, name in sorted(programs.items())) or "(no programs)"
    if args.action == "status":
        return "OK " + " ".join(f"{k}={v}" for k, v in link.status().items())
    {"hold": link.enable, "enable": link.enable, "release": link.disable, "disable": link.disable,
     "stop": lambda: link.command("STOP"), "ping": link.ping}[args.action]()
    return "OK"


def main(log: AuditLog) -> int:
    args = parse_args()
    if args.action == "ports":
        text = "\n".join(list_ports()) or "(no serial ports)"
        print(text)
        log.write("result", "ports: " + text.replace("\n", ", "))
        return EXIT_OK

    try:
        cfg = load_config()
    except ConfigError as e:
        return fail(log, f"ERR {e}", EXIT_FAIL)
    log.max_bytes = int(cfg.log_max_mb * 1024 * 1024)
    port = args.port or cfg.port
    try:
        link = PetriTurnLink.from_config(cfg, port)
    except serial.SerialException as e:
        return fail(log, f"ERR cannot open {port}: {e}", EXIT_FAIL)
    link.trace = log.write
    log.write("port", f"{port} opened")

    try:
        out = execute(link, args)
        print(out)
        log.write("result", out.replace("\n", " | "))
        return EXIT_OK
    except PetriTurnError as e:
        return fail(log, f"ERR {e.reason}", EXIT_BAD_CMD if e.reason in BAD_REQUEST_REASONS else EXIT_FAIL)
    except TimeoutError as e:
        return fail(log, f"ERR timeout: {e}", EXIT_FAIL)
    except serial.SerialException as e:
        return fail(log, f"ERR port: {e}", EXIT_FAIL)
    except KeyboardInterrupt:
        link.send_stop()
        return fail(log, "ERR interrupted, STOP sent", EXIT_FAIL)
    finally:
        link.close()


def fail(log: AuditLog, message: str, code: int) -> int:
    print(message, file=sys.stderr)
    log.write("error", message)
    return code


def logged_main() -> int:
    log = AuditLog("robot", DEFAULT_MAX_MB)
    _Parser.log = log
    log.session_start(f"petriturn {VERSION} | command: petriturn {' '.join(sys.argv[1:])}")
    t0 = time.monotonic()
    code = EXIT_BAD_CMD
    try:
        code = main(log)
    except SystemExit as e:                 # argparse: bad command line
        code = e.code if isinstance(e.code, int) else EXIT_BAD_CMD
    log.write("exit", f"code {code} after {time.monotonic() - t0:.2f} s")
    if log.error:                           # the call itself still counts; say that it is unlogged
        print(f"WARN {log.error}", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(logged_main())
