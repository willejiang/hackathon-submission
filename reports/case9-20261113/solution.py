import math
from build123d import *

SQ2 = math.sqrt(2.0)


def derive(facts):
    d = {}
    bb = facts["bounding_box_mm"]
    d["L"] = bb["x"]
    d["Ymax"] = bb["y"]
    d["Zmax"] = bb["z"]

    holes = facts["cylindrical_holes_and_bores"]
    d["bolt_d"] = holes[0]["diameter"]
    d["bolt_len"] = holes[0]["lengths"][0]
    d["bore_d"] = holes[2]["diameter"]
    d["bore_len"] = holes[2]["lengths"][0]
    d["slot_d"] = holes[4]["diameter"]
    d["slot_len"] = holes[4]["lengths"][0]

    d["bore_r"] = d["bore_d"] / 2.0
    d["Ax"] = [c[0] for c in holes[2]["centres"]]
    d["Ay"] = holes[2]["centres"][0][1]
    d["Az"] = holes[2]["centres"][0][2]
    d["Bx"] = [c[0] for c in holes[3]["centres"]]
    d["By"] = holes[3]["centres"][0][1]
    d["Bz"] = holes[3]["centres"][0][2]

    d["Abx"] = [c[0] for c in holes[0]["centres"]]
    d["Aby"] = [c[1] for c in holes[0]["centres"]]
    d["Abz"] = [c[2] for c in holes[0]["centres"]]
    d["Bbx"] = [c[0] for c in holes[1]["centres"]]
    d["Bby"] = [c[1] for c in holes[1]["centres"]]
    d["Bbz"] = [c[2] for c in holes[1]["centres"]]

    d["slot_y"] = holes[4]["centres"][0][1]
    d["slot_z"] = holes[4]["centres"][0][2]

    # radii named by the brief / facts
    d["r_small"] = 6.35
    d["r_med"] = 12.7
    d["r_big"] = 25.4
    d["r_concave"] = 50.8
    d["r_apex"] = 76.2          # = diameter 152.4 arcs in facts

    # bank half width: boss outer radius + small fillet (measured 82.55)
    d["hw"] = d["r_apex"] + d["r_small"]
    d["angA"] = 45.0            # brief: axes at 45 deg to Y and Z
    d["angB"] = -d["angA"]

    # axis frame coordinates (u along bank A, v along bank B)
    d["uA"] = (d["Ay"] + d["Az"]) / SQ2
    d["vA"] = (d["Ay"] - d["Az"]) / SQ2
    d["uB"] = (d["By"] + d["Bz"]) / SQ2
    d["vB"] = (d["By"] - d["Bz"]) / SQ2

    # deck planes and rear planes (bore length gives the slab thickness)
    d["half"] = d["bore_len"] / 2.0
    d["deckA"] = d["uA"] + d["half"]
    d["deckB"] = d["vB"] + d["half"]

    # cross-section corner radii / wall and end-plate thickness (tuned)
    d["wall"] = d["r_med"] + d["r_small"] / 2.0
    d["endt"] = 25.4

    # +Y apex: the crotch formed by the two rear faces
    d["Yapex"] = (d["uA"] - d["half"] + d["vB"] - d["half"]) / SQ2
    return d


def _cross_outline(p):
    """Closed Y-Z outline of the block (exact bbox corners)."""
    Ymax = p["Ymax"]
    Zmax = p["Zmax"]
    Ytp = p["Ay"] + (p["half"] - p["hw"]) / SQ2
    Ya = p["Yapex"]
    Z1 = Zmax - (Ymax - Ytp)
    Z2 = Z1 - (Ymax - Ya)
    Z3 = Zmax - Z2
    pts = [
        (Ytp, Zmax),
        (Ymax, Z1),
        (Ya, Z2),
        (Ya, Z3),
        (Ymax, Zmax - Z1),
        (Ytp, 0.0),
        (0.0, Ytp),
        (0.0, Zmax - Ytp),
    ]
    return pts


def _extrude_face(pts, x0, x1):
    with BuildPart() as bp:
        with BuildSketch(Plane.YZ) as sk:
            Polygon(*pts, align=None)
        extrude(amount=x1 - x0)
    s = bp.part
    if x0 != 0:
        s = Pos(x0, 0, 0) * s
    return s


