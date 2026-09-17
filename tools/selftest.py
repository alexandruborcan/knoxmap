"""Run the whole generator on a made-up town, offline, and check the result.

    python tools/selftest.py [--keep]

No internet, no game and no map tools needed: the town is invented here - a
street grid turned 30 degrees, a main road, a coast with the sea beyond, a
river and its bridge, a park, a multipolygon lake with an island, a school,
a church, flats of seven storeys (tall enough for a lift) and a row of
houses. It goes through the same steps as the app - terrain, buildings, the
paper map, the installed mod - and each step's output is checked for the
things that have broken before. Exits non-zero on any failure, so it can
gate a change (see .github/workflows/checks.yml).
"""
from __future__ import annotations

import contextlib
import io
import json
import math
import os
import re
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402

from generator import pz_colors as C  # noqa: E402
from generator.osm import OSMFeature  # noqa: E402

# A town near 40N, about 600 m across.
SOUTH, WEST = 40.0000, 20.0000
NORTH, EAST = 40.0054, 20.0070
ANGLE = math.radians(30)
_ids = iter(range(1, 10 ** 6))


def _ll(x_m: float, y_m: float) -> tuple[float, float]:
    """Metres east/north of the south-west corner, turned by ANGLE, to (lat, lon)."""
    cx, cy = 300.0, 300.0
    dx, dy = x_m - cx, y_m - cy
    rx = cx + dx * math.cos(ANGLE) - dy * math.sin(ANGLE)
    ry = cy + dx * math.sin(ANGLE) + dy * math.cos(ANGLE)
    return SOUTH + ry / 111320.0, WEST + rx / (111320.0 * math.cos(math.radians(SOUTH)))


def way(tags: dict, pts_m: list[tuple[float, float]]) -> OSMFeature:
    return OSMFeature(next(_ids), "way", tags, [_ll(x, y) for x, y in pts_m])


def box(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]


