"""Make the Workshop item's thumbnail and gallery pictures.

    python tools/make_workshop_art.py output/<a built and compiled map>

The pictures are the map itself, not mock-ups: the plan the generator draws,
and the compiled cells rendered the way the game stacks them (see
tools/render_lots.py). The thumbnail is the project's own cover art, which
already carries the wordmark, over a strip of that render.

Everything lands in workshop/preview.png and workshop/screenshots/.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from PIL import Image

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

OUT = BASE_DIR / "workshop"
SHOTS = OUT / "screenshots"
COVER = BASE_DIR / "branding" / "cover.png"
# Steam shows the thumbnail small and the gallery big.
PREVIEW = (512, 512)
SHOT = (1920, 1080)
BACKGROUND = (20, 24, 15)


def fit(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """`image` centred on the project's background, cropped to fill."""
    want_w, want_h = size
    scale = max(want_w / image.width, want_h / image.height)
    big = image.resize((max(1, round(image.width * scale)),
                        max(1, round(image.height * scale))), Image.Resampling.LANCZOS)
    left = (big.width - want_w) // 2
    top = (big.height - want_h) // 2
    return big.crop((left, top, left + want_w, top + want_h))


def letterbox(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """The whole of `image`, on the background, nothing cropped away.

    Never made bigger than it is: Steam shows these at whatever size they
    come in, and an upscaled picture only looks soft.
    """
    want_w, want_h = size
    scale = min(want_w / image.width, want_h / image.height, 1.0)
    if scale >= 1.0 and abs(image.width / image.height - want_w / want_h) < 0.01:
        return image.convert("RGB")
    small = image.resize((max(1, round(image.width * scale)),
                          max(1, round(image.height * scale))), Image.Resampling.LANCZOS)
    out = Image.new("RGB", size, BACKGROUND)
    out.paste(small, ((want_w - small.width) // 2, (want_h - small.height) // 2))
    return out


def render_lots(project: Path, x: int, y: int, w: int, h: int, scale: float,
                where: Path, max_level: int | None = None) -> Path | None:
    """One isometric view of the compiled cells, through render_lots.py."""
    cmd = [sys.executable, str(BASE_DIR / "tools" / "render_lots.py"), str(project),
           str(where), str(x), str(y), str(w), str(h), "--scale", str(scale)]
    if max_level is not None:
        cmd += ["--max-level", str(max_level)]
    done = subprocess.run(cmd, capture_output=True, text=True, check=False,
                          cwd=str(BASE_DIR))
    if done.returncode != 0 or not where.exists():
        print(f"   could not render {x},{y} {w}x{h}: "
              f"{(done.stderr or done.stdout).strip()[-200:]}")
        return None
    return where


def trim(image: Image.Image) -> Image.Image:
    """Cut the empty border off a render, which is mostly diagonal nothing."""
    if image.mode != "RGBA":
        return image
    box = image.getbbox()
    return image.crop(box) if box else image


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("project", help="a map folder that has been built and compiled")
    parser.add_argument("--spots", default="",
                        help="x,y,w,h[,top storey];... - which parts of the map to "
                             "render, and how far up; three views of the middle by "
                             "default, one of them with the roofs off")
    args = parser.parse_args(argv)

    project = Path(args.project).resolve()
    name = project.name
    info_path = project / f"{name}_info.json"
    if not info_path.exists():
        print(f"{info_path} is missing - is that a map folder?", file=sys.stderr)
        return 2
    import json
    info = json.loads(info_path.read_text(encoding="utf-8"))
    width, height = info["width_tiles"], info["height_tiles"]

    SHOTS.mkdir(parents=True, exist_ok=True)
    work = SHOTS / "_raw"
    work.mkdir(exist_ok=True)

    if args.spots:
        spots = []
        for piece in args.spots.split(";"):
            bits = [int(v) for v in piece.split(",")]
            spots.append(tuple(bits[:4]) + ((bits[4],) if len(bits) > 4 else ()))
    else:
        # The town from above; the same blocks with the roofs off, which is
        # the one that shows what is actually inside every building; and a
        # close view of a few streets.
        spots = [
            (width // 2 - 170, height // 2 - 170, 340, 340, None),
            (width // 2 - 80, height // 2 - 80, 160, 160, 0),
            (width // 2 - 60, height // 2 - 60, 120, 120, None),
        ]

    made: list[Path] = []
    print("rendering the compiled cells...")
    for n, spot in enumerate(spots, 1):
        x, y, w, h = spot[:4]
        max_level = spot[4] if len(spot) > 4 else None
        scale = 1.0 if w <= 180 else 0.55
        got = render_lots(project, x, y, w, h, scale, work / f"lots{n}.png",
                          max_level=max_level)
        if got:
            made.append(got)
            print(f"   {got.name}: {x},{y} {w}x{h}"
                  + (" (ground floor only)" if max_level == 0 else ""))

    shots: list[tuple[str, Image.Image]] = []
    for n, path in enumerate(made, 1):
        picture = trim(Image.open(path).convert("RGBA"))
        flat = Image.new("RGB", picture.size, BACKGROUND)
        flat.paste(picture, mask=picture.split()[3])
        shots.append((f"{n:02d}-town.png", letterbox(flat, SHOT)))

    plan = project / f"{name}_preview.png"
    if plan.exists():
        shots.append((f"{len(shots) + 1:02d}-plan.png",
                      letterbox(Image.open(plan).convert("RGB"), SHOT)))

    window = BASE_DIR / "branding" / "window.png"
    if window.exists():
        shots.append((f"{len(shots) + 1:02d}-window.png",
                      letterbox(Image.open(window).convert("RGB"), SHOT)))

    for filename, picture in shots:
        picture.save(SHOTS / filename)
        print(f"wrote {SHOTS / filename}")

    # The thumbnail: the cover art over a strip of the town.
    cover = Image.open(COVER).convert("RGB")
    preview = Image.new("RGB", PREVIEW, BACKGROUND)
    band = round(PREVIEW[1] * 0.46)
    if made:
        strip = trim(Image.open(made[0]).convert("RGBA"))
        flat = Image.new("RGB", strip.size, BACKGROUND)
        flat.paste(strip, mask=strip.split()[3])
        # An isometric view is a diamond: its corners are empty, and fitting
        # the whole of one into a thin band spends most of the band on
        # background. The middle of it is all town, so that is what is taken.
        keep = round(flat.height * 0.45)
        flat = flat.crop((0, (flat.height - keep) // 2,
                          flat.width, (flat.height + keep) // 2))
        preview.paste(fit(flat, (PREVIEW[0], band)), (0, PREVIEW[1] - band))
    art = cover.crop((150, 150, 1230, 520))
    art = art.resize((PREVIEW[0], round(art.height * PREVIEW[0] / art.width)),
                     Image.Resampling.LANCZOS)
    preview.paste(art, (0, (PREVIEW[1] - band - art.height) // 2))
    preview.save(OUT / "preview.png")
    print(f"wrote {OUT / 'preview.png'}")

    for path in work.glob("*"):
        path.unlink()
    work.rmdir()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
