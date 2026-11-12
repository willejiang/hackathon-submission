"""Measure the produced solid into facts.json's own structure.

Written for test_case_3's scaffold: one bore family along X, two coaxial shaft
families along X, no partial arcs, no rounds, no tori, no cones.

Only the shape reaches this module. Every number below is read off the B-rep.
"""

import math

from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cone, GeomAbs_Torus


def _cylinders(shape):
    """Group cylindrical faces into full cylinders and partial arcs."""
    groups = {}
    for face in shape.faces():
        if face.geom_type.name != "CYLINDER":
            continue
        axis = face.axis_of_rotation
        centre = face.center()
        direction = axis.direction
        offset = centre - axis.position
        radial = offset - direction * offset.dot(direction)
        radial_len = math.sqrt(radial.X ** 2 + radial.Y ** 2 + radial.Z ** 2)
        if radial_len < 1e-9:
            continue
        normal = face.normal_at(centre)
        dot = (normal.X * radial.X + normal.Y * radial.Y + normal.Z * radial.Z) / radial_len

        projections = [
            vertex.X * direction.X + vertex.Y * direction.Y + vertex.Z * direction.Z
            for vertex in face.vertices()
        ]
        extent = (max(projections) - min(projections)) if projections else 0.0

        components = [abs(direction.X), abs(direction.Y), abs(direction.Z)]
        label = "XYZ"[components.index(max(components))]

        key = (round(face.radius * 2.0, 3), label, "bore" if dot < 0 else "shaft")
        group = groups.setdefault(
            key,
            {"diameter": round(face.radius * 2.0, 3), "axis": label,
             "kind": "bore" if dot < 0 else "shaft",
             "faces": 0, "area": 0.0, "extent": 0.0, "centre": centre},
        )
        group["faces"] += 1
        group["area"] += float(face.area)
        group["extent"] = max(group["extent"], extent)

    for group in groups.values():
        radius = group["diameter"] / 2.0
        if radius > 1e-9 and group["extent"] > 1e-9:
            fraction = (group["area"] / (radius * group["extent"])) / (2.0 * math.pi)
        else:
            fraction = 1.0
        group["full"] = fraction > 0.9
        group["span"] = min(fraction, 2.0)
    return list(groups.values())


def _family(groups, kind):
    out = []
    for group in sorted(groups, key=lambda g: -g["diameter"]):
        if not group["full"] or group["kind"] != kind:
            continue
        centre = group["centre"]
        out.append(
            {
                "diameter": group["diameter"],
                "axis": group["axis"],
                "count": group["faces"],
                "lengths": [round(group["extent"], 3)],
                "centres": [[round(centre.X, 3), round(centre.Y, 3), round(centre.Z, 3)]],
            }
        )
    return out


def measure(shape):
    tori = {}
    cones = {}
    face_types = {}

    for face in shape.faces():
        kind = face.geom_type.name
        face_types[kind] = face_types.get(kind, 0) + 1
        adaptor = BRepAdaptor_Surface(face.wrapped)
        surface_type = adaptor.GetType()
        if surface_type == GeomAbs_Torus:
            radius = round(adaptor.Torus().MinorRadius(), 2)
            tori[str(radius)] = tori.get(str(radius), 0) + 1
        elif surface_type == GeomAbs_Cone:
            angle = round(math.degrees(adaptor.Cone().SemiAngle()), 1)
            cones[str(angle)] = cones.get(str(angle), 0) + 1

    groups = _cylinders(shape)
    box = shape.bounding_box()

    arcs = [
        {"diameter": g["diameter"], "type": "convex" if g["kind"] == "shaft" else "concave",
         "faces": g["faces"]}
        for g in groups
        if not g["full"]
    ]
    rounds = [
        {"radius": round(g["diameter"] / 2.0, 3), "type": "convex round", "faces": g["faces"]}
        for g in groups
        if not g["full"] and g["kind"] == "shaft"
    ]

    return {
        "bounding_box_mm": {
            "x": round(box.size.X, 3),
            "y": round(box.size.Y, 3),
            "z": round(box.size.Z, 3),
        },
        "volume_mm3": round(float(shape.volume), 2),
        "surface_area_mm2": round(float(shape.area), 2),
        "solids": len(list(shape.solids())),
        "through_holes_genus": _genus(shape),
        "faces": len(list(shape.faces())),
        "edges": len(list(shape.edges())),
        "face_types": face_types,
        "cylindrical_holes_and_bores": _family(groups, "bore"),
        "cylindrical_shafts_and_bosses": _family(groups, "shaft"),
        "partial_cylinders_arcs": arcs,
        "fillets_rounds_from_cylinders": rounds,
        "fillets_from_tori_minor_radii": tori,
        "cones_half_angle_deg": cones,
    }


def _genus(shape):
    """Euler characteristic of the closed surface: chi = 2 - 2g."""
    vertices, triangles = shape.tessellate(0.1, 0.3)
    points = [(v.X, v.Y, v.Z) for v in vertices]
    welded = {}
    for index, point in enumerate(points):
        key = (round(point[0], 4), round(point[1], 4), round(point[2], 4))
        welded.setdefault(key, len(welded))
    faces = {(welded[(round(points[a][0], 4), round(points[a][1], 4), round(points[a][2], 4))],
              welded[(round(points[b][0], 4), round(points[b][1], 4), round(points[b][2], 4))],
              welded[(round(points[c][0], 4), round(points[c][1], 4), round(points[c][2], 4))])
             for a, b, c in triangles}
    edges = set()
    for a, b, c in faces:
        for u, v in ((a, b), (b, c), (c, a)):
            edges.add((min(u, v), max(u, v)))
    return (2 - (len(welded) - len(edges) + len(faces))) // 2
