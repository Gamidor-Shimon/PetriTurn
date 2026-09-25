"""
Layout of the SBS PetriPlater controller on a breadboard-style PCB, with a netlist check
against WIRING.md and top / bottom drawings.

Run (from the project root):
    .venv\\Scripts\\python perfboard\\layout.py

The board
    A breadboard-style PCB, 89 x 52 mm, used whole (not cut). 30 rows. In every row A-E are
    joined and F-J are joined (like a breadboard); E and F are not. The power rails along both
    long sides are not used. Rows 1-6 stay empty: the 90 deg USB-C adapter sits over them.
    columns A..J   A-E | channel | F-J   (E to F = 3 x 2.54 mm, like a breadboard)
    rows    1..30  row 1 at the -Y end; the XIAO's USB-C looks towards row 1
The XIAO and the TMC2209 straddle the channel, exactly like on the test breadboard.
"""

from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Circle, FancyBboxPatch, Rectangle  # noqa: E402

HERE = Path(__file__).parent
PITCH = 2.54
GAP = 3                      # E -> F distance in pitches (check: 7.6 mm between hole centres)
COLS = "ABCDEFGHIJ"
COL_X = {c: (i if i < 5 else i + GAP - 1) for i, c in enumerate(COLS)}   # A0..E4, F7..J11
ROWS = 30
BOARD_W, BOARD_H = 52.0, 89.0
MOUNT_DY = 73.5          # the board's 2 mounting holes, on the channel line, this far apart
DY = 6                   # the layout starts 6 rows in (rows 1-6: room for the USB adapter)


def hole(h: str) -> tuple[str, int]:
    return h[0], int(h[1:])


# -----------------------------------------------------------------------------
# Components: pin -> hole
# -----------------------------------------------------------------------------
XIAO = {  # 2 x 7 female headers across the channel; USB-C towards row 1 (the USB wall)
    "5V": "D7", "GND": "D8", "3V3": "D9", "D10": "D10", "D9": "D11", "D8": "D12", "D7": "D13",
    "D0": "H7", "D1": "H8", "D2": "H9", "D3": "H10", "D4": "H11", "D5": "H12", "D6": "H13",
}
TMC = {  # 2 x 8 female headers across the channel; potentiometer / EN end towards the XIAO
    "EN": "G16", "MS1": "G17", "MS2": "G18", "PDN": "G19", "USART": "G20", "CLK": "G21",
    "STEP": "G22", "DIR": "G23",
    "VM": "D16", "GND_P": "D17", "A2": "D18", "A1": "D19", "B1": "D20", "B2": "D21",
    "VDD": "D22", "GND_L": "D23",
}
R1 = {"1": "J11", "2": "J20"}        # 1k, lying along column J: D4 strip -> USART strip
R2 = {"1": "I15", "2": "I16"}        # 10k, standing: 3.3V bus -> EN
C1 = {"+": "A16", "-": "A17"}       # 100uF / 35V, lying flat, body pointing out past the edge
MOTOR = {"1": "B18", "2": "B19", "3": "B20", "4": "B21"}   # JST-XH 4: black, green, red, blue
PWR = {"+24V": "C16", "0V": "C17"}  # wires from the DC jack
R3 = {"1": "B10", "2": "B14"}         # 330R, lying along column B: D10 strip -> LED wire
PANEL = {"LED+": "A14", "LED-": "A8", "BTN": "B8"}   # wires to the panel LED and RESET button
# (the RESET button's other wire goes straight to the EN pad under the XIAO, not to the board)

COMPONENTS = {"XIAO": XIAO, "TMC": TMC, "R1": R1, "R2": R2, "C1": C1, "MOTOR": MOTOR, "PWR": PWR,
              "R3": R3, "PANEL": PANEL}

