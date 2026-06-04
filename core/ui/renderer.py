import re
import sys
import shutil
import pyfiglet

RESET      = "\033[0m"
HOME       = "\033[H"
BOLD       = "\033[1m"
HIDE_CUR   = "\033[?25l"
SHOW_CUR   = "\033[?25h"
ALT_ENTER  = "\033[?1049h"   # switch to alternate screen buffer
ALT_EXIT   = "\033[?1049l"   # restore original screen buffer

# Font tiers: (min_width, header, console)
_TIERS = [
    (120, "doom",  "roman"),
    ( 60, "small", "small"),
    ( 40, "mini",  "mini"),
    (  0,  None,    None),
]


def hex_fg(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"\033[38;2;{r};{g};{b}m"


_figlet_cache: dict = {}
_title_cache: dict = {}

def _figlet(text: str, font: str) -> list:
    key = (text, font)
    if key not in _figlet_cache:
        raw = pyfiglet.figlet_format(text, font=font, width=10000)
        lines = raw.splitlines()
        while lines and not lines[-1].strip():
            lines.pop()
        _figlet_cache[key] = lines
    return _figlet_cache[key]


def _rendered_width(text: str, font: str) -> int:
    return max((len(l) for l in _figlet(text, font)), default=0)


def _flush(out: list, term_width: int, term_height: int):
    """Overwrite every line in place — no clear, no ghosting."""
    lines = "\n".join(out).splitlines()
    w = sys.stdout
    w.write(HIDE_CUR + HOME)
    for i in range(term_height):
        if i < len(lines):
            visible = re.sub(r'\x1b\[[0-9;]*m', '', lines[i])
            pad = max(0, term_width - len(visible))
            w.write(lines[i] + " " * pad)
        else:
            w.write(" " * term_width)
        if i < term_height - 1:
            w.write("\n")
    w.write(SHOW_CUR)
    w.flush()


def _center(line: str, width: int) -> str:
    visible = re.sub(r'\x1b\[[0-9;]*m', '', line)
    pad = max(0, (width - len(visible)) // 2)
    return " " * pad + line


def _pick_fonts(term_width: int, mfr: str, node: str):
    for min_width, f_header, f_console in _TIERS:
        if term_width < min_width:
            continue
        if f_header is None:
            return None, None
        widest_node = max(_rendered_width(w, f_console) for w in node.split())
        if max(_rendered_width(f"CPC  {mfr}", f_header), widest_node) <= term_width:
            return f_header, f_console
    return None, None


def _render_title(config: dict, primary: str, secondary: str,
                  term_width: int, f_header, f_console) -> list:
    key = (config["MANUFACTURER"], config["NODE_NAME"], primary, secondary, term_width, f_header, f_console)
    if key in _title_cache:
        return _title_cache[key]

    mfr  = config["MANUFACTURER"]
    node = config["NODE_NAME"]
    out  = []

    if f_header:
        for line in _figlet(f"CPC  {mfr}", f_header):
            out.append(_center(f"{secondary}{line}{RESET}", term_width))
        out.append("")
        for word in node.split():
            for line in _figlet(word, f_console):
                out.append(_center(f"{primary}{BOLD}{line}{RESET}", term_width))
    else:
        header = f"CPC {mfr.upper()} {node.upper()}"
        out.append(_center(f"{primary}{BOLD}{header}{RESET}", term_width))
        out.append(_center(f"{primary}{'─' * len(header)}{RESET}", term_width))

    _title_cache[key] = out
    return out


def render_menu(config: dict, items: list, cursor: int):
    """Render the main navigable menu."""
    primary     = hex_fg(config["UI_PRIMARY_COLOR"])
    secondary   = hex_fg(config["UI_SECONDARY_COLOR"])
    term        = shutil.get_terminal_size(fallback=(80, 24))
    term_width  = term.columns
    term_height = term.lines
    f_header, f_console = _pick_fonts(term_width, config["MANUFACTURER"], config["NODE_NAME"])

    out = [""]
    out += _render_title(config, primary, secondary, term_width, f_header, f_console)
    out.append("")

    longest = max(len(i) for i in items)
    pad = " " * max(0, (term_width - longest - 3) // 2)
    for i, item in enumerate(items):
        if i == cursor:
            out.append(f"{pad}{primary}{BOLD}>  {item}{RESET}")
        else:
            out.append(f"{pad}{secondary}   {item}{RESET}")

    btn_up      = config.get("BUTTON_UP",      "UP")
    btn_down    = config.get("BUTTON_DOWN",    "DOWN")
    btn_confirm = config.get("BUTTON_CONFIRM", "enter")
    btn_cancel  = config.get("BUTTON_CANCEL",  "B")
    hint = f"{btn_up}/{btn_down} navigate   {btn_confirm} select   {btn_cancel} quit"
    out.append("")
    out.append(_center(f"{secondary}{hint}{RESET}", term_width))

    _flush(out, term_width, term_height)


def render_list(config: dict, title: str, items: list, cursor: int):
    """Render a list view clamped to the terminal height — no scrolling past the screen."""
    primary     = hex_fg(config["UI_PRIMARY_COLOR"])
    secondary   = hex_fg(config["UI_SECONDARY_COLOR"])
    term        = shutil.get_terminal_size(fallback=(80, 24))
    term_width  = term.columns
    term_height = term.lines
    f_header, f_console = _pick_fonts(term_width, config["MANUFACTURER"], config["NODE_NAME"])

    title_block = _render_title(config, primary, secondary, term_width, f_header, f_console)
    # CLEAR line + top margin + title block + blank + label + divider + blank + hint
    chrome = 1 + 1 + len(title_block) + 1 + 1 + 1 + 1 + 1
    visible = max(1, term_height - chrome)

    offset = max(0, cursor - visible + 1)
    window = items[offset:offset + visible]

    out = [""]
    out += title_block
    out.append("")
    out.append(_center(f"{primary}{BOLD}{title}{RESET}", term_width))
    out.append(_center(f"{secondary}{'─' * len(title)}{RESET}", term_width))
    out.append("")

    longest = max(len(i) for i in items) if items else 0
    pad = " " * max(0, (term_width - longest - 3) // 2)
    for i, item in enumerate(window):
        abs_i = i + offset
        if abs_i == cursor:
            out.append(f"{pad}{primary}{BOLD}>  {item}{RESET}")
        else:
            out.append(f"{pad}{secondary}   {item}{RESET}")

    btn_up   = config.get("BUTTON_UP",   "UP")
    btn_down = config.get("BUTTON_DOWN", "DOWN")
    btn_back = config.get("BUTTON_BACK", "<")
    hint = f"{btn_up}/{btn_down} scroll   {btn_back} back"
    out.append("")
    out.append(_center(f"{secondary}{hint}{RESET}", term_width))

    _flush(out, term_width, term_height)
