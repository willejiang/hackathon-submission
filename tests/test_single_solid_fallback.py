"""A bad STEP must not ship or exhaust the whole-run deadline during recovery."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'src'))
import agent_docker as runner


class TestSingleSolidFallback(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.case = self.root / 'test_case_1'
        self.case.mkdir()
        (self.case / 'facts.json').write_text(json.dumps({
            'bounding_box_mm': {'x': 10, 'y': 10, 'z': 10}, 'volume_mm3': 1000,
        }))
        self.target = self.root / 'result.stp'
        self.snap = self.root / 'scratch/snapshots/test_case_1'
        self.snap.mkdir(parents=True)

    def test_multiple_solids_recover_a_real_valid_snapshot(self):
        from build123d import Box, Compound, Cylinder, Pos, export_step, import_step
        bad = Compound(children=[Box(2, 2, 2), Pos(5, 0, 0) * Box(2, 2, 2)])
        export_step(bad, str(self.target))
        good = Cylinder(4, 5) - Cylinder(2, 7)
        snapshot = self.snap / '0001.stp'
        export_step(good, str(snapshot))
        expected = snapshot.read_bytes()
        with patch.object(runner, 'SCRATCH', self.root / 'scratch'):
            message = runner.ensure_single_solid(self.case, self.target, time.time() + 20)
        self.assertIn('snapshot 0001.stp', message)
        self.assertEqual(self.target.read_bytes(), expected)
        shape = import_step(str(self.target))
        self.assertTrue(shape.is_valid)
        self.assertEqual(len(shape.solids()), 1)
        self.assertAlmostEqual(shape.volume, good.volume, places=4)

    def test_slow_reader_cannot_scan_six_snapshots_past_deadline(self):
        from build123d import Box, export_step, import_step
        export_step(Box(2, 2, 2), str(self.target))
        for n in range(6):
            (self.snap / f'{n:04}.stp').write_bytes(self.target.read_bytes())
        clock = [100.0]
        calls = []
        def slow_reader(path, timeout):
            calls.append(timeout)
            clock[0] += timeout
            return -1
        with patch.object(runner, 'SCRATCH', self.root / 'scratch'), \
             patch.object(runner.time, 'time', side_effect=lambda: clock[0]), \
             patch.object(runner, '_solid_count', side_effect=slow_reader):
            message = runner.ensure_single_solid(self.case, self.target, 102.0)
        self.assertEqual(calls, [1.0])
        self.assertIn('envelope box', message)
        shape = import_step(str(self.target))
        self.assertEqual(len(shape.solids()), 1)
        self.assertAlmostEqual(shape.volume, 1000, places=5)


if __name__ == '__main__':
    unittest.main()