# -----------------------------------------------------------------------------
# Wires (insulated). The strips do most of the work; these join the strips that must meet.
# (from, to, colour, what, side, drawing path through the gaps [(x, row)])
# -----------------------------------------------------------------------------
WIRES = [
    ("E15", "F15", "#e08a00", "3.3V bus: join both halves of row 15", "top", []),
    ("C9", "C15", "#e08a00", "XIAO 3V3 -> 3.3V bus", "bottom", []),
    ("B15", "B22", "#e08a00", "3.3V bus -> VDD", "bottom", [(0.5, 15.5), (0.5, 21.5)]),
    ("J8", "H16", "#7a7a7a", "D1 -> EN", "bottom", [(10.5, 8.5), (10.5, 15.5)]),
    ("F9", "F22", "#1f6fd1", "D2 -> STEP", "bottom", [(6.5, 9.5), (6.5, 21.5)]),
    ("I10", "I23", "#1f6fd1", "D3 -> DIR", "bottom", [(9.5, 10.5), (9.5, 22.5)]),
    ("I12", "H20", "#7b3fb8", "D5 -> USART", "bottom", [(8.5, 12.5), (8.5, 19.5)]),
    ("E17", "F17", "#222222", "MS1 -> GND (across the channel)", "top", []),
    ("I18", "I17", "#222222", "MS2 -> MS1 / GND", "bottom", []),
    ("B17", "B23", "#222222", "power GND <-> logic GND", "bottom", [(1.5, 17.5), (1.5, 22.5)]),
    ("C8", "C23", "#222222", "XIAO GND -> GND", "bottom", [(2.5, 8.5), (2.5, 22.5)]),
]

# -----------------------------------------------------------------------------
# Expected nets (WIRING.md)
# -----------------------------------------------------------------------------
EXPECTED = {
    "VM +24V": ["TMC.VM", "C1.+", "PWR.+24V"],
    "GND": ["TMC.GND_P", "TMC.GND_L", "C1.-", "PWR.0V", "XIAO.GND", "TMC.MS1", "TMC.MS2"],
    "3V3": ["XIAO.3V3", "TMC.VDD", "R2.1"],
    "EN": ["XIAO.D1", "TMC.EN", "R2.2"],
    "STEP": ["XIAO.D2", "TMC.STEP"],
    "DIR": ["XIAO.D3", "TMC.DIR"],
    "TX": ["XIAO.D4", "R1.1"],
    "USART": ["XIAO.D5", "R1.2", "TMC.USART"],
    "A2": ["TMC.A2", "MOTOR.1"], "A1": ["TMC.A1", "MOTOR.2"],
    "B1": ["TMC.B1", "MOTOR.3"], "B2": ["TMC.B2", "MOTOR.4"],
    "LED": ["XIAO.D10", "R3.1"],
    "LED anode": ["R3.2", "PANEL.LED+"],
}
EXPECTED["GND"] += ["PANEL.LED-", "PANEL.BTN"]
NOT_CONNECTED = ["TMC.PDN", "TMC.CLK", "XIAO.D0", "XIAO.D6", "XIAO.5V",
                 "XIAO.D9", "XIAO.D8", "XIAO.D7"]


def check() -> list[str]:
    parent: dict[str, str] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        parent[find(a)] = find(b)

    pins = {f"{comp}.{pin}": h for comp, pm in COMPONENTS.items() for pin, h in pm.items()}
    used = defaultdict(list)
    for name, h in pins.items():
        used[h].append(name)
    for a, b, *_ in WIRES:
        used[a].append(f"wire {a}-{b}")
        used[b].append(f"wire {a}-{b}")
    problems = [f"hole {h} used twice: {', '.join(n)}" for h, n in used.items() if len(n) > 1]
    # the copper strips
    for r in range(1, ROWS + 1):
        for half in ("ABCDE", "FGHIJ"):
            for c in half[1:]:
                union(f"{half[0]}{r}", f"{c}{r}")
    for a, b, *_ in WIRES:
        union(a, b)

    net_of = {name: find(h) for name, h in pins.items()}
    for net, members in EXPECTED.items():
        if len({net_of[m] for m in members}) != 1:
            problems.append(f"net {net} is split: " + ", ".join(f"{m}@{pins[m]}" for m in members))
    root_net = {find(pins[m[0]]): net for net, m in EXPECTED.items()}
    for name, root in net_of.items():
        owner = [net for net, m in EXPECTED.items() if name in m]
        if owner and root_net.get(root) not in owner:
            problems.append(f"{name} ended up in the wrong net")
        if name in NOT_CONNECTED:
            others = [n for n, r in net_of.items() if r == root and n != name]
            if others:
                problems.append(f"{name} must stay unconnected, but shares a strip with {others}")
    merged = defaultdict(list)
    for net, m in EXPECTED.items():
        merged[find(pins[m[0]])].append(net)
    problems += [f"SHORT between nets {', '.join(n)}" for n in merged.values() if len(n) > 1]
    return problems


