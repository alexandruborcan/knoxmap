"""KnoxMap keeps itself up to date from its GitHub releases.

Each new version used to mean downloading the release zip again and unzipping
it over the old folder by hand, and most people simply stayed on the version
they had. Now:

1. When the window opens, check() asks GitHub for the latest release. If it is
   newer than this copy, its zip is downloaded into update/ in the background
   and checked against the fingerprint GitHub publishes for it.
2. The window says an update is ready. Restarting - the button, or just the
   next time KnoxMap is opened - applies it before anything else loads:
   apply_staged() unpacks the new files over the old ones, removes the files
   the new version no longer has, and brings the Python packages and the map
   tools up to date when requirements.txt or setup changed.

Only KnoxMap's own files are touched. Maps (output/), logs, the Python
environment, the map tools and the tile cache are never in a release zip, and
nothing is written outside the KnoxMap folder.

A git checkout never updates itself (it has git for that), and the check can
be turned off with "auto_update": false in knoxmap_config.json or
KNOXMAP_NO_UPDATE=1.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
REPO = "spytheeuclidean-a11y/knoxmap"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
UPDATE_DIR = BASE_DIR / "update"
STAGED = UPDATE_DIR / "staged.json"
MANIFEST = BASE_DIR / ".knoxmap_files.json"
USER_AGENT = f"KnoxMap-updater (+https://github.com/{REPO})"
CHECK_EVERY_S = 6 * 3600

# Never replaced or removed by an update, whatever a zip contains.
PROTECTED = {".venv", ".python", "output", "logs", "vendor", "cache", "update", ".git",
             "knoxmap_config.json", MANIFEST.name}

_state = {"state": "idle", "current": None, "latest": None, "notes": "", "error": None}
_lock = threading.Lock()


def _log():
    import knoxlog
    return knoxlog.log


def current_version() -> str:
    import knoxlog
    return knoxlog.version()


def _parse(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in re.findall(r"\d+", version or "")[:4]) or (0,)


def is_newer(latest: str, current: str) -> bool:
    return _parse(latest) > _parse(current)


def enabled() -> bool:
    if os.environ.get("KNOXMAP_NO_UPDATE") == "1" or (BASE_DIR / ".git").exists():
        return False
    try:
        import knoxpaths
        return knoxpaths.load_config().get("auto_update", True) is not False
    except Exception:  # noqa: BLE001 - no config yet is the default
        return True


def status() -> dict:
    with _lock:
        out = dict(_state)
    out["current"] = current_version()
    out["enabled"] = enabled()
    return out


def _set(**fields) -> None:
    with _lock:
        _state.update(fields)


# --- 1. check and download ---------------------------------------------------

def check(force: bool = False) -> dict:
    """Look for a newer release and stage it. Safe to call from any thread."""
    import requests

    if not enabled():
        _set(state="disabled")
        return status()
    with _lock:
        if _state["state"] in ("checking", "downloading"):
            return dict(_state)
        _state.update(state="checking", error=None)
    current = current_version()
    try:
        staged = _read_staged()
        if staged and is_newer(staged["version"], current) and Path(staged["zip"]).exists():
            _set(state="ready", latest=staged["version"], notes=staged.get("notes", ""))
            return status()
        r = requests.get(API_LATEST, headers={"User-Agent": USER_AGENT,
                                              "Accept": "application/vnd.github+json"},
                         timeout=15)
        r.raise_for_status()
        release = r.json()
        latest = (release.get("tag_name") or "").lstrip("v")
        notes = release.get("body") or ""
        if not is_newer(latest, current):
            _set(state="current", latest=latest, notes="")
            return status()
        asset = next((a for a in release.get("assets", [])
                      if re.fullmatch(r"KnoxMap-v[\w.]+\.zip", a.get("name", ""))), None)
        if asset is None:
            _set(state="error", latest=latest, error="the release has no KnoxMap zip")
            return status()
        _set(state="downloading", latest=latest, notes=notes)
        _log().info("update: downloading KnoxMap %s (this is %s)", latest, current)
        UPDATE_DIR.mkdir(exist_ok=True)
        target = UPDATE_DIR / asset["name"]
        partial = target.with_suffix(".part")
        h = hashlib.sha256()
        with requests.get(asset["browser_download_url"], headers={"User-Agent": USER_AGENT},
                          stream=True, timeout=60) as dl:
            dl.raise_for_status()
            with open(partial, "wb") as f:
                for chunk in dl.iter_content(1 << 16):
                    f.write(chunk)
                    h.update(chunk)
        digest = (asset.get("digest") or "").lower()
        if digest.startswith("sha256:") and digest.split(":", 1)[1] != h.hexdigest():
            partial.unlink(missing_ok=True)
            raise RuntimeError("the download does not match GitHub's fingerprint")
        with zipfile.ZipFile(partial) as z:
            bad = z.testzip()
            if bad is not None:
                raise RuntimeError(f"the download is damaged ({bad})")
            if "KnoxMap/knoxmap.py" not in z.namelist():
                raise RuntimeError("the download is not a KnoxMap release")
        partial.replace(target)
        STAGED.write_text(json.dumps({"version": latest, "zip": str(target), "notes": notes,
                                      "sha256": h.hexdigest()}), encoding="utf-8")
        for old in UPDATE_DIR.glob("KnoxMap-v*.zip"):
            if old != target:
                old.unlink(missing_ok=True)
        _log().info("update: KnoxMap %s is ready and applies on the next start", latest)
        _set(state="ready", latest=latest, notes=notes)
    except Exception as exc:  # noqa: BLE001 - offline, rate-limited, anything: try later
        _log().warning("update check failed: %s", exc)
        _set(state="error", error=str(exc))
    return status()


def check_in_background() -> None:
    """Check now and every few hours while the app is open."""
    def loop():
        time.sleep(5)          # let the window come up first
        while True:
            check()
            time.sleep(CHECK_EVERY_S)
    threading.Thread(target=loop, name="updater", daemon=True).start()


def _read_staged() -> dict | None:
    try:
        return json.loads(STAGED.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# --- 2. apply ----------------------------------------------------------------

def _protected(rel: str) -> bool:
    first = rel.replace("\\", "/").split("/", 1)[0]
    return first in PROTECTED


def _digest(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def apply_staged() -> bool:
    """Install a downloaded update, if there is one. Returns True when files
    changed, so the caller restarts on the new code."""
    staged = _read_staged()
    if not staged or not enabled():
        return False
    zip_path = Path(staged.get("zip", ""))
    if not zip_path.exists() or not is_newer(staged["version"], current_version()):
        STAGED.unlink(missing_ok=True)
        return False
    log = _log()
    log.info("update: applying KnoxMap %s over %s", staged["version"], current_version())
    watched = {name: _digest(BASE_DIR / name)
               for name in ("requirements.txt", "knoxmap_setup.py")}
    try:
        with zipfile.ZipFile(zip_path) as z, tempfile.TemporaryDirectory(dir=UPDATE_DIR) as tmp:
            members = [m for m in z.namelist() if m.startswith("KnoxMap/") and not m.endswith("/")]
            new_files = []
            for m in members:
                rel = m[len("KnoxMap/"):]
                dest = (BASE_DIR / rel).resolve()
                if _protected(rel) or BASE_DIR not in dest.parents:
                    continue
                new_files.append(rel)
            # Unpack everything first, then move it into place: a failure while
            # unpacking leaves the working copy as it was.
            z.extractall(tmp, members=[f"KnoxMap/{rel}" for rel in new_files])
            for rel in new_files:
                src = Path(tmp) / "KnoxMap" / rel
                dest = BASE_DIR / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                os.replace(src, dest)
        # Files the old version had and the new one does not.
        try:
            old_files = json.loads(MANIFEST.read_text(encoding="utf-8")).get("files", [])
        except (OSError, ValueError):
            old_files = []
        keep = set(new_files)
        for rel in old_files:
            if rel not in keep and not _protected(rel):
                (BASE_DIR / rel).unlink(missing_ok=True)
        MANIFEST.write_text(json.dumps({"version": staged["version"], "files": sorted(new_files)}),
                            encoding="utf-8")
    except Exception:  # noqa: BLE001
        log.exception("update: applying %s failed; KnoxMap starts as it was", staged["version"])
        STAGED.unlink(missing_ok=True)
        return False
    STAGED.unlink(missing_ok=True)
    zip_path.unlink(missing_ok=True)
    log.info("update: now on KnoxMap %s", staged["version"])

    python = BASE_DIR / ".venv" / "Scripts" / "python.exe"
    if not python.exists():
        python = Path(sys.executable)
    if _digest(BASE_DIR / "requirements.txt") != watched["requirements.txt"]:
        _run([str(python), "-m", "pip", "install", "--disable-pip-version-check", "-q",
              "-r", str(BASE_DIR / "requirements.txt")], "update: Python packages")
    if _digest(BASE_DIR / "knoxmap_setup.py") != watched["knoxmap_setup.py"]:
        _run([str(python), str(BASE_DIR / "knoxmap_setup.py")], "update: setup",
             env={"KNOXMAP_UNATTENDED": "1", "KNOXMAP_NO_PAUSE": "1"})
    return True


def _run(cmd: list[str], what: str, env: dict | None = None) -> None:
    log = _log()
    try:
        proc = subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL,
                              timeout=1800, env={**os.environ, **(env or {})},
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        log.info("%s: exit %d\n%s", what, proc.returncode, (proc.stdout + proc.stderr)[-4000:])
    except Exception as exc:  # noqa: BLE001 - the app still starts
        log.warning("%s failed: %s", what, exc)


def relaunch() -> None:
    """Start a fresh KnoxMap window, on whatever code is on disk now."""
    exe = Path(sys.executable)
    windowless = exe.with_name("pythonw.exe")
    if windowless.exists():
        exe = windowless
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen([str(exe), str(BASE_DIR / "knoxmap.py")], cwd=BASE_DIR,
                     creationflags=flags, close_fds=True)


def restart() -> None:
    """End this window and open a new one, which applies the staged update."""
    _log().info("update: restarting")
    relaunch()
    threading.Timer(0.5, lambda: os._exit(0)).start()

