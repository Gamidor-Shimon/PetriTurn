"""
SBS PetriPlater enclosure - parametric FreeCAD script.

Builds the printed parts, checks them against simple models of the motor, perfboard and
connectors, and exports STL (print-ready orientation) and STEP (assembled position).

Run (from the project root):
    "C:\\Program Files\\FreeCAD 1.1\\bin\\freecadcmd.exe" -c "exec(open(r'enclosure/build_enclosure.py').read())"

All sizes in mm. Coordinates: X along the SBS length (127.76), Y along the width (85.48),
Z up; origin at the centre of the footprint, on the bench. -X end = USB, +X end = 24V.

Parts
    base      tray with walls, perfboard standoffs, lid screw posts, USB window, DC jack hole
    lid       top plate; the motor hangs under it (4 x M3), lid screws into the base (4 x M3)
    lid_text  engraved lettering as a separate body - print it in a second colour (AMS)
    hub       clamps the motor shaft (D-bore + M3 set screw in a heat insert)
    plate     dish nest: sits on the hub (3 x M3 countersunk), 3 low snap clips hold the dish
"""

import math
import os

import FreeCAD
import MeshPart
import Part

V = FreeCAD.Vector

# =============================================================================
# Parameters - measure the parts marked (MEASURE) before the final print
# =============================================================================

# SBS / ANSI-SLAS footprint (microplate)
FOOT_X, FOOT_Y, FOOT_R = 127.76, 85.48, 3.18
WALL = 2.4
FLOOR = 2.4

# Motor: LAM M1173040, NEMA17, 48 mm
MOTOR_W = 42.3
MOTOR_L = 48.0            # (MEASURE) body length without the boss
MOTOR_BOSS_D = 22.0
MOTOR_BOSS_H = 2.0
MOTOR_HOLES = 31.0        # M3 hole pattern
SHAFT_D = 5.0
SHAFT_FLAT = 0.5          # depth of the D-cut
SHAFT_L = 24.0            # (MEASURE) from the motor face (not the boss top) to the shaft end
UNDER_MOTOR = 3.0         # air gap between the motor bottom and the floor

LID_T = 4.0
LIP_H, LIP_T, LIP_GAP = 2.5, 1.6, 0.3   # alignment lip under the lid

# Fasteners
M3_CLEAR = 3.4
M3_HEAD_D, M3_HEAD_H = 6.4, 2.0          # counterbore for M3 button head
M3_INSERT_D, M3_INSERT_L = 4.0, 6.0      # hole for M3 x 5.7 heat insert
M3_CSK_D = 6.6                           # countersink top diameter (M3 flat head, 90 deg)
POST_R = 3.6
POST_INSET = 3.0                          # post centre from the inner wall corner

# Perfboard (30 x 60 mm, cut from a 30 x 70 board) on the -X side of the motor
PB_X, PB_Y, PB_T = 30.0, 60.0, 1.6
PB_GAP_WALL = 0.5
PB_STANDOFF_H, PB_STANDOFF_D, PB_PILOT_D = 6.0, 6.0, 2.2   # M2.5 self-tapping screws
PB_HOLE_INSET = 2.5
PB_PARTS_H = 22.0         # tallest part on the board (TMC2209 + heatsink on female headers)

# USB-C window (XIAO on female headers at the -X edge of the board)
USB_Y = 14.0              # (MEASURE after soldering) centre of the XIAO USB-C along Y (row 17 of the board)
USB_Z = 21.3              # (MEASURE after soldering) centre height of the USB-C above the bench
USB_W, USB_H = 13.5, 8.0  # lets the plug's plastic overmould in, so the plug seats fully

# DC jack 5.5 x 2.1, panel mount, on the +X end
DC_Y, DC_Z = 0.0, 26.0
DC_HOLE_D = 8.0           # (MEASURE) thread of your panel jack (DC-022B = 8 mm)
DC_DEPTH = 14.0           # how far the jack reaches into the box

# Ventilation slots in the long walls, next to the driver
VENT_N, VENT_W, VENT_Z0, VENT_Z1 = 6, 2.5, 14.0, 34.0

# Dish nest
DISH_D = 90.0             # (MEASURE) outer diameter of the dish base
PLATE_D = 84.0            # stays inside the 85.48 SBS width
PLATE_T = 3.0
HUB_GAP = 2.0             # air gap between the lid and the hub
HUB_D = 18.0
FLANGE_D, FLANGE_T = 40.0, 6.0
SHAFT_CLEAR = 0.15        # radial clearance of the D-bore
PLATE_SCREW_R = 14.0      # M3 screws plate -> hub flange
CLIP_ANGLES = (90.0, 210.0, 330.0)
CLIP_W, CLIP_T, CLIP_H = 8.0, 1.6, 5.0
CLIP_GAP = 0.2            # clip wall to dish, below the bump
CLIP_BUMP = 0.5           # the bump reaches this far past the gap: ~0.3 mm grip
PAD_D, PAD_DEPTH, PAD_R = 10.0, 0.8, 30.0   # pockets for anti-slip pads

# Lettering
FONT = "C:/Windows/Fonts/segoeuib.ttf"
TEXT_DEPTH = 0.6
LID_TEXT_LEFT = "GAMIDOR DIAGNOSTICS"
LID_TEXT_RIGHT = "SBS PETRIPLATER"
LID_TEXT_H = 5.0
WALL_TEXT_H = 4.0

OUT = os.path.join(os.path.dirname(os.path.abspath(
    __file__ if "__file__" in globals() else "enclosure/build_enclosure.py")))

# =============================================================================
# Derived heights (Z)
# =============================================================================
BASE_H = FLOOR + UNDER_MOTOR + MOTOR_L          # top of the walls = motor face
LID_TOP = BASE_H + LID_T
SHAFT_TOP = BASE_H + SHAFT_L
HUB_Z0 = LID_TOP + HUB_GAP
FLANGE_TOP = SHAFT_TOP + 1.0                    # the shaft ends 1 mm under the plate
PLATE_TOP = FLANGE_TOP + PLATE_T
IN_X, IN_Y = FOOT_X / 2 - WALL, FOOT_Y / 2 - WALL
POSTS = [(sx * (IN_X - POST_INSET), sy * (IN_Y - POST_INSET)) for sx in (-1, 1) for sy in (-1, 1)]
PB_X0 = -IN_X + PB_GAP_WALL                      # perfboard -X edge
PB_Z0 = FLOOR + PB_STANDOFF_H


# =============================================================================
# Helpers
# =============================================================================
def box(x0, x1, y0, y1, z0, z1):
    return Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def cyl(r, z0, h, x=0.0, y=0.0, direction=V(0, 0, 1)):
    return Part.makeCylinder(r, h, V(x, y, z0), direction)


def rounded_box(lx, ly, r, z0, h):
    b = box(-lx / 2, lx / 2, -ly / 2, ly / 2, z0, z0 + h)
    vertical = [e for e in b.Edges
                if abs(e.Vertexes[0].Point.z - e.Vertexes[1].Point.z) > 1e-6]
    return b.makeFillet(r, vertical)


def fuse_all(shapes):
    result = shapes[0]
    for s in shapes[1:]:
        result = result.fuse(s)
    return result.removeSplitter()


def text_solid(text, height, depth):
    """Lettering in XY (baseline +X, up +Y), centred on the origin, solid in z = [-depth, 0]."""
    chars = Part.makeWireString(text, FONT, height, 0)
    faces = [Part.makeFace(c, "Part::FaceMakerBullseye") for c in chars if c]
    comp = Part.Compound(faces)
    bb = comp.BoundBox
    comp.translate(V(-(bb.XMin + bb.XMax) / 2, -(bb.YMin + bb.YMax) / 2, 0))
    return comp.extrude(V(0, 0, -depth))


def placed(shape, x_axis, y_axis, z_axis, origin):
    """Map local axes onto the given world axes (right-handed), then move to origin."""
    m = FreeCAD.Matrix(x_axis.x, y_axis.x, z_axis.x, origin.x,
                       x_axis.y, y_axis.y, z_axis.y, origin.y,
                       x_axis.z, y_axis.z, z_axis.z, origin.z,
                       0, 0, 0, 1)
    return shape.transformGeometry(m)


