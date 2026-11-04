"""Size tables for printable hardware.

ISO rows are the coarse series. Imperial rows are UNC coarse plus the common
UNF sizes. Heat-set holes are typical starting diameters for short knurled
brass inserts. They are not a single manufacturer's drawing, and the pocket
is meant to be nudged after a test print.
"""

from __future__ import annotations

# designation, major diameter mm, pitch mm
ISO_METRIC_COARSE = (
    ('M1', 1.0, 0.25),
    ('M1.2', 1.2, 0.25),
    ('M1.4', 1.4, 0.3),
    ('M1.6', 1.6, 0.35),
    ('M2', 2.0, 0.4),
    ('M2.5', 2.5, 0.45),
    ('M3', 3.0, 0.5),
    ('M4', 4.0, 0.7),
    ('M5', 5.0, 0.8),
    ('M6', 6.0, 1.0),
    ('M8', 8.0, 1.25),
    ('M10', 10.0, 1.5),
    ('M12', 12.0, 1.75),
    ('M14', 14.0, 2.0),
    ('M16', 16.0, 2.0),
    ('M18', 18.0, 2.5),
    ('M20', 20.0, 2.5),
    ('M24', 24.0, 3.0),
)

# designation, major diameter inch, threads per inch.
# UNC coarse, plus the UNF sizes commonly paired with them.
IMPERIAL_THREADS = (
    ('#0-80', 0.060, 80),
    ('#1-64', 0.073, 64),
    ('#2-56', 0.086, 56),
    ('#3-48', 0.099, 48),
    ('#4-40', 0.112, 40),
    ('#4-48', 0.112, 48),
    ('#5-40', 0.125, 40),
    ('#6-32', 0.138, 32),
    ('#6-40', 0.138, 40),
    ('#8-32', 0.164, 32),
    ('#8-36', 0.164, 36),
    ('#10-24', 0.190, 24),
    ('#10-32', 0.190, 32),
    ('#12-24', 0.216, 24),
    ('1/4-20', 0.250, 20),
    ('1/4-28', 0.250, 28),
    ('5/16-18', 0.3125, 18),
    ('3/8-16', 0.375, 16),
    ('3/8-24', 0.375, 24),
    ('1/2-13', 0.500, 13),
    ('1/2-20', 0.500, 20),
    ('5/8-11', 0.625, 11),
    ('3/4-10', 0.750, 10),
)
UNC_COARSE = IMPERIAL_THREADS

# size, pilot hole mm, pocket depth mm, entrance chamfer mm
HEAT_SET_INSERTS = (
    ('M2', 3.2, 4.0, 0.5),
    ('M2.5', 3.6, 4.6, 0.5),
    ('M3', 4.0, 5.6, 0.5),
    ('M4', 5.6, 6.6, 0.6),
    ('M5', 6.4, 8.0, 0.8),
    ('M6', 8.0, 9.0, 0.8),
)

INCH_TO_MM = 25.4

# Modeled threads smaller than M5 / #10 are a poor match for a 0.4 mm nozzle.
SMALL_THREAD_MAJOR_MM = 4.8


def iso_by_size(size: str):
    for row in ISO_METRIC_COARSE:
        if row[0] == size:
            return {'size': row[0], 'major_mm': row[1], 'pitch_mm': row[2]}
    return None


def unc_by_size(size: str):
    for name, major_in, tpi in IMPERIAL_THREADS:
        if name == size:
            return {
                'size': name,
                'major_mm': major_in * INCH_TO_MM,
                'pitch_mm': INCH_TO_MM / tpi,
            }
    return None


def insert_by_size(size: str):
    for name, hole, depth, chamfer in HEAT_SET_INSERTS:
        if name == size:
            return {
                'size': name,
                'hole_mm': hole,
                'depth_mm': depth,
                'chamfer_mm': chamfer,
            }
    return None


def catalog():
    """JSON-ready tables for the palette."""
    return {
        'iso': [
            {'size': name, 'majorMm': major, 'pitchMm': pitch}
            for name, major, pitch in ISO_METRIC_COARSE
        ],
        'unc': [
            {
                'size': name,
                'majorMm': major_in * INCH_TO_MM,
                'pitchMm': INCH_TO_MM / tpi,
            }
            for name, major_in, tpi in IMPERIAL_THREADS
        ],
        'inserts': [
            {
                'size': name,
                'holeMm': hole,
                'depthMm': depth,
                'chamferMm': chamfer,
            }
            for name, hole, depth, chamfer in HEAT_SET_INSERTS
        ],
        'plasticClearanceMm': 0.20,
        'metalClearanceMm': 0.15,
        'threadNudgeMm': 0.05,
        'insertNudgeMm': 0.10,
        'defaultNozzleMm': 0.4,
        'defaultLayerMm': 0.2,
        'defaultFlankDeg': 45.0,
    }
