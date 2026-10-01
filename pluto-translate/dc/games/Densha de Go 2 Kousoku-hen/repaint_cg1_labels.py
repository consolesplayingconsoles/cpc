#!/usr/bin/env python3
"""Repaint CG1 labels (CG1.ROM VQ textures) with Zoinkity and mikeryan's Densha de Go! 64 English: the route and train banners
(OBJtopl*, OBJtopr*), the brake legend (OBJtop10), the controls labels (OBJcon20, OBJcon21) and the staff roll
(OBJstaff*, OBJmoginoya) and the departure board header (OBJstart16).

    repaint_cg1_labels.py <SPRITE.LST> <TBL.ROM> <CG1.ROM> <out TBL.ROM> <out CG1.ROM> [preview-dir]

A PORT (CLAUDE.md section 11): every role and label is Zoinkity and mikeryan's, from the DDG64 texture with the same Japanese
(number in the comment). Names are transcription, not translation (operator, 2026-09-30): the DDG64 romanisations,
and cpc's where the DDG64 roll has no entry or reads differently (marked). The logos stay.

Same method as repaint_cg1_plates.py: paint in RGB, re-tile into the slots only these records use, and re-fit only
the codebook entries nothing else uses, so every other sprite decodes exactly as before.
"""
import os, struct, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image
import ddg_assets as A
from dc import pvr_codec as P
import repaint_cg2 as R
from repaint_cg1_plates import vq_read, vq_write, tile_px, quads, q_rgb, fit_codes, lum

WHITE = (248, 248, 248)
DOT = " · "

ROUTES = {"OBJtopl01": "Tazawako",            # 田沢湖線 717
          "OBJtopl02": "Tokaido Main",        # 東海道本線 718
          "OBJtopl03": "Keihin-Tohoku",       # 京浜東北線 719
          "OBJtopl04": "Hokuhoku",            # ほくほく線 720
          "OBJtopl05": "Ouu Main",            # 奥羽本線 721
          "OBJtopl06": "Akita Shinkansen",    # 秋田新幹線 722
          "OBJtopl07": "Yamanote"}            # 山手線 723
TRAINS = {"OBJtopr01": "209 Series",          # 724
          "OBJtopr02": "681 Series",          # 725
          "OBJtopr03": "201 Series",          # 726
          "OBJtopr04": "205 Series",          # 727
          "OBJtopr05": "485 Series",          # 728
          "OBJtopr05b": "485 S. West",        # 485系W 729
          "OBJtopr05c": "485 S. East",        # 485系E 730
          "OBJtopr06": "E3 Series",           # 731
          "OBJtopr07": "221 Series",          # 732
          "OBJtopr08": "207 Series",          # 733
          "OBJtopr09": "701 Series",          # 734
          "OBJtopr10": "HK-100 Model",        # HK-100形 735 (DDG64 型: near match greenlit by the operator)
          "OBJtopr11": "223 Series"}          # 736

# person records (352x48): (surname, given name, roles). DDG64 1159-1186; roles with the DDG64 line breaks.
PEOPLE = {
    "OBJstaff01": ("SAITOU", "Akira", "Project Leader\nPlanning\nCharacter Design"),                 # 1159
    "OBJstaff02": ("MORIYAMA", "Yoshihiro", "Map Layout" + DOT + "Editing\nMap Design" + DOT + "Planning"),   # 1160
    "OBJstaff03": ("ISHII", "Hideki", "Models & Textures\nCharacter Coordinator\nEditing Coordinator"),       # 1161
    "OBJstaff04": ("KINOSHITA", "Masaya", "ape High-Speed Rendering\nMap Rendering Engine"),   # 1162; the red cross stays on the a
    "OBJstaff05": ("KIKUCHI", "Masayuki", "Driving Behavior" + DOT + "Director\nAdvertising & Marketing\nSoftware"),  # 1163; ソフト: DDG64 "Sound", "Software" operator
    "OBJstaff06": ("OGAWA", "Kouji", "Models & Textures"),                                            # 1164
    "OBJstaff07": ("NAKAGIRI", "Seiichirou", "Character Design"),                                     # 1165
    "OBJstaff08": ("BABA", "Takakazu", "Models & Textures\nCharacter Design"),   # 1166: DDG64 "AKIYUKI"; 馬場 transcribed
    "OBJstaff09": ("ITAKURA", "Kazuhisa", "Models & Textures\nMap Design" + DOT + "Editing"),         # 1167
    "OBJstaff10": ("ENOMOTO", "Kouji", "Cabinet Design"),                                             # 1169
    "OBJstaff11": ("KAWABATA", "Kazuhiro", "Electrical Engineer"),                                    # 1170
    "OBJstaff12": ("BANDOU", "Kazuhiko", "Hardware Design"),                                          # 1171
    "OBJstaff13": ("MIZOBE", "Kumi", "Design (GD)"),                                                  # 1172
    "OBJstaff14": ("YAMANAKA", "Misao", "Design (ID)"),                                               # 1173
    "OBJstaff15": ("FURUKAWA", "Norihiro", "Sound" + DOT + "Music"),                                  # 1174
    "OBJstaff16": ("KAMATA", "Yoshikazu", "Sound" + DOT + "Sound Effects"),                           # 1175
    "OBJstaff17": ("KUNIKYOU", "Saori", "Sound" + DOT + "Voices"),                                    # 1177
    "OBJstaff18": ("UNNO", "Kazuko", "Sound" + DOT + "Voices"),   # 海野和子: not in the DDG64 roll, name transcribed; サウンド 音声 = 1177
    "OBJstaff19": ("YAMADA", "Katsuji", "Supervising Engineer"),                                      # 1185
    "OBJstaff20": ("KASHIRAJIMA", "Akio", "GM2 HEAD"),                                                # 1186
    "OBJstaff31": ("URITA", "Yukiharu", "Sound" + DOT + "SE Direction"),                              # 1176
    "OBJstaff32": ("ISHII", "Takashi", "Software\nAttract Demo"),     # 1168; ソフト: DDG64 "Sound", "Software" operator
}
NAMES = {"OBJstaff22": ("AIZU", "Yoshikazu"), "OBJstaff23": ("MATSUMOTO", "Takashi"),   # 1181's three names
         "OBJstaff24": ("KAWADA", "Souji")}