def town() -> list[OSMFeature]:
    feats = []
    # Street grid, 80 m blocks, and one main road through the middle.
    for i in range(1, 7):
        feats.append(way({"highway": "residential", "name": f"Street {i}"},
                         [(i * 80, 60), (i * 80, 540)]))
        feats.append(way({"highway": "residential", "name": f"Avenue {i}"},
                         [(60, i * 80), (540, i * 80)]))
    feats.append(way({"highway": "primary", "name": "High Street", "lanes": "2"},
                     [(0, 300), (600, 300)]))
    # Buildings in the blocks: houses, flats tall enough for a lift, a school, a church.
    for bx in range(0, 5):
        for by in range(0, 5):
            x0, y0 = 90 + bx * 80, 90 + by * 80
            if (bx, by) == (2, 2):
                feats.append(way({"building": "apartments", "building:levels": "7"},
                                 box(x0, y0, x0 + 45, y0 + 30)))
            elif (bx, by) == (1, 3):
                feats.append(way({"building": "school", "name": "Selftest School"},
                                 box(x0, y0, x0 + 55, y0 + 40)))
            elif (bx, by) == (3, 1):
                feats.append(way({"building": "church", "name": "Selftest Church"},
                                 box(x0, y0, x0 + 30, y0 + 50)))
            elif (bx, by) == (4, 0):
                # A petrol station with room for a forecourt, and a car park.
                feats.append(way({"building": "retail", "amenity": "fuel", "name": "Selftest Gas"},
                                 box(x0 + 10, y0 + 5, x0 + 24, y0 + 15)))
                feats.append(way({"amenity": "parking"}, box(x0, y0 + 30, x0 + 60, y0 + 62)))
                # And its canopy, a roof over the forecourt, where the pumps go.
                feats.append(way({"building": "roof", "amenity": "fuel"},
                                 box(x0 + 34, y0 + 4, x0 + 54, y0 + 16)))
            elif (bx, by) == (0, 4):
                # A pizza place and a supermarket, to be fitted out as such.
                feats.append(way({"building": "yes", "amenity": "restaurant", "cuisine": "pizza",
                                  "name": "Selftest Pizza"}, box(x0, y0, x0 + 16, y0 + 12)))
                feats.append(way({"building": "retail", "shop": "supermarket",
                                  "name": "Selftest Market"}, box(x0 + 22, y0, x0 + 50, y0 + 24)))
            else:
                for k in range(3):
                    feats.append(way({"building": "house"},
                                     box(x0 + k * 20, y0, x0 + k * 20 + 12, y0 + 10)))
    feats.append(way({"leisure": "park", "name": "Selftest Park"}, box(410, 410, 470, 470)))
    # A river with a bridge carrying High Street over it.
    feats.append(way({"waterway": "river", "name": "Selftest River"}, [(560, 30), (560, 600)]))
    feats.append(way({"natural": "water", "water": "river"}, box(550, 0, 572, 600)))
    # A lane over the river on a bridge a little off square, to be laid square.
    feats.append(way({"highway": "residential"}, [(500, 452), (540, 452)]))
    feats.append(way({"highway": "residential", "bridge": "yes", "layer": "1",
                      "name": "Selftest Bridge"}, [(540, 452), (582, 458)]))
    feats.append(way({"highway": "residential"}, [(582, 458), (600, 458)]))
    # A flyover: a main road on a bridge over Avenue 5, with room for ramps.
    feats.append(way({"highway": "primary"}, [(510, 250), (510, 330)]))
    feats.append(way({"highway": "primary", "bridge": "yes", "layer": "1",
                      "name": "Selftest Flyover"}, [(510, 330), (510, 470)]))
    feats.append(way({"highway": "primary"}, [(510, 470), (510, 540)]))
    # A statue and a triumphal arch in the park.
    statue = OSMFeature(next(_ids), "node", {"historic": "memorial", "memorial": "statue",
                                             "name": "Selftest Statue"}, [_ll(450, 450)])
    feats.append(statue)
    feats.append(way({"building": "triumphal_arch", "historic": "monument", "height": "12",
                      "name": "Selftest Arch"}, box(420, 420, 432, 425)))
    # A coast along the south: land on the left of the line, sea to the right.
    # Deliberately short: a real download often holds only part of a shore.
    feats.append(way({"natural": "coastline"}, [(0, 30), (600, 30)]))
    # A lake as a multipolygon of two outer ways and an island.
    lake = OSMFeature(next(_ids), "relation", {"natural": "water", "name": "Selftest Lake"},
                      [])
    a = [(20, 420), (20, 500), (60, 500)]
    b = [(60, 500), (60, 420), (20, 420)]
    island = box(32, 450, 44, 466)
    lake.role_geoms = [("outer", [_ll(*p) for p in a]), ("outer", [_ll(*p) for p in b]),
                       ("inner", [_ll(*p) for p in island])]
    from generator.osm import assemble_rings
    lake.role_geoms = assemble_rings(lake.role_geoms)
    lake.geometry = [ring for _r, ring in lake.role_geoms]
    feats.append(lake)
    return feats


class Checks:
    def __init__(self):
        self.failed = 0

    def __call__(self, ok: bool, what: str) -> None:
        print(("  ok    " if ok else "  FAIL  ") + what)
        if not ok:
            self.failed += 1


