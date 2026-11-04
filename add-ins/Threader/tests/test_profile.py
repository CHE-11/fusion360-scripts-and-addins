"""Unit tests for thread section math. No Fusion session required."""

import importlib.util
import math
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'addin' / 'commands' / 'threader'
PACKAGE = 'threader_under_test'
pkg = types.ModuleType(PACKAGE)
pkg.__path__ = [str(ROOT)]
pkg.__package__ = PACKAGE
sys.modules[PACKAGE] = pkg


def load(name):
    full = f'{PACKAGE}.{name}'
    spec = importlib.util.spec_from_file_location(full, ROOT / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    module.__package__ = PACKAGE
    sys.modules[full] = module
    spec.loader.exec_module(module)
    return module


standards = load('standards')
profile = load('profile')


class StandardsTests(unittest.TestCase):
    def test_iso_m6_and_m24(self):
        m6 = standards.iso_by_size('M6')
        self.assertEqual(m6['major_mm'], 6.0)
        self.assertEqual(m6['pitch_mm'], 1.0)
        self.assertEqual(standards.iso_by_size('M24')['pitch_mm'], 3.0)

    def test_small_metric_coarse_pitches(self):
        self.assertEqual(standards.iso_by_size('M1')['pitch_mm'], 0.25)
        self.assertEqual(standards.iso_by_size('M1.2')['pitch_mm'], 0.25)
        self.assertEqual(standards.iso_by_size('M1.4')['pitch_mm'], 0.3)
        self.assertEqual(standards.iso_by_size('M1.6')['pitch_mm'], 0.35)

    def test_unc_quarter_twenty(self):
        row = standards.unc_by_size('1/4-20')
        self.assertAlmostEqual(row['major_mm'], 0.25 * 25.4)
        self.assertAlmostEqual(row['pitch_mm'], 25.4 / 20)

    def test_common_imperial_sizes(self):
        self.assertAlmostEqual(standards.unc_by_size('#2-56')['pitch_mm'], 25.4 / 56)
        self.assertAlmostEqual(standards.unc_by_size('#10-32')['pitch_mm'], 25.4 / 32)
        self.assertAlmostEqual(standards.unc_by_size('1/4-28')['major_mm'], 0.25 * 25.4)
        self.assertAlmostEqual(standards.unc_by_size('3/4-10')['pitch_mm'], 25.4 / 10)

    def test_insert_m3_is_a_starting_hole(self):
        row = standards.insert_by_size('M3')
        self.assertEqual(row['hole_mm'], 4.0)
        self.assertGreater(row['depth_mm'], 4.0)


class ProfileTests(unittest.TestCase):
    def _printable(self, **overrides):
        data = {
            'gender': 'male',
            'build': 'outset',
            'family': 'printable',
            'face_radius_mm': 5.0,
            'face_length_mm': 20.0,
            'pitch_mm': 2.0,
            'layer_mm': 0.2,
            'nozzle_mm': 0.4,
            'flank_deg': 45.0,
            'clearance_mm': 0.2,
            'axis_vertical': True,
        }
        data.update(overrides)
        return profile.resolve(data)

    def test_pitch_snaps_to_layer_height(self):
        self.assertAlmostEqual(profile.snap_pitch(2.05, 0.2, True), 2.0)
        self.assertAlmostEqual(profile.snap_pitch(2.11, 0.2, True), 2.2)
        self.assertAlmostEqual(profile.snap_pitch(2.05, 0.2, False), 2.05)

    def test_printable_crest_stays_wider_than_the_nozzle(self):
        spec = self._printable()
        self.assertGreaterEqual(spec['crest_width_mm'], 0.4)
        self.assertGreater(spec['root_width_mm'], spec['crest_width_mm'])
        self.assertLess(spec['root_width_mm'], spec['pitch_mm'])

    def test_male_clearance_shrinks_the_screw(self):
        loose = self._printable(clearance_mm=0.2)
        tight = self._printable(clearance_mm=0.0)
        self.assertLess(loose['major_mm'], tight['major_mm'])
        self.assertAlmostEqual(loose['root_radius_mm'], 5.0)
        self.assertGreater(loose['crest_radius_mm'], loose['root_radius_mm'])
        self.assertEqual(loose['operation'], 'join')

    def test_female_clearance_opens_the_nut(self):
        loose = self._printable(gender='female', build='outset', clearance_mm=0.3)
        tight = self._printable(gender='female', build='outset', clearance_mm=0.0)
        self.assertGreater(loose['minor_mm'], tight['minor_mm'])
        self.assertEqual(loose['operation'], 'join')

    def test_inset_cuts_and_outset_joins(self):
        self.assertEqual(self._printable(build='inset')['operation'], 'cut')
        self.assertEqual(self._printable(gender='female', build='inset')['operation'], 'cut')

    def test_chamfer_opens_both_ends_before_the_thread(self):
        spec = self._printable(chamfer=True, chamfer_mm=1.0)
        self.assertTrue(spec['chamfer'])
        self.assertAlmostEqual(spec['chamfer_mm'], 1.0)
        self.assertAlmostEqual(spec['offset_mm'], 1.0)
        self.assertAlmostEqual(spec['length_mm'], 18.0)
        self.assertTrue(any('chamfered' in note.lower() for note in spec['notes']))

    def test_offsets_from_both_ends(self):
        spec = self._printable(offset_mm=2, end_mm=4)
        self.assertAlmostEqual(spec['offset_mm'], 2)
        self.assertAlmostEqual(spec['end_mm'], 4)
        self.assertAlmostEqual(spec['length_mm'], 14)

    def test_flip_moves_a_short_thread_to_the_other_end(self):
        spec = self._printable(length_mm=10, offset_mm=1, flip=True)
        self.assertTrue(spec['flip'])
        self.assertAlmostEqual(spec['length_mm'], 10)
        self.assertAlmostEqual(spec['offset_mm'], 20 - 1 - 10)
        self.assertAlmostEqual(spec['inset_mm'], 1)

    def test_length_snaps_to_whole_turns(self):
        spec = self._printable(length_mm=5.5, pitch_mm=2.0)
        self.assertEqual(spec['turns'], 2)
        self.assertAlmostEqual(spec['length_mm'], 4.0)

    def test_iso_m6_truncation(self):
        spec = profile.resolve({
            'gender': 'male',
            'build': 'inset',
            'family': 'iso',
            'size': 'M6',
            'face_radius_mm': 3.0,
            'face_length_mm': 12.0,
            'layer_mm': 0.2,
            'nozzle_mm': 0.4,
            'clearance_mm': 0.15,
            'axis_vertical': True,
        })
        self.assertAlmostEqual(spec['pitch_mm'], 1.0)
        self.assertAlmostEqual(spec['tooth_height_mm'], profile.ISO_TOOTH_HEIGHT_FACTOR, places=6)
        self.assertAlmostEqual(spec['crest_width_mm'], 0.125)
        self.assertAlmostEqual(spec['root_width_mm'], 0.75)
        self.assertAlmostEqual(spec['flank_deg'], 60.0)
        self.assertAlmostEqual(spec['crest_radius_mm'], 3.0)
        self.assertAlmostEqual(spec['root_radius_mm'], 3.0 - spec['tooth_height_mm'] - 0.15)
        self.assertTrue(any('crest' in warning.lower() for warning in spec['warnings']))

    def test_small_metric_warns(self):
        spec = profile.resolve({
            'gender': 'female',
            'build': 'inset',
            'family': 'iso',
            'size': 'M3',
            'face_radius_mm': 1.25,
            'face_length_mm': 8.0,
            'nozzle_mm': 0.4,
            'layer_mm': 0.2,
            'clearance_mm': 0.15,
            'axis_vertical': True,
        })
        self.assertTrue(any('M5' in warning for warning in spec['warnings']))

    def test_unc_pitch_is_not_snapped(self):
        spec = profile.resolve({
            'gender': 'male',
            'build': 'inset',
            'family': 'unc',
            'size': '1/4-20',
            'face_radius_mm': 0.25 * 25.4 / 2,
            'face_length_mm': 20.0,
            'layer_mm': 0.2,
            'nozzle_mm': 0.4,
            'clearance_mm': 0.15,
            'axis_vertical': False,
        })
        self.assertAlmostEqual(spec['pitch_mm'], 25.4 / 20)
        self.assertTrue(any('vertical' in warning.lower() for warning in spec['warnings']))

    def test_fine_pitch_is_rejected_for_printable_crests(self):
        with self.assertRaises(profile.ProfileError):
            self._printable(pitch_mm=0.6, nozzle_mm=0.4)

    def test_nudge_directions(self):
        self.assertAlmostEqual(profile.nudge_clearance(0.2, 'tight'), 0.25)
        self.assertAlmostEqual(profile.nudge_clearance(0.02, 'loose'), 0.0)
        self.assertAlmostEqual(profile.nudge_hole(4.0, 'tight'), 4.1)
        self.assertAlmostEqual(profile.nudge_hole(4.0, 'loose'), 3.9)

    def test_samples_grow_with_radius(self):
        small = profile.samples_per_turn(3.0, 0.5)
        large = profile.samples_per_turn(40.0, 0.5)
        self.assertGreaterEqual(large, small)
        self.assertGreaterEqual(small, 16)
        self.assertLessEqual(large, 120)

    def test_iso_height_matches_basic_profile(self):
        expected = (5.0 / 8.0) * (math.sqrt(3.0) / 2.0)
        self.assertAlmostEqual(profile.ISO_TOOTH_HEIGHT_FACTOR, expected)


if __name__ == '__main__':
    unittest.main()
