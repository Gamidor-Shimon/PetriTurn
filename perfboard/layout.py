"""
Perfboard layout for the SBS PetriPlater controller board: placement, bottom-side wiring,
a netlist check against WIRING.md, and top / bottom drawings.

Run (from the project root):
    .venv\\Scripts\\python perfboard\\layout.py

Board: 30 x 60 mm (a 30 x 70 board cut to 60), 2.54 mm grid, 10 columns x 22 rows.
    columns A..J  = x, A at the USB (-X) end of the box, J towards the motor
    rows    1..22 = y, row 1 at the -Y end, row 22 at the +Y end
The top view below is the board as it sits in the box, seen from above.
"""

from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Circle, FancyBboxPatch, Rectangle  # noqa: E402

HERE = Path(__file__).parent
COLS = "ABCDEFGHIJ"
ROWS = 22
PITCH = 2.54
BOARD_W, BOARD_H = 30.0, 60.0


def hole(name: str) -> tuple[int, int]:
    """'C14' -> (2, 14)"""
    return COLS.index(name[0]), int(name[1:])


# -----------------------------------------------------------------------------
# Components: pin name -> hole
# -----------------------------------------------------------------------------
XIAO = {  # on 2 x 7 female headers, USB-C at the board edge next to the USB wall (column A)
    "D0": "A14", "D1": "B14", "D2": "C14", "D3": "D14", "D4": "E14", "D5": "F14", "D6": "G14",
    "5V": "A20", "GND": "B20", "3V3": "C20", "D10": "D20", "D9": "E20", "D8": "F20", "D7": "G20",
}
TMC = {  # TMC2209 V985 on 2 x 8 female headers, potentiometer / EN end towards the XIAO
    "EN": "C10", "MS1": "C9", "MS2": "C8", "PDN": "C7", "USART": "C6", "CLK": "C5",
    "STEP": "C4", "DIR": "C3",
    "VM": "H10", "GND_P": "H9", "A2": "H8", "A1": "H7", "B1": "H6", "B2": "H5",
    "VDD": "H4", "GND_L": "H3",
}
R1 = {"1": "A12", "2": "E12"}          # 1k   D4 -> USART
R2 = {"1": "C11", "2": "G11"}          # 10k  EN -> 3.3V
C1 = {"+": "J10", "-": "J9"}           # 100uF / 35V, 6.3 mm, 2.5 mm leads
MOTOR = {"1": "J7", "2": "J6", "3": "J5", "4": "J4"}   # JST-XH 4: black, green, red, blue
PWR = {"+24V": "J12", "0V": "I8"}      # wires from the DC jack, soldered in (I9 is under C1)

COMPONENTS = {"XIAO": XIAO, "TMC": TMC, "R1": R1, "R2": R2, "C1": C1, "MOTOR": MOTOR, "PWR": PWR}

# -----------------------------------------------------------------------------
# Bottom side: solder bridges between neighbouring holes, and insulated wires
# -----------------------------------------------------------------------------
BRIDGES = [  # (from, to) along a straight line of holes - every hole in between joins
    ("B14", "B10"),   # D1 -> ...
    ("B10", "C10"),   # ... EN
    ("C11", "C10"),   # R2 pin 1 -> EN
    ("C9", "C8"),     # MS1 + MS2
    ("E14", "E12"),   # D4 -> R1 pin 2
    ("H10", "J10"),   # VM -> C1 +
    ("H9", "J9"),     # GND -> C1 -
    ("J12", "J11"),   # +24V -> ...
    ("J11", "J10"),   # ... VM / C1 +
    ("H3", "I3"),     # logic GND pad
    ("I8", "I9"),     # 0V in -> power GND
]
WIRES = [  # (from, to, colour, what[, drawing path through the gaps between holes (col, row)])
    ("F14", "C6", "#7b3fb8", "D5 -> USART"),
    ("A12", "C6", "#7b3fb8", "R1 -> USART"),
    ("C14", "C4", "#1f6fd1", "D2 -> STEP", [(2.5, 13.5), (2.5, 4.5)]),
    ("D14", "C3", "#1f6fd1", "D3 -> DIR", [(3.5, 13.5), (3.5, 3.5)]),
    ("G11", "C20", "#e08a00", "R2 -> 3.3V"),
    ("C20", "H4", "#e08a00", "3.3V -> VDD"),
    ("B20", "I3", "#222222", "GND (XIAO) -> GND (logic)"),
    ("C8", "I3", "#222222", "MS1/MS2 -> GND"),
    ("I3", "I9", "#222222", "logic GND <-> power GND"),
    ("H8", "J7", "#222222", "A2 -> motor 1 (black)"),
    ("H7", "J6", "#2a9d3a", "A1 -> motor 2 (green)"),
    ("H6", "J5", "#d62d20", "B1 -> motor 3 (red)"),
    ("H5", "J4", "#1f6fd1", "B2 -> motor 4 (blue)"),
]