SUPPORT = "Support"                                                                     # 協力 1182-1184


# --- drawing ---------------------------------------------------------------------------------------------

def cover(text, cap, w, h, align="left", lead=1.3):
    """(h, w) coverage, aligned left, centre or right."""
    cov = R.fit(text, cap, w, h, "left" if align == "right" else align, lead if "\n" in text else None)
    if align == "right":
        on = np.nonzero(cov.max(0) > 0)[0]
        if len(on):
            cov = np.roll(cov, w - 1 - on[-1], 1)
    return cov


def flat(a, box, text, cap, rgb=WHITE, align="left", lead=1.3):
    """Blend `text` into box in one colour (antialiased): the credits' white on black."""
    x0, y0, x1, y1 = box
    cov = cover(text, cap, x1 - x0, y1 - y0, align, lead)
    alpha = np.clip((cov - 0.1) / 0.6, 0, 1)[..., None]
    reg = a[y0:y1, x0:x1, :3].astype(float)
    a[y0:y1, x0:x1, :3] = (reg * (1 - alpha) + np.array(rgb) * alpha).round().astype(np.uint8)
    a[y0:y1, x0:x1, 3][alpha[..., 0] > 0] = 255


def clear(a, box, rgba=(0, 0, 0, 255)):
    x0, y0, x1, y1 = box
    a[y0:y1, x0:x1] = rgba


def name_block(a, box, sur, given, cap=15):
    """The DDG64 layout: the surname on the upper line, the given name right-aligned under it."""
    x0, y0, x1, y1 = box
    ym = (y0 + y1) // 2
    flat(a, (x0, y0, x1, ym), sur, cap)
    flat(a, (x0, ym, x1, y1), given, cap, align="right")


BANNER_BG = (115, 115, 115, 255)             # the banners are flat grey behind the letters
BANNER_TPL = {}                               # row -> glyph colour, from all 20 banners (main() fills it)


def banner_template(sp):
    """Each row's most common bright glyph colour over every route and train banner: one chrome gradient for all."""
    counts = {}
    for n in list(ROUTES) + list(TRAINS):
        a = np.asarray(sp.render(n)).astype(int)
        span = a[:, 66:, :] if n in ROUTES else a[:, :172, :]
        rgb = span[..., :3]
        glyph = np.abs(rgb - np.array(BANNER_BG[:3])).sum(2) > 24
        L = lum(rgb)
        for y, x in zip(*np.nonzero(glyph & (L >= 120))):
            c = tuple(span[y, x].tolist())
            counts.setdefault(y, {}); counts[y][c] = counts[y].get(c, 0) + 1
    return {y: max(c, key=c.get) for y, c in counts.items()}