# -----------------------------------------------------------------------------
# Drawing
# -----------------------------------------------------------------------------
X_MAX = COL_X["J"]


def xy(h: str, mirror: bool) -> tuple[float, float]:
    c, r = hole(h)
    x = COL_X[c]
    return (X_MAX - x if mirror else x), r


def draw(mirror: bool, path: Path, title: str):
    fig, ax = plt.subplots(figsize=(7.4, 12.5), dpi=130)
    mx = (BOARD_W / PITCH - X_MAX) / 2
    my = (BOARD_H / PITCH - (ROWS - 1)) / 2
    ax.add_patch(FancyBboxPatch((-mx, 1 - my), X_MAX + 2 * mx, ROWS - 1 + 2 * my,
                                boxstyle="round,pad=0,rounding_size=0.3", fc="#1d1f22",
                                ec="#555", lw=1.2, zorder=0))
    ax.add_patch(Rectangle(((X_MAX - COL_X["F"] if mirror else COL_X["E"]) + 0.6, 1 - my),
                           GAP - 1.2, ROWS - 1 + 2 * my, fc="#111214", ec="none", zorder=0.5))
    for r in range(1, ROWS + 1):          # copper strips
        for a, b in (("A", "E"), ("F", "J")):
            xa, xb = sorted((xy(f"{a}{r}", mirror)[0], xy(f"{b}{r}", mirror)[0]))
            ax.plot([xa, xb], [r, r], color="#b8893a", lw=5, alpha=0.55, solid_capstyle="round",
                    zorder=1)
        for c in COLS:
            x, _ = xy(f"{c}{r}", mirror)
            ax.add_patch(Circle((x, r), 0.2, fc="#d9a441", ec="none", zorder=2))
        ax.text(-mx - 0.55 if not mirror else X_MAX + mx + 0.55, r, str(r), ha="center",
                va="center", fontsize=6.5, color="#333")
    for rail_x in (-3.2, -2.2, X_MAX + 2.2, X_MAX + 3.2):      # power rails - not used
        x = X_MAX - rail_x if mirror else rail_x
        ax.plot([x, x], [1, ROWS], color="#6b5a3a", lw=3, alpha=0.35, zorder=1)
        for r in range(1, ROWS + 1):
            ax.add_patch(Circle((x, r), 0.16, fc="#8a7650", ec="none", zorder=2))
    ax.text(X_MAX - (-2.7) if mirror else -2.7, ROWS + my - 0.2, "rails\n(unused)",
            ha="center", va="top", fontsize=4.5, color="#bbb")
    ch = X_MAX - (COL_X["E"] + COL_X["F"]) / 2 if mirror else (COL_X["E"] + COL_X["F"]) / 2
    mid = (1 + ROWS) / 2
    for dy in (-MOUNT_DY / 2 / PITCH, MOUNT_DY / 2 / PITCH):
        ax.add_patch(Circle((ch, mid + dy), 0.6, fc="#1d1f22", ec="#d9a441", lw=1.5, zorder=3))
    for c in COLS:
        x, _ = xy(f"{c}1", mirror)
        ax.text(x, 1 - my - 0.7, c, ha="center", va="center", fontsize=8, fontweight="bold")
        ax.text(x, ROWS + my + 0.7, c, ha="center", va="center", fontsize=8, fontweight="bold")

    def pin_dot(h, label, fc="#e6c86e"):
        x, y = xy(h, mirror)
        ax.add_patch(Circle((x, y), 0.34, fc=fc, ec="white", lw=0.6, zorder=8))
        if label:
            ax.text(x, y, label, ha="center", va="center", fontsize=4.6, zorder=9)

    if not mirror:
        # XIAO: 21 x 17.5 mm across the channel, USB-C over row 1
        cx = (COL_X["D"] + COL_X["H"]) / 2
        ax.add_patch(Rectangle((cx - 3.44, 0.87 + DY), 6.88, 8.26, fc="#2b2f36", ec="#000",
                               lw=1, alpha=0.9, zorder=5))
        ax.add_patch(Rectangle((cx - 0.9, 0.2 + DY), 1.8, 0.9, fc="#c3c8ce", ec="#555", zorder=6))
        ax.text(cx, 4.2 + DY, "XIAO\nESP32-C3\n↓ USB-C", ha="center", va="center", color="white",
                fontsize=7, zorder=7)
        # TMC2209: 15.3 x 20.3 mm across the channel, pot towards the XIAO
        tx = (COL_X["D"] + COL_X["G"]) / 2
        ax.add_patch(Rectangle((tx - 3.01, 9.5 + DY), 6.02, 8.0, fc="#1b1b1b", ec="#000", lw=1,
                               alpha=0.9, zorder=5))
        ax.add_patch(Circle((tx - 1.0, 10.3 + DY), 0.45, fc="#c7c7c7", zorder=6))
        ax.text(tx, 14.2 + DY, "TMC2209\nheatsink up", ha="center", va="center", color="white",
                fontsize=7, zorder=7)
        # R1 along column J, R2 standing, C1 lying flat past the edge, JST, 24V wires
        (x1, y1), (x2, y2) = xy(R1["1"], False), xy(R1["2"], False)
        ax.plot([x1, x2], [y1, y2], color="#888", lw=1.2, zorder=6)
        ax.add_patch(FancyBboxPatch((x1 - 0.3, 8.2 + DY), 0.6, 2.6, boxstyle="round,pad=0.02",
                                    fc="#d8c7a0", ec="#555", zorder=7))
        ax.text(x1 + 0.75, 9.5 + DY, "R1 1kΩ", rotation=90, fontsize=5.5, va="center", zorder=7)
        rx, _ = xy(R2["1"], False)
        ax.add_patch(FancyBboxPatch((rx - 0.35, 9.1 + DY), 0.7, 0.8, boxstyle="round,pad=0.02",
                                    fc="#9fc0e8", ec="#555", zorder=7))
        ax.text(rx + 0.2, 8.35 + DY, "R2 10kΩ\n(standing)", fontsize=4.8, ha="center", zorder=7)
        ax.add_patch(Rectangle((-3.4, 9.9 + DY), 3.0, 1.2, fc="#27303b", ec="#111", zorder=6))
        ax.plot([-0.4, 0], [10 + DY, 10 + DY], color="#999", lw=1, zorder=6)
        ax.plot([-0.4, 0], [11 + DY, 11 + DY], color="#999", lw=1, zorder=6)
        ax.text(-1.9, 10.5 + DY, "C1 100µF", color="white", fontsize=4.6, ha="center",
                va="center", zorder=7)
        ax.text(-0.5, 9.35 + DY, "+", color="#d62d20", fontsize=8, fontweight="bold", zorder=7)
        bx, _ = xy(MOTOR["1"], False)
        ax.add_patch(Rectangle((bx - 1.13, 11.57 + DY), 2.26, 3.86, fc="#f4f1e6", ec="#777",
                               alpha=0.9, zorder=6))
        for h, t in ((MOTOR["1"], "1 blk"), (MOTOR["2"], "2 grn"), (MOTOR["3"], "3 red"),
                     (MOTOR["4"], "4 blu")):
            pin_dot(h, t, "#f4f1e6")
        (x1, y1), (x2, y2) = xy(R3["1"], False), xy(R3["2"], False)
        ax.plot([x1, x2], [y1, y2], color="#888", lw=1.2, zorder=6)
        ax.add_patch(FancyBboxPatch((x1 - 0.3, 5.1 + DY), 0.6, 1.8, boxstyle="round,pad=0.02",
                                    fc="#e8b4b4", ec="#555", zorder=7))
        ax.text(x1 - 0.75, 6.0 + DY, "R3 330Ω", rotation=90, fontsize=5.3, va="center", zorder=7)
        for h, t, col in ((PANEL["LED+"], "LED+", "#2a9d3a"), (PANEL["LED-"], "LED−", "#222"),
                          (PANEL["BTN"], "RESET", "#555")):
            x, y = xy(h, False)
            ax.plot([x, -mx - 1.6], [y, y + (0.35 if t == "RESET" else 0)], color=col, lw=1.8, zorder=6)
            ax.text(-mx - 1.7, y + (0.35 if t == "RESET" else 0), t, fontsize=5, ha="right",
                    va="center", color=col, fontweight="bold", zorder=9)
        for h, t, col in ((PWR["+24V"], "+24V", "#d62d20"), (PWR["0V"], "0V", "#222")):
            x, y = xy(h, False)
            ax.add_patch(Circle((x, y), 0.3, fc=col, zorder=8))
            ax.text(x + 0.15, y + 0.52, t, fontsize=5, color=col, fontweight="bold", zorder=9)
        for pin, h in XIAO.items():
            pin_dot(h, pin)
        for pin, h in TMC.items():
            pin_dot(h, pin.replace("GND_P", "GND").replace("GND_L", "GND"))
        for a, b, colour, what, side, via in WIRES:
            if side == "top":
                (xa, ya), (xb, yb) = xy(a, False), xy(b, False)
                ax.plot([xa, xb], [ya, yb], color="white", lw=4.2, zorder=6.4)
                ax.plot([xa, xb], [ya, yb], color=colour, lw=2.4, zorder=6.5)
    else:
        for a, b, colour, what, side, via in WIRES:
            if side != "bottom":
                continue
            pts = [xy(a, True)] + [(X_MAX - x, r) for x, r in via] + [xy(b, True)]
            xs, ys = zip(*pts)
            ax.plot(xs, ys, color="white", lw=4.2, zorder=5.9, solid_capstyle="round")
            ax.plot(xs, ys, color=colour, lw=2.4, zorder=6, solid_capstyle="round")
            for h in (a, b):
                x, y = xy(h, True)
                ax.add_patch(Circle((x, y), 0.3, fc=colour, ec="white", lw=0.8, zorder=7))
        for comp, pm in COMPONENTS.items():
            for pin, h in pm.items():
                x, y = xy(h, True)
                ax.add_patch(Circle((x, y), 0.26, fc="#c9ced4", ec="#333", lw=0.6, zorder=8))
                short = pin.replace("GND_P", "GND").replace("GND_L", "GND")
                lab = short if comp in ("XIAO", "TMC") else f"{comp}.{short}"
                ax.text(x, y - 0.5, lab, ha="center", va="center", fontsize=4.3, color="white",
                        zorder=9)

    ax.set_xlim(-mx - 3.6, X_MAX + mx + 1.4)
    ax.set_ylim(1 - my - 1.4, ROWS + my + 1.4)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(title, fontsize=10)
    fig.tight_layout()
    fig.savefig(path, facecolor="white")
    plt.close(fig)


def main():
    problems = check()
    print("netlist check:", "OK - every net matches WIRING.md, no shorts, unused pins free"
          if not problems else "")
    for p in problems:
        print("  PROBLEM:", p)
    draw(False, HERE / "top.png", "TOP (components) — row 1 at the bottom, USB-C looks down")
    draw(True, HERE / "bottom.png", "BOTTOM (solder side) — mirrored left-right")
    print("wrote", HERE / "top.png", "and", HERE / "bottom.png")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
