import csv
import re

_BARE_FRACTION = re.compile(r'(-?)(\d+/\d+)')

HEADER = ('Body Name', 'Length', 'Width', 'Thickness', 'Units', 'Note')

NOTE_SEE_PDF = 'Complex Shape - see PDF drawing'
NOTE_SEE_DESIGN = 'Complex Shape - see design file'


def rows(infos, fmt, note_for=None):
    """Yield one row per body. Complex bodies carry their overall outline size.

    `fmt` is a drawing.LengthFormat. `note_for(info)` returns the note for a
    non-rectangular body; by default it points to the design file.
    """
    ordered = sorted(infos, key=lambda info: (info.name.lower(), info.name))
    for info in ordered:
        length, width, thickness = (spreadsheet_safe(fmt.format(value)) for value in info.size)
        if info.is_rectangle:
            note = ''
        else:
            note = note_for(info) if note_for else NOTE_SEE_DESIGN
        yield (info.name, length, width, thickness, fmt.unit, note)


def spreadsheet_safe(text):
    """Keep Excel from reading a bare fraction such as `3/4` as a date.

    `0 3/4` is read as the number 0.75 and shown as a fraction, like `1 1/4` is.
    """
    match = _BARE_FRACTION.fullmatch(text)
    if not match:
        return text
    return f'{match.group(1)}0 {match.group(2)}'


def write(path, infos, fmt, note_for=None):
    """Write all bodies to `path`. Returns (rows written, complex rows)."""
    count = 0
    complex_count = 0
    with open(path, 'w', newline='', encoding='utf-8-sig') as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        for row in rows(infos, fmt, note_for):
            writer.writerow(row)
            count += 1
            if row[-1]:
                complex_count += 1
    return count, complex_count
