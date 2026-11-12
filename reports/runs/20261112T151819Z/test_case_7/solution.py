from build123d import *
import math


def derive(facts):
    d = {}
    bb = facts["bounding_box_mm"]
    d["x"] = bb["x"]
    d["y"] = bb["y"]
    d["z"] = bb["z"]

    d["mid_x"] = (9.45 + 152.25) / 2        # brief: symmetry mid-plane
    d["flange_t"] = 16.25                  # facts: Ø11 Z hole length
    d["side_t"] = 38.95                    # facts: Ø9.5 Z hole length
    d["flange_bot"] = d["z"] - d["flange_t"]
    d["side_bot"] = d["z"] - d["side_t"]

    # ---------- top flange ----------
    d["flange_cy"] = 46.5
    d["flange_hy"] = 38.95
    d["flange_hw"] = (152.25 - 32.05) / 2
    d["flange_w"] = 2 * d["flange_hw"]
    d["flange_h"] = 2 * d["flange_hy"]
    d["flange_r"] = 6.0
    d["pocket_x0"] = 32.05
    d["pocket_x1"] = 133.26
    d["pocket_y0"] = 15.75
    d["pocket_y1"] = 73.55
    d["pocket_depth"] = 9.0
    d["pocket_r"] = 6.0

    # lug positions / radii
    d["lug_yl"] = d["y"] - 85.8
    d["lug_xl"] = 9.45                     # 162.25 - 152.25 -> 10, left -> 9.45
    d["lug_xr"] = d["x"] - 152.25

    # ---------- lower plate (face normal Y, rotated 20 deg in plane) ----------
    d["plate_cx"] = 85.65
    d["plate_w"] = 85.8
    d["plate_h"] = d["y"]
    d["plate_r"] = 24.0
    d["plate_t"] = 15.75 - 2
    d["plate_y0"] = 15.75 - 4 / 2      # Ø13 counterbore mouth
    d["plate_rot"] = 20.0
    import math as _m
    _a = _m.radians(d["plate_rot"])
    d["plate_cz"] = ((d["plate_w"] / 2 - d["plate_r"]) * _m.sin(_a)
                     + (d["plate_h"] / 2 - d["plate_r"]) * _m.cos(_a)
                     + d["plate_r"])

    # ---------- big stepped bore ----------
    d["hub_r"] = 68.5 / 2 + 2
    d["hub_y0"] = 26.9 - 11.3 / 2
    d["hub_y1"] = 72.05 + 9.0 / 2
    d["bore_cx"] = 85.65
    d["bore_cz"] = 64.39
    d["b29_r"] = 29.0 / 2
    d["b29_y1"] = 26.9 + 11.3 / 2
    d["b60_r"] = 60.0 / 2
    d["b60_y1"] = 50.55 + 34 / 2
    d["b65_r"] = 65.0 / 2
    d["b65_y1"] = 72.05 + 9.0 / 2
    d["b68_r"] = 68.5 / 2
    d["b68_y1"] = 73.55 + 2.0 / 2

    # ---------- domed horizontal boss (capsule along Y) ----------
    d["dome_r"] = 15.75
    d["dome_cx"] = 84.95
    d["dome_cz"] = 135.69
    d["dome_y0"] = 0
    d["dome_y1"] = 46.5 + 75.0 / 2
    d["dome_bore_r"] = 17.5 / 2
    d["dome_cb_r"] = 26.0 / 2
    d["dome_cb_y"] = 9.0
    d["dome_groove_r"] = 28.0 / 2
    d["dome_groove_y0"] = 3.0 - 2.0 / 2
    d["dome_groove_y1"] = 3.0 + 2.0 / 2

    # ---------- web / neck ----------
    d["web_x0"] = (9.45 + 152.25) / 2 - (152.25 - 32.05) / 2
    d["web_x1"] = (9.45 + 152.25) / 2 + (152.25 - 32.05) / 2
    d["web_y0"] = 26.9 - 11.3 / 2
    d["web_y1"] = 15.75 - 4 / 2 + 15.75
    d["web_z0"] = 92.09
    d["web_z1"] = 144.61

    # ---------- small holes ----------
    d["h11_r"] = 11.0 / 2
    d["h95_r"] = 9.5 / 2
    d["h85_r"] = 8.5 / 2
    d["h13_r"] = 13.0 / 2
    d["h9_r"] = 9.0 / 2
    d["cb_depth"] = 4.0
    d["incl_r"] = 4.5 / 2
    d["incl_len"] = 22.32
    d["incl_o"] = (80.96, 84.6, 146.58)
    d["incl_dir"] = (-0.29, -0.66, 0.70)

    # ---------- placement of lugs / ribs / small holes ----------
    d["side_lug_xl"] = 9.45
    d["side_lug_xr"] = 152.25
    d["side_lug_rr"] = d["x"] - 152.25
    d["side_lug_y"] = 32.05
    d["flange_xl"] = d["mid_x"] - d["flange_hw"]
    d["flange_xr"] = d["mid_x"] + d["flange_hw"]
    d["ylug_xl"] = 43.65
    d["ylug_xr"] = 113.95
    d["ylug_y"] = 85.8

    d["rib_inset"] = d["y"] - 85.8
    d["rib_y"] = (d["web_y0"] + d["web_y1"]) / 2
    d["rib_z"] = (d["web_z0"] + d["web_z1"]) / 2
    d["rib_w"] = 29.0
    d["rib_d"] = 16.25
    d["rib_h"] = 38.95
    d["rib_angle"] = 32.05

    d["sh1_x"] = 80.15
    d["sh1_z"] = 11.24
    d["sh2_x"] = 104.55
    d["sh2_z"] = 92.09
    d["p85_x1"] = 133.25
    d["p85_z1"] = 37.69
    d["p85_x2"] = 52.75
    d["p85_z2"] = 62.89
    d["hole_deep"] = 38.95
    d["b28_r"] = 28.0 / 2
    d["b21_r"] = 21.0 / 2
    d["b18_r"] = 18.0 / 2
    d["b21_y0"] = 26.9
    d["b21_y1"] = 26.9 + 2
    return d


