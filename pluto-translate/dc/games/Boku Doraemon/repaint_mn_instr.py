#!/usr/bin/env python3
"""Repaint the three mini-game `〜そうさ方法〜` tutorial boxes + `残りじかん…秒` timers -> Catalan.

One script for all three (like repaint_mn.py does the counter): each file has its own chunk layout
(index NOT stable, timer sometimes on a different chunk from the box), so CONFIG carries per-file
coordinates. The green board text is erased by refilling each row from a clean margin column (keeps
the vertical gradient); the timer sits on the transparent atlas bg, so it's an alpha-erase. Catalan
is redrawn centred, white + dark outline, with the A/B/Y button keys tinted like the original.

Runs on the ALREADY-counter-painted MN*.PVM (the textures dir) so the counter and these coexist.

    repaint_mn_instr.py <in-dir> <out-dir>     # reads/writes MN1.PVM MN2.PVM MN3.PVM
"""
import sys, os, struct, re
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))  # dc/ codecs
import pvr_codec as pv
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ARIAL = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
W_ = (245, 245, 245)                    # white body text
# button-key tints (pastel, matched to the originals): A pink-red, B periwinkle, Y light-green.
KEYCOLS = {"A": (240, 120, 120), "B": (140, 150, 255), "Y": (150, 235, 150)}
CX = 256                                # board centre x
CLEAN_X = 48                            # text-free green margin column to sample the gradient from

CONFIG = {
    "MN2.PVM": {                        # garden cleaning (草むしり); box + timer both on chunk 3
        "box_chunk": 3, "wipe": (42, 132, 470, 350), "timer_chunk": 3,
        "lines": [
            (157, 30, [("~ Com es juga ~", W_)]),
            (204, 24, [("Prem ", W_), ("A", "A"), (" per agafar l'herba", W_)]),
            (236, 24, [("i mou la creueta de pressa", W_)]),
            (268, 24, [("per arrencar-la", W_)]),
            (300, 24, [("Vigila les rates!", W_)]),
            (332, 24, [("Salta amb ", W_), ("B", "B"), (" per esquivar-les", W_)]),
        ],
        "timer_wipe": (118, 402, 406, 447),
        "timer_label": (229, 424, 26, "Temps"), "timer_unit": (374, 424, 26, "s"),
    },
    "MN1.PVM": {                        # shoulder massage (肩たたき); box on chunk 2, timer on chunk 5
        "box_chunk": 2, "wipe": (42, 246, 470, 462), "timer_chunk": 5,
        "lines": [
            (266, 30, [("~ Com es juga ~", W_)]),
            (314, 24, [("Mira el cursor de la barra", W_)]),
            (346, 24, [("i prem el botó al moment just", W_)]),
            (379, 24, [("per fer un massatge a la mare!!", W_)]),
            (411, 24, [("A", "A"), (" a la zona roja, ", W_), ("B", "B"), (" a la blava", W_)]),
            (443, 24, [("Cal ritme!", W_)]),
        ],
        "timer_wipe": (128, 396, 400, 448),
        "timer_label": (232, 424, 26, "Temps"), "timer_unit": (376, 424, 26, "s"),
        # top-left legend by the timing bar: Ａボタン/Ｂボタン (bold red/blue) -> Botó A / Botó B.
        # These sit on the transparent atlas bg (alpha erase), left-flush like the originals.
        "labels": [
            ((0, 34, 226, 95),  6, 63,  32, [("Botó A", (225, 55, 55))]),
            ((0, 99, 226, 159), 6, 127, 32, [("Botó B", (65, 95, 235))]),
        ],
    },
    "MN3.PVM": {                        # tidying up (おかたづけ); box + timer both on chunk 3
        "box_chunk": 3, "wipe": (42, 124, 470, 372), "timer_chunk": 3,
        "lines": [
            (140, 28, [("~ Com es juga ~", W_)]),
            (171, 22, [("Recorda bé on va tot", W_)]),
            (194, 22, [("i porta-ho al lloc a temps", W_)]),
            (217, 22, [("Amb ", W_), ("A", "A"), (" agafes les coses", W_)]),
            (240, 22, [("i les deixes", W_)]),
            (262, 22, [("Salta amb ", W_), ("B", "B"), (" per", W_)]),
            (285, 22, [("esquivar les rates", W_)]),
            (308, 22, [("Prem ", W_), ("Y", "Y"), (" per acabar", W_)]),
            (329, 22, [("abans, encara que", W_)]),
            (354, 22, [("et sobri temps", W_)]),
        ],
        "timer_wipe": (118, 402, 406, 447),
        "timer_label": (229, 424, 26, "Temps"), "timer_unit": (374, 424, 26, "s"),
    },
}


