"""worldmap.xml.bin: the paper map in the form Build 42 actually reads.

The in-game map (M) showed street names and nothing else - no roads, no
buildings, no water. worldmap.xml was being read, but Build 42 no longer
loads that format properly: its XML reader stores each outline's length in
coordinates rather than points, reads twice as far as it wrote, and every
outline fails with an IndexOutOfBoundsException (console.txt: "Error while
parsing xml element: geometry"). The game's own maps, and every working
Build 42 map mod, ship the binary file beside the XML, and when it is there
the game reads that instead. It also uses the new 256-tile cells, where the
XML is in the old 300-tile ones.

The layout, from the game's WorldMapBinary reader and checked against
Muldraugh's own file (every byte of it parses):

    "IGMB"  int version = 2  int cell size = 256
    int width, int height                  cells, counted from cell 0, 0
    int n, n x (short length, UTF-8 bytes) the string table
    width x height cells, row by row:
        int -1                             no data in this cell, or
        int x, int y, int features, then per feature:
            short type (a string index: "Polygon")
            byte rings, per ring: short points, points x (short x, short y)
            byte properties, per property: short key, short value (indices)

Points are in tiles from the cell's corner. Everything is little-endian.

The binary is converted from worldmap.xml, so a map built before this gets
its paper map back when it is installed again.
"""
from __future__ import annotations

import struct
import xml.etree.ElementTree as ET

from shapely.geometry import Polygon, box

XML_CELL = 300
BIN_CELL = 256


def _features(xml_path: str):
    """(rings in world tiles, [(key, value)]) for every feature in the XML."""
    root = ET.parse(xml_path).getroot()
    for cell in root.iter("cell"):
        ox = int(cell.get("x")) * XML_CELL
        oy = int(cell.get("y")) * XML_CELL
        for feature in cell.iter("feature"):
            geometry = feature.find("geometry")
            if geometry is None or geometry.get("type", "Polygon") != "Polygon":
                continue
            rings = []
            for coords in geometry.iter("coordinates"):
                ring = [(ox + int(float(p.get("x"))), oy + int(float(p.get("y"))))
                        for p in coords.iter("point")]
                if len(ring) >= 3:
                    rings.append(ring)
            if not rings:
                continue
            props = [(p.get("name"), p.get("value"))
                     for p in feature.iter("property") if p.get("name")]
            yield rings, props


def _pieces(rings, cell_x, cell_y):
    """The part of a polygon inside one 256-tile cell, as ring lists."""
    x0, y0 = cell_x * BIN_CELL, cell_y * BIN_CELL
    try:
        shape = Polygon(rings[0], rings[1:])
        if not shape.is_valid:
            shape = shape.buffer(0)
        clipped = shape.intersection(box(x0, y0, x0 + BIN_CELL, y0 + BIN_CELL))
    except Exception:  # noqa: BLE001 - a broken outline is left off, not fatal
        return []
    out = []
    for part in getattr(clipped, "geoms", [clipped]):
        if part.geom_type != "Polygon" or part.is_empty or part.area < 0.25:
            continue
        piece = []
        for ring in [part.exterior, *part.interiors]:
            pts = [(round(x) - x0, round(y) - y0) for x, y in list(ring.coords)[:-1]]
            tidy = [p for k, p in enumerate(pts) if k == 0 or p != pts[k - 1]]
            if len(tidy) >= 3:
                piece.append(tidy)
        if piece:
            out.append(piece)
    return out


def write_bin(xml_path: str, bin_path: str) -> int:
    """Convert worldmap.xml to worldmap.xml.bin. Returns features written."""
    cells: dict[tuple[int, int], list] = {}
    for rings, props in _features(xml_path):
        xs = [x for x, _ in rings[0]]
        ys = [y for _, y in rings[0]]
        cx0, cx1 = min(xs) // BIN_CELL, max(xs) // BIN_CELL
        cy0, cy1 = min(ys) // BIN_CELL, max(ys) // BIN_CELL
        if cx0 == cx1 and cy0 == cy1:
            if cx0 < 0 or cy0 < 0:
                continue
            local = [[(x - cx0 * BIN_CELL, y - cy0 * BIN_CELL) for x, y in r] for r in rings]
            cells.setdefault((cx0, cy0), []).append((local, props))
            continue
        for cy in range(max(0, cy0), cy1 + 1):
            for cx in range(max(0, cx0), cx1 + 1):
                for piece in _pieces(rings, cx, cy):
                    cells.setdefault((cx, cy), []).append((piece, props))

    strings: dict[str, int] = {}

    def index(text: str) -> int:
        if text not in strings:
            strings[text] = len(strings)
        return strings[text]

    index("Polygon")
    body = bytearray()
    width = max((x for x, _ in cells), default=-1) + 1
    height = max((y for _, y in cells), default=-1) + 1
    count = 0
    for y in range(height):
        for x in range(width):
            features = cells.get((x, y))
            if not features:
                body += struct.pack("<i", -1)
                continue
            features = features[:0x7FFFFFFF]
            body += struct.pack("<iii", x, y, len(features))
            for piece, props in features:
                body += struct.pack("<hB", index("Polygon"), min(len(piece), 255))
                for ring in piece[:255]:
                    ring = ring[:32767]
                    body += struct.pack("<h", len(ring))
                    for px, py in ring:
                        body += struct.pack("<hh", max(-32768, min(32767, px)),
                                            max(-32768, min(32767, py)))
                props = props[:255]
                body += struct.pack("<B", len(props))
                for key, value in props:
                    body += struct.pack("<hh", index(key), index(value or ""))
                count += 1

    head = bytearray(b"IGMB")
    head += struct.pack("<iiii", 2, BIN_CELL, width, height)
    head += struct.pack("<i", len(strings))
    for text in sorted(strings, key=strings.get):
        raw = text.encode("utf-8")
        head += struct.pack("<h", len(raw)) + raw
    with open(bin_path, "wb") as f:
        f.write(head + body)
    return count


def read_bin(bin_path: str) -> dict:
    """The file read back the way the game reads it, for the self-test:
    {(cell x, cell y): [(rings, {key: value})]}."""
    data = open(bin_path, "rb").read()
    pos = 0

    def take(fmt):
        nonlocal pos
        values = struct.unpack_from(fmt, data, pos)
        pos += struct.calcsize(fmt)
        return values if len(values) > 1 else values[0]

    if data[:4] != b"IGMB":
        raise ValueError("invalid format (magic doesn't match)")
    pos = 4
    version, cell, width, height = take("<iiii")
    if version != 2 or cell != 256:
        raise ValueError(f"version {version}, cell size {cell}")
    strings = []
    for _ in range(take("<i")):
        n = take("<h")
        strings.append(data[pos:pos + n].decode("utf-8"))
        pos += n
    out = {}
    for _ in range(width * height):
        x = take("<i")
        if x == -1:
            continue
        y, n = take("<ii")
        feats = []
        for _ in range(n):
            kind = strings[take("<h")]
            rings = []
            for _ in range(take("<B")):
                rings.append([take("<hh") for _ in range(take("<h"))])
            props = {strings[take("<h")]: strings[take("<h")] for _ in range(take("<B"))}
            feats.append((kind, rings, props))
        out[(x, y)] = feats
    if pos != len(data):
        raise ValueError(f"{len(data) - pos} bytes left over")
    return out
