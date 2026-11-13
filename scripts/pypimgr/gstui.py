"""gstui - stdlib-only "brushed steel" terminal UI shared by sysmgr and dashmgr.

Mirrors lib/gs-ui.sh: same palette, same keys (arrows move and wrap, left/right page, 1-9 jump,
0/Esc/Backspace back, Ctrl+C cancels), same header. Works on Linux, macOS and Windows 10+.
"""
from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import sys
import time

IS_WIN = os.name == "nt"
COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR") and os.environ.get("TERM", "") != "dumb"
TRUECOLOR = "truecolor" in os.environ.get("COLORTERM", "") or "24bit" in os.environ.get("COLORTERM", "") \
    or IS_WIN or bool(os.environ.get("WT_SESSION"))
UTF = "utf" in (getattr(sys.stdout, "encoding", "") or "").lower() and not os.environ.get("GS_ASCII")

PAL = dict(steel=(141, 153, 174), silver=(229, 233, 240), ice=(92, 225, 255), muted=(107, 118, 137),
           ok=(110, 231, 168), warn=(242, 193, 78), err=(255, 107, 107), vio=(180, 150, 255),
           selbg=(48, 60, 80), panel=(22, 28, 40))
RST = "\x1b[0m" if COLOR else ""
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def _c256(r, g, b):
    return 16 + 36 * ((r * 5 + 127) // 255) + 6 * ((g * 5 + 127) // 255) + ((b * 5 + 127) // 255)


def sgr(fg=None, bg=None, bold=False, dim=False) -> str:
    if not COLOR:
        return ""
    out = []
    if bold:
        out.append("1")
    if dim:
        out.append("2")
    for col, base in ((fg, 38), (bg, 48)):
        if col:
            r, g, b = PAL[col] if isinstance(col, str) else col
            out.append(f"{base};2;{r};{g};{b}" if TRUECOLOR else f"{base};5;{_c256(r, g, b)}")
    return "\x1b[" + ";".join(out) + "m" if out else ""


def paint(text, fg=None, bg=None, bold=False, dim=False) -> str:
    s = sgr(fg, bg, bold, dim)
    return f"{s}{text}{RST}" if s else str(text)


def grad(text: str) -> str:
    if not COLOR or not text:
        return text
    a, b = (200, 208, 222), PAL["ice"]
    n = max(len(text) - 1, 1)
    out = []
    for i, ch in enumerate(text):
        c = tuple(round(a[k] + (b[k] - a[k]) * i / n) for k in range(3))
        out.append(sgr(c) + ch)
    return "".join(out) + RST


G = dict(tl="┏", tr="┓", bl="┗", br="┛", h="━", v="┃", line="─", sel="▌", dot="◆", on="●", off="○", up="↑", dn="↓",
         ent="⏎", ell="…", ok="✔", warn="▲", err="✖", bar="█", barb="░") if UTF else \
    dict(tl="+", tr="+", bl="+", br="+", h="=", v="|", line="-", sel=">", dot="#", on="*", off="o", up="^", dn="v",
         ent="Enter", ell="...", ok="+", warn="!", err="x", bar="#", barb=".")
SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏" if UTF else "|/-\\"


def vlen(s: str) -> int:
    return len(ANSI.sub("", s))


def fit(text, width: int, right=False) -> str:
    """Clip plain text to width (with an ellipsis) and pad it."""
    text = str(text).replace("\n", " ")
    if len(text) > width:
        text = text[: max(width - 1, 0)] + G["ell"] if width > 1 else text[:width]
    return text.rjust(width) if right else text.ljust(width)


def term_size():
    s = shutil.get_terminal_size((100, 30))
    return min(max(s.columns, 60), 200), max(s.lines, 14)


# --------------------------------------------------------------------------------- terminal
class Term:
    """Alternate screen + raw keys. `key()` returns a token: UP DOWN LEFT RIGHT HOME END PGUP PGDN ENTER ESC
    BACKSPACE DEL TAB or the typed character; None on timeout."""

    def __init__(self):
        self.active = False
        self._old = None

    def start(self):
        if IS_WIN:
            try:
                import ctypes
                k = ctypes.windll.kernel32
                for h in (-11, -12):
                    hd = k.GetStdHandle(h)
                    mode = ctypes.c_uint32()
                    if k.GetConsoleMode(hd, ctypes.byref(mode)):
                        k.SetConsoleMode(hd, mode.value | 0x0004)
            except Exception:
                os.system("")
        else:
            import termios
            fd = sys.stdin.fileno()
            self._old = termios.tcgetattr(fd)
            new = termios.tcgetattr(fd)
            new[0] &= ~(termios.ICRNL | termios.IXON | termios.INLCR)
            new[3] &= ~(termios.ICANON | termios.ECHO | termios.ISIG)
            new[6][termios.VMIN] = 1
            new[6][termios.VTIME] = 0
            termios.tcsetattr(fd, termios.TCSADRAIN, new)
        sys.stdout.write("\x1b[?1049h\x1b[?25l\x1b[2J")
        sys.stdout.flush()
        self.active = True

    def stop(self):
        if not self.active:
            return
        sys.stdout.write("\x1b[?25h\x1b[?1049l" + RST)
        sys.stdout.flush()
        if not IS_WIN and self._old is not None:
            import termios
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self._old)
        self.active = False

    def suspend(self):
        self.stop()

    def resume(self):
        self.start()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *a):
        self.stop()

    def key(self, timeout=None):
        if IS_WIN:
            import msvcrt
            end = None if timeout is None else time.time() + timeout
            while not msvcrt.kbhit():
                if end is not None and time.time() >= end:
                    return None
                time.sleep(0.02)
            ch = msvcrt.getwch()
            if ch in ("\x00", "\xe0"):
                return {"H": "UP", "P": "DOWN", "K": "LEFT", "M": "RIGHT", "G": "HOME", "O": "END", "I": "PGUP",
                        "Q": "PGDN", "S": "DEL"}.get(msvcrt.getwch(), "OTHER")
            return {"\r": "ENTER", "\x1b": "ESC", "\x08": "BACKSPACE", "\x03": "ESC", "\t": "TAB"}.get(ch, ch)
        import select
        fd = sys.stdin.fileno()
        r, _, _ = select.select([fd], [], [], timeout)
        if not r:
            return None
        b = os.read(fd, 1)
        if b == b"\x1b":
            r, _, _ = select.select([fd], [], [], 0.04)
            if not r:
                return "ESC"
            rest = os.read(fd, 8)
            seq = rest.decode("ascii", "ignore")
            table = {"[A": "UP", "[B": "DOWN", "[C": "RIGHT", "[D": "LEFT", "[H": "HOME", "[F": "END", "OA": "UP",
                     "OB": "DOWN", "OC": "RIGHT", "OD": "LEFT", "[5~": "PGUP", "[6~": "PGDN", "[1~": "HOME",
                     "[4~": "END", "[3~": "DEL", "[7~": "HOME", "[8~": "END", "[Z": "TAB"}
            return table.get(seq, "OTHER")
        if b in (b"\r", b"\n"):
            return "ENTER"
        if b in (b"\x7f", b"\x08"):
            return "BACKSPACE"
        if b == b"\x03":
            return "ESC"
        if b == b"\t":
            return "TAB"
        if b[0] >= 0x80:       # utf-8 multibyte
            need = 1 if b[0] < 0xE0 else 2 if b[0] < 0xF0 else 3
            b += os.read(fd, need)
            return b.decode("utf-8", "ignore") or "OTHER"
        return b.decode("ascii", "ignore")

    def draw(self, lines):
        _, h = term_size()
        sys.stdout.write("\x1b[H" + "\x1b[K\n".join(lines[:h]) + "\x1b[K\x1b[J")
        sys.stdout.flush()