def sample_green(arr, wipe):
    y0, y1 = wipe[1], wipe[3]
    R, G, B, A = arr[..., 0].astype(int), arr[..., 1].astype(int), arr[..., 2].astype(int), arr[..., 3]
    m = (A > 128) & (G > 120) & (G > R + 30) & (G > B + 30)
    m[:y0] = False
    m[y1:] = False
    px = arr[m][:, :3]
    return tuple(int(c) for c in np.median(px, 0)) if len(px) else (136, 221, 153)


def draw_line(im, cy, size, segments, cx=CX, x_left=None):
    f = ImageFont.truetype(ARIAL, size)
    segs = [(t, KEYCOLS[c] if isinstance(c, str) else c) for t, c in segments]
    widths = [f.getbbox(t)[2] - f.getbbox(t)[0] for t, _ in segs]
    total = sum(widths)
    asc, desc = f.getmetrics()
    th = asc + desc
    tmp = Image.new("RGBA", (total + 12, th + 12), (0, 0, 0, 0))
    td = ImageDraw.Draw(tmp)
    x = 6
    for (t, col), w in zip(segs, widths):
        ox = x - f.getbbox(t)[0]
        for dx in (-2, -1, 0, 1, 2):                 # thick dark outline like the original HUD text
            for dy in (-2, -1, 0, 1, 2):
                if dx or dy:
                    td.text((ox + dx, 6 + dy), t, font=f, fill=(0, 0, 0, 255))
        x += w
    x = 6
    for (t, col), w in zip(segs, widths):
        ox = x - f.getbbox(t)[0]
        td.text((ox, 6), t, font=f, fill=col + (255,))
        x += w
    ox = (x_left - 6) if x_left is not None else (cx - (total + 12) // 2)
    im.alpha_composite(tmp, (ox, cy - (th + 12) // 2))


def chunk_offsets(d):
    return [m.start() for m in re.finditer(b"PVRT", d)]


def build(d, cfg):
    out = bytearray(d)
    offs = chunk_offsets(d)
    ops = {}                                         # chunk index -> set of {'box','timer'}
    ops.setdefault(cfg["box_chunk"], set()).add("box")
    ops.setdefault(cfg["timer_chunk"], set()).add("timer")
    for ci, kinds in ops.items():
        off = offs[ci]
        W, H = struct.unpack_from("<HH", d, off + 12)
        orig = pv.decode_argb4444(bytes(d), off + 16, W, H)
        arr = orig.copy()
        if "box" in kinds:
            x0, y0, x1, y1 = cfg["wipe"]
            for y in range(y0, y1):                  # erase JP board text, per row
                row = arr[y]
                marg = np.concatenate([row[x0:x0 + 24], row[x1 - 24:x1]])   # text-free board margins
                gr = marg[(marg[:, 1].astype(int) > marg[:, 0].astype(int) + 8) & (marg[:, 1] > 60)]
                fill = np.median(gr[:, :3], 0).astype(np.uint8) if len(gr) else row[CLEAN_X, :3]
                arr[y, x0:x1, :3] = fill              # flat board green (gradient is vertical only)
                arr[y, x0:x1, 3] = 255
            for wb, _xl, _cy, _sz, _sg in cfg.get("labels", []):   # legend labels: alpha-erase (transparent bg)
                wx0, wy0, wx1, wy1 = wb
                arr[wy0:wy1, wx0:wx1, 3] = 0
        if "timer" in kinds:
            tx0, ty0, tx1, ty1 = cfg["timer_wipe"]   # timer on transparent bg -> alpha erase
            arr[ty0:ty1, tx0:tx1, 3] = 0
        im = Image.fromarray(arr, "RGBA")
        if "box" in kinds:
            for cy, size, segs in cfg["lines"]:
                draw_line(im, cy, size, segs)
            for _wb, xl, cy, size, segs in cfg.get("labels", []):
                draw_line(im, cy, size, segs, x_left=xl)
        if "timer" in kinds:
            green = sample_green(orig, cfg["timer_wipe"])
            lcx, lcy, lsz, lt = cfg["timer_label"]
            draw_line(im, lcy, lsz, [(lt, green)], cx=lcx)
            ucx, ucy, usz, ut = cfg["timer_unit"]
            draw_line(im, ucy, usz, [(ut, green)], cx=ucx)
        enc = pv.encode_argb4444(np.array(im))
        assert len(enc) == W * H * 2, (len(enc), W * H * 2)
        out[off + 16: off + 16 + len(enc)] = enc
    return bytes(out)


def main():
    src, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    for fn, cfg in CONFIG.items():
        d = open(os.path.join(src, fn), "rb").read()
        patched = build(d, cfg)
        assert len(patched) == len(d), (fn, len(patched), len(d))
        open(os.path.join(out, fn), "wb").write(patched)
        print("  %s: repainted (%d B, same size)" % (fn, len(patched)))


if __name__ == "__main__":
    main()
