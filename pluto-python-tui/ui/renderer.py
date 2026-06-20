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


def _color_mode() -> str:
    """Detect the richest color mode the terminal can safely handle.

    Returns "truecolor" (24-bit), "256" (xterm-256), or "none".

    Rule of thumb: only local dev is assumed colorful; production only emits
    color when the terminal explicitly advertises support, otherwise none.

    The floor is deliberately "none" (monochrome), never basic ANSI: a
    primitive console such as the Wii framebuffer (TERM=linux) renders raw
    color escapes as garbage, so in production we only emit color when the
    terminal explicitly advertises it. truecolor needs COLORTERM; 256-color
    needs a 256color TERM (Terminal.app, iTerm, modern SSH clients). Anything
    that does not clearly say so falls back to the original no-color behavior.

    The dev entrypoint sets CPC_DEV=1 to force full color on the developer's
    trusted terminal regardless of how it advertises itself — best available
    (truecolor where COLORTERM says so, otherwise 256).
    """
    import os
    if os.environ.get("NO_COLOR") is not None:
        return "none"
    ct = os.environ.get("COLORTERM", "").lower()
    if ct in ("truecolor", "24bit"):
        return "truecolor"
    if os.environ.get("CPC_DEV") is not None:
        return "256"
    term = os.environ.get("TERM", "")
    if "256color" in term:
        return "256"
    return "none"


def _rgb_to_256(r: int, g: int, b: int) -> int:
    """Map an 8-bit-per-channel RGB color to the nearest xterm-256 index."""
    # Grayscale ramp gives a closer match for near-neutral colors.
    if abs(r - g) < 10 and abs(g - b) < 10:
        if r < 8:
            return 16
        if r > 248:
            return 231
        return 232 + round((r - 8) / 247 * 23)
    ri = round(r / 255 * 5)
    gi = round(g / 255 * 5)
    bi = round(b / 255 * 5)
    return 16 + 36 * ri + 6 * gi + bi


def hex_fg(hex_color: str) -> str:
    mode = _color_mode()
    if mode == "none":
        return ""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    if mode == "truecolor":
        return f"\033[38;2;{r};{g};{b}m"
    if mode == "256":
        return f"\033[38;5;{_rgb_to_256(r, g, b)}m"
    return f"\033[{_rgb_to_16(r, g, b)}m"


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
    """Overwrite every line in place — no clear, no ghosting.

    Pads each line to the full terminal width and joins with newlines, accumulated
    into one string so a line-buffered TTY does not flush mid-frame and flicker.
    Note: padding to the full width touches the last column, which on the Wii's
    framebuffer console nudges the prompt a single char right via the magic-margin
    quirk — a cosmetic artifact we accept; it reads as intentional and is stable.
    """
    lines = "\n".join(out).splitlines()
    parts = [HIDE_CUR, HOME]
    for i in range(term_height):
        last = (i == term_height - 1)
        if i < len(lines):
            visible = re.sub(r'\x1b\[[0-9;]*m', '', lines[i])
            if last:
                parts.append(lines[i] + "\033[K")
            else:
                pad = max(0, term_width - len(visible))
                parts.append(lines[i] + " " * pad)
        else:
            parts.append("\033[K" if last else " " * term_width)
        if not last:
            parts.append("\n")
    sys.stdout.write("".join(parts))
    sys.stdout.flush()


