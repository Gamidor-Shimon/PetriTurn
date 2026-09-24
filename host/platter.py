"""
platter — command-line bridge between the robot and the PetriPlatter ESP32.

Usage:
    platter run <slot>             run a stored program, block until it ends   <- robot uses this
    platter list                   list stored programs
    platter rotate <deg> <rpm>     one-off rotation, block until it ends
    platter enable                 hold the dish (coils energised)
    platter disable                release the dish
    platter status                 print driver/motor status
    platter ping
    platter ports                  list the serial ports on this PC

Options:
    --port COM6                    serial port for this call only (default: platter.ini)

Settings (port, baud rate, timeouts) live in platter.ini next to this program.

Exit codes:
    0 = OK
    1 = timeout / no reply / port error / device error / stopped
    2 = bad command, bad arguments or empty slot

Programs are created with platter_gui.

Build the exe (from the project root, with the project's .venv):
    .venv\\Scripts\\pyinstaller --onefile --name platter host\\platter.py
"""

from __future__ import annotations

import argparse
import sys

import serial

from platter_link import (BAD_REQUEST_REASONS, ConfigError, PlatterError, PlatterLink, list_ports,
                          load_config)

EXIT_OK, EXIT_FAIL, EXIT_BAD_CMD = 0, 1, 2


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"ERR {message}", file=sys.stderr)
        sys.exit(EXIT_BAD_CMD)


def parse_args():
    p = _Parser(prog="platter")
    p.add_argument("--port", help="serial port for this call only (default: platter.ini)")
    sub = p.add_subparsers(dest="action", required=True)
    run = sub.add_parser("run")
    run.add_argument("slot", type=int)
    rot = sub.add_parser("rotate")
    rot.add_argument("deg", type=float)
    rot.add_argument("rpm", type=float)
    for name in ("list", "enable", "disable", "status", "ping", "ports"):
        sub.add_parser(name)
    return p.parse_args()


def execute(link: PlatterLink, args) -> str:
    """Runs the action; returns the text to print."""
    if args.action == "run":
        link.run_program(args.slot)
        return "OK"
    if args.action == "rotate":
        link.rotate(args.deg, args.rpm)
        return "OK"
    if args.action == "list":
        programs = link.list_programs()
        return "\n".join(f"{slot}\t{name}" for slot, name in sorted(programs.items())) or "(no programs)"
    if args.action == "status":
        return "OK " + " ".join(f"{k}={v}" for k, v in link.status().items())
    {"enable": link.enable, "disable": link.disable, "ping": link.ping}[args.action]()
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
        link = PlatterLink.from_config(cfg, port)
    except serial.SerialException as e:
        print(f"ERR cannot open {port}: {e}", file=sys.stderr)
        return EXIT_FAIL

    try:
        print(execute(link, args))
        return EXIT_OK
    except PlatterError as e:
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
