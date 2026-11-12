from build123d import *
from math import sqrt, pi


def derive(facts):
    d = {}
    bb = facts["bounding_box_mm"]
    d["L"] = bb["x"]                 # 508
    d["Ymax"] = bb["y"]              # 255.94
    d["Zt"] = bb["z"]                # 511.87
    d["Zm"] = d["Zt"] / 2.0
    d["ang45"] = 45.0                # brief: bank axes at 45 deg to Y and Z

    bores = [h for h in facts["cylindrical_holes_and_bores"]
             if abs(h["diameter"] - 127.0) < 1 and h["axis"] != "X"]
    d["bore_d"] = bores[0]["diameter"]
    d["bore_r"] = d["bore_d"] / 2.0
    d["bore_len"] = bores[0]["lengths"][0]
    c = bores[0]["centres"][0]
    d["bore_up_z"] = c[2]
    d["bore_up_y"] = c[1]

    # bank frame: u = distance along the bore axis from the crank axis
    # (Y=0, Z=Zm).  The bore midpoint sits at u_mid.
    u_mid = (d["bore_up_y"] + (d["bore_up_z"] - d["Zm"])) / sqrt(2.0)
    d["u_out"] = u_mid + d["bore_len"] / 2.0
    d["u_in"] = u_mid - d["bore_len"] / 2.0

    # plate face:  Y + Z' = sqrt2*u_out ; its +v corner reaches Z' = Zt/2
    y_top = sqrt(2.0) * d["u_out"] - d["Zm"]
    d["y_top"] = y_top
    d["v_half"] = (d["Zm"] - y_top) / sqrt(2.0)

    # key profile stations
    d["Zh"] = 2.0 * d["v_half"]                       # base-face half height
    d["y_flat"] = d["Zh"] - sqrt(2.0) * d["v_half"]   # end of the flat top
    d["y_apex"] = sqrt(2.0) * d["v_half"]             # V notch apex, mid height
    d["y_tip"] = (d["u_out"] + d["v_half"]) / sqrt(2.0)   # extreme +Y corner
    d["z_tip"] = d["Zm"] - (d["y_tip"] - y_top)

    d["r_frame"] = 50.8    # convex round, flat top -> 45 deg bank side
    d["r_v"] = 76.2        # concave round at the V apex
    d["r_corner"] = 25.4   # convex rounds on block outline / plate corners
    d["r_slot"] = d["bore_d"] / 2.0

    bh = [h for h in facts["cylindrical_holes_and_bores"]
          if abs(h["diameter"] - 9.52) < 1]
    d["bolt_r"] = bh[0]["diameter"] / 2.0
    d["bolt_depth"] = bh[0]["lengths"][0]
    d["bolts"] = [tuple(c) for h in bh for c in h["centres"]]

    d["bores_up"] = [tuple(c) for h in bores if h["centres"][0][2] > d["Zm"]
                     for c in h["centres"]]
    d["bores_dn"] = [tuple(c) for h in bores if h["centres"][0][2] < d["Zm"]
                     for c in h["centres"]]
    d["bore_cut"] = d["bore_len"] + 2

    # ---- internal crankcase cavity -------------------------------
    # The six bores are through: their inner ends (u = u_in) must open into
    # an enclosed internal void.  Section of the outer shell (mm^2):
    pts = [(0.0, -d["Zh"]), (d["y_flat"], -d["Zh"]), (d["y_top"], -d["Zm"]),
           (d["y_tip"], -d["z_tip"]), (d["y_apex"], 0.0),
           (d["y_tip"], d["z_tip"]), (d["y_top"], d["Zm"]),
           (d["y_flat"], d["Zh"]), (0.0, d["Zh"])]
    a2 = 0.0
    for i in range(len(pts)):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % len(pts)]
        a2 += x0 * y1 - x1 * y0
    a_sec = abs(a2) / 2.0 + d["r_v"] ** 2 * (1.0 - pi / 2.0 / 2.0)
    v_shell = a_sec * d["L"]
    v_cuts = (6.0 * pi * d["bore_r"] ** 2 * d["bore_len"]
              + pi * d["r_slot"] ** 2 * d["L"] / 2.0
              + 16.0 * pi * d["bolt_r"] ** 2 * d["bolt_depth"])
    d["cav_e"] = d["r_corner"]
    d["cav_y0"] = d["r_slot"] + 1.0
    # centroid of the section
    a2 = 0.0; cx = 0.0; cyv = 0.0
    for i in range(len(pts)):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % len(pts)]
        cr = x0 * y1 - x1 * y0
        a2 += cr
        cx += (x0 + x1) * cr
        cyv += (y0 + y1) * cr
    d["cav_cy"] = cx / (3.0 * a2)
    need = v_shell - v_cuts - facts["volume_mm3"]
    d["cav_k"] = sqrt(need / (a_sec * (d["L"] - 2.0 * d["cav_e"])))
    d["V_target"] = facts["volume_mm3"]
    return d


