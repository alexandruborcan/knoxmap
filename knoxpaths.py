"""Where everything KnoxMap depends on lives, on whichever PC it runs on.

Nothing here assumes a particular machine. Each location is looked up in this
order, and the first that exists wins:

1. an environment variable, for people who keep things somewhere unusual
2. knoxmap_config.json next to this file, which Setup writes
3. the place Setup installs to by default, inside this folder
4. well-known locations (Steam libraries, ~/Zomboid)
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "knoxmap_config.json"
VENDOR_DIR = BASE_DIR / "vendor"


def load_config() -> dict:
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_config(values: dict) -> None:
    config = load_config()
    config.update({k: str(v) for k, v in values.items() if v})
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def _first(*candidates) -> Path | None:
    for c in candidates:
        if c and _exists(Path(c)):
            return Path(c)
    return None


def mapping_tools_dir() -> Path | None:
    """The PZ Mapping Tools folder (the one holding bin/ and config/)."""
    return _first(
        os.environ.get("PZ_MAPPING_TOOLS"),
        load_config().get("mapping_tools"),
        VENDOR_DIR / "PZMappingTools",
        BASE_DIR.parent / "PZMappingTools",     # the layout this grew up in
    )


def _tool(name: str, override: str) -> Path | None:
    """One of the map tools' programs: the Windows build, or a Linux one built
    from the same source beside it (see worlded/README.md)."""
    chosen = os.environ.get(override)
    if chosen and _exists(Path(chosen)):
        return Path(chosen)
    tools = mapping_tools_dir()
    if not tools:
        return None
    for candidate in (tools / "bin" / f"{name}.exe", tools / "bin" / name):
        if _exists(candidate):
            return candidate
    return None


def worlded_cli() -> Path | None:
    """The patched, headless map compiler (PZWorldEd_cli)."""
    return _tool("PZWorldEd_cli", "PZWORLDED_CLI")


def worlded_gui() -> Path | None:
    return _tool("PZWorldEd", "PZWORLDED")


def command_for(program: Path | str) -> list[str]:
    """How to run one of the map tools here.

    They are built for Windows. Off Windows the same binaries run under Wine,
    which every Steam-on-Linux machine already has; a Linux build of the tools
    (no .exe) is run directly. KNOXMAP_WINE names a different Wine.
    """
    program = str(program)
    if os.name != "nt" and program.lower().endswith(".exe"):
        return [os.environ.get("KNOXMAP_WINE", "wine"), program]
    return [program]


def chosen_steam_folders() -> list[str]:
    """Drives or folders the player named as holding Steam games, in the app
    or in Setup, looked in before anything found automatically. The
    KNOXMAP_STEAM_FOLDERS environment variable adds more, separated by ';'."""
    chosen = [p for p in os.environ.get("KNOXMAP_STEAM_FOLDERS", "").split(";") if p.strip()]
    saved = load_config().get("steam_folders", [])
    if isinstance(saved, str):
        saved = saved.split(";")
    return [p.strip().strip('"') for p in chosen + list(saved) if str(p).strip()]


def save_steam_folders(folders: list[str]) -> None:
    config = load_config()
    config["steam_folders"] = [str(f).strip().strip('"') for f in folders if str(f).strip()]
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    _LIBRARY_CACHE["libraries"] = None


def library_of(folder: str | Path) -> list[Path]:
    """The Steam libraries a folder the player named could mean: the library
    itself, one inside it (a drive's SteamLibrary), or the library a path
    deeper inside it belongs to (…/steamapps/common/ProjectZomboid)."""
    text = str(folder).strip().strip('"')
    if not text:
        return []
    if re.fullmatch(r"[A-Za-z]:?[\\/]?", text):        # "E", "E:" or "E:\"
        text = text[0] + ":\\"
    path = Path(text)
    parts = [p.lower() for p in path.parts]
    if "steamapps" in parts:
        path = Path(*path.parts[:parts.index("steamapps")])
    candidates = [path] + [path / sub for sub in _LIBRARY_NAMES]
    return [c for c in candidates if _is_dir(c / "steamapps")]


_LIBRARY_NAMES = ("SteamLibrary", "Steam", "Steam Library", "Games\\Steam", "Games\\SteamLibrary",
                  "Program Files (x86)\\Steam", "Program Files\\Steam")


def steam_libraries_found() -> list[dict]:
    """Every Steam library in use, and whether the player chose it or it was
    found automatically - for the app and Setup to show."""
    chosen = {str(lib).lower() for folder in chosen_steam_folders() for lib in library_of(folder)}
    return [{"path": str(lib), "chosen": str(lib).lower() in chosen} for lib in _steam_libraries()]


_LIBRARY_CACHE: dict = {"at": 0.0, "libraries": None}


def _steam_libraries() -> list[Path]:
    """Every Steam library folder on this PC: the ones the player chose, then
    the ones Steam itself lists, then the usual folders on every drive.

    Remembered for a minute: the page asks several times on every load, and a
    mapped network drive that is not connected can take seconds to answer."""
    import time

    chosen = tuple(chosen_steam_folders())
    if (_LIBRARY_CACHE["libraries"] is not None and _LIBRARY_CACHE.get("chosen") == chosen
            and time.time() - _LIBRARY_CACHE["at"] < 60):
        return list(_LIBRARY_CACHE["libraries"])
    found = _find_steam_libraries()
    _LIBRARY_CACHE.update(at=time.time(), libraries=found, chosen=chosen)
    return list(found)


def _find_steam_libraries() -> list[Path]:
    libraries: list[Path] = [lib for folder in chosen_steam_folders() for lib in library_of(folder)]
    roots: list[Path] = []
    try:
        import winreg

        for hive, key in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                          (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")):
            try:
                with winreg.OpenKey(hive, key) as k:
                    for name in ("SteamPath", "InstallPath"):
                        try:
                            roots.append(Path(winreg.QueryValueEx(k, name)[0]))
                        except OSError:
                            pass
            except OSError:
                pass
    except ImportError:
        pass
    roots += [Path(r"C:\Program Files (x86)\Steam"), Path.home() / ".steam" / "steam",
              Path.home() / ".local" / "share" / "Steam"]

    for root in roots:
        vdf = root / "steamapps" / "libraryfolders.vdf"
        if not _exists(vdf):
            continue
        libraries.append(root)
        try:
            text = vdf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in re.finditer(r'"path"\s+"([^"]+)"', text):
            libraries.append(Path(m.group(1).replace("\\\\", "\\")))
    # Steam keeps listing a library on a drive that has been unplugged or
    # removed; also look for the usual library folders on every drive, for a
    # library Steam's own files do not name.
    if os.name == "nt":
        for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
            libraries += [Path(f"{letter}:\\") / sub for sub in _LIBRARY_NAMES]
    seen, unique = set(), []
    for lib in libraries:
        key = str(lib).lower()
        if key not in seen and _is_dir(lib / "steamapps"):
            seen.add(key)
            unique.append(lib)
    return unique


def _exists(path: Path) -> bool:
    """Path.exists that is False, not an error, for a missing drive, a
    disconnected network share or a folder Windows will not let us read."""
    try:
        return path.exists()
    except (OSError, ValueError):
        return False


def _is_dir(path: Path) -> bool:
    try:
        return path.is_dir()
    except (OSError, ValueError):
        return False


def pz_install_dir() -> Path | None:
    """The Project Zomboid game folder (the one holding media/texturepacks)."""
    configured = _first(os.environ.get("PZ_INSTALL"), load_config().get("pz_install"))
    if configured:
        return configured
    for lib in _steam_libraries():
        candidate = lib / "steamapps" / "common" / "ProjectZomboid"
        if _exists(candidate / "media" / "texturepacks"):
            return candidate
    return None


def is_build42(game: Path | None) -> bool:
    """Whether this install is Build 42, the only one KnoxMap's maps load in.

    Build 42 split the floor tiles into their own *.floor.pack files; Build 41,
    still Steam's default branch for many players, has none.
    """
    return bool(game) and any((Path(game) / "media" / "texturepacks").glob("*.floor.pack"))


ELEVATORS_WORKSHOP_ID = "3780306632"


SPAWN_SELECTOR_WORKSHOP_ID = "3772052709"


def workshop_mod_installed(workshop_id: str, folder: str) -> bool:
    """Whether a mod is on this PC: subscribed on the Workshop in any Steam
    library, or copied into the mods folder under its own name."""
    for lib in _steam_libraries():
        if _is_dir(lib / "steamapps" / "workshop" / "content" / "108600" / workshop_id):
            return True
    return _is_dir(zomboid_user_dir() / "mods" / folder)


ERIKAS_TILES_WORKSHOP_ID = "3346506593"
ERIKAS_TILES_MOD_ID = "Erikas_Tiles"


def erikas_tiles_media() -> Path | None:
    """The media folder of Erika's Tiles, if the mod is on this PC."""
    for lib in _steam_libraries():
        base = lib / "steamapps" / "workshop" / "content" / "108600" / ERIKAS_TILES_WORKSHOP_ID
        if not _is_dir(base):
            continue
        for media in base.glob("mods/*/common/media"):
            if _exists(media / "texturepacks" / "Erikas_Tiles.pack"):
                return media
    return None


def erikas_tiles_ready() -> bool:
    """Erika's Tiles is installed and its sheets are in the map tools, so
    buildings may use them (Setup extracts them)."""
    tools = mapping_tools_dir()
    return bool(erikas_tiles_media() and tools and
                _exists(tools / "Tiles" / "2x" / "walls_decoration_paintings_erika_01.png"))


def elevators_mod_installed() -> bool:
    """Whether the Elevators mod, which runs KnoxMap's lifts, is installed."""
    return workshop_mod_installed(ELEVATORS_WORKSHOP_ID, "Elevators")


def spawn_selector_installed() -> bool:
    """Whether Spawn Selector, which offers the map's landmarks as starts, is installed."""
    return workshop_mod_installed(SPAWN_SELECTOR_WORKSHOP_ID, "SpawnSelector")


def zomboid_user_dir() -> Path:
    """~/Zomboid, where the game keeps saves and mods."""
    configured = os.environ.get("ZOMBOID_DIR") or load_config().get("zomboid_dir")
    return Path(configured) if configured else Path.home() / "Zomboid"
