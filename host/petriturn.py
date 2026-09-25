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

Settings (port, baud rate, timeouts) live in petriturn.ini next to this program.

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

import serial

from petriturn_link import (BAD_REQUEST_REASONS, ConfigError, PetriTurnError, PetriTurnLink, list_ports,
                          load_config)

EXIT_OK, EXIT_FAIL, EXIT_BAD_CMD = 0, 1, 2


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"ERR {message}", file=sys.stderr)
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


def main() -> int:
    args = parse_args()
    if args.action == "ports":
        print("\n".join(list_ports()) or "(no serial ports)")
        return EXIT_OK

    try:
        cfg = load_config()
    except ConfigError as e:
        print(f"ERR {e}", file=sys.stderr)
        return EXIT_FAIL
    port = args.port or cfg.port
    try:
        link = PetriTurnLink.from_config(cfg, port)
    except serial.SerialException as e:
        print(f"ERR cannot open {port}: {e}", file=sys.stderr)
        return EXIT_FAIL

    try:
        print(execute(link, args))
        return EXIT_OK
    except PetriTurnError as e:
        print(f"ERR {e.reason}", file=sys.stderr)
        return EXIT_BAD_CMD if e.reason in BAD_REQUEST_REASONS else EXIT_FAIL
    except TimeoutError as e:
        print(f"ERR timeout: {e}", file=sys.stderr)
        return EXIT_FAIL
    except serial.SerialException as e:
        print(f"ERR port: {e}", file=sys.stderr)
        return EXIT_FAIL
    except KeyboardInterrupt:
        link.send_stop()
        print("ERR interrupted, STOP sent", file=sys.stderr)
        return EXIT_FAIL
    finally:
        link.close()


if __name__ == "__main__":
    sys.exit(main())