# =============================================================================
# Base
# =============================================================================
def make_base():
    shell = rounded_box(FOOT_X, FOOT_Y, FOOT_R, 0, BASE_H)
    cavity = rounded_box(FOOT_X - 2 * WALL, FOOT_Y - 2 * WALL, max(FOOT_R - WALL, 0.5),
                         FLOOR, BASE_H)
    base = shell.cut(cavity)

    # lid screw posts with heat inserts
    posts = [cyl(POST_R, FLOOR, BASE_H - FLOOR, x, y) for x, y in POSTS]
    # fill from each post into its corner, so the post is part of both walls
    for x, y in POSTS:
        wx, wy = math.copysign(IN_X + 0.1, x), math.copysign(IN_Y + 0.1, y)
        posts.append(box(min(x, wx), max(x, wx), min(y, wy), max(y, wy), FLOOR, BASE_H))
    base = fuse_all([base] + posts)
    for x, y in POSTS:
        base = base.cut(cyl(M3_INSERT_D / 2, BASE_H - M3_INSERT_L, M3_INSERT_L + 1, x, y))

    # perfboard standoffs
    for hx in (PB_X0 + PB_HOLE_INSET, PB_X0 + PB_X - PB_HOLE_INSET):
        for hy in (-PB_Y / 2 + PB_HOLE_INSET, PB_Y / 2 - PB_HOLE_INSET):
            base = base.fuse(cyl(PB_STANDOFF_D / 2, FLOOR - 0.1, PB_STANDOFF_H + 0.1, hx, hy))
            base = base.cut(cyl(PB_PILOT_D / 2, FLOOR, PB_STANDOFF_H + 1, hx, hy))

    # USB-C window (-X end) with a 45 deg chamfer on the outside for the plug
    usb = box(-FOOT_X / 2 - 1, -IN_X + 0.01, USB_Y - USB_W / 2, USB_Y + USB_W / 2,
              USB_Z - USB_H / 2, USB_Z + USB_H / 2)
    base = base.cut(usb)

    # DC jack (+X end)
    base = base.cut(Part.makeCylinder(DC_HOLE_D / 2, WALL + 2, V(FOOT_X / 2 + 1, DC_Y, DC_Z),
                                      V(-1, 0, 0)))

    # ventilation slots, both long walls, beside the perfboard
    # clear of the corner posts (they end at x = -IN_X + POST_INSET + POST_R)
    x_first = -IN_X + POST_INSET + POST_R + 2 + VENT_W / 2
    x_last = PB_X0 + PB_X - 2
    xs = [x_first + i * (x_last - x_first) / (VENT_N - 1) for i in range(VENT_N)]
    for x in xs:
        for sy in (-1, 1):
            slot = box(x - VENT_W / 2, x + VENT_W / 2,
                       sy * IN_Y - 1 if sy > 0 else -FOOT_Y / 2 - 1,
                       FOOT_Y / 2 + 1 if sy > 0 else -IN_Y + 1,
                       VENT_Z0, VENT_Z1)
            base = base.cut(slot)

    # wall lettering
    usb_txt = placed(text_solid("USB", WALL_TEXT_H, TEXT_DEPTH), V(0, -1, 0), V(0, 0, 1),
                     V(-1, 0, 0), V(-FOOT_X / 2, USB_Y, USB_Z + USB_H / 2 + 4.5))
    dc_txt = placed(text_solid("24V DC", WALL_TEXT_H, TEXT_DEPTH), V(0, 1, 0), V(0, 0, 1),
                    V(1, 0, 0), V(FOOT_X / 2, DC_Y, DC_Z + DC_HOLE_D / 2 + 4.5))
    base = base.cut(usb_txt).cut(dc_txt)
    return base.removeSplitter()


