from build123d import *
def derive(facts):
    d = {}
    d["a"] = facts["bounding_box_mm"]["x"]
    d["r"] = 11.0 / 2
    return d
def _cyl_y(radius, y0, y1, x, z):
    return Pos(x, (y0 + y1) / 2.0, z) * Rot(90, 0, 0) * Cylinder(radius, y1 - y0)
def build(p):
    return _cyl_y(p["r"], 0, p["a"], 0, 0)
