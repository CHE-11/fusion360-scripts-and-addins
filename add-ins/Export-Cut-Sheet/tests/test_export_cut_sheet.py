"""Unit tests for cut sheet math, CSV rows, layout, and PDF output. No Fusion session required."""

import csv
import importlib.util
import os
import re
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'addin' / 'commands' / 'exportCutSheet'
PACKAGE = 'export_cut_sheet_under_test'
pkg = types.ModuleType(PACKAGE)
pkg.__path__ = [str(ROOT)]
pkg.__package__ = PACKAGE
sys.modules[PACKAGE] = pkg

# bodies.py imports the Fusion API at module level; its pure helpers don't use it.
adsk = types.ModuleType('adsk')
adsk.core = types.ModuleType('adsk.core')
adsk.fusion = types.ModuleType('adsk.fusion')
sys.modules.setdefault('adsk', adsk)
sys.modules.setdefault('adsk.core', adsk.core)
sys.modules.setdefault('adsk.fusion', adsk.fusion)


def load(name):
    full = f'{PACKAGE}.{name}'
    spec = importlib.util.spec_from_file_location(full, ROOT / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    module.__package__ = PACKAGE
    sys.modules[full] = module
    spec.loader.exec_module(module)
    return module


pdf_writer = load('pdf_writer')
shading = load('shading')
drawing = load('drawing')
bodies = load('bodies')
csv_export = load('csv_export')

INCHES = drawing.LengthFormat('in', 3)
CM_1 = drawing.LengthFormat('cm', 1)
MM_1 = drawing.LengthFormat('mm', 1)


class Info:
    def __init__(self, name, size, is_rectangle=True):
        self.name = name
        self.size = size
        self.is_rectangle = is_rectangle


class BoxClassificationTests(unittest.TestCase):
    def test_axis_aligned_box(self):
        normals = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]
        self.assertTrue(bodies.normals_form_box(normals))

    def test_rotated_box(self):
        s = 2 ** -0.5
        normals = [(s, s, 0), (-s, -s, 0), (-s, s, 0), (s, -s, 0), (0, 0, 1), (0, 0, -1)]
        self.assertTrue(bodies.normals_form_box(normals))

    def test_parallelepiped_is_not_a_box(self):
        normals = [(1, 0, 0), (-1, 0, 0), (0.5, 0.866, 0), (-0.5, -0.866, 0), (0, 0, 1), (0, 0, -1)]
        self.assertFalse(bodies.normals_form_box(normals))

    def test_wrong_face_count(self):
        self.assertFalse(bodies.normals_form_box([(1, 0, 0), (-1, 0, 0), (0, 1, 0)]))

    def test_volume_match(self):
        self.assertTrue(bodies.volume_matches_box(24.0, (4.0, 3.0, 2.0)))
        self.assertFalse(bodies.volume_matches_box(23.0, (4.0, 3.0, 2.0)))
        self.assertFalse(bodies.volume_matches_box(1.0, (0.0, 3.0, 2.0)))