def _center(line: str, width: int) -> str:
    visible = re.sub(r'\x1b\[[0-9;]*m', '', line)
    pad = max(0, (width - len(visible)) // 2)
    return " " * pad + line


def _fit_visible(s: str, width: int) -> str:
    """Truncate a plain (un-colored) string to at most `width` columns."""
    if width <= 0:
        return ""
    return s if len(s) <= width else s[:width - 1] + ">"


# ── Shared chat line builders ────────────────────────────────────────────────
# render_chat and update_chat_input MUST emit byte-identical bottom rows, and no
# line may exceed term_width or the terminal wraps it, scrolls, and desyncs the
# absolute-positioned updates (the duplicate-line bug). Both go through these.

def _chat_sep_line(secondary: str, term_width: int) -> str:
    return f"  {secondary}{'-' * min(max(0, term_width - 4), 60)}{RESET}"


def _chat_draft_line(draft: str, primary: str, secondary: str, term_width: int) -> str:
    # Visible chrome: "  > " (4) + cursor "_" (1), plus 1 column of safety margin.
    avail = max(1, term_width - 6)
    shown = draft if len(draft) <= avail else "<" + draft[-(avail - 1):]
    return f"  {primary}>{RESET} {shown}{secondary}_{RESET}"


def _chat_hint_line(status: str, secondary: str, term_width: int) -> str:
    """Controls / status line — left-aligned to sit under the header at the top."""
    if status:
        txt = _fit_visible(status, term_width - 2)
    else:
        # Progressively shorter hints; pick the longest that fits the width.
        for cand in (
            "ESC exit  Enter send  Ctrl+R refresh  Ctrl+C interrupt",
            "ESC exit  Enter send  Ctrl+R refresh",
            "ESC exit  Enter send",
            "ESC exit",
        ):
            if len(cand) <= term_width - 2:
                txt = cand
                break
        else:
            txt = _fit_visible("ESC exit", term_width - 2)
    return f"  {secondary}{txt}{RESET}"


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
        out.append(_center(f"{primary}{'-' * len(header)}{RESET}", term_width))

    _title_cache[key] = out
    return out


_CENSOR_REACTIONS = [
    "CENSORED",
    "UNACCEPTABLE",
    "NOT TODAY",
    "MUSICAL CRIMES",
    "TOO LOUD",
    "NOPE",
    "SIR THIS IS A WII",
    "MY EARS",
    "BEEEEEP",
    "CRITIC MODE",
]


def render_censor(config: dict, reaction: str, listening: bool):
    """Render the Bongo Censor view."""
    primary     = hex_fg(config["UI_PRIMARY_COLOR"])
    secondary   = hex_fg(config["UI_SECONDARY_COLOR"])
    term        = shutil.get_terminal_size(fallback=(80, 24))
    term_width  = term.columns
    term_height = term.lines
    f_header, f_console = _pick_fonts(term_width, config["MANUFACTURER"], config["NODE_NAME"])

    out = [""]
    out += _render_title(config, primary, secondary, term_width, f_header, f_console)
    out.append("")

    if reaction:
        f = _pick_fonts(term_width, "", reaction)[1] or "small"
        for line in _figlet(reaction, f):
            out.append(_center(f"{primary}{BOLD}{line}{RESET}", term_width))
    else:
        out.append("")
        out.append(_center(f"{secondary}. . . listening . . .{RESET}", term_width))

    out.append("")
    if listening:
        hint = "LIVE  |  q / ESC  exit"
    else:
        hint = "no mic  |  SPACE test beep  |  q / ESC  exit"
    out.append(_center(f"{secondary}{hint}{RESET}", term_width))

    _flush(out, term_width, term_height)


def render_controller(config: dict, device_name: str, events: list):
    """Render the controller button intercept view.
    events: list of (btn_name, code, pressed) tuples, newest last.
    """
    primary     = hex_fg(config["UI_PRIMARY_COLOR"])
    secondary   = hex_fg(config["UI_SECONDARY_COLOR"])
    term        = shutil.get_terminal_size(fallback=(80, 24))
    term_width  = term.columns
    term_height = term.lines
    f_header, f_console = _pick_fonts(term_width, config["MANUFACTURER"], config["NODE_NAME"])

    out = [""]
    out += _render_title(config, primary, secondary, term_width, f_header, f_console)
    out.append("")
    out.append(_center(f"{secondary}{device_name}{RESET}", term_width))
    out.append(_center(f"{secondary}{'-' * len(device_name)}{RESET}", term_width))
    out.append("")

    # fill remaining lines with the event log, newest at bottom
    chrome   = len(out) + 2   # reserve hint + trailing blank
    max_evts = max(1, term_height - chrome)
    for name, code, pressed in events[-max_evts:]:
        arrow = f"{primary}v{RESET}" if pressed else f"{secondary}^{RESET}"
        out.append(_center(
            f"  {arrow}  {primary}{name:<24}{RESET}  {secondary}{code}{RESET}",
            term_width,
        ))

    out.append("")
    out.append(_center(f"{secondary}q / ESC  exit{RESET}", term_width))

    _flush(out, term_width, term_height)


def render_bridge(config: dict, title: str, lines: list):
    """Render a live device-bridge view (generic across bridges).
    title: e.g. "Dreame L40 -> Wii".  lines: status strings, newest last."""
    primary     = hex_fg(config["UI_PRIMARY_COLOR"])
    secondary   = hex_fg(config["UI_SECONDARY_COLOR"])
    term        = shutil.get_terminal_size(fallback=(80, 24))
    term_width  = term.columns
    term_height = term.lines
    f_header, f_console = _pick_fonts(term_width, config["MANUFACTURER"], config["NODE_NAME"])

    out = [""]
    out += _render_title(config, primary, secondary, term_width, f_header, f_console)
    out.append("")
    out.append(_center(f"{secondary}{title}{RESET}", term_width))
    out.append("")

    chrome   = len(out) + 2   # reserve hint + trailing blank
    max_rows = max(1, term_height - chrome)
    for ln in lines[-max_rows:]:
        out.append(_center(f"{primary}{ln}{RESET}", term_width))

    out.append("")
    out.append(_center(f"{secondary}q / ESC  stop{RESET}", term_width))

    _flush(out, term_width, term_height)


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

    hint = "UP/DOWN navigate   Enter select   Q quit"
    out.append("")
    out.append(_center(f"{secondary}{hint}{RESET}", term_width))

    _flush(out, term_width, term_height)


def render_chat(config: dict, messages: list, draft: str, status: str = ""):
    """Render the full-screen group chat view.

    Intentionally skips the figlet title — this runs in a tight input loop
    and the full title block causes visible flicker on every keystroke.
    """
    primary     = hex_fg(config["UI_PRIMARY_COLOR"])
    secondary   = hex_fg(config["UI_SECONDARY_COLOR"])
    term        = shutil.get_terminal_size(fallback=(80, 24))
    term_width  = term.columns
    term_height = term.lines

    node    = config.get("NODE_NAME", "").lower()
    channel = "#consoles-chatting-consoles"

    # Layout (top to bottom): header, controls, divider, [msg_area], separator, draft.
    # The DRAFT is the very last line — keystrokes only ever repaint that one row, so
    # there is nothing below it to desync. msg_area is exact so len(out) == term_height.
    chrome   = 5
    msg_area = max(0, term_height - chrome)
    max_msgs = msg_area // 2

    # Width-safe header: keep node + channel when they fit, else drop channel,
    # else truncate node. A wrapped header at the top would scroll the whole view.
    avail = max(1, term_width - 3)  # 2 leading spaces + 1 safety column
    if len(node) + 2 + len(channel) <= avail:
        header      = f"  {primary}{BOLD}{node}{RESET}  {secondary}{channel}{RESET}"
        header_plain = f"{node}  {channel}"
    elif len(node) <= avail:
        header      = f"  {primary}{BOLD}{node}{RESET}"
        header_plain = node
    else:
        header_plain = _fit_visible(node, avail)
        header      = f"  {primary}{BOLD}{header_plain}{RESET}"
    divider = f"  {secondary}{'-' * min(len(header_plain), term_width - 2)}{RESET}"

    def _msg_lines(m):
        try:
            ts = m["ts"][11:16]
        except Exception:
            ts = "??:??"
        sender = str(m.get("sender", "?")).lower()
        text   = str(m.get("text", ""))
        if len(text) > 300:
            text = text[:297] + "..."
        first = text.splitlines()[0] if text.splitlines() else text
        max_w = max(10, term_width - 6)
        if len(first) > max_w:
            first = first[:max_w - 3] + "..."
        return (
            f"  {secondary}{sender}  {ts}{RESET}",
            f"    {primary}{first}{RESET}",
        )

    # Build message lines and pad at top to fill msg_area exactly.
    shown = messages[-max_msgs:] if max_msgs else []
    msg_lines = []
    for m in shown:
        h, body = _msg_lines(m)
        msg_lines.append(h)
        msg_lines.append(body)
    while len(msg_lines) < msg_area:
        msg_lines.insert(0, "")

    out = [
        header,                                          # row 1
        _chat_hint_line(status, secondary, term_width),  # row 2: controls / status
        divider,                                         # row 3
    ]
    out.extend(msg_lines)                                          # msg_area rows
    out.append(_chat_sep_line(secondary, term_width))             # row term_h - 1
    out.append(_chat_draft_line(draft, primary, secondary, term_width))  # row term_h (LAST)
    # len(out) == 3 + msg_area + 2 == term_height always

    _flush(out, term_width, term_height)


def update_chat_input(config: dict, draft: str, status: str = ""):
    """Repaint ONLY the draft line — the last row of the screen.

    Because the prompt is the final line (controls and status live up top), a
    keystroke never touches anything above it, so there is nothing to desync.
    The draft is width-fitted by _chat_draft_line, so it can never wrap/scroll.
    \033[K erases to EOL instead of space-padding the last column, which would
    otherwise set the terminal wrap-next flag and shift content.
    """
    primary   = hex_fg(config["UI_PRIMARY_COLOR"])
    secondary = hex_fg(config["UI_SECONDARY_COLOR"])
    term      = shutil.get_terminal_size(fallback=(80, 24))
    term_w    = term.columns
    term_h    = term.lines

    draft_line = _chat_draft_line(draft, primary, secondary, term_w)
    sys.stdout.write(f"\033[{term_h};1H{draft_line}\033[K")
    sys.stdout.flush()


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
    out.append(_center(f"{secondary}{'-' * len(title)}{RESET}", term_width))
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
    hint = f"{btn_up}/{btn_down} scroll   {btn_back}  back Q quit"
    out.append("")
    out.append(_center(f"{secondary}{hint}{RESET}", term_width))

    _flush(out, term_width, term_height)
