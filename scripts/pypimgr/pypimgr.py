#!/usr/bin/env python3
"""pypimgr - build, verify and release a Python package.

One command takes a project from "changes in the working tree" to "released on PyPI":

    pypimgr release patch --push

It bumps the version files, stamps CHANGELOG.md, runs the tests, builds from a clean staging copy, inspects
the artifacts for secrets and junk, then makes ONE commit (default message "Release vX.Y.Z") with a tag.
Push the tag to publish through the GitHub Actions Trusted Publishing workflow.
Run `pypimgr` for the interface or `pypimgr --help` for the actions. Works on Linux, macOS and Windows.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path

VERSION = "2.0.0"
HERE = Path(__file__).resolve().parent
IS_WIN = os.name == "nt"
PROJECT_CACHE_ENV = "PYPIMGR_USE_PROJECT_CACHE"

# -- shared terminal UI (optional: the command line works without it) --------------------------------------
for _d in (HERE, HERE.parent.parent / "lib", Path("/usr/local/lib/gscripts"), Path("/usr/lib/gscripts"),
           Path.home() / ".local" / "lib" / "gscripts"):
    if (_d / "gstui.py").is_file():
        sys.path.insert(0, str(_d))
        break
try:
    import gstui as ui
except Exception:  # noqa: BLE001
    ui = None


def paint(text, color=None, **kw):
    return ui.paint(text, color, **kw) if ui else str(text)


G = ui.G if ui else dict(ok="+", warn="!", err="x", on="*", dot="#")

# -- output routing: printed on the command line, collected for a viewer in the interface ----------------
TERM = None          # set while the interface is running
LINES: list[str] = []


def emit(text: str = "") -> None:
    if TERM is not None:
        LINES.extend(text.splitlines() or [""])
    else:
        print(text)


def ok(msg):
    emit(f"  {paint(G['ok'], 'ok')}  {msg}")


def warn(msg):
    emit(f"  {paint(G['warn'], 'warn')}  {msg}")


def err(msg):
    emit(f"  {paint(G['err'], 'err')}  {msg}")


def info(msg):
    emit(f"  {paint(G['on'], 'ice')}  {msg}")


def step(msg):
    emit("")
    emit(f"  {paint(G['dot'], 'ice')} {paint(msg, 'silver', bold=True)}")


class Fail(Exception):
    """A step failed; the message is shown and the action stops."""


def ask_yes(question: str, default: bool = False) -> bool:
    if os.environ.get("PYPIMGR_YES") == "1":
        return True
    if TERM is not None:
        return ui.confirm(TERM, question)
    if not sys.stdin.isatty():
        raise Fail(f"'{question}' needs confirmation; run on a terminal or add --yes")
    r = input(f"  {paint('?', 'warn')}  {question} [{'Y/n' if default else 'y/N'}] ").strip().lower()
    return default if not r else r in ("y", "yes")


def ask_text(label: str, default: str = "") -> str | None:
    if TERM is not None:
        return ui.prompt(TERM, label, default)
    if not sys.stdin.isatty():
        return None
    try:
        v = input(f"  {label}{f' [{default}]' if default else ''}: ")
    except (EOFError, KeyboardInterrupt):
        return None
    return v.strip() or default or None


# -- cache and logs --------------------------------------------------------------------------------------------
def find_root(start: Path) -> Path | None:
    for p in [start, *start.parents]:
        if (p / "pyproject.toml").is_file():
            return p
    return None


ROOT = Path(os.environ.get("PROJECT_DIR", "")) if os.environ.get("PROJECT_DIR") else \
    (find_root(Path.cwd()) or find_root(HERE) or Path.cwd())
ENVFILE = ROOT / ".env.release"


def write(p: Path, text: str) -> None:
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return ""


def load_env() -> dict:
    vals = {}
    for ln in read(ENVFILE).splitlines():
        m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$", ln)
        if m and not ln.lstrip().startswith("#"):
            vals[m.group(1)] = m.group(2).strip("'\"")
    return vals


def project_name() -> str:
    m = re.search(r'^name\s*=\s*"([^"]+)"', read(ROOT / "pyproject.toml"), re.M)
    return m.group(1) if m else ROOT.name


def use_project_cache() -> bool:
    value = os.environ.get(PROJECT_CACHE_ENV)
    if value is None:
        value = load_env().get(PROJECT_CACHE_ENV)
    return value is None or value.strip().lower() not in {"0", "false", "no", "off"}


def _xdg_dir(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    path = Path(value).expanduser() if value else default
    return path if path.is_absolute() else default


def global_dirs() -> tuple[Path, Path]:
    name = project_name()
    if IS_WIN:
        root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        project = root / "pypimgr" / name
        return project, project / "logs"
    if sys.platform == "darwin":
        root = Path.home() / "Library"
        return root / "Caches" / "pypimgr" / name, root / "Logs" / "pypimgr" / name
    cache_home = _xdg_dir("XDG_CACHE_HOME", Path.home() / ".cache")
    state_home = _xdg_dir("XDG_STATE_HOME", Path.home() / ".local" / "state")
    return cache_home / "pypimgr" / name, state_home / "pypimgr" / name


def dirs() -> tuple[Path, Path]:
    if use_project_cache():
        return ROOT / ".cache" / "pypimgr" / project_name(), ROOT / ".logs"
    return global_dirs()


CACHE, LOGDIR = dirs()


def new_log_path(category: str, name: str) -> Path:
    safe_category = re.sub(r"[^a-z0-9-]+", "-", category.lower()).strip("-") or "general"
    safe_name = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")[:48] or "run"
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    return LOGDIR / safe_category / f"{timestamp}-{safe_name}.log"


LOGFILE = new_log_path("general", "pypimgr-session")
ART = CACHE / "artifacts"
LAST_COMMAND_LOG: Path | None = None


def redact(text: str) -> str:
    return re.sub(r"(?i)pypi-[A-Za-z0-9_-]+", "[REDACTED_TOKEN]", text)


def sanitize_log_file(path: Path) -> str:
    content = path.read_text(encoding="utf-8", errors="replace")
    safe = redact(content)
    if safe != content:
        path.write_text(safe, encoding="utf-8")
    return safe


def log(level: str, msg: str) -> None:
    LOGFILE.parent.mkdir(parents=True, exist_ok=True)
    if LOGFILE.exists() and LOGFILE.stat().st_size > 1_048_576:
        LOGFILE.replace(LOGFILE.with_suffix(".log.1"))
    with LOGFILE.open("a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [{level}] {redact(msg)}\n")


def record_error(category: str, message: str) -> Path:
    path = new_log_path(category, "error")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{time.strftime('%Y-%m-%d %H:%M:%S')} ERROR\n{redact(message)}\n", encoding="utf-8")
    log("ERR", f"{category}: {message.splitlines()[0] if message else 'error'} [log: {path}]")
    return path


# -- project metadata ---------------------------------------------------------------------------------------
PY_VER = re.compile(r'^(\s*__version__\s*=\s*["\'])([^"\']+)(["\'])', re.M)
TOML_VER = re.compile(r'^(\s*version\s*=\s*")([^"]+)(")', re.M)
VERSION_RE = re.compile(r"^\d+(\.\d+)*([abrc]+\d+|\.post\d+|\.dev\d+)?$")


def version_file() -> tuple[Path, re.Pattern]:
    t = read(ROOT / "pyproject.toml")
    m = re.search(r'version\s*=\s*\{\s*attr\s*=\s*"([\w.]+)"', t)
    if m:
        mod = ".".join(m.group(1).split(".")[:-1]).replace(".", "/") + ".py"
        for base in (ROOT, ROOT / "src"):
            if (base / mod).is_file():
                return base / mod, PY_VER
    return ROOT / "pyproject.toml", TOML_VER


def get_version() -> str:
    f, rx = version_file()
    m = rx.search(read(f))
    return m.group(2) if m else "?"


def write_version(new: str) -> None:
    f, rx = version_file()
    txt = read(f)
    if not rx.search(txt):
        raise Fail(f"no version found in {f.relative_to(ROOT)}")
    write(f, rx.sub(lambda m: m.group(1) + new + m.group(3), txt, count=1))


def next_version(bump: str) -> str:
    cur = get_version()
    if bump == "fix":
        if not VERSION_RE.match(cur):
            raise Fail(f"cannot fix invalid version '{cur}'")
        return cur
    if VERSION_RE.match(bump) and re.match(r"^\d", bump):
        return bump
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)", cur)
    if not m or bump not in ("patch", "minor", "major"):
        raise Fail(f"cannot bump '{cur}' with '{bump}'; use patch/minor/major/fix or give an explicit version")
    a, b, c = map(int, m.groups())
    return {"major": f"{a + 1}.0.0", "minor": f"{a}.{b + 1}.0", "patch": f"{a}.{b}.{c + 1}"}[bump]


# -- changelog -------------------------------------------------------------------------------------------------
CHANGELOG = ROOT / "CHANGELOG.md"


def section(title: str):
    lines = read(CHANGELOG).splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.strip().lower() == f"## {title}".lower()), None)
    if start is None:
        return None
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return dict(start=start, end=end, body="\n".join(lines[start + 1:end]).strip(), lines=lines)


def stamp_changelog(new: str) -> None:
    un, st = section("Unreleased"), section(new)
    if not (un and un["body"]):
        if st:
            return
        if un:
            lines = un["lines"]
            lines[un["start"]:un["start"] + 1] = ["## Unreleased", "", f"## {new}"]
        else:
            lines = read(CHANGELOG).splitlines()
            start = next((i for i, line in enumerate(lines) if line.startswith("## ")), len(lines))
            if start and lines[start - 1].strip():
                lines.insert(start, "")
                start += 1
            lines[start:start] = [f"## {new}", ""]
        write(CHANGELOG, "\n".join(lines).rstrip() + "\n")
        return
    if st:
        lines = un["lines"]
        added = un["body"].splitlines()
        lines[un["start"] + 1:un["end"]] = [""]
        start = next(i for i, line in enumerate(lines) if line.strip().lower() == f"## {new}".lower())
        end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
        body = lines[start + 1:end]
        while body and not body[-1].strip():
            body.pop()
        body.extend(added)
        if end < len(lines):
            body.append("")
        lines[start + 1:end] = body
        write(CHANGELOG, "\n".join(lines).rstrip() + "\n")
        return
    lines = un["lines"]
    lines[un["start"]:un["start"] + 1] = ["## Unreleased", "", f"## {new}"]
    write(CHANGELOG, "\n".join(lines).rstrip() + "\n")


def cmd_notes(a) -> int:
    version = a.version.lstrip("v")
    s = section(version)
    if not s or not s["body"]:
        print(f"No changelog notes were provided for {version}.")
        return 0
    print(s["body"])
    return 0


# -- running things ----------------------------------------------------------------------------------------------
def sh(cmd, label: str = "", cwd=None, env=None, quiet=False) -> tuple[int, str]:
    """Run a command, save its output in a categorized log, and return its exit code and output tail."""
    global LAST_COMMAND_LOG
    cmd = [str(c) for c in cmd]
    name = label or Path(cmd[0]).stem
    lowered = name.lower()
    if "testpypi" in lowered:
        category = "testpypi"
    elif "upload" in lowered or "publish" in lowered:
        category = "publish"
    elif "ruff" in lowered or "pytest" in lowered or "test" in lowered:
        category = "tests"
    elif "verify" in lowered or "twine check" in lowered or "checking" in lowered:
        category = "verify"
    elif "build" in lowered:
        category = "build"
    elif "venv" in lowered or "install" in lowered or "python" in lowered:
        category = "setup"
    else:
        category = "commands"
    LAST_COMMAND_LOG = new_log_path(category, name)
    LAST_COMMAND_LOG.parent.mkdir(parents=True, exist_ok=True)
    with LAST_COMMAND_LOG.open("w", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} CMD: {redact(' '.join(cmd))}\n")
    log("CMD", f"{' '.join(cmd)} [log: {LAST_COMMAND_LOG}]")
    old = {}
    for k, v in (env or {}).items():                # secrets pass through the environment only, never the log
        old[k] = os.environ.get(k)
        os.environ[k] = v
    try:
        if TERM is not None:
            rc, tail = ui.run_task(TERM, label or cmd[0], cmd, log=str(LAST_COMMAND_LOG), cwd=cwd)
            return rc, sanitize_log_file(LAST_COMMAND_LOG)[-1500:]
        if label:
            info(label)
        tail = ""
        try:
            with LAST_COMMAND_LOG.open("a", encoding="utf-8") as f:
                proc = subprocess.Popen(
                    cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                    encoding="utf-8", errors="replace", bufsize=1,
                )
                with proc:
                    for line in proc.stdout:
                        safe_line = redact(line)
                        f.write(safe_line)
                        tail = (tail + safe_line)[-6000:]
                        if not quiet:
                            sys.stdout.write(safe_line)
                            sys.stdout.flush()
                    rc = proc.wait()
            return rc, tail
        except FileNotFoundError:
            message = f"{cmd[0]}: not found"
            with LAST_COMMAND_LOG.open("a", encoding="utf-8") as f:
                f.write(message + "\n")
            if not quiet:
                print(message, file=sys.stderr)
            return 127, message
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def command_error(message: str, output: str, log_path: Path | None = None) -> str:
    parts = [message]
    detail = output.strip()
    if detail:
        parts.append(detail[-1200:])
    path = log_path or LAST_COMMAND_LOG
    if path:
        parts.append(f"Full log: {path}")
    return "\n".join(parts)


def git(*args, check=False) -> subprocess.CompletedProcess:
    p = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    if check and p.returncode != 0:
        raise Fail(f"git {' '.join(args)} failed: {(p.stderr or p.stdout).strip()}")
    return p


def is_repo() -> bool:
    return shutil.which("git") is not None and git("rev-parse", "--is-inside-work-tree").returncode == 0


def dirty() -> list[str]:
    return [ln for ln in git("status", "--porcelain").stdout.splitlines() if ln.strip()]


# -- tool environment (isolated venv with build + twine) ----------------------------------------------------------
def tool_python() -> str:
    if os.environ.get("PYPIMGR_NO_VENV") or os.environ.get("CI"):
        return sys.executable
    venv = CACHE / "venv"
    py = venv / ("Scripts/python.exe" if IS_WIN else "bin/python")
    if not py.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        rc, o = sh([sys.executable, "-m", "venv", venv], "Creating the build environment")
        if rc != 0:
            raise Fail(command_error("venv creation failed", o))
    rc, _ = sh([py, "-c", "import build, twine"], quiet=True)
    if rc != 0:
        rc, o = sh([py, "-m", "pip", "install", "--quiet", "--upgrade", "pip", "build", "twine"],
                   "Installing build and twine")
        if rc != 0:
            raise Fail(command_error("pip install failed", o))
    return str(py)


# -- secrets ---------------------------------------------------------------------------------------------------
def env_file_problem() -> str:
    """Empty string when .env.release is safe to use (ignored, untracked); otherwise why not."""
    if not ENVFILE.exists():
        return ""
    if is_repo():
        if git("ls-files", "--error-unmatch", ".env.release").returncode == 0:
            return ".env.release is tracked by git. Remove it from version control and review the repository history."
        if git("check-ignore", "-q", ".env.release").returncode != 0:
            return ".env.release is not covered by .gitignore. Add the line  .env.release  first"
    if not IS_WIN:
        try:
            if ENVFILE.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
                ENVFILE.chmod(0o600)
        except OSError:
            pass
    return ""


# -- build and verify -------------------------------------------------------------------------------------------
TOP_SKIP = {".git", ".github", ".cache", ".logs", "build", "dist", "scripts", "tests", "test", "examples",
            "runs", "demo_runs", "docs"}
ANY_SKIP = {"__pycache__", "node_modules", ".venv", "venv", ".idea", ".vscode", ".pytest_cache", ".ruff_cache",
            ".mypy_cache", ".git"}
FILE_SKIP = ["*.pyc", "*.pyo", ".env", ".env.*", "*.pem", "*.key", ".pypirc", "*.map", "*.pkl", "*.pt", "*.pth",
             "*.log", "*.zip", "*.egg-info", "TODO.md", ".DS_Store", "*commit.txt"]


def stage() -> Path:
    dst = Path(tempfile.mkdtemp(prefix="pypimgr-"))
    root = ROOT.resolve()

    def ignore(d, names):
        top = Path(d).resolve() == root
        return [n for n in names if (top and n in TOP_SKIP) or n in ANY_SKIP or any(fnmatch(n, p) for p in FILE_SKIP)]
    shutil.copytree(root, dst / "src", ignore=ignore)
    return dst


def artifacts() -> list[Path]:
    return sorted(p for p in ART.glob("*") if p.suffix == ".whl" or p.name.endswith(".tar.gz")) if ART.exists() else []


def do_build() -> list[Path]:
    py = tool_python()
    step("Building from a clean staging copy")
    tmp = stage()
    try:
        out = tmp / "out"
        rc, tail = sh([py, "-m", "build", "--outdir", out], "Building sdist and wheel", cwd=tmp / "src")
        if rc != 0:
            raise Fail(command_error("build failed", tail))
        ART.mkdir(parents=True, exist_ok=True)
        for old in artifacts():
            old.unlink()
        for f in out.iterdir():
            shutil.copy2(f, ART / f.name)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    arts = artifacts()
    for f in arts:
        ok(f"{f.name}  ({f.stat().st_size // 1024} KB)")
    return arts


def do_verify() -> None:
    arts = artifacts()
    if not arts:
        raise Fail("no artifacts yet; run: pypimgr build")
    step("Inspecting artifacts")
    py = tool_python()
    ver = get_version()
    if not all(f"-{ver}" in f.name for f in arts):
        raise Fail(f"artifacts do not match version {ver}; run: pypimgr build")
    vd = HERE / "verify_dist.py"
    if vd.is_file():
        rc, o = sh([py, vd, *arts], "Checking for secrets and forbidden files")
        if rc != 0:
            raise Fail(command_error("verification FAILED - do not upload", o))
    rc, o = sh([py, "-m", "twine", "check", *arts], "twine check")
    if rc != 0:
        raise Fail(command_error("twine check failed", o))
    ok("artifacts passed verification")


def read_commit_message(path: Path) -> str:
    if not path.is_absolute():
        path = ROOT / path
    try:
        message = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as e:
        raise Fail(f"cannot read commit message from {path}: {e}") from e
    if not message:
        raise Fail(f"commit message file is empty: {path}")
    return message


def release_commit_message(version: str, a) -> str:
    default = f"Release v{version}"
    message = getattr(a, "message", None)
    message_file = getattr(a, "message_file", None)
    if message is not None and message_file is not None:
        raise Fail("use only one of --message and --message-file")
    if message_file is not None:
        if not str(message_file).strip():
            raise Fail("commit message file path must not be empty")
        return read_commit_message(Path(message_file))
    if message is not None:
        if not message.strip():
            raise Fail("custom commit message must not be empty")
        return message.strip()
    if a.yes or os.environ.get("PYPIMGR_YES") == "1":
        return default
    if not ask_yes("Use a custom commit message?"):
        return default
    if ask_yes("Use the message in commit.txt?", default=True):
        return read_commit_message(ROOT / "commit.txt")
    custom = ask_text("Custom commit message")
    if not custom:
        raise Fail("custom commit message was cancelled; no release was made")
    return custom.strip()


def validate_release_state(version: str, check_tag: bool = False) -> None:
    actual = get_version()
    if actual != version:
        raise Fail(f"version file has {actual}, expected {version}")
    unreleased = section("Unreleased")
    if unreleased and unreleased["body"]:
        raise Fail("CHANGELOG.md must have an empty Unreleased section after the release notes are stamped")
    released = section(version)
    if not released:
        raise Fail(f"CHANGELOG.md must contain a ## {version} section")
    if check_tag:
        latest = git("describe", "--tags", "--abbrev=0").stdout.strip()
        expected = f"v{version}"
        if latest != expected:
            raise Fail(f"latest git tag is {latest or 'missing'}, expected {expected}")


def ensure_release_is_unpushed(version: str) -> None:
    expected = f"v{version}"
    tagged = git("rev-parse", "--verify", f"refs/tags/{expected}^{{}}")
    head = git("rev-parse", "HEAD")
    if tagged.returncode != 0 or tagged.stdout.strip() != head.stdout.strip():
        raise Fail(f"same-version fixes can only amend HEAD when it is tagged {expected}")

    remotes = git("remote").stdout.splitlines()
    if not remotes:
        return
    for remote_name in remotes:
        result = git("ls-remote", "--heads", remote_name)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise Fail(f"cannot verify whether the release commit was pushed to {remote_name}: {detail}")
        for line in result.stdout.splitlines():
            remote_head = line.split(maxsplit=1)[0]
            # A remote branch whose commit is not in the local repo (e.g. a dependabot branch that was never
            # fetched) cannot contain HEAD, so it is skipped instead of aborting the release.
            if git("cat-file", "-e", f"{remote_head}^{{commit}}").returncode != 0:
                continue
            ancestor = git("merge-base", "--is-ancestor", "HEAD", remote_head)
            if ancestor.returncode == 0:
                raise Fail(f"release commit is already present on remote {remote_name}; refusing to amend it")
            if ancestor.returncode != 1:
                detail = (ancestor.stderr or ancestor.stdout).strip()
                raise Fail(f"cannot verify whether the release commit was pushed to {remote_name}: {detail}")

        tag_ref = f"refs/tags/{expected}"
        result = git("ls-remote", "--tags", remote_name, tag_ref, f"{tag_ref}^{{}}")
        if result.returncode != 0:
            raise Fail(f"cannot verify whether tag {expected} was pushed to {remote_name}: "
                       f"{(result.stderr or result.stdout).strip()}")
        if result.stdout.strip():
            raise Fail(f"tag {expected} already exists on remote {remote_name}; refusing to rewrite it")


# -- actions -------------------------------------------------------------------------------------------------------
def pypi_latest() -> str:
    try:
        with urllib.request.urlopen(f"https://pypi.org/pypi/{project_name()}/json", timeout=6) as r:
            return json.load(r)["info"]["version"]
    except Exception:  # noqa: BLE001
        return "unknown / not published"


def cmd_status(a=None) -> int:
    kv = lambda k, v: emit(f"  {paint(k.ljust(14), 'muted')} {v}")  # noqa: E731
    kv("Project", f"{project_name()}  ({ROOT})")
    kv("Version", get_version())
    kv("On PyPI", pypi_latest())
    if is_repo():
        br = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        tag = git("describe", "--tags", "--abbrev=0").stdout.strip() or "none"
        d = dirty()
        kv("Git", f"{br}, last tag {tag}, " + (f"{len(d)} uncommitted change(s)" if d else "clean"))
    else:
        kv("Git", "not a repository")
    un = section("Unreleased")
    kv("Changelog", "notes waiting under Unreleased" if un and un["body"] else "nothing under Unreleased")
    kv("Local settings", "present" if ENVFILE.exists() else "none")
    kv("Artifacts", ", ".join(f.name for f in artifacts()) or "none built")
    return 0


def cmd_check(a=None) -> int:
    bad = 0
    step("Project files")
    for f in ("README.md", "LICENSE", "pyproject.toml", "CHANGELOG.md", "MANIFEST.in", ".gitignore"):
        if (ROOT / f).is_file():
            ok(f)
        else:
            err(f"{f} missing")
            bad += 1
    step("Version")
    ok(f"{project_name()} {get_version()}  ({version_file()[0].relative_to(ROOT)})")
    if is_repo():
        step("Git")
        tags = git("tag", "--list", f"v{get_version()}").stdout.strip()
        (warn if tags else ok)(f"tag v{get_version()} " +
                               ("already exists (fix only while unpublished)" if tags else "is free"))
        d = dirty()
        (info if d else ok)(f"{len(d)} uncommitted change(s)" if d else "working tree clean")
    step("Local settings")
    problem = env_file_problem()
    if problem:
        err(problem)
        bad += 1
    else:
        ok(".env.release is ignored and untracked" if ENVFILE.exists() else "no .env.release")
    return 1 if bad else 0


def cmd_test(a=None) -> int:
    step("Running checks")
    py = sys.executable
    rc = 0
    if shutil.which("ruff") or subprocess.run([py, "-m", "ruff", "--version"], capture_output=True).returncode == 0:
        r, o = sh([py, "-m", "ruff", "check", "."], "ruff", cwd=ROOT)
        ruff_log = LAST_COMMAND_LOG
        if r == 0:
            ok("ruff clean")
        else:
            err(command_error("ruff found problems", o, ruff_log))
        rc |= r
    else:
        warn("ruff not installed; skipped (pip install -e '.[dev]')")
    r, o = sh([py, "-m", "pytest", "-q"], "pytest", cwd=ROOT)
    pytest_log = LAST_COMMAND_LOG
    if r == 0:
        ok("tests passed")
    else:
        err(command_error("tests failed", o, pytest_log))
    return rc | r


def cmd_build(a=None) -> int:
    do_build()
    do_verify()
    return 0


def cmd_verify(a=None) -> int:
    do_verify()
    return 0


def cmd_contents(a=None) -> int:
    import tarfile
    import zipfile
    arts = artifacts()
    if not arts:
        raise Fail("no artifacts yet; run: pypimgr build")
    for f in arts:
        step(f.name)
        names = zipfile.ZipFile(f).namelist() if f.suffix == ".whl" else tarfile.open(f).getnames()
        for n in names[:300]:
            emit("    " + n)
        if len(names) > 300:
            emit(f"    ... {len(names) - 300} more")
    return 0


def cmd_bump(a) -> int:
    new = next_version(a.version)
    cur = get_version()
    write_version(new)
    ok(f"{version_file()[0].relative_to(ROOT)}: {cur} -> {new}")
    if a.changelog:
        stamp_changelog(new)
        ok(f"CHANGELOG.md stamped with {new}")
    return 0


def cmd_publish(a=None) -> int:
    if not is_repo():
        raise Fail("not inside a git repository")
    version = get_version()
    tag = f"v{version}"
    tagged = git("rev-parse", "--verify", f"refs/tags/{tag}^{{}}")
    if tagged.returncode != 0:
        raise Fail(f"no local release tag {tag}; create one with `pypimgr release` first")
    head = git("rev-parse", "HEAD")
    if tagged.stdout.strip() != head.stdout.strip():
        raise Fail(f"local tag {tag} does not point to HEAD; check out the release commit before publishing")
    if dirty():
        raise Fail("working tree has uncommitted changes; commit or stash them before publishing")
    if git("remote", "get-url", "origin").returncode != 0:
        raise Fail("git remote 'origin' is not configured")
    remote_tag = git("ls-remote", "--tags", "origin", f"refs/tags/{tag}", f"refs/tags/{tag}^{{}}")
    if remote_tag.returncode != 0:
        detail = (remote_tag.stderr or remote_tag.stdout).strip()
        raise Fail(f"cannot check whether {tag} is on origin: {detail}")
    if remote_tag.stdout.strip():
        raise Fail(f"{tag} is already on origin; re-run the failed Release workflow in GitHub Actions")
    if not getattr(a, "yes", False) and not ask_yes(f"Push {tag} to origin and trigger PyPI publishing?"):
        info("cancelled")
        return 1
    result = git("push", "origin", tag)
    if result.returncode != 0:
        raise Fail(f"git push origin {tag} failed: {(result.stderr or result.stdout).strip()}")
    ok(f"pushed {tag}; GitHub Actions will publish through Trusted Publishing")
    return 0


def cmd_clean(a=None) -> int:
    if not ask_yes("Delete built artifacts, the build environment and build/ dist/ *.egg-info?", True):
        return 1
    shutil.rmtree(CACHE, ignore_errors=True)
    for p in (ROOT / "build", ROOT / "dist", *ROOT.glob("*.egg-info")):
        shutil.rmtree(p, ignore_errors=True)
    ok("cleaned")
    return 0


def cmd_doctor(a=None) -> int:
    bad = 0
    for name, good, hint in (
        ("python >= 3.10", sys.version_info >= (3, 10), "install Python 3.10 or newer"),
        ("git", shutil.which("git") is not None, "install git"),
        ("pyproject.toml", (ROOT / "pyproject.toml").is_file(), f"no project at {ROOT}; run from the project folder"),
        ("git user configured", bool(git("config", "user.email").stdout.strip()) if shutil.which("git") else False,
         "git config --global user.name ... && git config --global user.email ..."),
        ("CHANGELOG.md", CHANGELOG.is_file(), "create CHANGELOG.md with a '## Unreleased' section"),
    ):
        (ok if good else err)(name if good else f"{name}: {hint}")
        bad += 0 if good else 1
    problem = env_file_problem()
    (err if problem else ok)(problem or "local settings file policy")
    bad += 1 if problem else 0
    try:
        tool_python()
        ok("build and twine available")
    except Fail as e:
        err(str(e))
        bad += 1
    ok(f"storage {'project-local' if use_project_cache() else 'global'}")
    ok(f"cache {CACHE}")
    ok(f"logs  {LOGFILE}")
    return 1 if bad else 0


def cmd_logs(a=None) -> int:
    files = sorted(LOGDIR.rglob("*.log"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not files:
        emit("(no logs)")
        return 0
    for path in files[:12]:
        emit(f"--- {path.relative_to(LOGDIR)} ---")
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as e:
            emit(f"could not read log: {e}")
            continue
        for line in lines[-12:]:
            emit(line)
    return 0


def cmd_release(a) -> int:
    """Bump, test, build, verify, commit once, and tag; pushing triggers Trusted Publishing."""
    test = a.test
    step(f"Release plan  ({project_name()})")
    if not is_repo():
        raise Fail("not inside a git repository")
    new = next_version(a.bump)
    cur = get_version()
    fix_release = False
    info(f"version {cur} -> {new}" + ("   (build rehearsal: nothing is committed)" if test else ""))
    if not test:
        if git("tag", "--list", f"v{new}").stdout.strip():
            if new != cur:
                raise Fail(f"tag v{new} already exists")
            fix_release = True
            if not a.dry:
                ensure_release_is_unpushed(new)
        if not git("config", "user.email").stdout.strip():
            raise Fail("git user.name / user.email are not set")
        if a.push and git("remote", "get-url", "origin").returncode != 0:
            raise Fail("git remote 'origin' is not configured; add it before pushing a release")
    un, st = section("Unreleased"), section(new)
    if not ((un and un["body"]) or (st and st["body"])):
        info("no changelog notes; the release notes will state that none were provided")
    changes = dirty()
    include_all = not a.version_files_only
    if changes and not test:
        info(f"{len(changes)} uncommitted change(s) " +
             (("go into the existing release commit:" if fix_release else "go into the single release commit:")
              if include_all else "stay out of the release commit:"))
        for ln in changes[:15]:
            emit("      " + ln)
        if len(changes) > 15:
            emit(f"      ... {len(changes) - 15} more")
    if a.dry:
        if not a.skip_tests:
            if cmd_test() != 0:
                raise Fail("checks failed")
        ok("dry run complete; nothing was changed")
        return 0
    if not a.yes and not ask_yes(f"Release {project_name()} {new}" + (" as a build rehearsal" if test else "") + "?"):
        info("cancelled")
        return 1
    commit_message = f"Release v{new}"
    if not test and not a.dry:
        commit_message = release_commit_message(new, a)
    if not a.skip_tests:
        step("Tests")
        if cmd_test() != 0:
            raise Fail("checks failed; nothing was changed")
    vf, cl = version_file()[0], CHANGELOG
    snap = {vf: read(vf), cl: read(cl)}

    def restore():
        for p, t in snap.items():
            write(p, t)
    try:
        step("Version files")
        write_version(new)
        stamp_changelog(new)
        validate_release_state(new)
        ok(f"{vf.relative_to(ROOT)} and CHANGELOG.md updated")
        do_build()
        do_verify()
    except (Fail, KeyboardInterrupt):
        restore()
        warn("version files restored; nothing was committed")
        raise
    if test:
        restore()
        info("build and verification rehearsal complete; nothing was committed or published")
        return 0
    step("Amend release and tag" if fix_release else "Commit and tag")
    try:
        if include_all:
            git("add", "-A", check=True)
        else:
            git("add", str(vf), str(cl), check=True)
        if fix_release:
            git("commit", "--amend", "-m", commit_message, check=True)
        else:
            git("commit", "-m", commit_message, check=True)
    except Fail:
        restore()
        warn("version files restored; nothing was committed")
        raise
    try:
        if fix_release:
            git("tag", "--force", "--annotate", f"v{new}", "-m", f"v{new}", check=True)
        else:
            git("tag", "--annotate", f"v{new}", "-m", f"v{new}", check=True)
    except Fail:
        if fix_release:
            warn("the release commit was amended, but its local tag could not be updated")
        else:
            restore()
            warn("version files restored; nothing was committed")
        raise
    try:
        validate_release_state(new, check_tag=True)
    except Fail:
        warn("the release commit and tag were created, but the release consistency check failed")
        raise
    ok(f"{'amended' if fix_release else 'committed'} and tagged v{new} (one commit)")
    if a.push:
        step("Push")
        for refs in (["origin", "HEAD"], ["origin", f"v{new}"]):
            p = git("push", *refs)
            if p.returncode != 0:
                raise Fail(f"git push {' '.join(refs)} failed: {(p.stderr or p.stdout).strip()}")
        ok("pushed; the Release workflow will create the GitHub release")
    else:
        info(f"push when ready:  git push origin HEAD && git push origin v{new}")
    return 0


# -- interface ----------------------------------------------------------------------------------------------------
def tui_run(title, fn, *args) -> int:
    LINES.clear()
    try:
        rc = fn(*args)
    except Fail as e:
        details = str(e).splitlines() or [""]
        try:
            details.append(f"Error log: {record_error(title, str(e))}")
        except OSError as log_error:
            details.append(f"Could not save error log: {log_error}")
        LINES.append(f"  {paint(G['err'], 'err')}  {details[0]}")
        LINES.extend(f"     {line}" for line in details[1:])
        rc = 1
    except Exception as e:  # noqa: BLE001
        details = str(e).splitlines() or [""]
        try:
            details.append(f"Error log: {record_error(title, f'unexpected error: {e}')}")
        except OSError as log_error:
            details.append(f"Could not save error log: {log_error}")
        LINES.append(f"  {paint(G['err'], 'err')}  unexpected error: {details[0]}")
        LINES.extend(f"     {line}" for line in details[1:])
        rc = 1
    ui.view_text(TERM, title + ("" if rc == 0 else "  (failed)"), LINES[:] or ["  (done)"])
    return rc


def status_lines():
    return [f"  {paint('Project'.ljust(10), 'muted')} {project_name()}  v{get_version()}",
            f"  {paint('Git'.ljust(10), 'muted')} " + (
                f"{git('rev-parse', '--abbrev-ref', 'HEAD').stdout.strip()}, {len(dirty())} change(s)" if is_repo()
                else "not a repository"),
            f"  {paint('Artifacts'.ljust(10), 'muted')} {len(artifacts())}"]


def tui() -> int:
    global TERM
    if ui is None:
        print("The interface needs gstui.py next to this script or in the gscripts library. Use --help for the "
              "command line.", file=sys.stderr)
        return 1
    items = ["Status", "Check project", "Run tests", "Build and verify", "List artifact contents", "Bump version",
             "Release (guided)", "Publish local tag", "Doctor", "Clean", "View log", "Exit"]
    sel = 0
    with ui.Term() as term:
        TERM = term
        while True:
            sel = ui.menu(term, f"{project_name()} release manager", items, version=VERSION, status=status_lines,
                          selected=sel)
            if sel == 0:
                tui_run("Status", cmd_status)
            elif sel == 1:
                tui_run("Check", cmd_check)
            elif sel == 2:
                tui_run("Tests", cmd_test)
            elif sel == 3:
                tui_run("Build", cmd_build)
            elif sel == 4:
                tui_run("Artifacts", cmd_contents)
            elif sel == 5:
                v = ui.prompt(term, f"New version, or patch/minor/major (now {get_version()})", "patch")
                if v:
                    tui_run("Bump", cmd_bump, argparse.Namespace(version=v, changelog=True))
            elif sel == 6:
                _tui_release(term)
            elif sel == 7:
                tui_run("Publish", cmd_publish, argparse.Namespace(yes=False))
            elif sel == 8:
                tui_run("Doctor", cmd_doctor)
            elif sel == 9:
                tui_run("Clean", cmd_clean)
            elif sel == 10:
                tui_run("Log", cmd_logs)
            else:
                return 0


def _tui_release(term):
    b = ui.menu(term, "Version bump", ["patch", "minor", "major", "fix current version", "Custom version", "Back"],
                 version=VERSION)
    if b == 5:
        return
    bump = ["patch", "minor", "major", "fix"][b] if b < 4 else (ui.prompt(term, "Version (e.g. 1.2.3)") or "")
    if not bump:
        return
    new = next_version(bump)
    amending = new == get_version() and bool(git("tag", "--list", f"v{new}").stdout.strip())
    if amending:
        t = ui.menu(term, "Target", [
            "Amend and retag locally",
            "Amend, retag and push (Trusted Publishing)",
            "Build rehearsal (no commit or publish)",
            "Back",
        ], version=VERSION)
        if t == 3:
            return
        test, push = t == 2, t == 1
    else:
        t = ui.menu(term, "Target", [
            "Commit and tag locally",
            "Commit, tag, and push (Trusted Publishing)",
            "Build rehearsal (no commit or publish)",
            "Back",
        ], version=VERSION)
        if t == 3:
            return
        test, push = t == 2, t == 1
    a = argparse.Namespace(bump=bump, test=test, push=push, version_files_only=False,
                           skip_tests=False, dry=False, yes=False, message=None, message_file=None)
    tui_run("Release", cmd_release, a)


# -- command line ------------------------------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="pypimgr", description="Build, verify and release a Python package.",
                                 epilog=f"Files: cache {CACHE} | logs {LOGFILE} | settings {ENVFILE}")
    ap.add_argument("-V", "--version", action="version", version=f"pypimgr {VERSION}")
    ap.add_argument("-y", "--yes", action="store_true", help="answer yes to confirmations")
    ap.add_argument("-C", "--project", help="project directory (default: nearest folder with pyproject.toml)")
    ap.add_argument("--no-color", action="store_true")
    sub = ap.add_subparsers(dest="cmd", metavar="action")
    sub.add_parser("status", help="project, version, git and PyPI status")
    sub.add_parser("check", help="verify files, version, git and local settings policy")
    sub.add_parser("test", help="ruff and pytest")
    sub.add_parser("build", help="build from a clean staging copy and verify")
    sub.add_parser("verify", help="inspect built artifacts for secrets and junk")
    sub.add_parser("contents", help="list files inside the built artifacts")
    p = sub.add_parser("bump", help="change the version (and stamp the changelog)")
    p.add_argument("version", help="patch, minor, major, fix, or an explicit version")
    p.add_argument("--no-changelog", dest="changelog", action="store_false")
    p = sub.add_parser("release", help="bump, test, build, commit once, and tag",
                       description="Single-commit release: the version bump and your pending changes go into one "
                                   "commit (default message: 'Release vX.Y.Z'). Push the tag to publish through "
                                   "GitHub Actions Trusted Publishing.")
    p.add_argument("bump", nargs="?", default="patch", help="patch (default), minor, major, fix or X.Y.Z")
    p.add_argument("--test", action="store_true", help="build and verify only; do not commit, tag or publish")
    p.add_argument("--push", action="store_true",
                   help="push the commit and tag to origin (triggers GitHub Actions Trusted Publishing)")
    p.add_argument("--version-files-only", action="store_true",
                   help="commit only the version files and changelog, not other pending changes")
    p.add_argument("-m", "--message", help="custom release commit or amend message")
    p.add_argument("--message-file", type=Path,
                   help="read the release commit or amend message from a file (for example commit.txt)")
    p.add_argument("--skip-tests", action="store_true")
    p.add_argument("--dry", action="store_true", help="check and test only; change nothing")
    p = sub.add_parser("notes", help="print the changelog section of a version (used by CI)")
    p.add_argument("version")
    sub.add_parser("publish", help="push the local release tag to start GitHub Actions Trusted Publishing")
    sub.add_parser("clean", help="remove artifacts, the build environment and build/ dist/")
    sub.add_parser("doctor", help="check Python, git, tools and local settings policy")
    sub.add_parser("logs", help="print the log file")
    return ap


ACTIONS = {"status": cmd_status, "check": cmd_check, "test": cmd_test, "build": cmd_build, "verify": cmd_verify,
           "contents": cmd_contents, "bump": cmd_bump, "release": cmd_release, "notes": cmd_notes,
           "publish": cmd_publish,
           "clean": cmd_clean, "doctor": cmd_doctor, "logs": cmd_logs}


def main() -> int:
    global ROOT, CHANGELOG, ENVFILE, CACHE, LOGDIR, LOGFILE, ART, LAST_COMMAND_LOG
    if sys.version_info < (3, 10):  # noqa: UP036
        print("pypimgr requires Python 3.10 or newer.", file=sys.stderr)
        return 2
    if "--no-color" in sys.argv:
        os.environ["NO_COLOR"] = "1"
    a = build_parser().parse_args()
    if a.project:
        ROOT = Path(a.project).resolve()
        CHANGELOG, ENVFILE = ROOT / "CHANGELOG.md", ROOT / ".env.release"
        CACHE, LOGDIR = dirs()
        LOGFILE, ART = new_log_path("general", "pypimgr-session"), CACHE / "artifacts"
        LAST_COMMAND_LOG = None
    if a.yes:
        os.environ["PYPIMGR_YES"] = "1"
    if not (ROOT / "pyproject.toml").is_file():
        print(f"pypimgr: no pyproject.toml in {ROOT}. Run it inside a project or pass -C DIR.", file=sys.stderr)
        return 2
    if not IS_WIN and os.geteuid() == 0 and os.environ.get("SUDO_USER"):
        warn("running under sudo is not needed; files in your cache and project may become root-owned")
    if a.cmd is None:
        if not sys.stdout.isatty():
            build_parser().print_help()
            return 0
        return tui()
    log("INFO", "run: " + " ".join(sys.argv[1:]))
    try:
        return int(ACTIONS[a.cmd](a) or 0)
    except Fail as e:
        try:
            error_path = f"\nError log: {record_error(a.cmd, str(e))}"
        except OSError as log_error:
            error_path = f"\nCould not save error log: {log_error}"
        err(f"{e}{error_path}")
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print()
        sys.exit(130)