# -----------------------------------------------------------------------------
# Expected nets (from WIRING.md) - every group must be connected, and nothing else
# -----------------------------------------------------------------------------
EXPECTED = {
    "VM +24V": ["TMC.VM", "C1.+", "PWR.+24V"],
    "GND": ["TMC.GND_P", "TMC.GND_L", "C1.-", "PWR.0V", "XIAO.GND", "TMC.MS1", "TMC.MS2"],
    "3V3": ["XIAO.3V3", "TMC.VDD", "R2.2"],
    "EN": ["XIAO.D1", "TMC.EN", "R2.1"],
    "STEP": ["XIAO.D2", "TMC.STEP"],
    "DIR": ["XIAO.D3", "TMC.DIR"],
    "TX": ["XIAO.D4", "R1.2"],
    "USART": ["XIAO.D5", "R1.1", "TMC.USART"],
    "A2": ["TMC.A2", "MOTOR.1"], "A1": ["TMC.A1", "MOTOR.2"],
    "B1": ["TMC.B1", "MOTOR.3"], "B2": ["TMC.B2", "MOTOR.4"],
}
NOT_CONNECTED = ["TMC.PDN", "TMC.CLK", "XIAO.D0", "XIAO.D6", "XIAO.5V", "XIAO.D10",
                 "XIAO.D9", "XIAO.D8", "XIAO.D7"]


def line_holes(a: str, b: str) -> list[str]:
    (c0, r0), (c1, r1) = hole(a), hole(b)
    assert c0 == c1 or r0 == r1, f"bridge {a}-{b} is not straight"
    n = max(abs(c1 - c0), abs(r1 - r0))
    return [f"{COLS[c0 + (c1 - c0) * i // n]}{r0 + (r1 - r0) * i // n}" for i in range(n + 1)]


def check() -> list[str]:
    """Union-find over holes; compare the resulting nets with EXPECTED."""
    parent: dict[str, str] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        parent[find(a)] = find(b)

    pins = {f"{comp}.{pin}": h for comp, pinmap in COMPONENTS.items() for pin, h in pinmap.items()}
    used = defaultdict(list)
    for name, h in pins.items():
        used[h].append(name)
    problems = [f"hole {h} used by {', '.join(n)}" for h, n in used.items() if len(n) > 1]
    for a, b in BRIDGES:
        holes = line_holes(a, b)
        for x, y in zip(holes, holes[1:]):
            union(x, y)
    for a, b, *_ in WIRES:
        union(a, b)
    for h in pins.values():
        find(h)

    net_of = {name: find(h) for name, h in pins.items()}
    for net, members in EXPECTED.items():
        roots = {net_of[m] for m in members}
        if len(roots) != 1:
            problems.append(f"net {net} is split: " + ", ".join(
                f"{m}@{pins[m]}" for m in members))
    expected_root = {find(pins[m[0]]): net for net, m in EXPECTED.items()}
    for name, root in net_of.items():
        owner = [net for net, m in EXPECTED.items() if name in m]
        if owner and expected_root.get(root) not in owner:
            problems.append(f"{name} ended up in the wrong net")
        if not owner and name in NOT_CONNECTED and root in expected_root:
            problems.append(f"{name} must stay unconnected, but is on net {expected_root[root]}")
    # different expected nets must not have merged
    roots = defaultdict(list)
    for net, m in EXPECTED.items():
        roots[find(pins[m[0]])].append(net)
    problems += [f"SHORT between nets {', '.join(n)}" for n in roots.values() if len(n) > 1]
    return problems