def build(p):
    L = p["L"]
    Ymax = p["Ymax"]
    Zmax = p["Zmax"]
    hw = p["hw"]
    half = p["half"]
    w = p["wall"]
    te = p["endt"]

    prof = _rounded_profile(p)
    outer = extrude(Plane.YZ * prof, amount=L)
    end_edges = [e for e in outer.edges()
                 if e.bounding_box().size.X < 1e-5
                 and (abs(e.center().X)<1e-4 or abs(e.center().X-L)<1e-4)]
    outer = fillet(end_edges, p["r_big"])

    # Hollow with a true constant-thickness profile rather than a scale copy.
    inner = offset(prof, amount=-w, kind=Kind.INTERSECTION)
    cavity = Pos(te,0,0) * extrude(Plane.YZ * inner, amount=L-2*te)
    part = outer - cavity

    # six bore bosses (solid, outer radius r_apex) filling the deck walls inwards
    angA = p["angA"]
    angB = p["angB"]
    bosses = []
    for x in p["Ax"]:
        bosses.append(Pos(x, p["Ay"], p["Az"]) * Rot(angB, 0, 0) *
                      Cylinder(p["r_apex"], p["bore_len"]))
    for x in p["Bx"]:
        bosses.append(Pos(x, p["By"], p["Bz"]) * Rot(angA, 0, 0) *
                      Cylinder(p["r_apex"], p["bore_len"]))
    for b in bosses:
        part = part + b

    # bores: long enough to open both ends of each boss and the deck wall
    for x in p["Ax"]:
        part = part - (Pos(x, p["Ay"], p["Az"]) * Rot(angB, 0, 0) *
                       Cylinder(p["bore_r"], p["bore_len"]+0.1))
    for x in p["Bx"]:
        part = part - (Pos(x, p["By"], p["Bz"]) * Rot(angA, 0, 0) *
                       Cylinder(p["bore_r"], p["bore_len"]+0.1))

    # Each blind bolt hole needs its own supporting boss, visible as R12.7
    # convex partial cylinders in the supplied facts. Extend behind the blind
    # bottom by the named R6.35 wall, without moving its outer head face.
    rboss = p["r_med"]
    extra = p["r_small"]
    offset_y = extra / (2 * SQ2)
    for i in range(len(p["Abx"])):
        part = part + (Pos(p["Abx"][i], p["Aby"][i]-offset_y,
                          p["Abz"][i]-offset_y) * Rot(angB,0,0) *
                       Cylinder(rboss, p["bolt_len"]+extra))
    for i in range(len(p["Bbx"])):
        part = part + (Pos(p["Bbx"][i], p["Bby"][i]-offset_y,
                          p["Bbz"][i]+offset_y) * Rot(angA,0,0) *
                       Cylinder(rboss, p["bolt_len"]+extra))

    # blind bolt holes
    rb = p["bolt_d"] / 2.0
    for i in range(len(p["Abx"])):
        part = part - (Pos(p["Abx"][i], p["Aby"][i]+0.05/SQ2, p["Abz"][i]+0.05/SQ2) *
                       Rot(angB, 0, 0) * Cylinder(rb, p["bolt_len"]+0.1))
    for i in range(len(p["Bbx"])):
        part = part - (Pos(p["Bbx"][i], p["Bby"][i]+0.05/SQ2, p["Bbz"][i]-0.05/SQ2) *
                       Rot(angA, 0, 0) * Cylinder(rb, p["bolt_len"]+0.1))

    # crankshaft slot along X cut into the -Y base face
    part = part - (Pos(L / 2.0, p["slot_y"], p["slot_z"]) * Rot(0, 90, 0) *
                   Cylinder(p["slot_d"] / 2.0, p["slot_len"]))

    return part & outer


def _erode(pts, w):
    """Offset a closed polygon inwards by w by shifting each edge along its
    interior normal and intersecting consecutive edges."""
    n = len(pts)
    # decide orientation
    area = 0.0
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    sgn = 1.0 if area > 0 else -1.0
    lines = []
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        L = math.hypot(dx, dy)
        # inward normal for CCW oriented polygon
        nx, ny = -dy / L * sgn, dx / L * sgn
        lines.append((nx, ny, nx * x1 + ny * y1 + w))
    out = []
    for i in range(n):
        a1, b1, c1 = lines[i - 1]
        a2, b2, c2 = lines[i]
        det = a1 * b2 - a2 * b1
        px = (c1 * b2 - c2 * b1) / det
        py = (a1 * c2 - a2 * c1) / det
        out.append((px, py))
    return out


def _rounded_profile(p):
    zm = p["Zmax"] / 2
    umid = (p["Ay"] + p["Az"]-zm) / SQ2
    uout = umid + p["half"]
    yt = SQ2*uout-zm
    vh = (zm-yt)/SQ2
    zh = 2*vh
    yf = zh-SQ2*vh
    ya = SQ2*vh
    ytip = (uout+vh)/SQ2
    ztip = zm-(ytip-yt)
    pts=[(0,zm-zh),(yf,zm-zh),(yt,0),(ytip,zm-ztip),
         (ya,zm),(ytip,zm+ztip),(yt,p["Zmax"]),(yf,zm+zh),(0,zm+zh)]
    prof=Polygon(*pts,align=None)
    for y,z,r in [(ya,zm,p["r_apex"]),(yf,zm+zh,p["r_concave"]),(yf,zm-zh,p["r_concave"])]:
        v=min(prof.vertices(),key=lambda q:(q.X-y)**2+(q.Y-z)**2)
        prof=fillet([v],r)
    return prof
