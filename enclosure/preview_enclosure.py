"""
Renders preview images of the enclosure from the STL files that build_enclosure.py writes.

Run (from the project root, after build_enclosure.py):
    .venv\\Scripts\\python enclosure\\preview_enclosure.py
Needs matplotlib (pip install matplotlib).
"""

import struct
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402

HERE = Path(__file__).parent
PARTS = HERE / "preview" / "parts"
OUT = HERE / "preview"

# Gamidor palette (theme.py LIGHT): surfaces grey, the moving/brand parts in the accent colour
COLOURS = {
    "base": "#c9d0d8", "lid": "#dde2e8", "lid_text": "#e8563f", "hub": "#e8563f",
    "plate": "#e8563f", "motor": "#3b4148", "shaft": "#9aa5b1", "perfboard": "#2f8f4e",
    "board_parts": "#1b2733", "usb-c": "#9aa5b1", "dc_jack": "#1b2733", "dish": "#b8dcf5",
}
ALPHA = {"dish": 0.35}
LIGHT = np.array([-0.4, -0.6, 0.7])
LIGHT = LIGHT / np.linalg.norm(LIGHT)


def read_stl(path: Path) -> np.ndarray:
    """Triangles as an (n, 3, 3) array; binary or ASCII STL."""
    data = path.read_bytes()
    if data[:5] == b"solid" and b"facet" in data[:400]:
        verts = [list(map(float, line.split()[1:4]))
                 for line in data.decode("ascii", "ignore").splitlines()
                 if line.strip().startswith("vertex")]
        return np.array(verts).reshape(-1, 3, 3)
    n = struct.unpack("<I", data[80:84])[0]
    rec = np.frombuffer(data[84:84 + n * 50], dtype=np.dtype(
        [("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]))
    return rec["v"].astype(float)


def shade(tris: np.ndarray, colour: str) -> np.ndarray:
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    k = 0.45 + 0.55 * np.clip(np.abs(n @ LIGHT), 0, 1)
    base = np.array(matplotlib.colors.to_rgb(colour))
    return np.clip(base[None, :] * k[:, None], 0, 1)


def draw(ax, bodies, title, elev=24, azim=-58):
    # one collection for everything: matplotlib depth-sorts polygons inside a collection,
    # but draws separate collections whole, which hides parts behind the wrong body
    all_tris, all_rgba = [], []
    for name, tris in bodies:
        colour = COLOURS.get(name, "#888888")
        rgb = shade(tris, colour)
        all_tris.append(tris)
        all_rgba.append(np.concatenate([rgb, np.full((len(rgb), 1), ALPHA.get(name, 1.0))], axis=1))
    tris = np.concatenate(all_tris)
    ax.add_collection3d(Poly3DCollection(tris, facecolors=np.concatenate(all_rgba),
                                         edgecolors="none", linewidths=0))
    lo, hi = tris.reshape(-1, 3).min(0), tris.reshape(-1, 3).max(0)
    centre, span = (lo + hi) / 2, (hi - lo).max() / 2
    for setter, c in zip((ax.set_xlim, ax.set_ylim, ax.set_zlim), centre):
        setter(c - span, c + span)
    ax.set_box_aspect((1, 1, 1))
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()
    ax.set_title(title, fontsize=11, color="#1b2733")


def load(names, lift=None):
    lift = lift or {}
    out = []
    for name in names:
        tris = read_stl(PARTS / f"{name}.stl").copy()
        tris[:, :, 2] += lift.get(name, 0.0)
        out.append((name, tris))
    return out


def figure(bodies_list, titles, path, size=(8, 7), **view):
    fig = plt.figure(figsize=(size[0] * len(bodies_list), size[1]), dpi=110)
    for i, (bodies, title) in enumerate(zip(bodies_list, titles)):
        ax = fig.add_subplot(1, len(bodies_list), i + 1, projection="3d")
        draw(ax, bodies, title, **view)
    fig.tight_layout()
    fig.savefig(path, facecolor="white")
    plt.close(fig)
    print("wrote", path)


def main():
    closed = load(["base", "lid", "lid_text", "hub", "plate", "dish", "shaft"])
    inside = load(["base", "motor", "shaft", "perfboard", "board_parts", "usb-c", "dc_jack"])
    figure([closed, inside], ["assembled, with a 90 mm dish", "inside (lid removed)"],
           OUT / "assembled.png")
    figure([closed], ["USB end (-X)"], OUT / "usb_end.png", azim=-150, elev=12)
    figure([closed], ["24V end (+X)"], OUT / "power_end.png", azim=30, elev=12)

    exploded = load(["base", "motor", "perfboard", "board_parts", "dc_jack", "lid", "lid_text",
                     "shaft", "hub", "plate"],
                    lift={"lid": 45, "lid_text": 45, "motor": 45, "shaft": 45, "hub": 75,
                          "plate": 100})
    figure([exploded], ["exploded"], OUT / "exploded.png", size=(8, 9))

    printed = [(n, read_stl(HERE / "stl" / f"{n}.stl")) for n in ("base", "lid", "hub", "plate")]
    fig = plt.figure(figsize=(16, 4.6), dpi=110)
    for i, (name, tris) in enumerate(printed):
        ax = fig.add_subplot(1, 4, i + 1, projection="3d")
        extra = [("lid_text", read_stl(HERE / "stl" / "lid_text.stl"))] if name == "lid" else []
        draw(ax, [(name, tris)] + extra, f"{name}.stl  (as printed)", elev=30)
    fig.tight_layout()
    fig.savefig(OUT / "print_orientation.png", facecolor="white")
    plt.close(fig)
    print("wrote", OUT / "print_orientation.png")


if __name__ == "__main__":
    main()