# =============================================================================
# Lid
# =============================================================================
def lid_lettering():
    left = text_solid(LID_TEXT_LEFT, LID_TEXT_H, TEXT_DEPTH)
    right = text_solid(LID_TEXT_RIGHT, LID_TEXT_H, TEXT_DEPTH)
    strip = (PLATE_D / 2 + FOOT_X / 2) / 2 + 1.0          # middle of the free strip beside the nest
    # reads bottom-to-top when standing at the -Y side
    left = placed(left, V(0, 1, 0), V(-1, 0, 0), V(0, 0, 1), V(-strip, 0, LID_TOP))
    right = placed(right, V(0, 1, 0), V(-1, 0, 0), V(0, 0, 1), V(strip, 0, LID_TOP))
    return left.fuse(right)


def make_lid():
    lid = rounded_box(FOOT_X, FOOT_Y, FOOT_R, BASE_H, LID_T)
    # alignment lip: straight segments along the walls, clear of the corner posts
    lx, ly = IN_X - LIP_GAP, IN_Y - LIP_GAP
    cx = IN_X - POST_INSET - POST_R - 1.0
    cy = IN_Y - POST_INSET - POST_R - 1.0
    lips = [box(-cx, cx, sy * ly - (LIP_T if sy > 0 else 0), sy * ly + (0 if sy > 0 else LIP_T),
                BASE_H - LIP_H, BASE_H) for sy in (-1, 1)]
    lips += [box(sx * lx - (LIP_T if sx > 0 else 0), sx * lx + (0 if sx > 0 else LIP_T), -cy, cy,
                 BASE_H - LIP_H, BASE_H) for sx in (-1, 1)]
    lid = fuse_all([lid] + lips)
    # motor boss and shaft
    lid = lid.cut(cyl(MOTOR_BOSS_D / 2 + 0.3, BASE_H - 1, LID_T + 2))
    # motor screws and lid screws, counterbored from the top
    for x, y in [(sx * MOTOR_HOLES / 2, sy * MOTOR_HOLES / 2) for sx in (-1, 1) for sy in (-1, 1)] + POSTS:
        lid = lid.cut(cyl(M3_CLEAR / 2, BASE_H - LIP_H - 1, LID_T + LIP_H + 2, x, y))
        lid = lid.cut(cyl(M3_HEAD_D / 2, LID_TOP - M3_HEAD_H, M3_HEAD_H + 1, x, y))
    text = lid_lettering()
    return lid.cut(text).removeSplitter(), text


# =============================================================================
# Hub and plate (dish nest)
# =============================================================================
def d_bore(z0, h):
    r = SHAFT_D / 2 + SHAFT_CLEAR
    flat = SHAFT_D / 2 - SHAFT_FLAT + SHAFT_CLEAR
    return cyl(r, z0, h).common(box(-r - 1, flat, -r - 1, r + 1, z0 - 1, z0 + h + 1))


def make_hub():
    body = cyl(HUB_D / 2, HUB_Z0, FLANGE_TOP - FLANGE_T - HUB_Z0)
    flange = cyl(FLANGE_D / 2, FLANGE_TOP - FLANGE_T, FLANGE_T)
    hub = body.fuse(flange).removeSplitter()
    hub = hub.cut(d_bore(HUB_Z0 - 1, SHAFT_TOP - HUB_Z0 + 1 + 0.5))
    # radial M3 set screw (heat insert) pressing on the shaft flat (+X side)
    set_z = HUB_Z0 + (FLANGE_TOP - FLANGE_T - HUB_Z0) / 2
    hub = hub.cut(Part.makeCylinder(M3_INSERT_D / 2, HUB_D, V(0, 0, set_z), V(1, 0, 0)))
    # inserts for the plate screws, from the flange top
    for a in (0, 120, 240):
        x = PLATE_SCREW_R * math.cos(math.radians(a + 30))
        y = PLATE_SCREW_R * math.sin(math.radians(a + 30))
        hub = hub.cut(cyl(M3_INSERT_D / 2, FLANGE_TOP - M3_INSERT_L, M3_INSERT_L + 1, x, y))
    return hub


