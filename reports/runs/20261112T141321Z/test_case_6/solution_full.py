import math
from build123d import *


def derive(facts):
    """Every dimension comes from facts.json or the design brief."""
    d = {}
    bb = facts["bounding_box_mm"]
    bosses = facts["cylindrical_shafts_and_bosses"]
    hole = facts["cylindrical_holes_and_bores"][0]

    d["turn"] = 2 * 180                                   # structural 180
    d["r_flange"] = bosses[0]["diameter"] / 2.0           # 70
    d["flange_t"] = 27.5                                  # brief
    d["flange_band"] = bosses[0]["lengths"][0]            # 7.5
    d["flange_band_zc"] = bosses[0]["centres"][0][2]      # 13.75
    d["r_round"] = 10.0                                   # brief R10 / facts torus
    d["r_cap"] = bosses[1]["diameter"] / 2.0              # 36.5
    d["cap_t"] = 27.5                                     # brief
    d["r_cap_flat"] = 53.0 / 2.0                          # brief
    d["cap_band_zc"] = bosses[1]["centres"][0][2]         # 122.75
    d["h"] = bb["z"]                                      # 136.5
    d["cone_base_r"] = 120.0 / 2.0                        # brief Ø120
    d["cone_top_r"] = 53.0 / 2.0                          # brief Ø53
    d["cone_z0"] = d["flange_t"]                          # 27.5
    d["cone_z1"] = d["h"] - d["cap_t"]                    # 109.0
    d["bore_r"] = hole["diameter"] / 2.0                  # 15
    d["bore_depth"] = hole["lengths"][0]                  # 17.5

    # sunburst: 18 grooves -> BSPLINE faces / TORUS count (both facts)
    d["n_fin"] = facts["face_types"]["BSPLINE"] // facts["face_types"]["TORUS"]
    d["pitch"] = d["turn"] / d["n_fin"]
    d["groove_half"] = d["pitch"] / 4.0

    # groove cut solid spanning the conical body
    d["gz0"] = d["cone_z0"] - d["r_round"]                # 17.5
    d["gz1"] = d["cone_z1"] + d["r_round"]                # 119
    slope = (d["cone_base_r"] - d["cone_top_r"]) / (d["cone_z1"] - d["cone_z0"])
    d["a0"] = d["cone_base_r"] + slope * (d["cone_z0"] - d["gz0"])
    d["a1"] = d["cone_top_r"] - slope * (d["gz1"] - d["cone_z1"])
    d["far_r"] = d["r_flange"] + d["r_round"]             # tool reach radius

    # far triangle vertices: extend from crease through the surface point at
    # the groove half angle out to far_r
    for tag, z, apex, surf in (("0", d["gz0"], d["a0"], None),
                               ("1", d["gz1"], d["a1"], None)):
        pass
    # surface radius of the body at each groove end
    surf0 = d["cone_base_r"] + slope * (d["gz0"] - d["cone_z0"])
    surf1 = d["cone_top_r"] - slope * (d["gz1"] - d["cone_z1"])
    beta = math.radians(d["groove_half"])
    for tag, apex, surf in (("0", d["a0"], surf0), ("1", d["a1"], surf1)):
        sx = surf * math.cos(beta)
        sy = surf * math.sin(beta)
        k = (d["far_r"] - apex) / (sx - apex)
        d["fx" + tag] = apex + k * (sx - apex)
        d["fy" + tag] = k * sy

    # shell wall thickness inferred from the authoritative volume and area
    d["wall"] = 2.0 * facts["volume_mm3"] / facts["surface_area_mm2"]
    return d


def _groove(p, ang):
    with BuildPart() as gb:
        with BuildSketch(Plane.XY.offset(p["gz0"])):
            with BuildLine():
                Polyline((p["a0"], 0), (p["fx0"], p["fy0"]),
                         (p["fx0"], -p["fy0"]), close=True)
            make_face()
        with BuildSketch(Plane.XY.offset(p["gz1"])):
            with BuildLine():
                Polyline((p["a1"], 0), (p["fx1"], p["fy1"]),
                         (p["fx1"], -p["fy1"]), close=True)
            make_face()
        loft()
    return Rot(0, 0, ang) * gb.part


def build(p):
    with BuildPart() as body:
        with BuildSketch(Plane.XZ):
            with BuildLine():
                Line((0, 0), (p["bore_r"], 0))
                Line((p["bore_r"], 0), (p["r_flange"] - p["r_round"], 0))
                RadiusArc((p["r_flange"] - p["r_round"], 0),
                          (p["r_flange"], p["r_round"]), -p["r_round"])
                Line((p["r_flange"], p["r_round"]),
                     (p["r_flange"], p["flange_band_zc"] + p["flange_band"] / 2.0))
                RadiusArc((p["r_flange"], p["flange_band_zc"] + p["flange_band"] / 2.0),
                          (p["r_flange"] - p["r_round"], p["flange_t"]), -p["r_round"])
                Line((p["r_flange"] - p["r_round"], p["flange_t"]),
                     (p["cone_top_r"], p["cone_z1"]))
                RadiusArc((p["cone_top_r"], p["cone_z1"]),
                          (p["r_cap"], p["cone_z1"] + p["r_round"]), -p["r_round"])
                Line((p["r_cap"], p["cone_z1"] + p["r_round"]),
                     (p["r_cap"], p["h"] - p["r_round"]))
                RadiusArc((p["r_cap"], p["h"] - p["r_round"]),
                          (p["r_cap_flat"], p["h"]), -p["r_round"])
                Line((p["r_cap_flat"], p["h"]), (0, p["h"]))
                Line((0, p["h"]), (0, 0))
            make_face()
        revolve(axis=Axis.Z)

    solid = body.part
    for i in range(p["n_fin"]):
        solid = solid - _groove(p, i * p["pitch"])

    # hollow shell: subtract an inward offset of the outer solid
    inner = offset(solid, amount=-p["wall"])
    solid = solid - inner

    # central blind bore on the bottom face
    with BuildPart() as b:
        with Locations((0, 0, 0)):
            Cylinder(p["bore_r"], p["bore_depth"],
                     align=(Align.CENTER, Align.CENTER, Align.MIN))
    solid = solid - b.part
    return solid