# -----------------------------------------------------------------------------
# Drawing
# -----------------------------------------------------------------------------
def xy(h: str, mirror: bool) -> tuple[float, float]:
    c, r = hole(h)
    return (len(COLS) - 1 - c if mirror else c), r


def draw(mirror: bool, path: Path, title: str):
    fig, ax = plt.subplots(figsize=(6.2, 11), dpi=130)
    mx = (BOARD_W / PITCH - (len(COLS) - 1)) / 2
    my = (BOARD_H / PITCH - (ROWS - 1)) / 2
    ax.add_patch(FancyBboxPatch((-mx, 1 - my), len(COLS) - 1 + 2 * mx, ROWS - 1 + 2 * my,
                                boxstyle="round,pad=0,rounding_size=0.4", fc="#d9b36c",
                                ec="#8a6a2f", lw=1.2, zorder=0))
    for c in range(len(COLS)):
        for r in range(1, ROWS + 1):
            ax.add_patch(Circle((len(COLS) - 1 - c if mirror else c, r), 0.18,
                                fc="#6b5326", ec="none", zorder=1))
    for c, name in enumerate(COLS):
        ax.text(len(COLS) - 1 - c if mirror else c, ROWS + 1.0, name, ha="center", va="center",
                fontsize=8, color="#3b2f1a", fontweight="bold")
    for r in range(1, ROWS + 1):
        ax.text(len(COLS) - 1 + 1.05 if not mirror else -1.05, r, str(r), ha="center",
                va="center", fontsize=6.5, color="#3b2f1a")

    def label_pins(comp, pinmap, colour, side_offset):
        for pin, h in pinmap.items():
            x, y = xy(h, mirror)
            ax.add_patch(Circle((x, y), 0.3, fc=colour, ec="white", lw=0.6, zorder=6))
            ax.text(x + side_offset(pin), y, pin.replace("GND_P", "GND").replace("GND_L", "GND"),
                    ha="center", va="center", fontsize=5.3, zorder=7, color="#111111")

    if not mirror:   # components are on the top side
        # XIAO outline (21 x 17.5 mm), USB-C at the A end
        x0, _ = xy("A14", False)
        ax.add_patch(Rectangle((x0 - 1.13, 13.6), 8.27, 6.8, fc="#2b2f36", ec="#111", lw=1,
                               alpha=0.88, zorder=3))
        ax.add_patch(Rectangle((x0 - 1.6, 16.1), 1.2, 1.8, fc="#b8bec6", ec="#555", zorder=4))
        ax.text(x0 + 3, 17, "XIAO ESP32-C3\nUSB-C ←", ha="center", va="center", color="white",
                fontsize=7.5, zorder=5)
        # TMC2209 outline (15.3 x 20.3 mm), pot at the EN end
        ax.add_patch(Rectangle((xy("C3", False)[0] - 0.5, 2.5), 6.0, 8.0, fc="#1b1b1b", ec="#111",
                               lw=1, alpha=0.85, zorder=3))
        ax.add_patch(Circle((xy("E10", False)[0], 9.6), 0.45, fc="#c7c7c7", zorder=4))
        ax.text(xy("E6", False)[0] + 0.5, 6.5, "TMC2209\n(heatsink up)", ha="center",
                va="center", color="white", fontsize=7, zorder=5)
        # resistors, capacitor, motor connector, power wires
        for comp, pins, text, fc in ((R1, ("1", "2"), "R1 1kΩ", "#d8c7a0"),
                                     (R2, ("1", "2"), "R2 10kΩ", "#9fc0e8")):
            (xa, ya), (xb, yb) = xy(comp[pins[0]], False), xy(comp[pins[1]], False)
            ax.plot([xa, xb], [ya, yb], color="#777", lw=1.2, zorder=3)
            ax.add_patch(FancyBboxPatch((min(xa, xb) + 0.8, ya - 0.28), abs(xb - xa) - 1.6, 0.56,
                                        boxstyle="round,pad=0.02", fc=fc, ec="#555", zorder=4))
            ax.text((xa + xb) / 2, ya, text, ha="center", va="center", fontsize=5.8, zorder=5)
        cx, cy = xy("J10", False)[0], 9.5
        ax.add_patch(Circle((cx, cy), 1.24, fc="#27303b", ec="#111", zorder=4))
        ax.add_patch(Rectangle((cx + 0.55, cy - 1.0), 0.45, 2.0, fc="#c9d0d8", zorder=5))
        ax.text(cx - 0.35, cy, "C1\n100µ", ha="center", va="center", color="white", fontsize=5,
                zorder=6)
        ax.text(cx - 1.55, 10, "+", ha="center", va="center", fontsize=9, color="#d62d20",
                fontweight="bold", zorder=6)
        mxj = xy("J4", False)[0]
        ax.add_patch(Rectangle((mxj - 1.13, 3.57), 2.26, 3.86, fc="#f4f1e6", ec="#777", zorder=4))
        ax.text(mxj + 1.75, 5.5, "MOTOR\nJST-XH", ha="center", va="center", fontsize=5.5,
                rotation=90, zorder=5)
        label_pins("MOTOR", {"1 blk": "J7", "2 grn": "J6", "3 red": "J5", "4 blu": "J4"},
                   "#f4f1e6", lambda p: 0)
        for pin, h, col in (("+24V", "J12", "#d62d20"), ("0V", "I8", "#222222")):
            x, y = xy(h, False)
            ax.plot([x, x + 1.6], [y, y + (1.2 if pin == "+24V" else -0.2)], color=col, lw=2.2,
                    zorder=6)
            ax.text(x + 1.7, y + (1.5 if pin == "+24V" else -0.6), pin + "\n(DC jack)",
                    fontsize=5.5, color=col, fontweight="bold", zorder=7)
        label_pins("XIAO", XIAO, "#e6c86e", lambda p: 0)
        label_pins("TMC", TMC, "#e6c86e", lambda p: -0.95 if hole(TMC[p])[0] == 2 else 0.95)
    else:            # bottom side: bridges and wires, mirrored
        for a, b in BRIDGES:
            holes = line_holes(a, b)
            xs, ys = zip(*(xy(h, True) for h in holes))
            ax.plot(xs, ys, color="#c0c4c8", lw=7, solid_capstyle="round", zorder=4)
            ax.plot(xs, ys, color="#8d949b", lw=1, zorder=5)
        for a, b, colour, what, *via in WIRES:
            pts = [xy(a, True)] + [(len(COLS) - 1 - c, r) for c, r in (via[0] if via else [])]                 + [xy(b, True)]
            xs, ys = zip(*pts)
            ax.plot(xs, ys, color=colour, lw=2.2, zorder=6, alpha=0.9)
        for comp, pinmap in COMPONENTS.items():
            for pin, h in pinmap.items():
                x, y = xy(h, True)
                ax.add_patch(Circle((x, y), 0.3, fc="#b7bcc2", ec="#555", lw=0.6, zorder=7))
                short = pin.replace("GND_P", "GND").replace("GND_L", "GND")
                ax.text(x, y - 0.52, f"{comp if comp not in ('XIAO', 'TMC') else ''}{'.' if comp not in ('XIAO', 'TMC') else ''}{short}",
                        ha="center", va="center", fontsize=4.6, zorder=8, color="#111")

    ax.set_xlim(-2.2, len(COLS) + 1.4)
    ax.set_ylim(-0.6, ROWS + 2.2)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(title, fontsize=10)
    fig.tight_layout()
    fig.savefig(path, facecolor="white")
    plt.close(fig)


def main():
    problems = check()
    print("netlist check:", "OK - every net matches WIRING.md, no shorts" if not problems else "")
    for p in problems:
        print("  PROBLEM:", p)
    draw(False, HERE / "top.png", "TOP (components) — USB wall on the left, motor on the right")
    draw(True, HERE / "bottom.png", "BOTTOM (solder side) — mirrored: USB wall on the right")
    print("wrote", HERE / "top.png", "and", HERE / "bottom.png")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
