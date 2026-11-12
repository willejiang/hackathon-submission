"""Reconstruction of a hydraulic pump main body (test_case_8).

All dimensions come from facts.json / the design brief, or are derived from
them by formula.
"""
import math

from build123d import (
    Align, Box, Circle, Cone, Cylinder, Polygon, Pos, Rectangle, Rot,
    extrude, fillet,
)


def _by_dia(holes, dia):
    for h in holes:
        if abs(h["diameter"] - dia) < 1e-9:
            return h
    raise KeyError(dia)


def derive(facts):
    d = {}
    bb = facts["bounding_box_mm"]
    d["L"] = bb["x"]
    d["W"] = bb["y"]
    d["H"] = bb["z"]

    d["cx"] = d["L"] / 2

    holes = facts["cylindrical_holes_and_bores"]
    h7 = _by_dia(holes, 7)
    h6 = _by_dia(holes, 6)
    h42 = _by_dia(holes, 4.2)
    h20 = _by_dia(holes, 20)

    d["bolt_r"] = h7["diameter"] / 2
    d["bolt_pts"] = [tuple(c) for c in h7["centres"]]

    d["blind_r"] = h6["diameter"] / 2
    d["blind_depth"] = h6["lengths"][0]
    d["blind_pts"] = [tuple(c) for c in h6["centres"]]

    d["cross_r"] = h42["diameter"] / 2
    d["cross_pts"] = [tuple(c) for c in h42["centres"]]
    d["cross_len"] = h42["lengths"][0]

    d["bore_r"] = h20["diameter"] / 2
    d["bore_c"] = tuple(h20["centres"][0])
    d["bore_len"] = h20["lengths"][0]

    d["mid_y"] = d["bore_c"][1]

    ys = sorted({p[1] for p in d["bolt_pts"]})
    d["y_top"] = ys[-1]
    d["y_bot"] = ys[0]
    side = [p for p in d["bolt_pts"] if abs(p[1] - d["mid_y"]) < 1e-6]
    d["side_dx"] = abs(side[0][0] - d["cx"])
    d["rect_w"] = 2 * d["side_dx"]

    # figure-eight window: two circular bores of 44.45 dia; centres offset
    # inwards from the corner bolt rows by half the bolt rectangle width.
    d["win_r"] = 44.45 / 2
    corner_hi = min(p[1] for p in d["bolt_pts"] if p[1] > d["mid_y"])
    corner_lo = max(p[1] for p in d["bolt_pts"] if p[1] < d["mid_y"])
    d["win_y1"] = corner_hi - d["side_dx"]
    d["win_y2"] = corner_lo + d["side_dx"]

    d["outer_r"] = 60 / 2
    d["web_half"] = 66 / 2
    d["web_x0"] = d["cx"] - d["web_half"]
    d["web_x1"] = d["cx"] + d["web_half"]
    d["lobe_r"] = 12 / 2

    # feet
    d["foot_in0"] = d["cx"] - d["side_dx"]
    d["foot_cham"] = d["outer_r"] - d["win_r"]
    d["foot_in1"] = d["foot_in0"] + d["foot_cham"]
    d["foot_y1"] = d["y_bot"]

    # pocket on the outer face (left/right views)
    d["pocket_w"] = 8.0
    d["pocket_h"] = 11.0
    d["pocket_d"] = 4.0
    d["pocket_z1"] = d["H"] - 9.0
    d["pocket_z2"] = 9.0
    d["pocket_y"] = 3.0 + d["pocket_w"] / 2

    d["cham_ang"] = 59.0
    d["cham_d"] = 1.0

    return d


def _sink(r, depth, ang_deg):
    """Countersink tool: large end at z=0, small end at z=depth, axis +Z."""
    grow = depth * math.tan(math.radians(ang_deg))
    return Cone(bottom_radius=r + grow, top_radius=r, height=depth,
                align=(Align.CENTER, Align.CENTER, Align.MIN))