def check_repair(check, out: str) -> None:
    """A project broken at its edges, as older versions and hand edits leave
    them, is repaired before compiling instead of stopping it."""
    from knoxbuild.repair import repair_project

    source = os.path.join(out, "selftest.pzw")
    broken = os.path.join(out, "broken.pzw")
    text = open(source, encoding="utf-8", newline="").read()
    nl = "\r\n" if "\r\n" in text else "\n"
    first_lot = re.search(r'map="(buildings/selftest_\d+\.tbx)"', text).group(1)
    # Not among the buildings: the checks further on read every file there.
    os.makedirs(os.path.join(out, "broken"), exist_ok=True)
    with open(os.path.join(out, "broken", "broken.tbx"), "w", encoding="utf-8") as f:
        f.write("<building version=\"4\" width=\"0\" height=\"3\"></building>")
    extra = nl.join([
        ' <cell x="9" y="0" map="">',                       # a whole cell past the edge
        f'  <lot x="5" y="5" level="0" width="3" height="3" map="{first_lot}"/>',
        " </cell>",
        ' <cell x="0" y="0" map="">',
        f'  <lot x="310" y="20" level="0" width="3" height="3" map="{first_lot}"/>',  # in cell 1,0 really
        '  <lot x="20" y="20" level="0" width="3" height="3" map="buildings/missing.tbx"/>',
        '  <lot x="30" y="20" level="0" width="3" height="3" map="broken/broken.tbx"/>',
        '  <object name="" group="TownZone" type="TownZone" x="10" y="950" level="0" width="5" height="5"/>',
        " </cell>",
    ])
    text = text.replace("</world>", extra + nl + "</world>")
    with open(broken, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    report = repair_project(broken)
    fixed = open(broken, encoding="utf-8").read()
    cells = [(int(a), int(b)) for a, b in re.findall(r'<cell x="(-?\d+)" y="(-?\d+)"', fixed)]
    size = re.search(r'<world version="[^"]*" width="(\d+)" height="(\d+)"', fixed)
    w, h = int(size.group(1)), int(size.group(2))
    reasons = " ".join(why for _what, why in report["dropped"])
    check(report["changed"] and report["moved"] == 1 and len(report["dropped"]) == 4
          and all(0 <= x < w and 0 <= y < h for x, y in cells)
          and len(cells) == len(set(cells))
          and "missing.tbx" not in fixed and "broken.tbx" not in fixed
          and "missing" in reasons and "outside" in reasons
          and os.path.exists(broken + ".bak"),
          f"a project broken at its edges is repaired, not refused "
          f"(moved {report['moved']}, dropped {len(report['dropped'])})")
    check(not repair_project(broken)["changed"] and not repair_project(source)["changed"],
          "a sound project is left exactly as it is")


def check_straight_roads(check) -> None:
    """Knox County roads: every road in grid or 45-degree runs, roads that met
    still meeting, and the buildings beside them moved with them."""
    from generator.octilinear import straighten_roads
    from generator.renderer import Projector, _is_polygon, classify

    proj = Projector.build(SOUTH, WEST, SOUTH + 0.0054, WEST + 0.0068, 1.0)
    # A long road at 12 degrees, a side street off it at 70, a crescent, and a
    # house beside the first.
    main = way({"highway": "primary"}, [(20, 100), (560, 215)])
    side = way({"highway": "residential"}, [(20, 100), (80, 265), (140, 430)])
    crescent = way({"highway": "residential"},
                   [(300, 400 + 60 * math.sin(t / 10)) for t in range(0, 32)])
    house = way({"building": "house"}, box(300, 170, 312, 180))
    before = proj.to_px(*house.geometry[0])
    feats = [main, side, crescent, house]
    straighten_roads(feats, proj, classify, _is_polygon)

    def runs_ok(f):
        pts = [proj.to_px(*p) for p in f.geometry]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            dx, dy = round(x1 - x0), round(y1 - y0)
            if not (dx == 0 or dy == 0 or abs(dx) == abs(dy)):
                return False
        return True

    check(all(runs_ok(f) for f in (main, side, crescent)),
          "Knox County roads run only along the tiles or on 45-degree diagonals")
    check(main.geometry[0] == side.geometry[0],
          "roads that met still meet once straightened")
    check(len({round(proj.to_px(*p)[1]) for p in main.geometry}) <= 2,
          "a long road at 12 degrees becomes straight, not a staircase")
    after = proj.to_px(*house.geometry[0])
    check(math.dist(before, after) > 0.5, "the houses beside a road move with it")


def check_missing_drive(check) -> None:
    """A Steam library on a drive that is gone (Windows raises for it rather
    than saying it is not there) is skipped, not a crash in Setup."""
    import knoxpaths

    class Gone(type(Path())):
        def stat(self, *a, **k):
            raise OSError(433, "A device which does not exist was specified", str(self))

    gone = Gone("F:/SteamLibrary")
    check(not knoxpaths._is_dir(gone / "steamapps") and not knoxpaths._exists(gone),
          "a Steam library on a missing drive is skipped")

    # A drive or folder the player names finds the library in it or above it.
    import tempfile
    with tempfile.TemporaryDirectory() as drive:
        lib = Path(drive) / "SteamLibrary"
        game = lib / "steamapps" / "common" / "ProjectZomboid"
        game.mkdir(parents=True)
        check(knoxpaths.library_of(drive) == [lib] and knoxpaths.library_of(game) == [lib]
              and knoxpaths.library_of(Path(drive) / "nothing") == [],
              "a chosen drive or folder finds its Steam library")
        old = os.environ.get("KNOXMAP_STEAM_FOLDERS")
        os.environ["KNOXMAP_STEAM_FOLDERS"] = drive
        try:
            found = knoxpaths.steam_libraries_found()
            check(found and found[0]["path"] == str(lib) and found[0]["chosen"],
                  "a chosen Steam library is looked in first")
        finally:
            if old is None:
                os.environ.pop("KNOXMAP_STEAM_FOLDERS")
            else:
                os.environ["KNOXMAP_STEAM_FOLDERS"] = old


def check_updater(check, work: str) -> None:
    """An update applied to a pretend install: new and changed files go in,
    dropped files go, and maps, logs and the Python environment are left alone."""
    import zipfile

    import updater

    base = Path(work) / "install"
    (base / "output" / "mytown").mkdir(parents=True)
    (base / "output" / "mytown" / "mytown.bmp").write_text("map")
    (base / ".venv").mkdir()
    (base / ".venv" / "keep.txt").write_text("env")
    (base / "knoxmap.py").write_text("old")
    (base / "dropped.py").write_text("gone in the new version")
    (base / "requirements.txt").write_text("flask")
    (base / "knoxmap_setup.py").write_text("setup")
    (base / updater.MANIFEST.name).write_text(json.dumps(
        {"version": "1.0", "files": ["knoxmap.py", "dropped.py", "requirements.txt",
                                     "knoxmap_setup.py"]}))
    update_dir = base / "update"
    update_dir.mkdir()
    zip_path = update_dir / "KnoxMap-v9.9.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr("KnoxMap/knoxmap.py", "new")
        z.writestr("KnoxMap/requirements.txt", "flask")
        z.writestr("KnoxMap/knoxmap_setup.py", "setup")
        z.writestr("KnoxMap/added/module.py", "added")
        z.writestr("KnoxMap/output/mytown/mytown.bmp", "a release must not overwrite maps")
        z.writestr("KnoxMap/../escape.txt", "outside the folder")
    saved = {k: getattr(updater, k) for k in ("BASE_DIR", "UPDATE_DIR", "STAGED", "MANIFEST",
                                              "current_version", "enabled")}
    try:
        updater.BASE_DIR, updater.UPDATE_DIR = base, update_dir
        updater.STAGED, updater.MANIFEST = update_dir / "staged.json", base / saved["MANIFEST"].name
        updater.current_version = lambda: "1.0"
        updater.enabled = lambda: True
        updater.STAGED.write_text(json.dumps({"version": "9.9", "zip": str(zip_path)}))
        applied = updater.apply_staged()
        check(applied and (base / "knoxmap.py").read_text() == "new"
              and (base / "added" / "module.py").exists() and not (base / "dropped.py").exists(),
              "an update puts in the new files and takes out the dropped ones")
        check((base / "output" / "mytown" / "mytown.bmp").read_text() == "map"
              and (base / ".venv" / "keep.txt").exists()
              and not (Path(work) / "escape.txt").exists(),
              "an update leaves maps and the Python environment alone and stays in its folder")
        check(not updater.STAGED.exists() and not zip_path.exists() and not updater.apply_staged(),
              "an update is applied once")
        # An older version goes in only when it was chosen in the version menu.
        old_zip = update_dir / "KnoxMap-v0.5.zip"
        with zipfile.ZipFile(old_zip, "w") as z:
            z.writestr("KnoxMap/knoxmap.py", "old release")
        updater.STAGED.write_text(json.dumps({"version": "0.5", "zip": str(old_zip)}))
        check(not updater.apply_staged() and (base / "knoxmap.py").read_text() == "new",
              "an automatic update never goes back to an older version")
        updater.STAGED.write_text(json.dumps({"version": "0.5", "zip": str(old_zip), "chosen": True}))
        updater.enabled = lambda: False       # choosing an older one turns them off
        check(updater.apply_staged() and (base / "knoxmap.py").read_text() == "old release",
              "a version chosen in the menu goes in, older ones too")
        check(updater.is_newer("1.10", "1.9") and not updater.is_newer("1.2", "1.2.0")
              and updater.is_newer("1.2.1", "1.2"), "versions compare as numbers")
    finally:
        for k, v in saved.items():
            setattr(updater, k, v)


def main(argv: list[str]) -> int:
    keep = "--keep" in argv
    check = Checks()
    work = tempfile.mkdtemp(prefix="knoxmap-selftest-")
    os.environ["KNOXMAP_LOG_DIR"] = os.path.join(work, "logs")
    try:
        from generator import renderer
        from knoxbuild.build import build
        from knoxbuild.settings import Settings

        feats = town()
        angle, strength = renderer.dominant_road_angle(feats, SOUTH, WEST, NORTH, EAST)
        print(f"street grid: {angle:.1f} degrees, strength {strength:.2f}")
        check(abs(abs(angle) - 30) < 2 and strength > 0.8, "finds the 30-degree street grid")

        out = os.path.join(work, "selftest")
        print("terrain")
        renderer.render(feats, SOUTH, WEST, NORTH, EAST, meters_per_tile=1.0,
                        output_dir=out, map_name="selftest", rotation=-angle)
        ground = Image.open(os.path.join(out, "selftest.bmp")).convert("RGB")
        colours = {}
        for c in ground.get_flattened_data() if hasattr(ground, "get_flattened_data") else ground.getdata():
            colours[c] = colours.get(c, 0) + 1
        total = ground.width * ground.height
        check(colours.get(C.WATER, 0) / total > 0.03, "sea, river and lake are water")
        check(colours.get(C.MEDIUM_ASPHALT, 0) > 0 and colours.get(C.DARKEST_ASPHALT, 0) > 0,
              "streets and the main road are tarmac")
        check(colours.get(C.PALE_CONCRETE, 0) > 0, "streets have pavements")
        print("bridges and monuments")
        import json as _json
        raised = _json.load(open(os.path.join(out, "selftest_structures.json"), encoding="utf-8"))
        tiles = raised["tiles"]
        check(any(t[3] == "Floor" and t[4].startswith("ramps_01") and t[2] == 0 for t in tiles)
              and any(t[3] == "Floor" and t[2] == 1 for t in tiles),
              "the flyover climbs on ramps to a deck a storey up")
        proj = renderer.Projector.build(SOUTH, WEST, NORTH, EAST, 1.0, -angle)
        ax, ay = proj.to_px(*_ll(510, 400))
        under = {ground.getpixel((int(ax) + dx, int(ay) + dy)) for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
        check(C.DARKEST_ASPHALT not in under,
              "the avenue runs on under the flyover instead of meeting it")
        bx, by = proj.to_px(*_ll(556, 455))
        cx, _ = proj.to_px(*_ll(567, 455))

        def tarmac_rows(x):
            return [y for y in range(int(by) - 15, int(by) + 15)
                    if ground.getpixel((int(x), y)) == C.MEDIUM_ASPHALT]
        check(tarmac_rows(bx) and tarmac_rows(bx) == tarmac_rows(cx),
              "the bridge over the river is laid square")
        names = open(os.path.join(out, "selftest_buildings.geojson"), encoding="utf-8").read()
        check(any("cemetary_01" in t[4] for t in tiles) and "Selftest Arch" not in names
              and any(t[4] == "ramps_01_19" and t[2] >= 2 for t in tiles),
              "a statue stands in the park and the arch is an arch, not a house")
        veg = Image.open(os.path.join(out, "selftest_veg.bmp")).convert("RGB")
        pixels = veg.get_flattened_data() if hasattr(veg, "get_flattened_data") else veg.getdata()
        kerbs = sum(1 for c in pixels if c[0] == 12 and c[1] == 34)
        check(kerbs > 100, f"kerbs laid ({kerbs})")
        trees = sum(1 for c in pixels if c == C.TREES)
        shrubs = sum(1 for c in pixels if c == C.BUSHES)
        check(trees > 20 and shrubs > 20, f"gardens planted ({trees} trees, {shrubs} shrubs)")

        print("buildings")
        with contextlib.redirect_stdout(io.StringIO()) as log:
            build(out, settings=Settings(seed=1))
        rows = open(os.path.join(out, "selftest_placements.csv"), encoding="utf-8").read().splitlines()
        check(len(rows) - 1 >= 60, f"buildings placed ({len(rows) - 1})")
        pzw_text = open(os.path.join(out, "selftest.pzw"), encoding="utf-8").read()
        size = re.search(r'<world version="[^"]*" width="(\d+)" height="(\d+)"', pzw_text)
        cells = [(int(a), int(b)) for a, b in re.findall(r'<cell x="(\d+)" y="(\d+)"', pzw_text)]
        check(size and all(x < int(size.group(1)) and y < int(size.group(2)) for x, y in cells),
              "every cell in the WorldEd project is inside the world")
        check_repair(check, out)
        from knoxbuild.world import Placement, Zone, render_pzw
        edge = render_pzw(2, 2, "m.bmp", [Placement("a.tbx", 10, 599, 3, 3),
                                          Placement("b.tbx", 10, 600, 3, 3)], "m",
                          zones=[Zone("TownZone", 5, 650, 4, 4)])
        check(set(re.findall(r'<cell x="(\d+)" y="(\d+)"', edge)) ==
              {("0", "0"), ("0", "1"), ("1", "0"), ("1", "1")} and edge.count("<lot ") == 1,
              "a lot or zone past the map's edge never names a cell outside the world")
        tbx = [os.path.join(out, "buildings", f) for f in os.listdir(os.path.join(out, "buildings"))]
        import validate_tbx
        bad = [p for p in tbx if validate_tbx.check(p)]
        check(not bad, f"every building passes the editor's rules ({len(tbx)} files)")
        tall = [p for p in tbx if "fixtures_escalators_01_49" in open(p, encoding="utf-8").read()]
        check(len(tall) >= 1, "the seven-storey flats have a lift")
        school = [p for p in tbx if 'InternalName="classroom"' in open(p, encoding="utf-8").read()]
        pumps = [p for p in tbx if os.path.basename(p).startswith("selftest_pumps_")]
        check(pumps and any("_01_14" in open(p, encoding="utf-8").read() or
                            "_01_12" in open(p, encoding="utf-8").read() for p in pumps)
              and any("selftest_pumps_" in line for line in pzw_text.splitlines()),
              "the petrol station has pumps")
        stalls = len(re.findall(r'group="ParkingStall"', pzw_text))
        check(stalls >= 40, f"car parks and drives have parking stalls ({stalls})")
        check(len(school) >= 1, "the school has classrooms")
        texts = [open(p, encoding="utf-8").read() for p in tbx]
        windows = {m for t in texts for m in re.findall(r'category="windows">\s*<tile enum="West" tile="(\w+)"', t)}
        check(len(windows) >= 3, f"window styles vary ({len(windows)})")

        def gaps_match(t: str) -> bool:
            blocks = re.findall(r"<tile_entry[^>]*>(.*?)</tile_entry>", t, re.S)
            head = re.search(r"<building[^>]*>", t).group(0)
            ext = int(re.search(r'ExteriorWall="(\d+)"', head).group(1))
            cap = int(re.search(r'RoofCap="(\d+)"', head).group(1))
            west = re.search(r'enum="West" tile="(\w+)"', blocks[ext - 1])
            gap = re.search(r'enum="CapGapE3" tile="(\w+)"', blocks[cap - 1])
            return bool(west and gap and west.group(1) == gap.group(1))
        houses_tbx = [t for p, t in zip(tbx, texts) if not any(k in p for k in ("_fences_", "_structures_", "_pumps_"))]
        check(all(gaps_match(t) for t in houses_tbx), "flat roofs wall in the top floor with its own material")
        check(any("_fences_" in p for p in tbx), "back yards are fenced")
        yard = Image.open(os.path.join(out, "selftest.bmp")).convert("RGB")
        stone = sum(1 for c in (yard.get_flattened_data() if hasattr(yard, "get_flattened_data") else yard.getdata())
                    if c == C.PAVING_STONE)
        check(stone > 50, f"front paths laid ({stone} stone tiles)")
        check(any('RoofType="Peak' in t for t in texts), "houses have pitched roofs")
        check(any('InternalName="pizzakitchen"' in t and 'InternalName="restaurantdining"' in t
                  for t in texts), "the pizza place has a dining room and a pizza kitchen")
        check(any('InternalName="grocery"' in t and "location_shop_generic_01_015" in t for t in texts),
              "the supermarket has aisles of shelving")
        check(not any("fixtures_bathroom_01_026" in t and 'InternalName="grocery"' in t for t in texts),
              "no bath in a shop")
        from knoxbuild.layout import _erika_ready
        if _erika_ready():
            # The town has no shops; lay one out on a street to the south.
            from knoxbuild.layout import build_building
            from knoxbuild import catalog as KC
            from knoxbuild.tbx import render_tbx
            shop_path = os.path.join(out, "buildings", "selftest_shop.tbx")
            shop = render_tbx(build_building(18, 12, levels=2, commercial=True, kind="shop",
                                             seed=3, street="S"),
                              "selftest_shop", KC.SPECIAL_STYLES["shop"])
            open(shop_path, "w", encoding="utf-8").write(shop)
            check('type="wall"' in shop and "walls_commercial_erika" in shop,
                  "a shop gets Erika's glass shop front")
            check('<tiles layer="WallFurniture">' in shop, "a sign hangs over it")
            check(not validate_tbx.check(shop_path), "and still passes the editor's rules")
            speed = sum(1 for c in pixels if c in C.SPEED_SIGNS.values())
            check(speed > 0, f"speed limit signs on the streets ({speed})")
        else:
            check(not any("_erika_" in t for t in texts), "no mod tiles without Erika's Tiles")

        print("compile")
        from compile_map import clear_stale
        stale = os.path.join(out, "lots")
        os.makedirs(stale, exist_ok=True)
        old_lot = os.path.join(stale, "0_0.lotheader")
        open(old_lot, "wb").write(b"old")
        os.utime(old_lot, (1, 1))
        clear_stale(Path(out))
        check(not os.path.exists(old_lot), "a rebuilt map's old lots are cleared")
        open(old_lot, "wb").write(b"new")
        clear_stale(Path(out))
        check(os.path.exists(old_lot), "lots newer than the map are kept, so compiles resume")
        os.remove(old_lot)

        print("paper map")
        root = ET.parse(os.path.join(out, "worldmap.xml")).getroot()
        props = {p.get("value") for p in root.iter("property")}
        check("Residential" in props and "CommunityServices" in props,
              "buildings on the paper map, by kind")
        ET.parse(os.path.join(out, "streets.xml"))
        notes = open(os.path.join(out, "worldmap-annotations.lua"), encoding="utf-8").read()
        check("OpenStreetMap contributors" in notes, "OpenStreetMap credit on the in-game map")
        check("Selftest School" in notes or "Selftest Church" in notes, "landmarks labelled")

        print("spawn map")
        pop = json.load(open(os.path.join(out, "selftest_population.json"), encoding="utf-8"))
        check(pop.get("residents", 0) > 0, f"people counted ({pop.get('residents')} residents)")

        print("app page")

        import app as knoxmap_app
        client = knoxmap_app.app.test_client()
        page = client.get("/")
        assets = re.findall(r'(?:href|src)="(/static/[^"]+)"', page.get_data(as_text=True))
        missing = [a for a in assets if client.get(a).status_code != 200]
        check(page.status_code == 200 and len(assets) >= 8 and not missing,
              f"page and all {len(assets)} of its files are served" + (f" - missing {missing}" if missing else ""))
        # Scripts, images and stylesheets only; a plain <a> link loads nothing.
        import knoxlog as _kl
        check(f"v{_kl.version()}" in page.get_data(as_text=True) and _kl.version() != "unknown",
              f"the window shows the version ({_kl.version()})")
        check(not re.search(r'(?:src="|<link[^>]*href=")https?://', page.get_data(as_text=True)),
              "page loads nothing from other sites")

        print("updates")
        check_updater(check, work)
        check_missing_drive(check)
        check_straight_roads(check)

        print("error log")
        import zipfile

        import knoxlog

        def _boom():
            raise ValueError("selftest boom")
        real = knoxmap_app.app.view_functions["api_lots"]
        knoxmap_app.app.view_functions["api_lots"] = _boom
        try:
            reply = client.get("/api/lots?map=x")
        finally:
            knoxmap_app.app.view_functions["api_lots"] = real
        body = reply.get_json(silent=True) or {}
        logged = open(knoxlog.MAIN_LOG, encoding="utf-8").read() if knoxlog.MAIN_LOG.exists() else ""
        check(reply.status_code == 500 and reply.is_json and str(body.get("errorId", "")).startswith("E-")
              and body["errorId"] in logged and "ValueError: selftest boom" in logged,
              "a crash comes back as JSON with an id that finds its traceback in the log")
        refused = client.post("/api/buildings", json={"mapName": "no such map"}).get_json() or {}
        logged = open(knoxlog.MAIN_LOG, encoding="utf-8").read()
        check(refused.get("errorId", "-") in logged, "refusals are logged with their id too")
        client.post("/api/client-error", json={"message": "selftest page error", "where": "x.js:1:1"})
        check("selftest page error" in open(knoxlog.MAIN_LOG, encoding="utf-8").read(),
              "errors in the page reach the log")
        report = client.get("/api/report")
        names = zipfile.ZipFile(io.BytesIO(report.data)).namelist() if report.status_code == 200 else []
        check("system.txt" in names and "logs/knoxmap.log" in names,
              f"the problem report holds the log and a description of the PC ({len(names)} files)")
        home = str(Path.home())
        check(home not in knoxlog.redact(os.path.join(home, "KnoxMap", "x.log"))
              and "<home>" in knoxlog.redact(home),
              "the report leaves the user's name out of paths")

        print("install")
        lots = os.path.join(out, "lots")
        os.makedirs(lots, exist_ok=True)
        open(os.path.join(lots, "0_0.lotheader"), "wb").write(b"stand-in")
        from make_map_mod import package
        mods = os.path.join(work, "mods")
        with contextlib.redirect_stdout(io.StringIO()):
            mod_root, cells, extras = package(out, "Selftest: Town", "selftest", mods_dir=mods)
        check(os.path.exists(os.path.join(mod_root, "ATTRIBUTION.txt")), "ATTRIBUTION.txt in the mod")
        info = open(os.path.join(mod_root, "mod.info"), encoding="utf-8").read()
        check("OpenStreetMap" in info, "OpenStreetMap credit in the mod description")
        check("require=" not in info, "a map without mod tiles requires no mods")
        from knoxbuild.worldmap_bin import read_bin
        bin_map = os.path.join(mod_root, "common", "media", "maps", "Selftest Town", "worldmap.xml.bin")
        try:
            paper = read_bin(bin_map)
        except (OSError, ValueError) as exc:
            paper = {}
            print(f"        {exc}")
        kinds = {k for feats in paper.values() for _t, _r, props in feats for k in props}
        check(paper and "building" in kinds
              and all(x >= 82 for x, _y in paper)
              and all(-32768 <= px <= 32767 for feats in paper.values()
                      for _t, rings, _p in feats for ring in rings for px, _ in ring),
              f"the paper map is written as Build 42's worldmap.xml.bin ({len(paper)} cells)")
        objects = os.path.join(mod_root, "common", "media", "maps", "Selftest Town", "objects.lua")
        text = open(objects, encoding="utf-8").read() if os.path.exists(objects) else ""
        check(text.startswith("objects = {") and text.count('type = "ParkingStall"') == stalls
              and re.search(r'x = 2\d{4}, y = \d+, z = 0', text),
              "the parking stalls reach the game in objects.lua, at world tiles")
        open(os.path.join(lots, "0_0.lotheader"), "wb").write(b"LOTH\x01\x00\x00\x00signs_erika_01_000\n")
        with contextlib.redirect_stdout(io.StringIO()):
            mod_root, cells, extras = package(out, "Selftest: Town", "selftest", mods_dir=mods)
        info_erika = open(os.path.join(mod_root, "mod.info"), encoding="utf-8").read()
        check("require=\\Erikas_Tiles" in info_erika, "a map using Erika's tiles requires Erika's Tiles")
        check(os.path.isdir(os.path.join(mod_root, "common", "media", "maps", "Selftest Town")),
              "map folder name is safe for Windows")
        lua_dir = os.path.join(mod_root, "common", "media", "lua", "shared", "KnoxMap")
        selector = [open(os.path.join(lua_dir, f), encoding="utf-8").read()
                    for f in os.listdir(lua_dir)] if os.path.isdir(lua_dir) else []
        check(selector and "Selftest School" in selector[0] and "OnGameBoot" in selector[0]
              and selector[0].count("{") == selector[0].count("}"),
              "Spawn Selector gets the town and its landmarks")
    except Exception:
        import traceback
        traceback.print_exc()
        check(False, "ran to the end without an error")
    finally:
        if keep:
            print(f"kept in {work}")
        else:
            shutil.rmtree(work, ignore_errors=True)

    print("selftest " + ("passed" if not check.failed else f"FAILED ({check.failed})"))
    return 1 if check.failed else 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    raise SystemExit(main(sys.argv))