def chrome(a, box, text, cap, bg=None, align="center", inset=(0, 0), tpl=None, tol=24):
    """Metallic label (banners, controls labels): the glyphs go back to the background (bg: an RGBA, or None for each
    row's own most common colour), then the English is drawn with each row's glyph colour (the original's vertical
    gradient, or `tpl`) inside a 1-pixel ring of the glyphs' darkest colour, `inset` (x, y) pixels in from the box."""
    x0, y0, x1, y1 = box
    sub = a[y0:y1, x0:x1]
    orig = sub.copy()
    H, W = sub.shape[:2]
    rgb = orig[..., :3].astype(int)
    rowbg = []
    for y in range(H):
        vals = [tuple(p) for p in orig[y].tolist()]
        rowbg.append(bg if bg is not None else max(set(vals), key=vals.count))
    rowbg = np.array(rowbg, np.uint8)
    glyph = np.abs(rgb - rowbg[:, None, :3].astype(int)).sum(2) > tol     # a flat background: tol 6 takes the halos too
    if bg is not None and bg[3] == 0:
        glyph = orig[..., 3] > 0
    L = lum(rgb)
    dark = [tuple(p) for p in orig[glyph & (L < 60)].tolist()]
    ring = max(set(dark), key=dark.count) if dark else (0, 0, 0, 255)
    if tpl is None:
        tpl = {}
        for y in range(H):
            v = [tuple(p) for p in orig[y][glyph[y] & (L[y] >= 60)].tolist()]
            if v:
                tpl[y] = max(set(v), key=v.count)
    sub[glyph] = rowbg[np.nonzero(glyph)[0]]
    ix, iy = inset
    cov = cover(text, cap, W - 2 - 2 * ix, H - 2 - 2 * iy, align)
    m = np.zeros((H, W), bool)
    m[1 + iy:1 + iy + cov.shape[0], 1 + ix:1 + ix + cov.shape[1]] = cov >= 0.5
    g = m.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            g |= np.roll(np.roll(m, dy, 0), dx, 1)
    sub[g & ~m] = ring
    rows = sorted(tpl)
    for y, x in zip(*np.nonzero(m)):
        sub[y, x] = tpl[min(rows, key=lambda r: abs(r - y))]


def solid(a, box, text, cap, bg, rgb, align="center", tol=24, lead=1.3, pad=(0, 0)):
    """A label in one colour on a flat background: every pixel of the box that is not the background goes back to
    it, then `text` is drawn in `rgb`, `pad` (x, y) pixels in from the box."""
    x0, y0, x1, y1 = box
    sub = a[y0:y1, x0:x1]
    sub[np.abs(sub[..., :3].astype(int) - np.array(bg[:3])).sum(2) > tol] = bg
    flat(a, (x0 + pad[0], y0 + pad[1], x1 - pad[0], y1 - pad[1]), text, cap, rgb, align, lead)


def vertical(a, box, text, cap, bg, rgb, tol=24):
    """solid(), turned to read bottom to top (the vertical axis label)."""
    x0, y0, x1, y1 = box
    sub = a[y0:y1, x0:x1]
    sub[np.abs(sub[..., :3].astype(int) - np.array(bg[:3])).sum(2) > tol] = bg
    cov = np.rot90(cover(text, cap, y1 - y0, x1 - x0, "center"))
    alpha = np.clip((cov - 0.1) / 0.6, 0, 1)[..., None]
    sub[..., :3] = (sub[..., :3].astype(float) * (1 - alpha) + np.array(rgb) * alpha).round().astype(np.uint8)


def pieces(on):
    """Connected pieces (8-way) of a mask -> label array, and each piece's bbox (x0, y0, x1, y1)."""
    H, W = on.shape
    lab = np.zeros((H, W), int)
    boxes = [None]
    for y0 in range(H):
        for x0 in range(W):
            if on[y0, x0] and not lab[y0, x0]:
                n = len(boxes); lab[y0, x0] = n; st = [(y0, x0)]; bb = [x0, y0, x0 + 1, y0 + 1]
                while st:
                    y, x = st.pop()
                    bb = [min(bb[0], x), min(bb[1], y), max(bb[2], x + 1), max(bb[3], y + 1)]
                    for yy in (y - 1, y, y + 1):
                        for xx in (x - 1, x, x + 1):
                            if 0 <= yy < H and 0 <= xx < W and on[yy, xx] and not lab[yy, xx]:
                                lab[yy, xx] = n; st.append((yy, xx))
                boxes.append(tuple(bb))
    return lab, boxes


def outlined(a, box, text, cap, rgb, align="center"):
    """`text` in one colour inside a 1-pixel black ring, drawn over whatever is there."""
    x0, y0, x1, y1 = box
    sub = a[y0:y1, x0:x1]
    H, W = sub.shape[:2]
    cov = cover(text, cap, W - 2, H - 2, align)
    m = np.zeros((H, W), bool)
    m[1:1 + cov.shape[0], 1:1 + cov.shape[1]] = cov >= 0.5
    g = m.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            g |= np.roll(np.roll(m, dy, 0), dx, 1)
    sub[g & ~m] = (0, 0, 0, 255)
    sub[m] = tuple(rgb) + (255,)


