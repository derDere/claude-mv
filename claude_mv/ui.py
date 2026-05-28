"""Console output: ANSI colors, stage indicator, progress bar."""

import os
import sys


def _enable_vt_on_windows() -> bool:
    if sys.platform != "win32":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except Exception:
        return False


_VT_OK = _enable_vt_on_windows()
_USE_COLOR = sys.stdout.isatty() and _VT_OK and "NO_COLOR" not in os.environ

RESET = "\033[0m" if _USE_COLOR else ""
BOLD = "\033[1m" if _USE_COLOR else ""
DIM = "\033[2m" if _USE_COLOR else ""
RED = "\033[31m" if _USE_COLOR else ""
GREEN = "\033[32m" if _USE_COLOR else ""
YELLOW = "\033[33m" if _USE_COLOR else ""
CYAN = "\033[36m" if _USE_COLOR else ""


def info(msg: str = "") -> None:
    print(msg)


def ok(msg: str) -> None:
    print(f"{GREEN}{msg}{RESET}")


def warn(msg: str) -> None:
    print(f"{YELLOW}WARN:{RESET} {msg}", file=sys.stderr)


def error(msg: str) -> None:
    print(f"{RED}ERROR:{RESET} {msg}", file=sys.stderr)


def dim(msg: str) -> None:
    print(f"{DIM}{msg}{RESET}")


def heading(msg: str) -> None:
    print(f"{BOLD}{msg}{RESET}")


class Stage:
    """Stage indicator: prints `[n/total] label... msg` per phase."""

    def __init__(self, total: int) -> None:
        self.total = total
        self.n = 0
        self._inline = False

    def begin(self, label: str) -> None:
        self.n += 1
        sys.stdout.write(f"{BOLD}[{self.n}/{self.total}]{RESET} {label}... ")
        sys.stdout.flush()
        self._inline = True

    def multiline(self) -> None:
        if self._inline:
            sys.stdout.write("\n")
            sys.stdout.flush()
            self._inline = False

    def end(self, msg: str = "OK", color: str = GREEN) -> None:
        if self._inline:
            sys.stdout.write(f"{color}{msg}{RESET}\n")
        else:
            sys.stdout.write(f"      {DIM}->{RESET} {color}{msg}{RESET}\n")
        sys.stdout.flush()
        self._inline = False

    def skip(self, msg: str) -> None:
        self.end(msg, color=DIM)


class Bar:
    """Progress bar. In TTY: overwrites in place. In non-TTY (pipe/CI): prints
    a new line per 10% so the log stays readable."""

    def __init__(self, total: int, width: int = 40) -> None:
        self.total = max(total, 1)
        self.width = width
        self.n = 0
        self._last_pct = -1
        self._tty = sys.stdout.isatty()

    def tick(self, by: int = 1) -> None:
        self.n += by
        pct = int(self.n * 100 / self.total)
        if pct == self._last_pct and self.n < self.total:
            return
        self._last_pct = pct
        if self._tty:
            filled = int(self.n * self.width / self.total)
            bar = "#" * filled + "-" * (self.width - filled)
            sys.stdout.write(f"\r  [{bar}] {self.n}/{self.total} {pct}%")
            sys.stdout.flush()
        else:
            if pct % 10 == 0 or self.n == self.total:
                sys.stdout.write(f"  {self.n}/{self.total} ({pct}%)\n")
                sys.stdout.flush()

    def close(self) -> None:
        if self._tty:
            sys.stdout.write("\n")
            sys.stdout.flush()
