#!/usr/bin/env python3
"""English captions under the yellow road signs and driving prompts (MARK.PVM / MARK.DAT).

    /usr/bin/python3 repaint_mark_signs.py <SYSTEM dir of the original disc> <MARK.PVM> <out dir>

<MARK.PVM> is the translation's own (the fourth texture is the English penalty sheet). The
out dir gets MARK.PVM, MARK.DAT and MARK_PARTS.DAT, plus signs_en.png (the new texture as
encoded) and check.png (every sign drawn back from the output files).

A sign is a list of parts placed on screen (MARK.DAT), each part a rectangle of a texture
(MARK_PARTS.DAT, NJS_TEXANIM with UVs on a 256 scale whatever the texture size). The
Japanese captions are glyphs from texture 1, one part per character. English does not fall
one letter per cell, so each caption becomes one strip on a fifth texture, one part per
strip, and every sign swaps its glyph parts for its strip. The pictograms are untouched.
The route load asks for five textures (013ae8_route_load.c in the translation layer).
The same texture carries the stop counter's "STOP" label and "/" (MARK_PART_STOP and
MARK_PART_SLASH in 0129cc_pause.c): parts 396 and 397, right after the captions.
MARK.DAT and MARK_PARTS.DAT are only ever loaded from \\SYSTEM (012f44_game.c).
"""
import sys, os, struct
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from dc import pvr_codec as P

FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
SIZE, STROKE = 22, 2
FILL, OUTLINE = (255, 255, 0, 255), (17, 0, 0, 255)   # the Japanese glyphs' own colours
MAXW = 150              # widest line before it wraps (the Japanese band is ~124 px)
CENTRE_X = 99           # where the Japanese captions are centred
TOP_Y = 222             # the Japanese captions start at 224; the strip has 2 px of air
TEX_W = TEX_H = 512
LABEL_FONT = "/System/Library/Fonts/Supplemental/Arial Narrow Bold.ttf"
LABEL_RED = (255, 0, 0)     # the red BUS STOP sign's red; TIME is (255,170,0), NOW (102,255,0)
PART_STOP, PART_SLASH = 396, 397
GBIX = 2705             # 2701-2703 the original sheets, 2704 the penalty sheet
TEXID = 4

# (English, [records]) with the Japanese each record shows.
CAPTIONS = [
    ("Sound horn", [12]),                       # 警笛鳴らせ
    ("Bend to right", [13]),                    # 右方屈曲有り
    ("Bend to left", [14]),                     # 左方屈曲有り
    ("Winding road", [15]),                     # つづら折有り
    ("Falling rocks", [16]),                    # 落石注意
    ("Merging traffic", [17]),                  # 合流注意
    ("Lane ends", [18]),                        # 車線数減少
    ("Steep hill upwards", [19]),               # 上急勾配有り
    ("Steep hill downwards", [20]),             # 下急勾配有り
    ("Road works", [21]),                       # 道路工事中
    ("Other danger", [22]),                     # その他の危険
    ("Next: straight on", [23]),                # 次は直進
    ("Next: turn right", [24]),                 # 次は右折
    ("Next: turn left", [25]),                  # 次は左折
    ("Next: bear right", [26]),                 # 次は斜め右
    ("Stop before level crossing", [27]),       # 踏切前一時停止
    ("Change lanes", [28, 29]),                 # 車線変更せよ
    ("Lane control",                            # 通行区分
     list(range(30, 42)) + list(range(50, 59)) + list(range(70, 75)) + [80]),
]


def read_signs(dat):
    w = struct.unpack_from("<%dI" % (len(dat) // 4), dat)
    signs = []
    for s in range(125):
        o, items = w[s], []
        while w[o] != 0xFFFFFFFF:
            items.append((w[o],) + struct.unpack_from("<2f", dat, (o + 1) * 4))
            o += 3
        signs.append(items)
    return signs


def write_signs(signs):
    """The header is 126 words: the 125 offsets, then a 0, as on the disc."""
    out, words = [], 126
    offsets = []
    for items in signs:
        offsets.append(words)
        for pi, x, y in items:
            out.append(struct.pack("<I2f", pi, x, y))
        out.append(struct.pack("<I", 0xFFFFFFFF))
        words += 3 * len(items) + 1
    return struct.pack("<126I", *(offsets + [0])) + b"".join(out)


def lines_for(text, font):
    width = lambda t: font.getbbox(t, stroke_width=STROKE)[2]
    if text.startswith("Next: "):
        return ["Next:", text[6:]]              # the direction prompts, all alike
    if width(text) <= MAXW:
        return [text]
    words = text.split(" ")
    best = min(([" ".join(words[:k]), " ".join(words[k:])] for k in range(1, len(words))),
               key=lambda ls: max(width(l) for l in ls))
    if max(width(l) for l in best) > MAXW:
        raise SystemExit("too wide even on two lines: %r" % text)
    return best


def render(text, font):
    ls = lines_for(text, font)
    asc, desc = font.getmetrics()
    lh = asc + desc + 1
    wide = max(font.getbbox(l, stroke_width=STROKE)[2] for l in ls)
    w = (wide + 4 + 1) & ~1                     # even: UVs are in 2-texel steps on 512
    h = (lh * len(ls) + 4 + 1) & ~1
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for n, l in enumerate(ls):
        lw = font.getbbox(l, stroke_width=STROKE)[2]
        d.text(((w - lw) // 2, 2 + n * lh), l, font=font, fill=FILL,
               stroke_width=STROKE, stroke_fill=OUTLINE)
    return img


def label(text, colour, h=10):
    """Like the HUD's TIME / NOW labels (BUSSTOP.PVM): small bold capitals h px tall, the
    edge pixels a darker shade of the colour rather than an outline. 1 px of air around."""
    big = 8
    f = ImageFont.truetype(LABEL_FONT, h * big * 13 // 10)
    l, t, r, b = f.getbbox(text)
    m = Image.new("L", (r - l, b - t), 0)
    ImageDraw.Draw(m).text((-l, -t), text, font=f, fill=255)
    m = np.array(m.resize((max(1, m.width * h // (b - t)), h), Image.LANCZOS))
    rgb = np.where((m < 200)[..., None], (np.array(colour) * 0.55).astype(np.uint8),
                   np.array(colour, dtype=np.uint8))
    out = np.zeros((h + 2, (m.shape[1] + 2 + 1) & ~1, 4), dtype=np.uint8)
    out[1:h + 1, 1:m.shape[1] + 1, :3] = rgb
    out[1:h + 1, 1:m.shape[1] + 1, 3] = m
    return Image.fromarray(out)


def slash():
    """A '/' for the counter, in the HUD digits' white with a grey edge, on a 16x16 cell."""
    img = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.line((10, 1, 2, 15), fill=(110, 110, 110, 255), width=3)
    d.line((10, 1, 2, 15), fill=(255, 255, 255, 255), width=2)
    return img


def pack_sheet(strips):
    """Shelf-pack the strips onto one texture, tallest first, at even coordinates."""
    order = sorted(range(len(strips)), key=lambda i: -strips[i].height)
    sheet = Image.new("RGBA", (TEX_W, TEX_H), (0, 0, 0, 0))
    rects, x, y, shelf = [None] * len(strips), 0, 0, 0
    for i in order:
        s = strips[i]
        if x + s.width > TEX_W:
            x, y, shelf = 0, y + shelf, 0
        if y + s.height > TEX_H:
            raise SystemExit("captions do not fit on one %dx%d texture" % (TEX_W, TEX_H))
        sheet.paste(s, (x, y))
        rects[i] = (x, y, s.width, s.height)
        x, shelf = x + s.width, max(shelf, s.height)
    return sheet, rects


def argb4444(rgba):
    rgba = rgba.copy()
    rgba[rgba[..., 3] == 0] = 0                 # transparent is transparent, whatever its colour
    a, r, g, b = (rgba[..., i].astype(np.uint16) >> 4 for i in (3, 0, 1, 2))
    return (a << 12) | (r << 8) | (g << 4) | b


def encode_vq(rgba):
    """(h, w, 4) RGBA -> PVRT VQ data: a 256-entry codebook of 2x2 ARGB4444 blocks (texels in
    the order top-left, bottom-left, top-right, bottom-right) and one twiddled index byte per
    block. The codebook is k-means over the sheet's distinct blocks. It starts from the most
    different blocks (farthest-point), not the most common, and weighs blocks by the square
    root of how often they occur: a colour used by a few blocks only (the white "/" among
    yellow captions) still gets entries of its own. check_vq and check.png are the proof."""
    v = argb4444(rgba)
    h, w = v.shape
    blk = np.stack([v[dy::2, dx::2] for dx in range(2) for dy in range(2)], axis=-1).reshape(-1, 4)
    uniq, inv, count = np.unique(blk, axis=0, return_inverse=True, return_counts=True)
    inv = inv.ravel()
    chan = lambda u: np.stack([(u >> s) & 15 for s in (12, 8, 4, 0)], axis=-1).reshape(len(u), 16)
    feat = chan(uniq).astype(np.float64)
    weight = np.tile([2.0, 1.0, 1.0, 1.0], 4)   # alpha counts double: edges must stay crisp
    far = lambda k: (((feat - feat[k]) ** 2) * weight).sum(axis=1)
    if len(uniq) <= 256:
        book, assign = feat.copy(), np.arange(len(uniq))
    else:
        pick = [int(np.argmax(count))]
        nearest = far(pick[0])
        while len(pick) < 256:
            pick.append(int(np.argmax(nearest)))
            nearest = np.minimum(nearest, far(pick[-1]))
        book = feat[pick].copy()
        for _ in range(30):
            dist = (((feat[:, None, :] - book[None, :, :]) ** 2) * weight).sum(axis=2)
            assign = dist.argmin(axis=1)
            for k in range(256):
                m = assign == k
                if m.any():
                    book[k] = np.average(feat[m], axis=0, weights=np.sqrt(count[m]))
                else:                           # an empty entry takes the worst-served block
                    book[k] = feat[dist.min(axis=1).argmax()]
            book = np.clip(np.rint(book), 0, 15)
        dist = (((feat[:, None, :] - book[None, :, :]) ** 2) * weight).sum(axis=2)
        assign = dist.argmin(axis=1)
    book = np.vstack([book, np.zeros((256 - len(book), 16))]).astype(np.uint16).reshape(256, 4, 4)
    codebook = (book[..., 0] << 12) | (book[..., 1] << 8) | (book[..., 2] << 4) | book[..., 3]
    codes = assign[inv].astype(np.uint8).reshape(h // 2, w // 2)
    sx, sy = P.twiddle_table(w // 2), P.twiddle_table(h // 2)
    flat = np.zeros((h // 2) * (w // 2), dtype=np.uint8)
    flat[((sx[None, :] << 1) | sy[:, None]).ravel()] = codes.ravel()
    return codebook.astype("<u2").tobytes() + flat.tobytes(), len(uniq)


MAX_ERR = 96        # per channel, 0-255: a wrong colour (white read back yellow is 255) fails
P99_ERR = 48        # VQ softens the blended texels where fill meets outline; 99% stay close


def check_vq(rgba, data):
    """Decode the VQ data and compare it with what was drawn, on every clearly opaque texel:
    none may be off by more than MAX_ERR on a channel, 99% within P99_ERR, or the build stops."""
    got = P.decode_vq(data, 0, rgba.shape[1], rgba.shape[0], 2).astype(int)
    want = rgba.astype(int)
    solid = want[..., 3] >= 192
    e = np.abs(got - want)[..., :3].max(axis=2)[solid]
    worst, p99 = int(e.max()), int(np.percentile(e, 99))
    if worst > MAX_ERR or p99 > P99_ERR:
        raise SystemExit("VQ texture too far off: worst %d/255, 99%% within %d" % (worst, p99))
    print("VQ check: worst %d/255, 99%% within %d" % (worst, p99))


def read_pvm(d):
    hs, flags, count = struct.unpack_from("<IHH", d, 4)
    if d[:4] != b"PVMH" or flags != 0x14F:
        raise SystemExit("not the PVM layout expected (flags %#x)" % flags)
    entries = [d[12 + 38 * k: 12 + 38 * (k + 1)] for k in range(count)]
    chunks, i = [], 8 + hs
    while i < len(d):
        size = struct.unpack_from("<I", d, i + 4)[0]
        chunks.append(d[i:i + 8 + size])
        i += 8 + size
    return entries, chunks


def write_pvm(entries, chunks):
    body = struct.pack("<HH", 0x14F, len(entries)) + b"".join(entries)
    hs = ((8 + len(body) + 15) & ~15) - 8       # the chunks start 16-aligned
    return b"PVMH" + struct.pack("<I", hs) + body.ljust(hs, b"\0") + b"".join(chunks)


def main():
    system, pvm_in, out = sys.argv[1], sys.argv[2], sys.argv[3]
    os.makedirs(out, exist_ok=True)
    dat = open(os.path.join(system, "MARK.DAT"), "rb").read()
    parts = open(os.path.join(system, "MARK_PARTS.DAT"), "rb").read()
    tanim = [struct.unpack_from("<10h", parts, k * 20) for k in range(len(parts) // 20)]
    signs = read_signs(dat)

    # Every sign drawing texture-1 glyphs must be one we caption, and only its caption row.
    listed = {r for _, recs in CAPTIONS for r in recs}
    glyphs = {s for s, items in enumerate(signs) if any(tanim[p][8] == 1 for p, _, _ in items)}
    road = {s for s in glyphs if s < 82}        # 123/124 draw texture 1 too: the pause screen
    if road != listed:
        raise SystemExit("captioned records differ: missing %s, extra %s"
                         % (sorted(road - listed), sorted(listed - road)))
    for s in listed:
        for p, x, y in signs[s]:
            if tanim[p][8] == 1 and y < 220:
                raise SystemExit("record %d has a texture-1 part above the caption row" % s)

    font = ImageFont.truetype(FONT, SIZE)
    strips = [render(text, font) for text, _ in CAPTIONS] + [label("STOP", LABEL_RED), slash()]
    sheet, rects = pack_sheet(strips)
    sheet.save(os.path.join(out, "signs_en.png"))

    first = len(tanim)
    if (first + len(CAPTIONS), first + len(CAPTIONS) + 1) != (PART_STOP, PART_SLASH):
        raise SystemExit("the counter's parts would not be %d/%d: fix 0129cc_pause.c too"
                         % (PART_STOP, PART_SLASH))
    new_parts = b""
    for x, y, w, h in rects:
        new_parts += struct.pack("<10h", w, h, 0, 0, x // 2, y // 2, (x + w) // 2, (y + h) // 2,
                                 TEXID, 0)
    for k, (_, recs) in enumerate(CAPTIONS):
        w = rects[k][2]
        for s in recs:
            signs[s] = [it for it in signs[s] if tanim[it[0]][8] != 1]
            signs[s].append((first + k, float(CENTRE_X - w // 2), float(TOP_Y)))
    open(os.path.join(out, "MARK_PARTS.DAT"), "wb").write(parts + new_parts)
    open(os.path.join(out, "MARK.DAT"), "wb").write(write_signs(signs))

    d = open(pvm_in, "rb").read()
    entries, chunks = read_pvm(d)
    pvrt = [c for c in chunks if c[:4] == b"PVRT"]
    if len(entries) not in (4, 5) or len(pvrt) != len(entries):
        raise SystemExit("expected the translation's MARK.PVM (4 textures, or 5 to redo)")
    data, distinct = encode_vq(np.array(sheet))
    check_vq(np.array(sheet), data)
    tmpl = pvrt[3]                              # the penalty sheet: 512x512 VQ ARGB4444
    if (tmpl[8], tmpl[9]) != (2, 3) or struct.unpack_from("<HH", tmpl, 12) != (TEX_W, TEX_H):
        raise SystemExit("texture 3 is not the 512x512 VQ sheet expected")
    chunk = tmpl[:16] + data + tmpl[16 + len(data):]
    if len(chunk) != len(tmpl):
        raise SystemExit("VQ data size mismatch")
    entry = struct.pack("<H", TEXID) + b"signs_en".ljust(28, b"\0") + entries[3][30:34] \
        + struct.pack("<I", GBIX)
    entries, chunks = entries[:4] + [entry], [c for c in chunks if c not in pvrt[4:]] + [chunk]
    open(os.path.join(out, "MARK.PVM"), "wb").write(write_pvm(entries, chunks))

    # Draw every captioned sign back from the files just written.
    pvm = open(os.path.join(out, "MARK.PVM"), "rb").read()
    texs, i = [], 0
    while True:
        j = pvm.find(b"PVRT", i)
        if j < 0:
            break
        texs.append(Image.fromarray(P.decode_pvrt(pvm, j)))
        i = j + 4
    tanim2 = [struct.unpack_from("<10h", parts + new_parts, k * 20)
              for k in range(len(parts + new_parts) // 20)]
    signs2 = read_signs(open(os.path.join(out, "MARK.DAT"), "rb").read())
    shown = [recs[0] for _, recs in CAPTIONS]
    cols, cw, ch = 6, 190, 110
    check = Image.new("RGB", (cols * cw, -(-len(shown) // cols) * ch), (70, 90, 110))
    for k, s in enumerate(shown):
        ox, oy = (k % cols) * cw - 5, (k // cols) * ch - 165
        for p, x, y in signs2[s]:
            sx, sy, cx, cy, u1, v1, u2, v2, t, _ = tanim2[p]
            T = texs[t]
            f = T.width / 256.0
            crop = T.crop((int(u1 * f), int(v1 * f), int(u2 * f), int(v2 * f))).resize((sx, sy))
            check.paste(crop, (ox + int(x - cx), oy + int(y - cy)), crop)
    check.save(os.path.join(out, "check.png"))
    print("%d captions, %d parts from %d, %d distinct 2x2 blocks, %d textures"
          % (len(CAPTIONS), len(rects), first, distinct, len(texs)))


if __name__ == "__main__":
    main()
