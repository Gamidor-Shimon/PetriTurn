"""
Layout of the PetriTurn controller on a breadboard-style PCB, with a netlist check
against WIRING.md and top / bottom drawings.

Run (from the project root):
    .venv\\Scripts\\python perfboard\\layout.py

The board
    A breadboard-style PCB, 89 x 52 mm, used whole (not cut). 30 rows. In every row A-E are
    joined and F-J are joined (like a breadboard); E and F are not. The power rails along both
    long sides are not used. The 90 deg USB-C adapter sits over rows ~3-8, in front of the XIAO.
    columns A..J   A-E | channel | F-J   (E to F = 3 x 2.54 mm, like a breadboard)
    rows    1..30  as printed on the board. Seen from above: row 1 at the top, A on the left.
    In the box row 1 is at the +Y end, column J (screw terminals) towards the motor.
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


def hole(h: str) -> tuple[str, int]:
    return h[0], int(h[1:])


# -----------------------------------------------------------------------------
# Components: pin -> hole
# -----------------------------------------------------------------------------
XIAO = {  # 2 x 7 female headers across the channel; parts side up, USB-C towards row 1.
    # As placed on the board (photo): D9 = D0, H9 = 5V (VUSB).
    "D0": "D9", "D1": "D10", "D2": "D11", "D3": "D12", "D4": "D13", "D5": "D14", "D6": "D15",
    "5V": "H9", "GND": "H10", "3V3": "H11", "D10": "H12", "D9": "H13", "D8": "H14", "D7": "H15",
}
TMC = {  # 2 x 8 female headers across the channel; potentiometer / EN end towards the XIAO.
    # As placed on the board (photo): D19 = EN, G19 = VM.
    "EN": "D19", "MS1": "D20", "MS2": "D21", "PDN": "D22", "USART": "D23", "CLK": "D24",
    "STEP": "D25", "DIR": "D26",
    "VM": "G19", "GND_P": "G20", "A2": "G21", "A1": "G22", "B1": "G23", "B2": "G24",
    "VDD": "G25", "GND_L": "G26",
}
R1 = {"1": "A13", "2": "A14"}        # 1k, standing: D4 strip -> D5 strip (D5 is wired to USART)
R2 = {"1": "A18", "2": "A19"}        # 10k, standing: 3.3V bus -> EN
C1 = {"+": "H28", "-": "H27"}       # 100uF / 35V, lying along column H towards row 30 (clear of the mounting screw)
# Screw terminals, 2.5 mm pitch (one pin per row, each pin on its own strip)
MOTOR = {"1": "J21", "2": "J22", "3": "J23", "4": "J24"}   # 4 pins, on the driver's A2..B2 strips
PWR = {"+24V": "J28", "0V": "J27"}                         # 2 pins: from the panel DC jack
PANEL = {"RST": "J1", "GND": "J2", "LED+": "J3"}           # 3 pins: panel RESET button and LED
ENPAD = {"wire": "H1"}   # thin wire from the EN pad under the XIAO -> the RST terminal strip
TERMINALS = [  # (holes, labels)
    ([MOTOR["1"], MOTOR["2"], MOTOR["3"], MOTOR["4"]], ["A2 blk", "A1 grn", "B1 red", "B2 blu"], 1),
    ([PWR["0V"], PWR["+24V"]], ["0V", "+24V"], 1),
    ([PANEL["RST"], PANEL["GND"], PANEL["LED+"]], ["RST", "GND", "LED+"], 1),
]

COMPONENTS = {"XIAO": XIAO, "TMC": TMC, "R1": R1, "R2": R2, "C1": C1, "MOTOR": MOTOR, "PWR": PWR,
              "PANEL": PANEL, "ENPAD": ENPAD}

# -----------------------------------------------------------------------------
# Wires (insulated). The strips do most of the work; these join the strips that must meet.
# (from, to, colour, what, side, drawing path through the gaps [(x, row)])
# -----------------------------------------------------------------------------
WIRES = [
    ("E18", "F18", "#e08a00", "3.3V bus: join both halves of row 18", "top", []),
    ("J11", "J18", "#e08a00", "XIAO 3V3 -> 3.3V bus", "bottom", [(11.5, 11.5), (11.5, 17.5)]),
    ("H18", "I25", "#e08a00", "3.3V bus -> VDD", "bottom", [(9.5, 18.5), (9.5, 24.5)]),
    ("C10", "C19", "#7a7a7a", "D1 -> EN", "bottom", [(2.5, 10.5), (2.5, 18.5)]),
    ("B11", "B25", "#1f6fd1", "D2 -> STEP", "bottom", [(1.5, 11.5), (1.5, 24.5)]),
    ("C12", "C26", "#1f6fd1", "D3 -> DIR", "bottom", [(3.5, 12.5), (3.5, 25.5)]),
    ("E14", "E23", "#7b3fb8", "D5 -> USART", "bottom", [(4.5, 14.5), (4.5, 22.5)]),
    ("E20", "F20", "#222222", "MS1 -> GND (across the channel)", "top", []),
    ("B20", "B21", "#222222", "MS2 -> MS1 / GND", "bottom", []),
    ("I20", "I26", "#222222", "power GND <-> logic GND", "bottom", [(10.3, 20.5), (10.3, 25.5)]),
    ("I10", "F26", "#222222", "XIAO GND -> GND", "bottom", [(10.7, 10.5), (10.7, 18.7), (7.5, 18.7), (7.5, 25.5)]),
    ("H19", "G28", "#d62d20", "+24V: terminal -> VM", "bottom", [(8.7, 19.5), (8.7, 27.5), (8.0, 27.5)]),
    ("J26", "I27", "#222222", "0V: terminal -> GND", "bottom", [(11.5, 26.5), (10.5, 26.8)]),
    ("G10", "G2", "#222222", "GND -> panel terminal", "bottom", [(7.5, 9.5), (7.5, 2.5)]),
    ("J12", "H3", "#2a9d3a", "LED+ -> panel terminal", "bottom", [(11.5, 11.5), (11.5, 4.5), (9.0, 3.5)]),
    ("A22", "A23", "#7b3fb8", "PDN <-> USART", "top", []),
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
    "USART": ["XIAO.D5", "R1.2", "TMC.USART", "TMC.PDN"],   # this driver talks on PDN (tested)
    "A2": ["TMC.A2", "MOTOR.1"], "A1": ["TMC.A1", "MOTOR.2"],
    "B1": ["TMC.B1", "MOTOR.3"], "B2": ["TMC.B2", "MOTOR.4"],
    "LED": ["XIAO.D10", "PANEL.LED+"],   # the panel LED has its own series resistor
}
EXPECTED["GND"] += ["PANEL.GND"]
EXPECTED["RESET"] = ["PANEL.RST", "ENPAD.wire"]
NOT_CONNECTED = ["TMC.CLK", "XIAO.D0", "XIAO.D6", "XIAO.5V",
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
        # XIAO: 21 x 17.5 mm (8.3 x 6.9 pitches) centred on its pins, USB-C at the row-1 end
        xc = (int(XIAO["D0"][1:]) + int(XIAO["D6"][1:])) / 2
        cx = (COL_X["D"] + COL_X["H"]) / 2
        ax.add_patch(Rectangle((cx - 3.44, xc - 4.13), 6.88, 8.26, fc="#2b2f36", ec="#000",
                               lw=1, alpha=0.9, zorder=5))
        ax.add_patch(Rectangle((cx - 0.9, xc - 4.13 - 0.6), 1.8, 0.9, fc="#c3c8ce", ec="#555", zorder=6))
        ax.text(cx, xc, "XIAO ESP32-C3", ha="center", va="center", color="white", fontsize=7, zorder=7)
        # TMC2209: 15.3 x 20.3 mm (6 x 8 pitches) centred on its pins, pot at the EN end
        tc = (int(TMC["EN"][1:]) + int(TMC["DIR"][1:])) / 2
        tx = (COL_X["D"] + COL_X["G"]) / 2
        ax.add_patch(Rectangle((tx - 3.01, tc - 4.0), 6.02, 8.0, fc="#1b1b1b", ec="#000", lw=1,
                               alpha=0.9, zorder=5))
        ax.add_patch(Circle((tx + 1.0, tc - 3.2), 0.45, fc="#c7c7c7", zorder=6))
        ax.text(tx, tc, "TMC2209", ha="center", va="center", color="white", fontsize=7, zorder=7)
        # resistors: lying ones drawn between their holes, standing ones as a short body
        for pm, name, fc in ((R1, "R1 1kΩ", "#d8c7a0"), (R2, "R2 10kΩ", "#9fc0e8"),
                             ):
            (x1, y1), (x2, y2) = xy(pm["1"], False), xy(pm["2"], False)
            ax.plot([x1, x2], [y1, y2], color="#888", lw=1.2, zorder=6)
            lo, hi = min(y1, y2), max(y1, y2)
            if hi - lo > 1:
                mid = (lo + hi) / 2
                ax.add_patch(FancyBboxPatch((x1 - 0.3, mid - 0.9), 0.6, 1.8, boxstyle="round,pad=0.02",
                                            fc=fc, ec="#555", zorder=7))
                ax.text(x1 + 0.75, mid, name, rotation=90, fontsize=5.3, va="center", zorder=7)
            else:
                ax.add_patch(FancyBboxPatch((x1 - 0.35, lo + 0.1), 0.7, 0.8, boxstyle="round,pad=0.02",
                                            fc=fc, ec="#555", zorder=7))
                ax.text(x1 - 0.6, lo + 0.5, name + " (standing)", fontsize=4.8, ha="right",
                        va="center", zorder=7)
        (cxp, cyp), (cxm, cym) = xy(C1["+"], False), xy(C1["-"], False)
        ax.add_patch(Rectangle((cxp - 1.57, max(cyp, cym) + 0.3), 3.14, 4.7, fc="#27303b", ec="#111",
                               alpha=0.9, zorder=6.8))
        ax.text(cxp, max(cyp, cym) + 2.6, "C1 100µF (lying)", color="white", fontsize=4.6,
                ha="center", va="center", rotation=90, zorder=7)
        ax.text(cxp - 0.6, cyp, "+", color="#d62d20", fontsize=8, fontweight="bold", zorder=7)
        for holes, labels, face in TERMINALS:
            pts = [xy(h, False) for h in holes]
            x = pts[0][0]
            ys = [p[1] for p in pts]
            x0 = x - 1.0 if face > 0 else x - 1.8
            ax.add_patch(Rectangle((x0, min(ys) - 1.0), 2.8, max(ys) - min(ys) + 2.0, fc="#2f6fb0",
                                   ec="#123", alpha=0.85, zorder=6))
            for (hx, hy), t in zip(pts, labels):
                pin_dot(holes[ys.index(hy)], "", "#e6c86e")
                ax.text(x0 + 1.4, hy + 0.55, t, fontsize=4.6, ha="center", va="center",
                        fontweight="bold", color="white", zorder=9)
        ex, ey = xy(ENPAD["wire"], False)
        ax.plot([ex, ex - 0.6, (COL_X["D"] + COL_X["H"]) / 2], [ey, ey + 1.5, (int(XIAO['D0'][1:]) + int(XIAO['D6'][1:])) / 2],
                color="#9b59b6", lw=1.2, ls="--", zorder=7.5)
        ax.text(ex - 0.8, ey + 0.2, "EN pad wire", fontsize=4.5, ha="right", color="#9b59b6", zorder=9)
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

    ax.set_xlim(-mx - 3.6, X_MAX + mx + 3.4)
    ax.set_ylim(1 - my - 1.4, ROWS + my + 1.4)
    ax.set_aspect("equal")
    ax.invert_yaxis()                     # row 1 at the top, like the numbers printed on the board
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
    draw(False, HERE / "top.png", "TOP (components) — row 1 at the top, A on the left (as printed)")
    draw(True, HERE / "bottom.png", "BOTTOM (solder side) — row 1 at the top, A on the RIGHT")
    print("wrote", HERE / "top.png", "and", HERE / "bottom.png")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