class FrameTests(unittest.TestCase):
    def test_sort_frame_orders_and_is_right_handed(self):
        center, axes, extents = bodies.sort_frame(
            (0, 0, 0), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (2.0, 10.0, 5.0)
        )
        self.assertEqual(extents, (10.0, 5.0, 2.0))
        self.assertEqual(axes[0], (0.0, 1.0, 0.0))
        self.assertEqual(axes[1], (0.0, 0.0, 1.0))
        cross = bodies.cross(axes[0], axes[1])
        self.assertAlmostEqual(bodies.dot(cross, axes[2]), 1.0)

    def test_align_frame_matches_front_view(self):
        # Upright panel facing the front, as Fusion's bounding box might report it.
        box_axes = ((0.0, 0.0, -1.0), (-1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
        box_extents = (118.7, 45.1, 1.9)
        front = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
        axes, extents = bodies.align_frame(box_axes, box_extents, front)
        self.assertEqual(axes, front)
        self.assertEqual(extents, (45.1, 1.9, 118.7))

    def test_align_frame_squares_up_rotated_part_and_stays_right_handed(self):
        # Flat board turned 120 degrees about Z, thickness up, box axes reported upside down.
        c, s = -0.5, 3 ** 0.5 / 2
        box_axes = ((c, s, 0.0), (-s, c, 0.0), (0.0, 0.0, -1.0))
        front = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
        axes, extents = bodies.align_frame(box_axes, (30.0, 20.0, 2.0), front)
        self.assertAlmostEqual(bodies.dot(bodies.cross(axes[0], axes[1]), axes[2]), 1.0)
        self.assertGreater(bodies.dot(axes[0], front[0]), 0)
        self.assertEqual(axes[2], (0.0, 0.0, 1.0))
        self.assertEqual(extents, (20.0, 30.0, 2.0))

    def test_view_frame_rotates_into_component_space(self):
        # Component turned 90 degrees about Z: root +X is the component's -Y.
        matrix = (0, -1, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)
        frame = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
        local = bodies._to_body_space(frame, matrix)
        self.assertEqual(tuple(round(c, 9) + 0.0 for c in local[0]), (0.0, -1.0, 0.0))
        self.assertEqual(tuple(round(c, 9) + 0.0 for c in local[2]), (0.0, 0.0, 1.0))

    def test_to_local(self):
        axes = ((0, 1, 0), (-1, 0, 0), (0, 0, 1))
        self.assertEqual(bodies.to_local((1, 3, 2), (1, 1, 1), axes), (2, 0, 1))


class FormatTests(unittest.TestCase):
    def test_decimal(self):
        self.assertEqual(INCHES.format(2.54), '1.000')
        self.assertEqual(MM_1.format(-0.001), '0.0')

    def test_fraction_inches(self):
        fmt = drawing.LengthFormat('in', 3, 16)
        self.assertTrue(fmt.uses_fractions)
        self.assertEqual(fmt.format(12.375 * 2.54), '12 3/8')
        self.assertEqual(fmt.format(0.5 * 2.54), '1/2')
        self.assertEqual(fmt.format(3.0 * 2.54), '3')
        self.assertEqual(fmt.format(1.99 * 2.54), '2')

    def test_fraction_precision_rounds(self):
        self.assertEqual(drawing.format_fraction(0.3, 4), '1/4')
        self.assertEqual(drawing.format_fraction(0.3, 64), '19/64')

    def test_feet_inches(self):
        fmt = drawing.LengthFormat('ft', 3, 16)
        self.assertEqual(fmt.format(40.5 * 2.54), '3\' 4 1/2"')
        self.assertEqual(fmt.format(6.25 * 2.54), '6 1/4"')
        self.assertEqual(fmt.format(24.0 * 2.54), '2\' 0"')

    def test_fractions_ignored_for_metric(self):
        fmt = drawing.LengthFormat('mm', 2, 16)
        self.assertFalse(fmt.uses_fractions)
        self.assertEqual(fmt.format(1.0), '10.00')

    def test_angle(self):
        self.assertEqual(drawing.format_angle(30.0), '30\u00b0')
        self.assertEqual(drawing.format_angle(15.64), '15.6\u00b0')


class CsvTests(unittest.TestCase):
    def test_rows_convert_sort_and_round(self):
        infos = [Info('Shelf', (60.96, 30.48, 1.905)), Info('back', (91.44, 60.96, 0.635))]
        rows = list(csv_export.rows(infos, INCHES))
        self.assertEqual(rows[0], ('back', '36.000', '24.000', '0.250', 'in', ''))
        self.assertEqual(rows[1], ('Shelf', '24.000', '12.000', '0.750', 'in', ''))

    def test_rows_with_fractions(self):
        rows = list(csv_export.rows([Info('Shelf', (60.96, 30.48, 1.905))], drawing.LengthFormat('in', 3, 8)))
        self.assertEqual(rows[0], ('Shelf', '24', '12', '0 3/4', 'in', ''))

    def test_spreadsheet_safe_only_touches_bare_fractions(self):
        self.assertEqual(csv_export.spreadsheet_safe('3/4'), '0 3/4')
        self.assertEqual(csv_export.spreadsheet_safe('-1/2'), '-0 1/2')
        self.assertEqual(csv_export.spreadsheet_safe('1 1/4'), '1 1/4')
        self.assertEqual(csv_export.spreadsheet_safe('43'), '43')
        self.assertEqual(csv_export.spreadsheet_safe('0.750'), '0.750')
        self.assertEqual(csv_export.spreadsheet_safe('6 1/4"'), '6 1/4"')

    def test_complex_bodies_get_outline_and_note(self):
        infos = [
            Info('Bracket', (30.0, 10.0, 8.0), is_rectangle=False),
            Info('Gusset', (5.0, 5.0, 1.0), is_rectangle=False),
            Info('Panel', (50.0, 20.0, 2.0)),
        ]
        drawn = {'Bracket'}

        def note_for(info):
            return csv_export.NOTE_SEE_PDF if info.name in drawn else csv_export.NOTE_SEE_DESIGN

        rows = list(csv_export.rows(infos, CM_1, note_for))
        self.assertEqual(rows[0], ('Bracket', '30.0', '10.0', '8.0', 'cm', 'Complex Shape - see PDF drawing'))
        self.assertEqual(rows[1], ('Gusset', '5.0', '5.0', '1.0', 'cm', 'Complex Shape - see design file'))
        self.assertEqual(rows[2][-1], '')

    def test_complex_note_defaults_to_design_file(self):
        rows = list(csv_export.rows([Info('Knob', (2.0, 2.0, 1.0), is_rectangle=False)], CM_1))
        self.assertEqual(rows[0][-1], csv_export.NOTE_SEE_DESIGN)

    def test_write_has_header_and_bom(self):
        infos = [Info('Side, left', (10.0, 5.0, 1.0)), Info('Leg', (70.0, 4.0, 4.0), is_rectangle=False)]
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'cut.csv')
            self.assertEqual(csv_export.write(path, infos, MM_1), (2, 1))
            with open(path, 'rb') as handle:
                self.assertTrue(handle.read().startswith(b'\xef\xbb\xbf'))
            with open(path, newline='', encoding='utf-8-sig') as handle:
                rows = list(csv.reader(handle))
        self.assertEqual(rows[0], ['Body Name', 'Length', 'Width', 'Thickness', 'Units', 'Note'])
        self.assertEqual(rows[1], ['Leg', '700.0', '40.0', '40.0', 'mm', 'Complex Shape - see design file'])
        self.assertEqual(rows[2], ['Side, left', '100.0', '50.0', '10.0', 'mm', ''])


class ScaleTests(unittest.TestCase):
    def test_reduction_snaps_to_next_standard(self):
        scale, label = drawing.standard_scale(drawing.PT_PER_CM / 3.7)
        self.assertEqual(label, '1:4')
        self.assertAlmostEqual(scale, drawing.PT_PER_CM / 4)

    def test_full_size(self):
        self.assertEqual(drawing.standard_scale(drawing.PT_PER_CM)[1], '1:1')

    def test_enlargement(self):
        self.assertEqual(drawing.standard_scale(drawing.PT_PER_CM * 4.4)[1], '4:1')

    def test_beyond_table(self):
        self.assertEqual(drawing.standard_scale(drawing.PT_PER_CM / 1234.2)[1], '1:1235')


class LayoutTests(unittest.TestCase):
    def test_views_fit_inside_area_and_align(self):
        area = (50.0, 80.0, 700.0, 450.0)
        layout = drawing.layout_views((120.0, 60.0, 2.0), area)
        boxes = layout.boxes
        front, top, right = boxes['front'], boxes['top'], boxes['right']
        self.assertAlmostEqual(front.x, top.x)
        self.assertAlmostEqual(front.y, right.y)
        self.assertGreater(top.y, front.y + front.height)
        self.assertGreater(right.x, front.x + front.width)
        self.assertGreaterEqual(front.x - drawing.LEFT_MARGIN, area[0] - 1e-6)
        self.assertGreaterEqual(front.y - drawing.BOTTOM_MARGIN, area[1] - 1e-6)
        self.assertLessEqual(right.x + right.width + drawing.RIGHT_MARGIN, area[0] + area[2] + 1e-6)
        self.assertLessEqual(top.y + top.height + drawing.TOP_MARGIN, area[1] + area[3] + 1e-6)
        self.assertAlmostEqual(top.width, layout.scale * 120.0)

    def test_zero_size_raises(self):
        with self.assertRaises(ValueError):
            drawing.layout_views((0.0, 0.0, 0.0), (0, 0, 500, 500))

    def test_overview_grid_fits_and_aligns(self):
        area = (50.0, 80.0, 700.0, 450.0)
        extents = {'top': (100.0, 40.0), 'front': (100.0, 60.0), 'right': (40.0, 60.0), 'home': (110.0, 90.0)}
        layout = drawing.layout_overview(extents, area)
        boxes = layout.boxes
        top, front, right, home = boxes['top'], boxes['front'], boxes['right'], boxes['home']
        self.assertAlmostEqual(top.x, front.x)
        self.assertAlmostEqual(front.y, right.y)
        self.assertGreater(top.y, front.y + front.height)
        self.assertGreater(home.y, right.y + right.height)
        self.assertGreater(right.x, front.x + front.width)
        self.assertGreater(home.x, top.x + top.width)
        self.assertAlmostEqual(front.width, layout.scale * 100.0)
        self.assertGreaterEqual(front.x - drawing.LEFT_MARGIN, area[0] - 1e-6)
        self.assertLessEqual(home.x + home.width + drawing.RIGHT_MARGIN, area[0] + area[2] + 1e-6)
        self.assertLessEqual(home.y + home.height + drawing.TOP_MARGIN, area[1] + area[3] + 1e-6)

    def test_overview_empty_raises(self):
        with self.assertRaises(ValueError):
            drawing.layout_overview({}, (0, 0, 500, 500))


class OverviewProjectionTests(unittest.TestCase):
    def test_z_up_views(self):
        views = drawing.default_view_directions(z_up=True)
        point = (1.0, 2.0, 3.0)
        self.assertEqual(self.project(point, *views['top']), (1.0, 2.0))
        self.assertEqual(self.project(point, *views['front']), (1.0, 3.0))
        self.assertEqual(self.project(point, *views['right']), (2.0, 3.0))

    def test_y_up_views(self):
        views = drawing.default_view_directions(z_up=False)
        point = (1.0, 2.0, 3.0)
        self.assertEqual(self.project(point, *views['top']), (1.0, -3.0))
        self.assertEqual(self.project(point, *views['front']), (1.0, 2.0))
        self.assertEqual(self.project(point, *views['right']), (-3.0, 2.0))

    def test_home_view_shows_front_right_and_top(self):
        basis = drawing.view_basis(*drawing.default_view_directions(z_up=True)['home'])
        right, up = basis
        self.assertGreater(right[0], 0)
        self.assertGreater(right[1], 0)
        self.assertAlmostEqual(right[2], 0.0)
        self.assertGreater(up[2], 0)

    def test_parallel_up_raises(self):
        with self.assertRaises(ValueError):
            drawing.view_basis((0.0, 0.0, -1.0), (0.0, 0.0, 1.0))

    def test_transform_point(self):
        matrix = (0, -1, 0, 10, 1, 0, 0, 20, 0, 0, 1, 30, 0, 0, 0, 1)
        self.assertEqual(bodies.transform_point(matrix, (1.0, 2.0, 3.0)), (8.0, 21.0, 33.0))

    @staticmethod
    def project(point, direction, up):
        u, v = drawing.project_onto(point, drawing.view_basis(direction, up))
        return (round(u, 9) + 0.0, round(v, 9) + 0.0)


class CircleTests(unittest.TestCase):
    def test_duplicates_merge_and_groups_count(self):
        circles = [
            (1.0, 1.0, 0.25), (1.0, 1.0, 0.25),
            (5.0, 1.0, 0.25), (9.0, 1.0, 0.25),
            (5.0, 3.0, 1.0),
        ]
        groups = drawing.group_circles(circles, drawing.LengthFormat('cm', 2))
        self.assertEqual([label for label, _ in groups], ['2.00', '0.50'])
        self.assertEqual(len(groups[1][1]), 3)
        self.assertEqual(drawing.diameter_label('0.50', 3), '3X \u00d8 0.50')
        self.assertEqual(drawing.diameter_label('2.00', 1), '\u00d8 2.00')

    def test_split_hole_becomes_circle(self):
        view = drawing.ViewData(arcs=[
            (5.0, 5.0, 0.0, 0.4, 180.0, 5.4, 5.0),
            (5.0, 5.0, 0.0, 0.4, 180.0, 4.6, 5.0),
            (5.0, 5.0, 1.0, 0.4, 180.0, 5.4, 5.0),
            (5.0, 5.0, 1.0, 0.4, 180.0, 4.6, 5.0),
        ])
        circles, arcs = drawing.resolve_arcs(view)
        self.assertEqual(circles, [(5.0, 5.0, 0.4)])
        self.assertEqual(arcs, [])

    def test_rounded_end_stays_an_arc(self):
        # Top and bottom edges of a 180 degree rounded end must not add up to a circle.
        view = drawing.ViewData(arcs=[
            (10.0, 2.0, 0.0, 2.0, 180.0, 12.0, 2.0),
            (10.0, 2.0, 1.0, 2.0, 180.0, 12.0, 2.0),
            (0.5, 0.5, 0.0, 0.5, 90.0, 0.15, 0.15),
        ])
        circles, arcs = drawing.resolve_arcs(view)
        self.assertEqual(circles, [])
        self.assertEqual(len(arcs), 2)
        groups = drawing.group_arcs(arcs, CM_1)
        self.assertEqual([label for label, _ in groups], ['2.0', '0.5'])
        self.assertEqual(drawing.radius_label('0.5', 4), '4X R 0.5')


class FeatureStationTests(unittest.TestCase):
    def test_notch_positions(self):
        stations = drawing.feature_stations([0.0, 3.5, 3.5, 7.0, 7.1, 100.0], 100.0, 0.5)
        self.assertEqual(stations, [0.0, 3.5, 7.0, 100.0])

    def test_plain_rectangle_has_no_chain(self):
        self.assertEqual(drawing.feature_stations([0.0, 50.0, 0.0, 50.0], 50.0, 0.5), [])

    def test_station_near_end_merges(self):
        self.assertEqual(drawing.feature_stations([10.0, 49.8], 50.0, 0.5), [0.0, 10.0, 50.0])


class AngleTests(unittest.TestCase):
    def test_taper_lines_found_once(self):
        lines = [
            ((0.0, 1.5), (5.5, 0.0)),
            ((5.5, 0.0), (0.0, 1.5)),
            ((0.0, 1.5), (43.0, 1.5)),
            ((37.5, 0.0), (43.0, 1.5)),
            ((10.0, 0.0), (10.0, 1.5)),
        ]
        found = drawing.angled_lines(lines, 0.1)
        self.assertEqual(len(found), 2)
        for _start, _end, degrees, reference in found:
            self.assertEqual(reference, 'h')
            self.assertAlmostEqual(degrees, 15.255, places=2)

    def test_steep_line_measured_from_vertical(self):
        found = drawing.angled_lines([((0.0, 0.0), (1.0, 10.0))], 0.1)
        self.assertEqual(found[0][3], 'v')
        self.assertAlmostEqual(found[0][2], 5.711, places=2)


class TextTests(unittest.TestCase):
    def test_fit_text_truncates(self):
        size, text = drawing.fit_text('A very long body name indeed', 40.0, 11.0, 6.0)
        self.assertEqual(size, 6.0)
        self.assertTrue(text.endswith('...'))
        self.assertLessEqual(pdf_writer.text_width(text, size), 40.0)

    def test_fit_text_keeps_short(self):
        self.assertEqual(drawing.fit_text('Leg', 100.0, 11.0, 6.0), (11.0, 'Leg'))

    def test_escape(self):
        self.assertEqual(pdf_writer.escape_text('a(b)\\'), 'a\\(b\\)\\\\')
        self.assertEqual(pdf_writer.escape_text('\u00d8'), '\\330')
        self.assertEqual(pdf_writer.escape_text('\u00b0'), '\\260')


def box_mesh(low, high):
    """Triangles and edge polylines of an axis-aligned box in model space."""
    (x0, y0, z0), (x1, y1, z1) = low, high
    corners = [(x, y, z) for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)]
    quads = ((0, 1, 3, 2), (4, 5, 7, 6), (0, 1, 5, 4), (2, 3, 7, 6), (0, 2, 6, 4), (1, 3, 7, 5))
    triangles = []
    for a, b, c, d in quads:
        triangles.append((corners[a], corners[b], corners[c]))
        triangles.append((corners[a], corners[c], corners[d]))
    pairs = ((0, 1), (1, 3), (3, 2), (2, 0), (4, 5), (5, 7), (7, 6), (6, 4), (0, 4), (1, 5), (2, 6), (3, 7))
    edges = [[corners[a], corners[b]] for a, b in pairs]
    return triangles, edges


