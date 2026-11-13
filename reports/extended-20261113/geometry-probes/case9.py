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
    d["endt"] = 19.05

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
    L, te = p["L"], p["endt"]
    prof = _rounded_profile(p)
    outer = extrude(Plane.YZ * prof, amount=L)
    end_edges=[e for e in outer.edges() if e.bounding_box().size.X<1e-5 and (abs(e.center().X)<1e-4 or abs(e.center().X-L)<1e-4)]
    outer=fillet(end_edges,p["r_big"])

    # Open crankcase: its sloped roof is the back face of each cylinder bank.
    # The visible upper and lower frame edges lie a half bank width off centre.
    ur=p["uA"]-p["half"]
    vr=p["vB"]-p["half"]
    zhi=(ur-(p["vA"]-p["hw"]))/SQ2
    zlo=((p["uB"]-p["hw"])-vr)/SQ2
    yi=(ur+vr)/SQ2
    zi=(ur-vr)/SQ2
    yhi=ur*SQ2-zhi
    ylo=vr*SQ2+zlo
    # Keep a 12.7 mm back wall under the rounded V valley.
    # Exact sharp V root is sqrt(2)*hw; R76.2 moves it by R*(sqrt(2)-1).
    ycap=175.26-p["r_med"]
    crank_pts=[(-2,zlo),(-2,zhi),(yhi,zhi),(ycap,ur*SQ2-ycap),
               (ycap,ycap-vr*SQ2),(ylo,zlo)]
    crank=_extrude_face(crank_pts,te,L-te)
    part=outer-crank

    # Bank cooling / relief pockets. Preserve the R76.2 cylinder envelopes,
    # R12.7 blind-bolt posts and the narrow radial webs visible on the decks.
    depth=127.0
    wcut=p["r_apex"]-p["r_small"]
    for bank in ["A","B"]:
        xs=p[bank+"x"]
        x0=min(xs)-p["hw"]
        x1=max(xs)+p["hw"]
        ang=p["angB"] if bank=="A" else p["angA"]
        cy,cz=p[bank+"y"],p[bank+"z"]
        def place(obj): return Pos(0,cy,cz)*Rot(ang,0,0)*obj
        # In bank coordinates X is longitudinal, Y transverse, Z the bore axis.
        zz=(p["half"]-depth/2+.01)*(1 if bank=="A" else -1)
        cutter=place(Pos((x0+x1)/2,0,zz)*Box(x1-x0,2*wcut,depth+.02))
        for x in xs:
            cutter=cutter-place(Pos(x,0,zz)*Cylinder(p["r_apex"],depth+.4))
        for i,x in enumerate(p[bank+"bx"]):
            wy,wz=p[bank+"by"][i],p[bank+"bz"][i]
            trans=((wy-cy)-(wz-cz))/SQ2 if bank=="A" else ((wy-cy)+(wz-cz))/SQ2
            # Ribs at each bolt line, with a short spoke out to the frame.
            post_depth=p["bolt_len"]+p["r_small"]
            post_z=(p["half"]-post_depth/2+.01)*(1 if bank=="A" else -1)
            cutter=cutter-place(Pos(x,trans,post_z)*Cylinder(p["r_med"],post_depth+.02))
            cutter=cutter-place(Pos((x0+x1)/2,trans,zz)*Box(x1-x0+1,p["r_small"],depth+.4))
            spoke_mid=(trans+(wcut if trans>0 else -wcut))/2
            cutter=cutter-place(Pos(x,spoke_mid,zz)*Box(p["r_small"],abs(wcut-abs(trans))+.1,depth+.4))
        part=part-cutter

    for bank in ["A","B"]:
        ang=p["angB"] if bank=="A" else p["angA"]
        for x in p[bank+"x"]:
            part=part-Pos(x,p[bank+"y"],p[bank+"z"])*Rot(ang,0,0)*Cylinder(p["bore_r"],p["bore_len"]+.1)
        for i,x in enumerate(p[bank+"bx"]):
            sign=1 if bank=="A" else -1
            part=part-Pos(x,p[bank+"by"][i]+.05/SQ2,p[bank+"bz"][i]+sign*.05/SQ2)*Rot(ang,0,0)*Cylinder(p["bolt_d"]/2,p["bolt_len"]+.1)
    part=part-Pos(L/2,p["slot_y"],p["slot_z"])*Rot(0,90,0)*Cylinder(p["slot_d"]/2,p["slot_len"]+.1)
    return part


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
    # Side-view measurements distinguish two R50.8 valley rounds and a
    # straight 6.9 inch root from a single circular V apex.
    zm=p["Zmax"]/2
    yt=p["Ay"]+(p["half"]-p["hw"])/SQ2
    yf=(zm-yt)*(SQ2-1)
    zfront=zm-2*(zm-yt)/SQ2
    zpeak=p["Zmax"]-(p["Ymax"]-yt)
    yroot=175.26
    zroot_hi=zpeak-(p["Ymax"]-yroot)
    zroot_lo=p["Zmax"]-zroot_hi
    pts=[(0,zfront),(yf,zfront),(yt,0),(p["Ymax"],p["Zmax"]-zpeak),
         (yroot,zroot_lo),(yroot,zroot_hi),(p["Ymax"],zpeak),(yt,p["Zmax"]),
         (yf,p["Zmax"]-zfront),(0,p["Zmax"]-zfront)]
    prof=Polygon(*pts,align=None)
    for y,z in [(yroot,zroot_lo),(yroot,zroot_hi),(yf,zfront),(yf,p["Zmax"]-zfront)]:
        v=min(prof.vertices(),key=lambda q:(q.X-y)**2+(q.Y-z)**2)
        prof=fillet([v],p["r_concave"])
    return prof
