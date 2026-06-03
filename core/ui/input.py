import sys
import tty
import termios


def get_key() -> str:
    """Read a single keypress and return a normalised key name."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)

        if ch == "\x1b":
            ch2 = sys.stdin.read(1)
            if ch2 == "[":
                ch3 = sys.stdin.read(1)
                return {
                    "A": "UP",
                    "B": "DOWN",
                    "C": "RIGHT",
                    "D": "BACK",
                }.get(ch3, "UNKNOWN")
            return "ESC"

        if ch in ("\r", "\n"):
            return "ENTER"
        if ch in ("\x7f", "\x08"):   # backspace / delete
            return "BACK"
        if ch == "\x03":   # Ctrl-C
            return "QUIT"
        if ch == "q":
            return "QUIT"
        if ch == "k":
            return "UP"
        if ch == "j":
            return "DOWN"

        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