def build(p):
    cx = p["cx"]
    H = p["H"]
    L = p["L"]

    # ---------------------------------------------------------------- profile
    d1 = Pos(cx, p["win_y1"], 0) * Circle(p["outer_r"])
    d2 = Pos(cx, p["win_y2"], 0) * Circle(p["outer_r"])
    web = Pos(cx, (p["win_y1"] + p["win_y2"]) / 2, 0) * Rectangle(
        2 * p["web_half"], p["win_y1"] - p["win_y2"])
    prof = d1 + d2 + web
    for (bx, by) in p["bolt_pts"]:
        prof = prof + Pos(bx, by, 0) * Circle(p["lobe_r"])

    def foot_pts(mirror):
        c = p["foot_cham"]
        xi0 = p["foot_in0"]
        xi1 = p["foot_in1"]
        yT = p["foot_y1"]
        pts = [
            (0.0, 0.0),
            (xi0, 0.0),
            (xi1, c),
            (xi1, yT),
            (11.0, yT),
            (0.0, c),
        ]
        if mirror:
            pts = [(L - u, v) for (u, v) in pts]
        return pts

    prof = prof + Polygon(*foot_pts(False), align=None)
    prof = prof + Polygon(*foot_pts(True), align=None)

    body = extrude(prof, amount=H)

    # ------------------------------------------------------------- bolt holes
    for (bx, by, bz) in p["bolt_pts"]:
        body = body - Pos(bx, by, H / 2) * Cylinder(p["bolt_r"], H)
        body = body - Pos(bx, by, H) * Rot(180, 0, 0) * _sink(p["bolt_r"], p["cham_d"], p["cham_ang"])
        body = body - Pos(bx, by, 0) * _sink(p["bolt_r"], p["cham_d"], p["cham_ang"])

    # -------------------------------------------------------- figure-eight window
    win = Pos(cx, p["win_y1"], 0) * Circle(p["win_r"])
    win = win + Pos(cx, p["win_y2"], 0) * Circle(p["win_r"])
    win = extrude(win, amount=H + 2)
    body = body - Pos(0, 0, -1) * win

    # ------------------------------------------------------------- main X bore
    yb, zb = p["bore_c"][1], p["bore_c"][2]
    tool = Pos(p["web_x0"] + p["bore_len"] / 2, yb, zb) * Rot(0, 90, 0) * \
        Cylinder(p["bore_r"], p["bore_len"])
    body = body - tool
    body = body - Pos(p["web_x0"], yb, zb) * Rot(0, 270, 0) * _sink(p["bore_r"], p["cham_d"], p["cham_ang"])
    body = body - Pos(p["web_x1"], yb, zb) * Rot(0, 90, 0) * _sink(p["bore_r"], p["cham_d"], p["cham_ang"])

    # --------------------------------------------------------- 4 cross holes
    for (xx, yy, zz) in p["cross_pts"]:
        tool = Pos(p["web_x0"] + p["cross_len"] / 2, yy, zz) * Rot(0, 90, 0) * \
            Cylinder(p["cross_r"], p["cross_len"])
        body = body - tool
        body = body - Pos(p["web_x0"], yy, zz) * Rot(0, 270, 0) * _sink(p["cross_r"], p["cham_d"], p["cham_ang"])
        body = body - Pos(p["web_x1"], yy, zz) * Rot(0, 90, 0) * _sink(p["cross_r"], p["cham_d"], p["cham_ang"])

    # --------------------------------------------------- front face blind holes
    for (xx, yy, zz) in p["blind_pts"]:
        tool = Pos(xx, p["blind_depth"] / 2, zz) * Rot(90, 0, 0) * \
            Cylinder(p["blind_r"], p["blind_depth"])
        body = body - tool

    # ------------------------------------------------------- foot outer pockets
    for xf, sgn in ((0.0, 1), (L, -1)):
        for zc in (p["pocket_z2"], p["pocket_z1"]):
            box = Box(p["pocket_d"], p["pocket_w"], p["pocket_h"],
                      align=(Align.CENTER, Align.CENTER, Align.CENTER))
            body = body - Pos(xf + sgn * (p["pocket_d"] / 2 - 1),
                              p["pocket_y"], zc) * box

    return body