# --------------------------------------------------------------------------------- widgets
def header(title: str, sub: str = "", version: str = "") -> list[str]:
    w, _ = term_size()
    inner = w - 4
    left = f" {G['dot']}  {title}"
    right = (f"{sub}  " if sub else "") + (f"v{version} " if version else "")
    pad = max(inner - 2 - len(left) - len(right), 1)
    return [
        "  " + grad(G["tl"] + G["h"] * (inner - 2) + G["tr"]),
        "  " + paint(G["v"], "steel") + paint(left, "silver", bold=True) + " " * pad + paint(right, "muted")
        + paint(G["v"], "steel"),
        "  " + grad(G["bl"] + G["h"] * (inner - 2) + G["br"]),
    ]


def hints(pairs) -> str:
    return "  " + paint("   ".join(f"{k} {v}" for k, v in pairs), "muted")


def bar(frac: float, width: int = 20) -> str:
    frac = min(max(frac, 0.0), 1.0)
    n = round(frac * width)
    col = "ok" if frac < 0.6 else "warn" if frac < 0.85 else "err"
    return paint(G["bar"] * n, col) + paint(G["barb"] * (width - n), "muted")


def hbytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return str(n)


def hdur(sec: float) -> str:
    sec = int(sec)
    d, r = divmod(sec, 86400)
    h, r = divmod(r, 3600)
    m, sc = divmod(r, 60)
    if d:
        return f"{d}d {h}h"
    if h:
        return f"{h}h {m}m"
    return f"{m}m {sc}s" if m else f"{sc}s"


def menu(term: Term, title: str, items: list[str], sub: str = "", version: str = "", status=None,
         selected: int = 0) -> int:
    """Numbered menu. The last item is key 0 (back). Returns the chosen index (last = back)."""
    per = 9
    n = len(items)
    pn = n - 1
    pages = max((pn + per - 1) // per, 1)
    sel = min(selected, n - 1)
    page = sel // per if sel < pn else 0
    while True:
        lines = header(title, sub, version) + [""]
        if status:
            lines += list(status() if callable(status) else status) + [""]
        st = page * per
        for slot in range(min(per, pn)):
            j = st + slot
            if j < pn:
                lines.append(_row(items[j], str(slot + 1), j == sel))
            else:
                lines.append("")
        if pages > 1:
            lines.append(paint(f"     page {page + 1}/{pages}", "muted"))
        lines.append("")
        lines.append(_row(items[-1], "0", sel == n - 1))
        lines += ["", hints([(G["up"] + G["dn"], "move"), (G["ent"], "select"), ("1-9", "jump")]
                            + ([("</>", "page")] if pages > 1 else []) + [("esc", "back")])]
        term.draw(lines)
        k = term.key(2.0 if status else None)
        if k is None:
            continue
        if k == "UP":
            sel = (sel - 1) % n
        elif k == "DOWN":
            sel = (sel + 1) % n
        elif k in ("LEFT", "PGUP", "-") and pages > 1:
            page = (page - 1) % pages
            sel = page * per
        elif k in ("RIGHT", "PGDN", "+", "=") and pages > 1:
            page = (page + 1) % pages
            sel = page * per
        elif k == "HOME":
            sel, page = 0, 0
        elif k == "END":
            sel = n - 1
        elif k == "ENTER":
            return sel
        elif k in ("ESC", "BACKSPACE", "q", "Q", "0"):
            return n - 1
        elif k.isdigit() and k != "0" and st + int(k) - 1 < pn:
            return st + int(k) - 1
        if sel < pn:
            page = sel // per


def _row(text, num, selected):
    w, _ = term_size()
    t = fit(text, w - 14)
    if selected:
        return "  " + sgr(bg="selbg") + paint(G["sel"], "ice") + sgr(bg="selbg", bold=True) + " " + \
            paint(f"[{num}]", "ice", bg="selbg") + paint("  " + t + " ", "silver", bg="selbg", bold=True)
    return "    " + paint(f"[{num}]", "ice") + "  " + t


def message(term: Term, title: str, lines: list[str], kind: str = "info", wait: bool = True):
    col = {"ok": "ok", "warn": "warn", "err": "err"}.get(kind, "ice")
    glyph = {"ok": G["ok"], "warn": G["warn"], "err": G["err"]}.get(kind, G["on"])
    out = header(title) + [""]
    out += [("  " + paint(glyph, col) + "  " + ln) for ln in lines]
    out += ["", hints([("any key", "continue")])]
    term.draw(out)
    if wait:
        while term.key(1.0) is None:
            pass


def confirm(term: Term, question: str, detail=()) -> bool:
    out = header("Confirm") + ["", "  " + paint("?", "warn") + "  " + paint(question, "silver", bold=True)]
    out += ["     " + paint(d, "muted") for d in detail]
    out += ["", hints([("y", "yes"), ("n / esc", "no")])]
    term.draw(out)
    while True:
        k = term.key(1.0)
        if k in ("y", "Y"):
            return True
        if k in ("n", "N", "ESC", "ENTER", "BACKSPACE"):
            return False


def prompt(term: Term, label: str, default: str = "", hint: str = "", validate=None, secret=False):
    """Single-line input. Returns the text, or None if cancelled with Esc."""
    buf = list(default)
    error = ""
    while True:
        shown = ("*" * len(buf)) if secret else "".join(buf)
        out = header("Input") + ["", "  " + paint(label, "silver", bold=True)]
        if hint:
            out.append("  " + paint(hint, "muted"))
        out += ["", "  " + paint(G["sel"], "ice") + " " + shown + paint("_", "ice")]
        if error:
            out += ["", "  " + paint(error, "err")]
        out += ["", hints([(G["ent"], "accept"), ("esc", "cancel")])]
        term.draw(out)
        k = term.key(1.0)
        if k is None:
            continue
        if k == "ESC":
            return None
        if k == "ENTER":
            val = "".join(buf).strip() or default
            if validate:
                msg = validate(val)
                if msg:
                    error = msg
                    continue
            return val
        if k == "BACKSPACE":
            if buf:
                buf.pop()
        elif len(k) == 1 and k.isprintable():
            buf.append(k)
            error = ""


def view_text(term: Term, title: str, lines: list[str], refresh=None):
    """Scrollable viewer. `refresh()` may return new lines (r key)."""
    top = None
    while True:
        w, h = term_size()
        body_h = h - 7
        if top is None:
            top = max(len(lines) - body_h, 0)
        top = min(max(top, 0), max(len(lines) - body_h, 0))
        out = header(title) + [""]
        for ln in lines[top:top + body_h]:
            out.append("  " + (ln if vlen(ln) <= w - 4 else ANSI.sub("", ln)[: w - 4]))
        out += [""] * max(body_h - len(lines[top:top + body_h]), 0)
        out.append(hints([(G["up"] + G["dn"], "scroll"), ("pgup/pgdn", "page"), ("g/G", "top/end")]
                         + ([("r", "reload")] if refresh else []) + [("esc", "back")]))
        term.draw(out)
        k = term.key(None)
        if k in ("ESC", "BACKSPACE", "q", "Q", "0"):
            return
        if k == "UP":
            top -= 1
        elif k == "DOWN":
            top += 1
        elif k == "PGUP":
            top -= body_h
        elif k == "PGDN":
            top += body_h
        elif k in ("HOME", "g"):
            top = 0
        elif k in ("END", "G"):
            top = len(lines)
        elif k in ("r", "R") and refresh:
            lines = refresh()
            top = None


# --------------------------------------------------------------------------------- operations
def is_admin() -> bool:
    if IS_WIN:
        try:
            import ctypes
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
    return os.geteuid() == 0


def real_user() -> str:
    if not IS_WIN and os.geteuid() == 0 and os.environ.get("SUDO_USER") not in (None, "", "root"):
        return os.environ["SUDO_USER"]
    import getpass
    return getpass.getuser()


def ensure_sudo(term: Term | None = None) -> bool:
    """Make sure privileged commands will not prompt halfway. Asks for the password on the real terminal."""
    if IS_WIN or is_admin():
        return True
    if not shutil.which("sudo"):
        return False
    if subprocess.run(["sudo", "-n", "true"], stderr=subprocess.DEVNULL).returncode == 0:
        return True
    if term:
        term.suspend()
    print(paint("\n  Administrator rights needed - enter your password.", "warn"))
    rc = subprocess.run(["sudo", "-v"]).returncode
    if term:
        term.resume()
    return rc == 0


def priv(argv: list[str]) -> list[str]:
    return argv if (IS_WIN or is_admin()) else ["sudo", *argv]


def relaunch_as_admin(argv: list[str]) -> None:
    """Re-run the current program elevated (sudo / UAC) and exit with its status."""
    if IS_WIN:
        import ctypes
        params = " ".join('"%s"' % a for a in argv[1:])
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, '"%s" %s' % (argv[0], params), None, 1)
        sys.exit(0)
    if not shutil.which("sudo"):
        print("This action needs administrator rights and sudo is not installed; re-run as root.", file=sys.stderr)
        sys.exit(1)
    os.execvp("sudo", ["sudo", sys.executable, *argv])