def box_scene(low, high):
    triangles, edges = box_mesh(low, high)
    views = {}
    for name, direction in drawing.default_view_directions(z_up=True).items():
        frame = shading.view_frame(*drawing.view_basis(*direction))
        views[name] = shading.SceneView(
            triangles=[tuple(shading.project(p, frame) for p in t) for t in triangles],
            edges=[[shading.project(p, frame) for p in e] for e in edges],
        )
    return views


class ShadingTests(unittest.TestCase):
    def test_hidden_edges_are_removed(self):
        view = box_scene((0, 0, 0), (40, 20, 10))['home']
        bounds = shading.scene_bounds(view)
        _raster, runs = shading.render(view, bounds, 5.0, dpi=100)
        # A box seen from a corner shows 9 of its 12 edges.
        self.assertEqual(len(runs), 9)

    def test_faces_are_filled_and_background_stays_white(self):
        view = box_scene((0, 0, 0), (40, 20, 10))['front']
        raster, runs = shading.render(view, shading.scene_bounds(view), 5.0, dpi=72)
        self.assertEqual(raster.width * raster.height, len(raster.pixels))
        middle = raster.pixels[(raster.height // 2) * raster.width + raster.width // 2]
        self.assertNotEqual(middle, shading.BACKGROUND)
        self.assertEqual(len(runs), 4)

    def test_edge_behind_another_body_is_hidden(self):
        near = box_mesh((0, 0, 0), (40, 2, 40))
        far_edge = [[(10.0, 20.0, 20.0), (30.0, 20.0, 20.0)]]
        frame = shading.view_frame(*drawing.view_basis(*drawing.default_view_directions()['front']))
        view = shading.SceneView(
            triangles=[tuple(shading.project(p, frame) for p in t) for t in near[0]],
            edges=[[shading.project(p, frame) for p in e] for e in far_edge],
        )
        _raster, runs = shading.render(view, shading.scene_bounds(view), 5.0, dpi=72)
        self.assertEqual(runs, [])

    def test_pixel_budget_is_respected(self):
        view = box_scene((0, 0, 0), (400, 200, 100))['top']
        raster, _runs = shading.render(view, shading.scene_bounds(view), 10.0, dpi=300, max_pixels=50_000)
        self.assertLessEqual(raster.width * raster.height, 52_000)

    def test_palette_ends_white(self):
        self.assertEqual(len(shading.PALETTE), 256 * 3)
        self.assertEqual(shading.PALETTE[-3:], b'\xff\xff\xff')


def notched_taper_part():
    """A 40 x 20 x 1.2 plate with a notch, an angled edge, two holes, and a fillet."""
    views = drawing.empty_views()
    outline = [(0, 0), (40, 0), (40, 20), (8, 20), (8, 16), (4, 14), (0, 14), (0, 0)]
    for name in views:
        for z in (0.0, 1.2):
            points3 = [(x, y, z) for x, y in outline]
            views[name].polylines.append([drawing.project(p, name) for p in points3])
            for a, b in zip(points3, points3[1:]):
                segment = (drawing.project(a, name), drawing.project(b, name))
                if max(abs(segment[0][0] - segment[1][0]), abs(segment[0][1] - segment[1][1])) > 1e-6:
                    views[name].lines.append(segment)
    views['top'].circles.extend([(5, 5, 0.4), (35, 5, 0.4)])
    views['top'].arcs.append((38.0, 18.0, 0.0, 2.0, 90.0, 39.41, 19.41))
    return drawing.PartSheet(views, 'Bracket (rev A)', 'Frame', 'Shop Cart', (40.0, 20.0, 1.2), 2)


class PdfTests(unittest.TestCase):
    def test_document_structure(self):
        document = drawing.build_document([notched_taper_part(), notched_taper_part()], INCHES, 'Letter', '2026-11-22')
        data = document.to_bytes()
        self.assertTrue(data.startswith(b'%PDF-1.4'))
        self.assertTrue(data.rstrip().endswith(b'%%EOF'))
        self.assertIn(b'/Count 2', data)

        startxref = int(re.search(rb'startxref\n(\d+)', data).group(1))
        self.assertTrue(data[startxref:].startswith(b'xref'))
        entries = re.findall(rb'(\d{10}) 00000 n ', data[startxref:])
        for number, offset in enumerate(entries, start=1):
            self.assertTrue(data[int(offset):].startswith(f'{number} 0 obj'.encode()))

    def test_page_content_has_feature_dimensions(self):
        document = drawing.build_document([notched_taper_part()], INCHES, 'A4', '2026-11-22')
        content = document.pages[0].content().decode('ascii')
        self.assertIn('(2X \\330 0.315)', content)
        self.assertIn('(R 0.787)', content)
        self.assertIn('(26.6\\260)', content)
        self.assertIn('(Bracket \\(rev A\\))', content)
        self.assertIn('(15.748)', content)
        # Chain along the length: notch at 4 and 8 cm, hole center at 35 cm.
        self.assertIn('(1.575)', content)
        self.assertIn('(10.630)', content)

    def test_fractions_in_drawing(self):
        document = drawing.build_document([notched_taper_part()], drawing.LengthFormat('in', 3, 16), 'Letter', 'x')
        content = document.pages[0].content().decode('ascii')
        self.assertIn('(15 3/4)', content)
        self.assertIn('(in \\(1/16\\))', content)

    def test_overview_is_first_sheet_and_shaded(self):
        views = box_scene((0, 0, 0), (50, 30, 20))
        overview = drawing.OverviewSheet(views, 'Shop Cart', 7)
        document = drawing.build_document([notched_taper_part()], CM_1, 'Letter', '2026-11-23', overview)
        self.assertEqual(len(document.pages), 2)
        first = document.pages[0]
        content = first.content().decode('ascii')
        for label in ('(HOME)', '(TOP)', '(FRONT)', '(RIGHT)', '(MODEL OVERVIEW)', '(1 / 2)'):
            self.assertIn(label, content)
        self.assertIn('(50.0 x 30.0 x 20.0)', content)
        self.assertEqual(len(first.images), 4)
        self.assertIn('/Im4 Do', content)
        self.assertIn('(2 / 2)', document.pages[1].content().decode('ascii'))
        data = document.to_bytes()
        self.assertIn(b'/Count 2', data)
        self.assertIn(b'/Subtype /Image', data)
        self.assertIn(b'/XObject << /Im1', data)

    def test_save(self):
        document = drawing.build_document([notched_taper_part()], MM_1, 'Tabloid', '2026-11-22')
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'out.pdf')
            document.save(path)
            self.assertGreater(os.path.getsize(path), 500)


if __name__ == '__main__':
    unittest.main()