def make_clip(angle):
    r_in = DISH_D / 2 + CLIP_GAP
    r_out = r_in + CLIP_T
    z0 = PLATE_TOP
    h = CLIP_H
    # profile in the (radius, z) plane: bump grips the dish, chamfer leads it in from above
    pts = [V(r_in, 0, 0), V(r_out, 0, 0), V(r_out, 0, h), V(r_in + 0.7, 0, h),
           V(r_in - CLIP_BUMP, 0, 0.55 * h), V(r_in, 0, 0.3 * h), V(r_in, 0, 0)]
    face = Part.Face(Part.makePolygon(pts))
    upright = face.extrude(V(0, CLIP_W, 0))
    upright.translate(V(0, -CLIP_W / 2, z0))
    arm = box(PLATE_D / 2 - 4, r_out, -CLIP_W / 2, CLIP_W / 2, PLATE_TOP - PLATE_T, PLATE_TOP)
    clip = upright.fuse(arm)
    clip.rotate(V(0, 0, 0), V(0, 0, 1), angle)
    return clip


def make_plate():
    plate = cyl(PLATE_D / 2, PLATE_TOP - PLATE_T, PLATE_T)
    plate = fuse_all([plate] + [make_clip(a) for a in CLIP_ANGLES])
    for a in (0, 120, 240):
        x = PLATE_SCREW_R * math.cos(math.radians(a + 30))
        y = PLATE_SCREW_R * math.sin(math.radians(a + 30))
        plate = plate.cut(cyl(M3_CLEAR / 2, PLATE_TOP - PLATE_T - 1, PLATE_T + 2, x, y))
        csk_h = (M3_CSK_D - M3_CLEAR) / 2
        plate = plate.cut(Part.makeCone(M3_CLEAR / 2, M3_CSK_D / 2, csk_h,
                                        V(x, y, PLATE_TOP - csk_h)))
        plate = plate.cut(cyl(M3_CSK_D / 2, PLATE_TOP - 0.01, 1, x, y))
    for a in CLIP_ANGLES:
        x = PAD_R * math.cos(math.radians(a + 60))
        y = PAD_R * math.sin(math.radians(a + 60))
        plate = plate.cut(cyl(PAD_D / 2, PLATE_TOP - PAD_DEPTH, PAD_DEPTH + 1, x, y))
    return plate.removeSplitter()


# =============================================================================
# Reference models (not printed) - used for the collision check and the preview
# =============================================================================
def reference_models():
    motor = box(-MOTOR_W / 2, MOTOR_W / 2, -MOTOR_W / 2, MOTOR_W / 2, BASE_H - MOTOR_L, BASE_H)
    motor = motor.fuse(cyl(MOTOR_BOSS_D / 2, BASE_H, MOTOR_BOSS_H))
    flat = SHAFT_D / 2 - SHAFT_FLAT
    shaft = cyl(SHAFT_D / 2, BASE_H, SHAFT_L).common(
        box(-SHAFT_D, flat, -SHAFT_D, SHAFT_D, BASE_H - 1, BASE_H + SHAFT_L + 1))
    board = box(PB_X0, PB_X0 + PB_X, -PB_Y / 2, PB_Y / 2, PB_Z0, PB_Z0 + PB_T)
    parts = box(PB_X0 + 1, PB_X0 + PB_X - 1, -PB_Y / 2 + 1, PB_Y / 2 - 1,
                PB_Z0 + PB_T, PB_Z0 + PB_T + PB_PARTS_H)
    usb = box(-IN_X + 0.2, -IN_X + 7.5, USB_Y - 4.5, USB_Y + 4.5, USB_Z - 1.7, USB_Z + 1.7)
    jack = Part.makeCylinder(5.5, DC_DEPTH, V(IN_X, DC_Y, DC_Z), V(-1, 0, 0))
    dish = cyl(DISH_D / 2, PLATE_TOP, 14.0).cut(cyl(DISH_D / 2 - 1.2, PLATE_TOP + 1.2, 14))
    return {"motor": motor, "shaft": shaft, "perfboard": board, "board parts": parts,
            "usb-c": usb, "dc jack": jack, "dish": dish}