def graded(a, box, text, cap, colours, ring=(0, 0, 0, 255), align="center", lead=1.3):
    """`text` drawn over whatever is there, each line shaded top to bottom through `colours` (the original letters'
    own gradient), inside a 1-pixel ring."""
    x0, y0, x1, y1 = box
    sub = a[y0:y1, x0:x1]
    H, W = sub.shape[:2]
    cov = cover(text, cap, W - 2, H - 2, align, lead)
    m = np.zeros((H, W), bool)
    m[1:1 + cov.shape[0], 1:1 + cov.shape[1]] = cov >= 0.5
    g = m.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            g |= np.roll(np.roll(m, dy, 0), dx, 1)
    sub[g & ~m] = ring
    rows = [y for y in range(H) if m[y].any()]
    n = text.count("\n") + 1                     # one gradient per line: the lines may touch, so split evenly
    top, bot = rows[0], rows[-1] + 1
    bands = [(top + (bot - top) * k // n, top + (bot - top) * (k + 1) // n) for k in range(n)]
    for b0, b1 in bands:
        for y in range(b0, b1):
            c = colours[min(len(colours) - 1, (y - b0) * len(colours) // (b1 - b0))]
            sub[y][m[y]] = tuple(c) + (255,)


def curved(a, text, centres, cap, rgb):
    """`text` along the circle through the original letters' `centres` (left to right, under the centre), each
    letter turned to the curve, inside a 1-pixel black ring: the dial's 通常ブレーキ follows its arc."""
    from PIL import Image, ImageDraw, ImageFont
    pts = np.array(centres, float)
    c = np.linalg.lstsq(np.c_[pts, np.ones(len(pts))], (pts ** 2).sum(1), rcond=None)[0]
    cx, cy = c[0] / 2, c[1] / 2
    rad = np.hypot(pts[:, 0] - cx, pts[:, 1] - cy).mean()
    t0, t1 = [np.arctan2(p[1] - cy, p[0] - cx) for p in (pts[0], pts[-1])]
    H, W = a.shape[:2]
    S = R.SS
    size = cap
    while True:
        font = ImageFont.truetype(R.FONT, int(round(size * S / R.CAP)))
        adv = [font.getlength(ch) / S for ch in text]
        if sum(adv) <= rad * (t0 - t1) or size <= 8:
            break
        size -= 1
    big = Image.new("L", (W * S, H * S))
    th = (t0 + t1) / 2 + sum(adv) / 2 / rad          # centred on the original span, reading left to right
    for ch, w in zip(text, adv):
        mid = th - w / 2 / rad
        g = Image.new("L", (int(w * S) + 8 * S, int(size * S / R.CAP * 1.4)))
        ImageDraw.Draw(g).text((4 * S, 0), ch, 255, font=font)
        g = g.rotate(90 - np.degrees(mid), resample=Image.BICUBIC, expand=True)
        x, y = cx + rad * np.cos(mid), cy + rad * np.sin(mid)
        big.paste(g, (int(x * S - g.width / 2), int(y * S - g.height / 2)), g)
        th -= w / rad
    cov = np.asarray(big.resize((W, H), Image.LANCZOS)) / 255.0
    m = cov >= 0.5
    gr = m.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            gr |= np.roll(np.roll(m, dy, 0), dx, 1)
    a[gr & ~m] = (0, 0, 0, 255)
    a[m] = tuple(rgb) + (255,)


# the brake dial (OBJcon16): the pieces that are art, by their top-left corner; every other piece is a letter
DIAL_ART = {(203, 39), (63, 70), (47, 45), (257, 9)}      # red arc, yellow-to-red arc, blue block, the ◀
DIAL_ARC = [(55, 112), (79, 134), (112, 149), (140, 160), (167, 162), (194, 161)]   # 通常ブレーキ's letters
DIAL = [((272, 3, 336, 29), "Start", (255, 0, 107)),       # スタート  operator
        ((0, 62, 48, 100), "Brake\nReady", (0, 107, 255)),  # 解除      DDG64 0 (the notch icon)
        ((236, 112, 322, 154), "!!!", (255, 8, 0), 28)]    # 非常      DDG64 9 (the notch icon)


def mode(a):
    v = [tuple(p) for p in a.reshape(-1, 4).tolist()]
    return max(set(v), key=v.count)


CARD = [((4, 49, 278, 79), "Accuracy of schedule"),            # ダイヤの正確さ           operator
        ((4, 81, 278, 111), "Braking (ride comfort)"),         # ブレーキ（乗り心地）     operator
        ((4, 113, 278, 143), "Precision of stopping position"),   # 停止位置の正確さ    operator
        ((4, 145, 278, 175), "Obedience to signals and signs"),   # 信号・標識を守る    operator
        ((4, 177, 278, 207), "Attention to safety")]           # 安全性への配慮           operator
PANELS = {"OBJcon22": "Acceleration", "OBJcon23": "Acceleration",   # 加速 operator (lit / dim)
          "OBJcon24": "Coasting", "OBJcon25": "Coasting",           # 惰行 operator
          "OBJcon26": "Braking", "OBJcon27": "Braking"}             # 制動 operator
BLUE = (0, 99, 255)
KET_GRAD = [(0, 74, 231), (0, 57, 255), (0, 0, 231)]                                       # 決定's blue, top to bottom
SEL_GRAD = [(255, 206, 0), (255, 189, 0), (255, 165, 0), (255, 140, 0), (255, 99, 0)]     # 選択's orange, top to bottom
HEI_GRAD = [(255, 247, 0), (255, 198, 0), (255, 148, 0), (255, 99, 0), (255, 0, 0)]       # 併合準備's yellow to red


# --- the records ----------------------------------------------------------------------------------------

def paint(name, rgba):
    a = rgba.copy()
    if name in ROUTES:                        # stripe on the left, name on the right of it
        chrome(a, (66, 0, 240, 32), ROUTES[name], 20, bg=BANNER_BG, inset=(5, 1), tpl=BANNER_TPL, tol=6)
    elif name in TRAINS:                      # name on the left, stripe on the right
        chrome(a, (0, 0, 172, 32), TRAINS[name], 20, bg=BANNER_BG, inset=(5, 1), tpl=BANNER_TPL, tol=6)
    elif name == "OBJtop10":                  # 選択：ブレーキ 716; 決定：スタートボタン operator
        clear(a, (0, 0, 160, 48))
        flat(a, (2, 2, 158, 22), "Select: Brake", 14)
        flat(a, (2, 26, 158, 46), "Confirm: Start button", 14)
    elif name == "OBJtop09":                  # 乗務記録 operator: on the flat grey of the plate
        chrome(a, (16, 6, 148, 38), "Duty Log", 22, bg=BANNER_BG, tol=6, inset=(4, 1))
    elif name == "OBJcon17":                  # the lever arrow: 切 on top, 加速（力行） under it (operator)
        chrome(a, (0, 0, 80, 34), "Off", 24, bg=(0, 0, 0, 0))
        chrome(a, (0, 186, 80, 256), "Acceleration", 14, bg=(0, 0, 0, 0))
    elif name == "OBJcon18":                  # マスコン（アクセル） operator
        chrome(a, (6, 5, 170, 67), "Master Controller\n(Throttle)", 20, bg=(0, 0, 0, 0))
    elif name == "OBJcon19":                  # ブレーキ operator
        chrome(a, (5, 4, 171, 60), "Brake", 30, bg=(0, 0, 0, 0))
    elif name in PANELS:                      # black on the lit / dim panel
        solid(a, (0, 0, 96, 32), PANELS[name], 18, mode(a), (0, 0, 0), pad=(4, 2))
    elif name == "OBJcon16":                  # the brake dial: its letters are pieces apart from the arcs
        lab, boxes = pieces(a[..., 3] > 0)
        for i, bb in enumerate(boxes[1:], 1):
            if bb[:2] not in DIAL_ART:
                a[lab == i] = (0, 0, 0, 0)
        for box, t, rgb, *cap in DIAL:
            outlined(a, box, t, cap[0] if cap else 18, rgb)
        curved(a, "Service Brake", DIAL_ARC, 18, (255, 189, 0))   # 通常ブレーキ operator, along the arc
    elif name == "OBJcon30":                  # 速度 operator, up the graph's axis
        vertical(a, (4, 46, 44, 126), "Speed", 20, (0, 0, 0, 255), BLUE)
    elif name == "OBJcon31":                  # 距離 operator, along the axis
        solid(a, (214, 4, 306, 46), "Distance", 22, (0, 0, 0, 255), BLUE)
    elif name == "OBJtuuti01":                # the report card, black on white; the rules stay
        white = (255, 255, 255, 255)
        solid(a, (100, 4, 380, 46), "Evaluation", 26, white, (0, 0, 0))            # 運転評価 DDG64 141
        for box, t in CARD:
            solid(a, box, t, 16, white, (0, 0, 0))
        solid(a, (150, 214, 300, 254), "Overall evaluation", 18, white, (0, 0, 0))   # 総合評価 operator
        solid(a, (400, 214, 476, 254), "points", 18, white, (0, 0, 0))              # 点 operator
    elif name == "OBJstart16":                # the departure board header: 発車案内 -> Departure Guide (468)
        x0, y0, x1, y1 = 84, 3, 332, 37
        for y in range(y0, y1):               # each row back to the plate's own grey at its left edge
            bgc = a[y, 86].copy()
            diff = np.abs(a[y, x0:x1, :3].astype(int) - bgc[:3].astype(int)).sum(1) > 24
            a[y, x0:x1][diff] = bgc
        flat(a, (92, 5, 324, 35), "Departure Guide", 20, align="center")
    elif name in ("OBJcon35", "OBJcon39"):    # the controls captions, green with a dark green edge
        chrome(a, (0, 0, a.shape[1], a.shape[0]), CAPTIONS[name], LINE_CAPS[name], bg=(0, 0, 0, 0),
               inset=(6, 1))
    elif name in LINES2:                      # two lines, each in its own colour and edge (green, or red under it)
        W, H = a.shape[1], a.shape[0]
        for k, t in enumerate(LINES2[name]):
            chrome(a, (0, k * H // 2, W, (k + 1) * H // 2), t, LINE_CAPS[name][k], bg=(0, 0, 0, 0), inset=(6, 1))
    elif name in STAMPS:                      # the grade stamp: the kanji inside the ring goes, the word in its red
        red = tuple(int(v) for v in mode(a[a[..., 3] > 0][None])[:3])
        yy, xx = np.mgrid[:32, :32]
        inside = (yy - 15.5) ** 2 + (xx - 15.5) ** 2 < 12.6 ** 2
        a[inside] = (0, 0, 0, 0)
        cov = cover(STAMPS[name], 10, 24, 14, "center")       # solid, like the stamp: no blend into the clear
        a[9:23, 4:28][cov >= 0.45] = red + (255,)
    elif name == "OBJcon42":                  # 870: Select and Choose beside the arrows; the art stays
        graded(a, (40, 124, 104, 145), "Select", 14, SEL_GRAD, align="left")
        graded(a, (102, 92, 170, 112), "Choose", 14, KET_GRAD)          # under the blue arrow, for 決定
    elif name in HEI:                         # 857: small along the bottom of the picture; the art stays
        graded(a, (2, 100, 94, 127), "Coupler\nDeployed!", 10, HEI_GRAD, lead=1.25)
    elif name in ("OBJcon20", "OBJcon21"):    # 選択 / 決定 870 (the button legend's words)
        chrome(a, (6, 5, 106, 43), "Select" if name == "OBJcon20" else "Choose", 22, bg=(0, 0, 0, 0))
    elif name in PEOPLE:
        sur, given, roles = PEOPLE[name]
        orig = a.copy()
        clear(a, (0, 0, a.shape[1], a.shape[0]))
        name_block(a, (4, 1, 150, 47), sur, given)
        rx = 158
        if name == "OBJstaff04":              # the red cross: the roles start under it, so it sits on the "a"
            red = (orig[..., :3].astype(int).max(2) - orig[..., :3].astype(int).min(2)) > 60
            ys, xs = np.nonzero(red)
            rx = int(xs.min()) - 1
        n = roles.count("\n") + 1
        cap = 11 if n < 3 else 10
        flat(a, (rx, 1, a.shape[1] - 2, 47), roles, cap)
        if name == "OBJstaff04":
            a[red] = orig[red]
    elif name in NAMES:
        clear(a, (0, 0, a.shape[1], a.shape[0]))
        name_block(a, (4, 1, a.shape[1] - 4, 47), *NAMES[name])
    elif name == "OBJstaff00":                # 高速編 -> High-Speed (1158); the logo and STAFF stay
        clear(a, (304, 0, 464, 48))
        flat(a, (304, 6, 460, 42), "High-Speed", 22, align="center")
    elif name == "OBJstaff21":                # 1181: 制作協力 + the DDG64 name for the company; the JR mark stays
        green = orig_green(a)
        clear(a, (0, 0, 464, 18)); clear(a, (78, 18, 464, 64))
        flat(a, (2, 1, 200, 17), "Production Support", 11)
        flat(a, (84, 19, 460, 63), "EAST JAPAN\nRAILWAY COMPANY", 17, green, lead=1.2)
    elif name in ("OBJstaff25", "OBJmoginoya"):   # 1183: 協力 + the DDG64 note by the logo
        clear(a, (0, 0, 64, 19)); clear(a, (228, 0, 336, 19))
        flat(a, (2, 1, 64, 19), SUPPORT, 11)
        flat(a, (228, 1, 334, 19), "(Oginoya Co.)", 11, align="center")
    elif name == "OBJstaff26":                # 1184
        clear(a, (0, 0, 64, 19)); clear(a, (0, 48, 352, 96))
        flat(a, (2, 1, 64, 19), SUPPORT, 11)
        flat(a, (4, 52, 348, 92), "SHIMIZU Yasunori" + DOT + "TSUKANO Toshiaki" + DOT + "YAMABE Kishio", 12,
             align="center")
    elif name == "OBJstaff27":                # 1179
        clear(a, (0, 0, a.shape[1], a.shape[0]))
        flat(a, (0, 1, 288, 18), "Planning" + DOT + "Development Support", 10, align="center")
        name_block(a, (4, 20, 140, 62), "MURAKASHI", "Yasuo")
        name_block(a, (150, 20, 284, 62), "ABE", "Kazumasa")
    elif name == "OBJstaff28":                # 1180
        clear(a, (0, 0, a.shape[1], a.shape[0]))
        flat(a, (0, 1, 368, 18), "Development Support", 10, align="center")
        name_block(a, (4, 20, 120, 62), "IWAI", "Akira")
        name_block(a, (126, 20, 244, 62), "ONOGI", "Yuuichi")
        name_block(a, (250, 20, 364, 62), "ABE", "Satoshi")
    elif name == "OBJstaff29":                # 1182
        clear(a, (0, 0, a.shape[1], a.shape[0]))
        flat(a, (2, 1, 64, 19), SUPPORT, 11)
        flat(a, (24, 22, 380, 62), "Hokuetsu Express Co.,Ltd", 22, align="center")
    elif name == "OBJstaff30":                # 1178: 音声 -> the DDG64 heading; the two names
        clear(a, (0, 0, a.shape[1], a.shape[0]))
        name_block(a, (4, 1, 160, 47), "KIKUCHI", "Masayuki")
        name_block(a, (168, 1, 324, 47), "YAMAJI", "Tetsuyoshi")
        flat(a, (330, 8, 396, 40), "Voice Actors", 10, align="center")
    else:
        raise SystemExit("no layout for %s" % name)
    return a


def orig_green(a):
    rgb = a[..., :3].astype(int)
    g = (rgb[..., 1] > 150) & (rgb[..., 0] < 100) & (rgb[..., 2] < 100)
    vals = [tuple(p) for p in rgb[g].tolist()]
    return max(set(vals), key=vals.count)


def fit_weighted(blocks, counts, k, pin=64, rng=np.random.RandomState(7)):
    """Unique quads (with how often each occurs) -> at most k codebook quads. The `pin` most frequent quads are kept
    exactly (the black and white fields of the credits); the rest come from a k-means weighted by frequency, so a
    background block used a thousand times is not averaged with a rare edge block."""
    if len(blocks) <= k:
        return blocks.copy()
    order = np.argsort(-counts, kind="stable")
    pin = min(pin, k // 2)
    feats, w = q_rgb(blocks), counts.astype(float)
    cent = [feats[i] for i in order[:max(pin, 1)]]      # with no room to pin, the most frequent block still seeds
    dmin = ((feats[:, None, :] - np.array(cent)[None]) ** 2).sum(2).min(1)
    while len(cent) < k:                           # farthest-first, weighted, for the free centroids
        i = int((dmin * w).argmax())
        cent.append(feats[i]); dmin = np.minimum(dmin, ((feats - feats[i]) ** 2).sum(1))
    cent = np.array(cent)
    for _ in range(20):
        lab = ((feats[:, None, :] - cent[None]) ** 2).sum(2).argmin(1)
        for j in range(pin, k):
            sel = lab == j
            if sel.any():
                cent[j] = (feats[sel] * w[sel, None]).sum(0) / w[sel].sum()
    A_ = (np.clip(cent[:, 0:4], 0, 31) > 15).astype(np.int64)
    R_ = np.clip(cent[:, 4:8], 0, 31).round().astype(np.int64)
    G_ = np.clip(cent[:, 8:12], 0, 31).round().astype(np.int64)
    B_ = np.clip(cent[:, 12:16], 0, 31).round().astype(np.int64)
    return ((A_ << 15) | (R_ << 10) | (G_ << 5) | B_).astype(np.uint16)


CAPTIONS = {"OBJcon35": "Turn off the master control and coast.",               # マスコン「切」惰性走行 990
            "OBJcon39": "Brake settings range from 1~8, plus an emergency brake."}  # ブレーキは8段階あります 960
LINES2 = {"OBJcon34": ("Move the master controller to the full-notch position.", "Accelerate rapidly."),   # operator
          "OBJcon36": ("Decelerate and stop using the brake.", "Emergency braking results in a point deduction."),
          "OBJcon38": ("Pull the lever to accelerate.", "(Brake is released during acceleration.)")}
STAMPS = {"OBJtuuti02": "Great", "OBJtuuti03": "Good", "OBJtuuti04": "Pass", "OBJtuuti05": "Fail"}   # 優 良 可 否 operator
LINE_CAPS = {"OBJcon34": (12, 13), "OBJcon36": (13, 12), "OBJcon38": (13, 13),   # one size for the whole controls
             "OBJcon35": 13, "OBJcon39": 12}                                       # screen (12 where 13 would squeeze)
HEI = ["OBJhei001", "OBJhei002", "OBJhei003", "OBJhei004"]                       # E3 併合準備

LABELS = (list(ROUTES) + list(TRAINS) + ["OBJtop10", "OBJcon20", "OBJcon21", "OBJstart16", "OBJtop09", "OBJcon17",
                                         "OBJcon18", "OBJcon19", "OBJcon30", "OBJcon31", "OBJtuuti01", "OBJcon16"] + list(PANELS) + list(PEOPLE) + list(NAMES)
          + ["OBJstaff00", "OBJstaff21", "OBJstaff25", "OBJmoginoya", "OBJstaff26", "OBJstaff27", "OBJstaff28",
             "OBJstaff29", "OBJstaff30"] + list(CAPTIONS) + list(LINES2) + list(STAMPS) + ["OBJcon42"] + HEI)


# --- re-tiling ------------------------------------------------------------------------------------------

def main(lst_p, tbl_p, cg1_p, out_tbl, out_cg1, preview=None):
    names = {a: o for a, o, s in A.lst(open(lst_p, encoding="latin-1").read())}
    tbl = bytearray(open(tbl_p, "rb").read())
    cg = bytearray(open(cg1_p, "rb").read())
    sp = A.Sprites(lst_p, bytes(tbl), bytes(cg))
    ents = A.rom2(bytes(cg))

    users = {}
    for n in names:
        if not sp.flagged(n):
            for t in sp.tilemap(n)[2]:
                users.setdefault(t, set()).add(n)
    mine = set(LABELS)
    freeable = sorted(t for t, u in users.items() if u <= mine)

    pages = {p: vq_read(cg, ents[p][0]) for p in sorted({t // 256 for t in freeable})}
    existing = {}                                  # any VQ texture's tile can be reused: a record mixes textures
    for p, (o, s_) in enumerate(ents):
        if cg[o + 9] == 3:
            cb, idx = pages.get(p) or vq_read(cg, o)
            for s in range(256):
                existing.setdefault(tile_px(cb, idx, s).tobytes(), p * 256 + s)

    BANNER_TPL.update(banner_template(sp))
    new = {}
    for name in LABELS:
        out = paint(name, np.asarray(sp.render(name)).copy())
        new[name] = P.pack_argb1555(out)
        if preview:
            os.makedirs(preview, exist_ok=True)
            Image.fromarray(P._unpack(new[name], 0), "RGBA").save(os.path.join(preview, name + ".png"))

    def tiles(name):
        w, h, _ = sp.tilemap(name)
        v = new[name]
        return [v[(k // w) * 16:(k // w) * 16 + 16, (k % w) * 16:(k % w) * 16 + 16] for k in range(w * h)]

    kept = {existing[t.tobytes()] for n in new for t in tiles(n)
            if t.tobytes() in existing and existing[t.tobytes()] in set(freeable)}
    pool = [t for t in freeable if t not in kept]
    room = {}                                      # free codebook entries per page: fill the roomiest pages first,
    for p, (cb, idx) in pages.items():             # so new tiles don't land where a handful of codes must stand in
        fs = {t % 256 for t in freeable if t // 256 == p}   # for dozens of blocks
        used = set()
        for sl in range(256):
            if sl not in fs:
                ty, tx = divmod(sl, 16)
                used.update(idx[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8].ravel().tolist())
        room[p] = 256 - len(used)
    pool.sort(key=lambda t: (-room.get(t // 256, 0), t))
    placed, assigned, ids_for = {}, {}, {}
    for name in new:
        ids = []
        for tile in tiles(name):
            key = tile.tobytes()
            if key not in placed:
                if key in existing:
                    placed[key] = existing[key]
                else:
                    if not pool:
                        raise SystemExit("out of CG1 tile slots (%d freed, %d kept)" % (len(freeable), len(kept)))
                    t = pool.pop(0); placed[key] = t; assigned[t] = tile
            ids.append(placed[key])
        ids_for[name] = ids

    for p, (cb, idx) in pages.items():
        freed = {t % 256 for t in freeable if t // 256 == p}
        keep_codes = set()
        for s in range(256):
            if s not in freed or p * 256 + s in kept:
                ty, tx = divmod(s, 16)
                keep_codes.update(idx[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8].ravel().tolist())
        free_codes = [c for c in range(256) if c not in keep_codes]
        slots = {t % 256: tile for t, tile in assigned.items() if t // 256 == p}
        if not slots:
            continue
        freq = {}
        for tile in slots.values():
            for q in quads(tile).reshape(-1, 4):
                freq[tuple(q)] = freq.get(tuple(q), 0) + 1
        exact = {tuple(q) for q in cb[sorted(keep_codes)]} if keep_codes else set()
        todo = [b for b in sorted(freq) if b not in exact]
        blocks = np.array(sorted(freq), np.uint16)
        cents = (fit_weighted(np.array(todo, np.uint16), np.array([freq[b] for b in todo]), len(free_codes))
                 if todo else np.zeros((0, 4), np.uint16))
        todo = np.array(todo, np.uint16).reshape(-1, 4)
        for c, q in zip(free_codes, cents):
            cb[c] = q
        usable = sorted(keep_codes) + free_codes[:len(cents)]
        U = q_rgb(cb[usable])
        for s, tile in slots.items():
            ty, tx = divmod(s, 16)
            qs = quads(tile).reshape(-1, 4)
            d = ((q_rgb(qs)[:, None, :] - U[None]) ** 2).sum(2)
            idx[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8] = np.array(usable)[d.argmin(1)].reshape(8, 8)
        vq_write(cg, ents[p][0], cb, idx)
        print("texture %d: %d slots rewritten, %d codebook entries kept, %d re-fitted to %d new blocks" % (
            p, len(slots), len(keep_codes), len(cents), len(todo)))

    for name, ids in ids_for.items():
        struct.pack_into("<%dH" % len(ids), tbl, names[name] + 2, *ids)
    open(out_tbl, "wb").write(tbl); open(out_cg1, "wb").write(cg)
    print("%d labels, %d slots freed, %d kept, %d rewritten" % (len(LABELS), len(freeable), len(kept), len(assigned)))


if __name__ == "__main__":
    if len(sys.argv) not in (6, 7):
        sys.exit(__doc__)
    main(*sys.argv[1:])
