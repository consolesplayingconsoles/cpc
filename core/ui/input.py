import os
import tty
import termios


def get_key() -> str:
    """Read a single keypress and return a normalised key name.

    Opens /dev/tty directly so it works even when stdin is redirected
    (e.g. launched via nohup with </dev/null).
    """
    tty_f = open("/dev/tty", "rb", buffering=0)
    fd    = tty_f.fileno()
    old   = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = os.read(fd, 1).decode("latin-1")

        if ch == "\x1b":
            ch2 = os.read(fd, 1).decode("latin-1")
            if ch2 == "[":
                ch3 = os.read(fd, 1).decode("latin-1")
                return {
                    "A": "UP",
                    "B": "DOWN",
                    "C": "RIGHT",
                    "D": "BACK",
                }.get(ch3, "UNKNOWN")
            return "ESC"

        if ch in ("\r", "\n"):
            return "ENTER"
        if ch in ("\x7f", "\x08"):
            return "BACK"
        if ch == "\x03":
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
        tty_f.close()