def check(printed, refs):
    """Report every overlap between printed parts and reference models (should be none)."""
    lines = []
    pairs = [(p, r) for p in printed for r in refs]
    for pname, rname in pairs:
        if (pname, rname) in {("plate", "dish")}:
            continue                        # the clips are meant to touch the dish
        common = printed[pname].common(refs[rname])
        if common.Volume > 0.01:
            lines.append(f"COLLISION  {pname} x {rname}: {common.Volume:.2f} mm3")
    # the clip bump must reach into the dish wall a little - that is the grip
    grip = printed["plate"].common(refs["dish"]).Volume
    lines.append(f"clip grip overlap with the dish: {grip:.2f} mm3 (expected > 0)")
    moving = printed["hub"].fuse(printed["plate"])
    for name in ("base", "lid"):
        if moving.common(printed[name]).Volume > 0.01:
            lines.append(f"COLLISION  rotating nest x {name}")
    return lines


# =============================================================================
# Build, check, export
# =============================================================================
def write_stl(shape, path, fine=True):
    """FreeCAD refuses to overwrite a mesh file, so remove the old one first."""
    if os.path.exists(path):
        os.remove(path)
    mesh = MeshPart.meshFromShape(Shape=shape, LinearDeflection=0.02 if fine else 0.1,
                                  AngularDeflection=0.15 if fine else 0.3, Relative=False)
    mesh.write(path)


def export(shape, name, print_matrix=None, frame=None):
    """STEP in the assembled position; STL turned for printing and put on the bed.
    frame: shape whose bounding box sets the move (keeps lid and lid_text aligned)."""
    os.makedirs(os.path.join(OUT, "stl"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "step"), exist_ok=True)
    shape.exportStep(os.path.join(OUT, "step", name + ".step"))
    s = shape.copy()
    ref = (frame or shape).copy()
    if print_matrix is not None:
        s = s.transformGeometry(print_matrix)
        ref = ref.transformGeometry(print_matrix)
    bb = ref.BoundBox
    s.translate(V(-(bb.XMin + bb.XMax) / 2, -(bb.YMin + bb.YMax) / 2, -bb.ZMin))
    write_stl(s, os.path.join(OUT, "stl", name + ".stl"))
    return s.BoundBox


def flip_x():
    """Upside down (rotate 180 deg about X) - for parts printed top face on the bed."""
    return FreeCAD.Matrix(1, 0, 0, 0,  0, -1, 0, 0,  0, 0, -1, 0,  0, 0, 0, 1)


def main():
    base = make_base()
    lid, lid_text = make_lid()
    hub = make_hub()
    plate = make_plate()
    printed = {"base": base, "lid": lid, "hub": hub, "plate": plate}
    refs = reference_models()

    report = [f"base height {BASE_H:.1f}, lid top {LID_TOP:.1f}, dish bottom {PLATE_TOP:.1f} mm "
              f"above the bench", f"footprint {FOOT_X} x {FOOT_Y} mm"]
    report += check(printed, refs)
    for name, shape in printed.items():
        report.append(f"{name}: valid={shape.isValid()} solids={len(shape.Solids)} "
                      f"volume={shape.Volume / 1000:.1f} cm3")

    # lid and lid_text share one frame, so they stay aligned when loaded together (AMS)
    lid_frame = lid.fuse(lid_text)
    sizes = {
        "base": export(base, "base"),
        "lid": export(lid, "lid", flip_x(), lid_frame),
        "lid_text": export(lid_text, "lid_text", flip_x(), lid_frame),
        "hub": export(hub, "hub", flip_x()),
        "plate": export(plate, "plate"),
    }
    for name, bb in sizes.items():
        report.append(f"{name}.stl print size {bb.XLength:.1f} x {bb.YLength:.1f} x {bb.ZLength:.1f} mm")

    # assembled model for the preview (printed parts + references), one STL per body
    os.makedirs(os.path.join(OUT, "preview", "parts"), exist_ok=True)
    for name, s in list(printed.items()) + [("lid_text", lid_text)] + list(refs.items()):
        write_stl(s, os.path.join(OUT, "preview", "parts", name.replace(" ", "_") + ".stl"), fine=False)

    with open(os.path.join(OUT, "build_report.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(report) + "\n")


main()
