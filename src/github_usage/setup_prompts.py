"""Interactive prompt helpers for the setup wizard.

Lifted out of ``setup_wizard`` so the termios raw-mode loop is
reusable and the main wizard file stays focused on orchestration.
"""

from __future__ import annotations

import getpass
import sys


def _prompt_yes_no(message: str, default: bool = False) -> bool:
    suffix = " [Y/n]: " if default else " [y/N]: "
    answer = input(message + suffix).strip().lower()
    if not answer:
        return default
    return answer in {"y", "yes"}


def _prompt_secret(prompt: str) -> str:
    """Prompt for a secret value, echoing * for each character typed.

    Falls back to getpass.getpass on Windows or when stdin is not a TTY.
    The fallback suppresses all echo (no per-character feedback).
    """
    sys.stdout.write(prompt)
    sys.stdout.flush()
    if sys.platform == "win32" or not sys.stdin.isatty():
        return getpass.getpass("")
    try:
        import termios
        import tty
    except ImportError:
        return getpass.getpass("")
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        chars: list[str] = []
        while True:
            ch = sys.stdin.read(1)
            if ch in ("\r", "\n"):
                break
            if ch == "\x03":
                raise KeyboardInterrupt
            if ch in ("\x7f", "\x08"):
                if chars:
                    chars.pop()
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
                continue
            if ch and ord(ch) < 0x20:
                continue
            chars.append(ch)
            sys.stdout.write("*")
            sys.stdout.flush()
        sys.stdout.write(f" ({len(chars)} chars)\n")
        sys.stdout.flush()
        return "".join(chars)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def _prompt_value(label: str, default: str = "", secret: bool = False) -> str:
    if secret:
        value = _prompt_secret(f"{label} (hidden): ")
    else:
        prompt = f"{label} [{default}]: " if default else f"{label}: "
        value = input(prompt).strip()
    if not value and default:
        return default
    return value


def _prompt_int(label: str, default: int) -> int:
    while True:
        raw = input(f"{label} [{default}]: ").strip()
        if not raw:
            return default
        try:
            return int(raw)
        except ValueError:
            print("Enter an integer.")


def _wrap_description(text: str, width: int = 66) -> list[str]:
    """Word-wrap a description string to the given width."""
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        if len(current) + 1 + len(word) <= width:
            current = f"{current} {word}"
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines
