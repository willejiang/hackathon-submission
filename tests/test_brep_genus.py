"""Recover passage counts from CAD topology when triangles have seam cracks."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from agentic_cad import factsgen, meshutil
from build123d import Box, Compound, Cone, Cylinder, Pos, Sphere, Torus


class TestBrepGenus(unittest.TestCase):
    def test_periodic_faces_annular_wires_and_poles(self):
        models = [
            ('box', Box(10, 10, 10), 0),
            ('sphere', Sphere(10), 0),
            ('cone pole', Cone(10, 0, 20), 0),
            ('cylinder seam', Cylinder(10, 10), 0),
            ('annular faces', Cylinder(10, 10) - Cylinder(5, 12), 1),
            ('blind pocket', Box(30, 30, 30) - Pos(0, 0, 10) * Cylinder(5, 15), 0),
            ('two periodic directions', Torus(20, 5), 1),
        ]
        for name, shape, expected in models:
            with self.subTest(name=name):
                self.assertEqual(factsgen._brep_genus(shape), expected)
                with patch.object(meshutil, 'genus', return_value=None):
                    self.assertEqual(factsgen._genus(shape), expected)

    def test_multiple_shells_are_not_counted_as_passage_handles(self):
        cavity = Box(20, 20, 20) - Sphere(5)
        self.assertEqual(len(cavity.shells()), 2)
        self.assertIsNone(factsgen._brep_genus(cavity))
        compound = Compound(children=[Box(2, 2, 2), Pos(5, 0, 0) * Box(2, 2, 2)])
        self.assertIsNone(factsgen._brep_genus(compound))


if __name__ == '__main__':
    unittest.main()
