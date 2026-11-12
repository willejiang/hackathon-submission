from build123d import *
import math


def derive(facts):
    d = {}
    bb = facts["bounding_box_mm"]
    d["X"] = bb["x"]
    d["Y"] = bb["y"]
    d["Z"] = bb["z"]

    # ---- diameters / lengths (facts.json + design brief) ----
    d["shaft_r"] = 76.2 / 2          # journal and exposed pin diameter
    d["pin_r"] = 101.6 / 2           # crank pin / web lobe diameter
    d["lobe_r"] = 88.9 / 2           # web lobe at the rotation axis
    d["pin_len"] = 87.54             # crank pin axial length
    d["gap"] = 54.62                 # exposed pin length between the two webs
    d["blend_r"] = 169.0             # broad convex blend on the webs
    d["round_r"] = 2.54
    d["web_t"] = (d["pin_len"] - d["gap"]) / 2
    d["main_len"] = 379.46           # axial span of the throw region

    # ---- positions straight out of facts.json (bbox-min frame) ----
    pins = None
    axis = None
    for e in facts["cylindrical_shafts_and_bosses"]:
        if round(e["diameter"], 1) == 101.6:
            pins = sorted(e["centres"], key=lambda c: c[2])
        if round(e["diameter"], 1) == 88.9:
            axis = e["centres"][0]

    d["x0"] = axis[0]
    d["y0"] = axis[1]
    d["pin_centres"] = pins
    d["z0"] = pins[0][2]
    d["dz"] = (pins[2][2] - pins[0][2]) / 2
    d["end_len"] = (d["Z"] - d["main_len"]) / 2

    angs = []
    offs = []
    for c in pins:
        dx = c[0] - d["x0"]
        dy = c[1] - d["y0"]
        offs.append(math.hypot(dx, dy))
        angs.append(math.degrees(math.atan2(dy, dx)))
    d["angles"] = angs
    d["offset"] = sum(offs) / len(offs)
    return d


def build(p):
    r1 = p["lobe_r"]
    r2 = p["pin_r"]
    d = p["offset"]
    t = p["web_t"]
    R = p["blend_r"]
    x0 = p["x0"]
    y0 = p["y0"]
    hl = p["pin_len"] / 2

    parts = []

    # ---- central shaft segments on the rotation axis ----
    z0 = p["z0"]
    dz = p["dz"]
    z_bots = [0, z0 + hl, z0 + dz + hl, z0 + 2 * dz + hl]
    z_tops = [z0 - hl, z0 + dz - hl, z0 + 2 * dz - hl, p["Z"]]
    for a, b in zip(z_bots, z_tops):
        parts.append(Pos(x0, y0, (a + b) / 2) * Cylinder(p["shaft_r"], b - a))

    # ---- the three throws: pin + two counterweight webs ----
    for ang, i in zip(p["angles"], range(3)):
        zc = z0 + i * dz
        parts.append(Pos(x0, y0, zc) * Rot(0, 0, ang) *
                     Pos(d, 0, 0) * Cylinder(p["shaft_r"], p["pin_len"]))

        for zb in (zc - hl, zc + hl - t):
            # web profile: lobe at the pin + lobe at the axis blended by R169
            prof = Cylinder(r1, t) + Pos(d, 0, 0) * Cylinder(r2, t)
            prof = fillet(prof.edges().filter_by(Axis.Z), R)
            parts.append(Pos(x0, y0, zb + t / 2) * Rot(0, 0, ang) * prof)

    solid = parts[0]
    for q in parts[1:]:
        solid = solid + q
    return solid