def run(cmd, timeout=None, input_=None) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, input=input_)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except FileNotFoundError:
        return 127, f"{cmd[0]}: not found"
    except subprocess.TimeoutExpired:
        return 124, "timed out"


def run_task(term: Term, label: str, cmd, log: str | None = None, cwd=None) -> tuple[int, str]:
    """Run a command with a spinner; Esc / Ctrl+C cancels it (the whole process group is terminated).
    Returns (returncode, tail of output); returncode 130 means cancelled."""
    out = open(log, "ab") if log else subprocess.DEVNULL
    kw = {"start_new_session": True} if not IS_WIN else {"creationflags": 0x00000200}
    p = subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, cwd=cwd, **kw)
    t0, i = time.time(), 0
    while p.poll() is None:
        term.draw(header("Working") + ["", "  " + paint(SPIN[i % len(SPIN)], "ice") + "  " + label
                                       + paint(f"  ({int(time.time() - t0)}s)", "muted"),
                                       "", hints([("esc", "cancel")])])
        i += 1
        if term.key(0.12) == "ESC":
            try:
                if IS_WIN:
                    subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
                else:
                    os.killpg(p.pid, signal.SIGTERM)
                    try:
                        p.wait(3)
                    except subprocess.TimeoutExpired:
                        os.killpg(p.pid, signal.SIGKILL)
            except Exception:
                pass
            p.wait()
            if log:
                out.close()
            return 130, "cancelled"
    tail = ""
    if log:
        out.close()
        try:
            with open(log, "rb") as f:
                f.seek(0, 2)
                f.seek(max(f.tell() - 1500, 0))
                tail = f.read().decode("utf-8", "replace")
        except OSError:
            pass
    return p.returncode, tail


def find_lib_dir() -> str:
    here = os.path.dirname(os.path.realpath(__file__))
    return here
