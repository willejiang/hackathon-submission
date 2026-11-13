"""Reproduce the controlled probe from the case-8 output at commit d3ee186.

Usage: python case8_probe.py previous.stp candidate.stp
The locations of cross-drillings are stated in the brief. The short internal
plug interval is an image-based hypothesis, subject to official validation.
"""
import sys
from build123d import Cylinder, Pos, Rot, export_step, import_step

body = import_step(sys.argv[1])
for y in (60.45, 85.45):
    for z in (7.6, 32.6):
        for x in (15.5, 64.5):
            body += Pos(x, y, z) * Rot(0, 90, 0) * Cylinder(2.1, 5)
assert body.is_valid and len(body.solids()) == 1
export_step(body, sys.argv[2])
