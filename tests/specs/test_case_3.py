"""Reference spec for test_case_3 — crankshaft bushing (flanged sleeve).

Written by hand from `description.md` + `facts.json` to validate the pipeline, and
kept as a test fixture. It is what the model is asked to produce: every dimension
through `derive()`, `build()` limited to structural literals.

Axes: the part's own frame, millimetres, bbox minimum corner at the origin, so the
sleeve axis runs along X and the annulus is centred at (·, 66.04, 66.04).

This file is inert unless AGENTIC_CAD_SPEC_DIR points at its directory.
"""

from build123d import Cylinder, Pos, Rot


def derive(facts):
    d = {}
    box = facts["bounding_box_mm"]
    bores = facts["cylindrical_holes_and_bores"]
    bosses = facts["cylindrical_shafts_and_bosses"]

    # grounded: the bore is the only through-passage; the two bosses are the two
    # stepped outer diameters, distinguished by their stated axial lengths.
    d["bore_d"] = bores[0]["diameter"]
    d["total_l"] = box["x"]
    d["flange_d"] = bosses[0]["diameter"]
    d["flange_l"] = bosses[0]["lengths"][0]
    d["sleeve_d"] = bosses[1]["diameter"]
    d["sleeve_l"] = bosses[1]["lengths"][0]

    # derived
    d["bore_r"] = d["bore_d"] / 2
    d["flange_r"] = d["flange_d"] / 2
    d["sleeve_r"] = d["sleeve_d"] / 2
    d["sleeve_x0"] = 0.0
    d["sleeve_mid"] = d["sleeve_l"] / 2
    d["flange_x0"] = d["sleeve_l"]
    d["flange_mid"] = d["sleeve_l"] + d["flange_l"] / 2
    d["bore_mid"] = d["total_l"] / 2
    return d


def build(p):
    # Cylinder is Z-up; Rot(0, 90, 0) maps the axis onto +X.
    axial = Rot(0, 90, 0)

    sleeve = Pos(p["sleeve_mid"], 0, 0) * axial * Cylinder(p["sleeve_r"], p["sleeve_l"])
    flange = Pos(p["flange_mid"], 0, 0) * axial * Cylinder(p["flange_r"], p["flange_l"])
    body = sleeve + flange

    # One bore through the whole length: coaxial with both outer surfaces.
    bore = Pos(p["bore_mid"], 0, 0) * axial * Cylinder(p["bore_r"], p["total_l"])
    return body - bore


NOTES = "no estimated or assumed parameters; every dimension comes from facts.json"
