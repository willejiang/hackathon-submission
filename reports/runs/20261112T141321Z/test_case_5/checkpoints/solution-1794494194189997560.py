"""Reconstruction of test_case_5: long hollow engine-cover type block.

All dimensions are taken from facts.json / the design brief, or derived from
them by formula.  The frame is the frame of the eight views: X to the right,
Z up, Y from the thin front (tab) face towards the thick back face.
"""

from build123d import *
import math


def derive(facts):
    d = {}
    bb = facts["bounding_box_mm"]
    d["L"] = bb["x"]
    d["W"] = bb["y"]
    d["H"] = bb["z"]

    # ---- global edge treatment -------------------------------------------
    d["r_corner"] = facts["fillets_rounds_from_cylinders"][0]["radius"]

    # ---- bore inventory, grouped by diameter -----------------------------
    by_d = {}
    for b in facts["cylindrical_holes_and_bores"]:
        by_d.setdefault(b["diameter"], []).append(b)

    b127 = by_d[127][0]
    d["d127"] = b127["diameter"]
    d["l127"] = b127["lengths"][0]
    d["r127"] = d["d127"] / 2
    d["group_x"] = [c[0] for c in b127["centres"]]
    d["group_z"] = b127["centres"][0][2]

    b28 = by_d[28][0]
    d["d28"] = b28["diameter"]
    d["l28"] = b28["lengths"][0]
    d["r28"] = d["d28"] / 2
    d["bore28_x"] = sorted(c[0] for c in b28["centres"])
    d["bore28_z"] = b28["centres"][0][2]
    # the medium bores are machined from the front face
    d["front_y"] = b28["centres"][0][1] - d["l28"] / 2

    b6 = by_d[6.35][0]
    d["d6"] = b6["diameter"]
    d["r6"] = d["d6"] / 2
    d["l6"] = sum(b6["lengths"]) / len(b6["lengths"])
    # the small coaxial bores break through the front wall into the cavity:
    # their far end is the inner face of the front wall
    d["wall_inner_y"] = (sum(c[1] for c in b6["centres"]) / len(b6["centres"])
                         + d["l6"] / 2)

    b5 = by_d[5.11][0]
    d["d5"] = b5["diameter"]
    d["r5"] = d["d5"] / 2
    d["l5"] = b5["lengths"][0]
    front5 = [c for c in b5["centres"] if c[1] > d["front_y"] + d["l5"] / 2]
    tab5 = [c for c in b5["centres"] if c[1] <= d["front_y"]]
    d["bore5_z"] = front5[0][2]
    tab_x = sorted({round(c[0], 2) for c in tab5})
    d["tab_x0"] = tab_x[0]
    d["tab_hole_z"] = sorted({c[2] for c in tab5})

    b12 = by_d[12.7][0]
    d["d12"] = b12["diameter"]
    d["r12"] = d["d12"] / 2
    d["l12"] = b12["lengths"][0]
    d["bore12"] = [tuple(c) for c in b12["centres"]]
    d["bore12_axis"] = tuple(float(v) for v in b12["axis"].strip("()").split(","))

    b25 = by_d[25.4][0]
    d["d25"] = b25["diameter"]
    d["r25"] = d["d25"] / 2
    d["l25"] = b25["lengths"][0]
    d["bore25_y"] = b25["centres"][0][1]
    d["bore25_z"] = b25["centres"][0][2]
    d["bore25_x"] = b25["centres"][0][0]

    # ---- pitch of the repeated groups ------------------------------------
    d["pitch"] = round((max(d["group_x"]) - min(d["group_x"]))
                       / (len(d["group_x"]) - 1), 2)
    n_tabs = len(d["group_x"]) + 1
    d["tab_x"] = [d["tab_x0"] + d["pitch"] * i for i in range(n_tabs)]
    d["tab_d"] = d["front_y"]                 # tabs fill Y = 0 .. front face
    d["tab_w"] = d["r_corner"] - 2 * d["l127"]        # 20.32 wide in X
    d["tab_h"] = 2 * d["r_corner"]                    # 50.8 tall in Z
    d["tab_zc"] = (d["tab_hole_z"][0] + d["tab_hole_z"][-1]) / 2

    # ---- internal cavity --------------------------------------------------
    # thin back wall under the big openings, thick front wall, 25.4 border
    d["cav_y0"] = d["wall_inner_y"]
    d["cav_y1"] = d["W"] - d["l127"]
    d["cav_margin"] = d["r_corner"]
    d["cav_lx"] = d["L"] - 4 * d["r_corner"]
    d["cav_lz"] = d["H"] - 4 * d["r_corner"]

    # ---- round pockets on the top / bottom faces -------------------------
    # centred over the right-hand medium bore of every group, on the top face
    d["right_bore_x"] = d["bore28_x"][1::2]
    d["pocket_x_top"] = list(d["right_bore_x"])
    d["pocket_x_bot"] = [x - d["pitch"] / 2 for x in d["right_bore_x"]]
    d["pocket_w"] = d["r_corner"] + d["d6"]           # 31.75 across X
    d["pocket_l"] = 3 * d["d12"]                      # 38.1 along Y
    d["pocket_r"] = 2 * d["l127"]                     # 5.08 corner radius
    d["pocket_yc"] = (d["front_y"] + d["W"]) / 2
    d["pocket_depth"] = d["d6"]

    # ---- round-bottomed relief at the front/bottom edge ------------------
    # half-ball cutter plunged at the front face on the group centrelines
    d["dimple_r"] = d["r_corner"] - d["l127"]
    d["dimple_z"] = d["r_corner"] / 2 + d["l127"]

    # ---- small 59 deg countersinks on the 5.11 holes ---------------------
    d["cs_half_angle"] = 59.0
    d["cs_depth"] = d["l127"] / 2
    d["cs_r"] = d["r5"] + d["cs_depth"] * math.tan(math.radians(d["cs_half_angle"]))

    # ---- 5 deg chamfer on the 28 bores ----------------------------------
    d["ch_half_angle"] = 5.0
    d["ch_depth"] = d["l127"] / 2
    d["ch_r"] = d["r28"] + d["ch_depth"] * math.tan(math.radians(d["ch_half_angle"]))

    # ---- 2.54 edge blends around the bores ------------------------------
    d["fillet_r"] = d["l127"]

    # axis of the three inclined bores, as a rotation about X
    ay, az = d["bore12_axis"][1], d["bore12_axis"][2]
    d["bore12_rot"] = -math.degrees(math.atan2(ay, az))
    return d


def _hole_y(r, y0, y1):
    """Cylinder of radius r spanning y0..y1 along +Y (axis on the Y axis)."""
    return Pos(0, (y0 + y1) / 2, 0) * Rot(90, 0, 0) * Cylinder(r, y1 - y0)


def build(p):
    # ---------------- outer body: rounded rectangle extruded in Y --------
    prof = Pos(p["L"] / 2, p["H"] / 2) * RectangleRounded(p["L"], p["H"], p["r_corner"])
    body = extrude(prof, amount=p["W"] - p["front_y"])
    body = Rot(90, 0, 0) * body          # extrusion axis Z -> -Y
    body = Pos(0, p["W"], 0) * body      # Y now spans front_y .. W

    # ---------------- four side tabs on the front face -------------------
    for tx in p["tab_x"]:
        body = body + Pos(tx, p["tab_d"] / 2, p["tab_zc"]) * Box(
            p["tab_w"], p["tab_d"], p["tab_h"])

    # ---------------- internal cavity ------------------------------------
    cav = Pos(p["L"] / 2, (p["cav_y0"] + p["cav_y1"]) / 2, p["H"] / 2) * Box(
        p["cav_lx"], p["cav_y1"] - p["cav_y0"], p["cav_lz"])
    body = body - cav

    # ---------------- three big openings in the thin back wall -----------
    for gx in p["group_x"]:
        body = body - Pos(gx, 0, p["group_z"]) * _hole_y(
            p["r127"], p["W"] - p["l127"], p["W"] + p["l127"])

    # ---------------- six medium counterbores + pilot bores --------------
    for bx in p["bore28_x"]:
        # 5 deg chamfer at the mouth
        body = body - Pos(bx, p["front_y"] + p["ch_depth"] / 2, p["bore28_z"]) * (
            Rot(90, 0, 0) * Cone(p["r28"], p["ch_r"], p["ch_depth"]))
        body = body - Pos(bx, 0, p["bore28_z"]) * _hole_y(
            p["r28"], p["front_y"] - p["l127"], p["front_y"] + p["l28"])
        # small coaxial bore through the front wall into the cavity
        body = body - Pos(bx, 0, p["bore28_z"]) * _hole_y(
            p["r6"], p["front_y"] + p["l28"], p["wall_inner_y"] + p["r6"])

    # ---------------- six 5.11 holes on the front face -------------------
    for bx in p["bore28_x"]:
        body = body - Pos(bx, p["front_y"] - p["cs_depth"] / 2, p["bore5_z"]) * (
            Rot(90, 0, 0) * Cone(p["r5"], p["cs_r"], p["cs_depth"]))
        body = body - Pos(bx, 0, p["bore5_z"]) * _hole_y(
            p["r5"], p["front_y"] - p["l127"], p["front_y"] + p["l5"])

    # ---------------- eight 5.11 holes in the tabs -----------------------
    for tx in p["tab_x"]:
        for tz in p["tab_hole_z"]:
            body = body - Pos(tx, -p["cs_depth"] / 2, tz) * (
                Rot(90, 0, 0) * Cone(p["r5"], p["cs_r"], p["cs_depth"]))
            body = body - Pos(tx, 0, tz) * _hole_y(p["r5"], -p["l5"], p["l5"])

    # ---------------- three inclined 12.7 bores -------------------------
    for c in p["bore12"]:
        body = body - Pos(c[0], c[1], c[2]) * Rot(p["bore12_rot"], 0, 0) * Cylinder(
            p["r12"], p["l12"])

    # ---------------- long transverse relief through the tabs ------------
    body = body - Pos(p["bore25_x"], p["bore25_y"], p["bore25_z"]) * Rot(0, 90, 0) * Cylinder(
        p["r25"], p["l25"])

    # ---------------- half-ball relief on the bottom front edge ----------
    for gx in p["group_x"]:
        body = body - Pos(gx, p["front_y"], p["dimple_z"]) * Sphere(p["dimple_r"])

    # ---------------- rounded pockets, top and bottom faces --------------
    def pocket(xc, ztop, up):
        pr = Pos(xc, p["pocket_yc"]) * RectangleRounded(
            p["pocket_w"], p["pocket_l"], p["pocket_r"])
        s = extrude(pr, amount=p["pocket_depth"] if up else -p["pocket_depth"])
        return Pos(0, 0, ztop) * s

    for px in p["pocket_x_top"]:
        body = body - pocket(px, p["H"], False)
        hole = Pos(px, p["pocket_yc"], p["H"] - p["pocket_depth"]) * Cylinder(
            p["r6"], p["pocket_depth"])
        body = body - hole
    for px in p["pocket_x_bot"]:
        body = body - pocket(px, 0, True)

    return body