def _cyl_y(radius, y0, y1, x, z):
    return Pos(x, (y0 + y1) / 2, z) * Rot(90, 0, 0) * Cylinder(radius, y1 - y0)


def _cyl_z(radius, z0, z1, x, y):
    return Pos(x, y, (z0 + z1) / 2) * Cylinder(radius, z1 - z0)


def build(p):
    solids = []

    # ----- lower plate -----
    prof = RectangleRounded(p["plate_w"], p["plate_h"], p["plate_r"])
    plate = extrude(prof, p["plate_t"])
    plate = (Pos(p["plate_cx"], p["plate_y0"] + p["plate_t"], p["plate_cz"])
             * Rot(0, p["plate_rot"], 0)
             * Rot(90, 0, 0) * plate)
    solids.append(plate)

    # ----- big bore hub -----
    solids.append(_cyl_y(p["hub_r"], p["hub_y0"], p["hub_y1"],
                         p["bore_cx"], p["bore_cz"]))

    # ----- top flange -----
    main = Pos(p["mid_x"], p["flange_cy"], p["flange_bot"]) * extrude(
        RectangleRounded(p["flange_w"], p["flange_h"], p["flange_r"]),
        p["flange_t"])
    solids.append(main)

    # side lugs (deep) + necks
    for lugx, lugr, sx in ((p["side_lug_xl"], p["side_lug_xl"], p["flange_xl"]),
                           (p["side_lug_xr"], p["side_lug_rr"], p["flange_xr"])):
        solids.append(_cyl_z(lugr, p["side_bot"], p["z"], lugx, p["side_lug_y"]))
        neck = Pos((lugx + sx) / 2, p["side_lug_y"],
                   (p["flange_bot"] + p["z"]) / 2) * Box(
            abs(sx - lugx), 2 * lugr, p["z"] - p["flange_bot"])
        solids.append(neck)

    # +Y lugs
    for lx in (p["ylug_xl"], p["ylug_xr"]):
        solids.append(_cyl_z(p["lug_yl"], p["flange_bot"], p["z"], lx, p["ylug_y"]))

    # ----- domed boss (capsule along Y) -----
    cyl = _cyl_y(p["dome_r"], p["dome_y0"], p["dome_y1"] - p["dome_r"],
                 p["dome_cx"], p["dome_cz"])
    sph1 = Pos(p["dome_cx"], p["dome_y1"] - p["dome_r"], p["dome_cz"]) * Sphere(p["dome_r"])
    solids.append(cyl + sph1)

    # ----- web -----
    web = Pos((p["web_x0"] + p["web_x1"]) / 2,
              (p["web_y0"] + p["web_y1"]) / 2,
              (p["web_z0"] + p["web_z1"]) / 2) * Box(
        p["web_x1"] - p["web_x0"], p["web_y1"] - p["web_y0"],
        p["web_z1"] - p["web_z0"])
    solids.append(web)

    solid = solids[0]
    for s in solids[1:]:
        solid = solid + s

    # ================= cuts =================
    holes = []
    # top flange Z holes
    for lx in (p["ylug_xl"], p["ylug_xr"]):
        holes.append(_cyl_z(p["h11_r"], p["flange_bot"] - 1, p["z"] + 1, lx, p["ylug_y"]))
    for lx in (p["side_lug_xl"], p["side_lug_xr"]):
        holes.append(_cyl_z(p["h95_r"], p["side_bot"] - 1, p["z"] + 1, lx, p["side_lug_y"]))

    # pocket
    pk = Pos((p["pocket_x0"] + p["pocket_x1"]) / 2,
             (p["pocket_y0"] + p["pocket_y1"]) / 2,
             p["z"] - p["pocket_depth"] / 2) * Box(
        p["pocket_x1"] - p["pocket_x0"], p["pocket_y1"] - p["pocket_y0"],
        p["pocket_depth"] + 1)
    holes.append(pk)

    # stepped big bore
    holes.append(_cyl_y(p["b29_r"], p["hub_y0"] - 1, p["b29_y1"], p["bore_cx"], p["bore_cz"]))
    holes.append(_cyl_y(p["b60_r"], p["b29_y1"] - 1, p["b60_y1"], p["bore_cx"], p["bore_cz"]))
    holes.append(_cyl_y(p["b65_r"], p["b60_y1"] - 1, p["b65_y1"], p["bore_cx"], p["bore_cz"]))
    holes.append(_cyl_y(p["b68_r"], p["b68_y1"], p["hub_y1"] + 1,
                        p["bore_cx"], p["bore_cz"]))

    # dome bore and counterbore
    holes.append(_cyl_y(p["dome_bore_r"], p["dome_y0"] + p["dome_cb_y"] - 1,
                        p["dome_y1"] + 1, p["dome_cx"], p["dome_cz"]))
    holes.append(_cyl_y(p["dome_cb_r"], p["dome_y0"] - 1,
                        p["dome_y0"] + p["dome_cb_y"], p["dome_cx"], p["dome_cz"]))
    holes.append(_cyl_y(p["dome_groove_r"], p["dome_groove_y0"],
                        p["dome_groove_y1"], p["dome_cx"], p["dome_cz"]))

    # extra stepped features of the boss / big bore
    holes.append(_cyl_y(p["b28_r"], p["dome_groove_y0"], p["dome_groove_y1"],
                        p["dome_cx"], p["dome_cz"]))
    holes.append(_cyl_y(p["b21_r"], p["b21_y0"], p["b21_y1"],
                        p["dome_cx"], p["dome_cz"]))
    holes.append(_cyl_y(p["b18_r"], p["plate_y0"] - 1, p["hub_y0"],
                        p["bore_cx"], p["bore_cz"]))

    # lower plate small Y holes
    for hx, hz, rr in ((p["sh1_x"], p["sh1_z"], p["h11_r"]),
                       (p["sh2_x"], p["sh2_z"], p["h9_r"])):
        holes.append(_cyl_y(rr, p["plate_y0"] - 1, p["plate_y0"] + p["hole_deep"],
                            hx, hz))
        holes.append(_cyl_y(p["h13_r"], p["plate_y0"] - 1, p["plate_y0"] + p["cb_depth"],
                            hx, hz))
    for hx, hz in ((p["p85_x1"], p["p85_z1"]), (p["p85_x2"], p["p85_z2"])):
        holes.append(_cyl_y(p["h85_r"], p["plate_y0"] - 1, p["plate_y0"] + p["hole_deep"],
                            hx, hz))

    # inclined dome vent hole
    hp = Plane(origin=p["incl_o"], z_dir=p["incl_dir"]) * Cylinder(p["incl_r"], p["incl_len"])
    holes.append(hp)

    for h in holes:
        solid = solid - h

    return solid