def build(p):
    Zm = p["Zm"]
    # profile in the (Y, Z') plane, Z' measured from mid height
    pts = [
        (0.0, -p["Zh"]),
        (p["y_flat"], -p["Zh"]),
        (p["y_top"], -Zm),
        (p["y_tip"], -p["z_tip"]),
        (p["y_apex"], 0.0),
        (p["y_tip"], p["z_tip"]),
        (p["y_top"], Zm),
        (p["y_flat"], p["Zh"]),
        (0.0, p["Zh"]),
    ]
    prof = Polygon(*pts, align=None)
    specs = [
        ((p["y_apex"], 0.0), p["r_v"]),
        ((p["y_flat"], p["Zh"]), p["r_frame"]),
        ((p["y_flat"], -p["Zh"]), p["r_frame"]),
    ]
    for (y, z), r in specs:
        v = min(prof.vertices(), key=lambda q: (q.X - y) ** 2 + (q.Y - z) ** 2)
        prof = fillet([v], r)

    part = extrude(Plane.YZ * prof, amount=p["L"])

    # --- cuts -------------------------------------------------------
    # crankshaft slot: half cylinder along X centred on the base face
    part = part - (Pos(0, 0, 0) * Rot(0, 90, 0) *
                   Cylinder(p["r_slot"], p["L"] * 2))
    for c in p["bores_up"]:
        cc = (c[0], c[1], c[2] - Zm)
        part = part - (Pos(*cc) * Rot(-p["ang45"], 0, 0) *
                       Cylinder(p["bore_r"], p["bore_cut"]))
    for c in p["bores_dn"]:
        cc = (c[0], c[1], c[2] - Zm)
        part = part - (Pos(*cc) * Rot(p["ang45"], 0, 0) *
                       Cylinder(p["bore_r"], p["bore_cut"]))
    for c in p["bolts"]:
        zsign = 1 if c[2] > p["Zm"] else -1
        cc = (c[0], c[1], c[2] - Zm)
        part = part - (Pos(*cc) * Rot(-p["ang45"] * zsign, 0, 0) *
                       Cylinder(p["bolt_r"], p["bolt_depth"]))
    # internal crankcase cavity: a scaled copy of the outer section,
    # enclosed in X, opening only through the six bores.  Its scale is
    # solved so that the finished solid has the measured volume.
    def with_cavity(k):
        cv = Pos(p["cav_cy"], 0) * scale(Pos(-p["cav_cy"], 0) * prof, k)
        cav = extrude(Plane.YZ * cv, amount=p["L"] - 2.0 * p["cav_e"])
        return part - (Pos(p["cav_e"], 0, 0) * cav)

    k = p["cav_k"]
    for _ in (1, 2, 3):
        body = with_cavity(k)
        c_eff = (part.volume - body.volume) / (k * k)
        k = sqrt(max(part.volume - p["V_target"], 0.0) / c_eff)
    # put the bounding-box minimum at the origin
    return Pos(0, 0, Zm) * body
