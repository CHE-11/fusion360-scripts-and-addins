"""Minimal PDF 1.4 writer: vector lines, filled polygons, and Helvetica text.

Coordinates are PDF points (1/72 inch) with the origin at the bottom-left.
"""
import math
import zlib

FONT_REGULAR = 'F1'
FONT_BOLD = 'F2'

# Helvetica advance widths per 1000 em for common characters.
_WIDTHS = {
    ' ': 278, '.': 278, ',': 278, ':': 278, ';': 278, '-': 333, '_': 556, '/': 278,
    '(': 333, ')': 333, '[': 278, ']': 278, '#': 556, '%': 889, '&': 667, "'": 191,
    'x': 500, 'X': 667, 'I': 278, 'i': 222, 'j': 222, 'l': 222, 'f': 278, 't': 278,
    'r': 333, 'm': 833, 'w': 722, 'M': 833, 'W': 944, '\u00d8': 778,
}
_DIGIT_WIDTH = 556
_UPPER_WIDTH = 667
_LOWER_WIDTH = 520
_OTHER_WIDTH = 600
_BOLD_FACTOR = 1.06


def text_width(text, size, bold=False):
    total = 0
    for char in text:
        if char in _WIDTHS:
            total += _WIDTHS[char]
        elif char.isdigit():
            total += _DIGIT_WIDTH
        elif char.isupper():
            total += _UPPER_WIDTH
        elif char.islower():
            total += _LOWER_WIDTH
        else:
            total += _OTHER_WIDTH
    width = total * size / 1000.0
    return width * _BOLD_FACTOR if bold else width


def escape_text(text):
    data = text.encode('cp1252', errors='replace')
    out = bytearray()
    for byte in data:
        if byte in (0x28, 0x29, 0x5C):
            out += b'\\' + bytes([byte])
        elif byte < 0x20 or byte > 0x7E:
            out += f'\\{byte:03o}'.encode('ascii')
        else:
            out.append(byte)
    return out.decode('ascii')


def _num(value):
    text = f'{value:.3f}'.rstrip('0').rstrip('.')
    return '0' if text in ('-0', '') else text


class Page:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self._ops = []

    def line(self, x1, y1, x2, y2, width=0.5, dash=None):
        self._stroke_style(width, dash)
        self._ops.append(f'{_num(x1)} {_num(y1)} m {_num(x2)} {_num(y2)} l S')

    def polyline(self, points, width=0.5, dash=None, closed=False):
        if len(points) < 2:
            return
        self._stroke_style(width, dash)
        parts = [f'{_num(points[0][0])} {_num(points[0][1])} m']
        parts.extend(f'{_num(x)} {_num(y)} l' for x, y in points[1:])
        parts.append('s' if closed else 'S')
        self._ops.append(' '.join(parts))

    def polygon(self, points):
        if len(points) < 3:
            return
        parts = [f'{_num(points[0][0])} {_num(points[0][1])} m']
        parts.extend(f'{_num(x)} {_num(y)} l' for x, y in points[1:])
        parts.append('h f')
        self._ops.append(' '.join(parts))

    def rect(self, x, y, width, height, line_width=0.5):
        self._stroke_style(line_width, None)
        self._ops.append(f'{_num(x)} {_num(y)} {_num(width)} {_num(height)} re S')

    def text(self, x, y, text, size=9, bold=False, align='left', angle=0.0):
        if not text:
            return
        offset = 0.0
        if align == 'center':
            offset = text_width(text, size, bold) / 2.0
        elif align == 'right':
            offset = text_width(text, size, bold)
        radians = math.radians(angle)
        cos_a, sin_a = math.cos(radians), math.sin(radians)
        start_x = x - offset * cos_a
        start_y = y - offset * sin_a
        font = FONT_BOLD if bold else FONT_REGULAR
        self._ops.append(
            f'BT /{font} {_num(size)} Tf {_num(cos_a)} {_num(sin_a)} {_num(-sin_a)} {_num(cos_a)} '
            f'{_num(start_x)} {_num(start_y)} Tm ({escape_text(text)}) Tj ET'
        )

    def content(self):
        return ('\n'.join(self._ops) + '\n').encode('ascii')

    def _stroke_style(self, width, dash):
        pattern = ' '.join(_num(value) for value in dash) if dash else ''
        self._ops.append(f'{_num(width)} w [{pattern}] 0 d')


class PdfDocument:
    def __init__(self, title=''):
        self.title = title
        self.pages = []

    def add_page(self, width, height):
        page = Page(width, height)
        self.pages.append(page)
        return page

    def to_bytes(self):
        objects = []

        def reserve():
            objects.append(None)
            return len(objects)

        catalog_id = reserve()
        pages_id = reserve()
        regular_id = reserve()
        bold_id = reserve()
        info_id = reserve()

        objects[regular_id - 1] = (
            b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>'
        )
        objects[bold_id - 1] = (
            b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>'
        )
        objects[info_id - 1] = (
            f'<< /Title ({escape_text(self.title)}) /Producer (Export Cut Sheet) >>'.encode('ascii')
        )

        page_ids = []
        for page in self.pages:
            stream = zlib.compress(page.content())
            content_id = reserve()
            objects[content_id - 1] = (
                f'<< /Length {len(stream)} /Filter /FlateDecode >>\nstream\n'.encode('ascii')
                + stream
                + b'\nendstream'
            )
            page_id = reserve()
            objects[page_id - 1] = (
                f'<< /Type /Page /Parent {pages_id} 0 R '
                f'/MediaBox [0 0 {_num(page.width)} {_num(page.height)}] '
                f'/Resources << /Font << /{FONT_REGULAR} {regular_id} 0 R /{FONT_BOLD} {bold_id} 0 R >> >> '
                f'/Contents {content_id} 0 R >>'
            ).encode('ascii')
            page_ids.append(page_id)

        kids = ' '.join(f'{page_id} 0 R' for page_id in page_ids)
        objects[pages_id - 1] = f'<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>'.encode('ascii')
        objects[catalog_id - 1] = f'<< /Type /Catalog /Pages {pages_id} 0 R >>'.encode('ascii')

        output = bytearray(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')
        offsets = []
        for number, body in enumerate(objects, start=1):
            offsets.append(len(output))
            output += f'{number} 0 obj\n'.encode('ascii') + body + b'\nendobj\n'

        xref_offset = len(output)
        output += f'xref\n0 {len(objects) + 1}\n'.encode('ascii')
        output += b'0000000000 65535 f \n'
        for offset in offsets:
            output += f'{offset:010d} 00000 n \n'.encode('ascii')
        output += (
            f'trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R /Info {info_id} 0 R >>\n'
            f'startxref\n{xref_offset}\n%%EOF\n'
        ).encode('ascii')
        return bytes(output)

    def save(self, path):
        with open(path, 'wb') as handle:
            handle.write(self.to_bytes())
