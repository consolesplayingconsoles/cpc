#!/usr/bin/env python3
"""Repaint the departure-board plates (OBJstart*, CG1.ROM VQ textures) with Zoinkity and mikeryan's Densha de Go! 64 English.

    repaint_cg1_plates.py <SPRITE.LST> <TBL.ROM> <CG1.ROM> <out TBL.ROM> <out CG1.ROM> [preview-dir]

A PORT (CLAUDE.md section 11): every string is Zoinkity and mikeryan's, from the DDG64 plate texture with the same Japanese
(469-508, the board header 468), in the same order as the Dreamcast records. No wording here is Claude's.

CG1 textures are 256x256 VQ (ARGB1555): one 256-entry codebook of 2x2 blocks per texture. A plate is painted in RGB
(its own background restored row by row, so the split-flap line behind the letters survives; the English blended
between the plate's text and background colours), then re-tiled: a tile that already exists keeps its id, new
tiles take the slots only these plates used. Each touched texture keeps every codebook entry that untouched tiles
use; only the entries used by nothing else are re-fitted to the new blocks (k-means), so every other sprite on the
texture decodes exactly as before.
"""
import os, struct, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image
import ddg_assets as A
from dc import pvr_codec as P
import repaint_cg2 as R

WHITE, BLACK = (248, 248, 248), (0, 0, 0)
DARK = dict(box=(6, 11, 122, 39), clear=(6, 6, 122, 42), text="light", fill=WHITE, cap=20)         # white letters on the black plate: kept to
                                                                            # two tile rows, or the English outgrows the
                                                                            # 520 slots the plates free (CG1 has no others)
TWO = dict(DARK, box=(6, 6, 122, 42), cap=13, lead=1.25)                    # the DDG64 two-line plates
SER = dict(DARK, split=((6, 11, 56, 39), (58, 11, 122, 39)))                # "NNN Series": the number right-aligned,
                                                                            # "Series" at one spot on every plate, so
                                                                            # its tiles are shared (slots are scarce)
PINK = dict(DARK, box=(12, 11, 116, 39), clear=(12, 5, 116, 43), colour=True)   # こまち: white on pink
GREEN = PINK                                                                # やまびこ: white on green
HAKU = dict(DARK, haku=True)                                                # 特急はくたか: the DDG64 red "Ltd" badge + black
                                                                            # Hakutaka on the white box

PLATES = {  # record: (English, DDG64 number, style); verbatim
    "OBJstart01": ("Tokyo", 469, DARK), "OBJstart02": ("Ueno", 470, DARK), "OBJstart03": ("Yokohama", 471, DARK),
    "OBJstart04": ("Osaka", 472, DARK), "OBJstart05": ("Shinjuku", 473, DARK), "OBJstart06": ("Kobe", 474, DARK),
    "OBJstart07": ("Express", 475, DARK), "OBJstart08": ("Local", 476, DARK),
    "OBJstart09": ("223 Series", 477, SER), "OBJstart10": ("209 Series", 478, SER),
    "OBJstart11": ("221 Series", 479, SER), "OBJstart12": ("205 Series", 480, SER),
    "OBJstart17": ("Akita", 484, DARK), "OBJstart18": ("Omagari", 485, DARK), "OBJstart19": ("Morioka", 486, DARK),
    "OBJstart20": ("Shin-\nHanamaki", 487, TWO), "OBJstart21": ("Naoetsu", 488, DARK),
    "OBJstart22": ("Muikamachi", 489, DARK), "OBJstart23": ("Echigo-\nYuzawa", 490, TWO),
    "OBJstart24": ("681 Series", 491, SER), "OBJstart25": ("485 Series", 492, SER),
    "OBJstart26": ("200 Series", 493, SER), "OBJstart27": ("E2 Series", 494, SER),     # DDG64 writes it without the '
    "OBJstart28": ("E3 Series", 495, SER), "OBJstart29": ("207 Series", 496, SER),
    "OBJstart30": ("201 Series", 497, SER), "OBJstart31": ("HK100 M.", 498, DARK),
    "OBJstart32": ("701 Series", 499, SER),
    "OBJstart33": (("Ltd", "Hakutaka"), 500, HAKU),
    "OBJstart34": ("Komachi", 501, PINK), "OBJstart35": ("Yamabiko", 502, GREEN),
    "OBJstart36": ("Limited\nExpress", 503, TWO), "OBJstart37": ("Shinagawa", 504, DARK),
    "OBJstart38": ("Uragawara", 505, DARK), "OBJstart39": ("Shibuya", 506, DARK),
    "OBJstart40": ("Osaki", 507, DARK), "OBJstart41": ("Tazawako", 508, DARK),
}
# not yet: OBJstart16 board header (468)


def lum(rgb):
    return rgb[..., 0] * 0.3 + rgb[..., 1] * 0.59 + rgb[..., 2] * 0.11


def paint_plate(rgba, text, st, blank=None):
    """RGBA plate -> repainted RGBA. Dark plates start from the game's own empty plate (OBJstart13: same frame and
    split-flap line, no text); coloured ones clear inside their colour box, row by row. Then the English is drawn in
    st["box"], or split over st["split"] (number right-aligned, last word left-aligned)."""
    if st.get("haku"):
        return paint_haku(rgba, text)
    if st.get("colour"):
        a = rgba.copy()
        cx0, cy0, cx1, cy1 = st["clear"]
        sub = a[cy0:cy1, cx0:cx1, :3].astype(int)
        L = lum(sub)
        chroma = sub.max(2) - sub.min(2)
        for y in range(sub.shape[0]):              # the design is coloured (the box, its brighter split-flap line);
            col = np.nonzero(chroma[y] > 60)[0]    # the text is grey (white letters, grey edges, dark shadow)
            if len(col) < 2:
                continue
            vals = [tuple(p) for p in sub[y][col]]
            mode = max(set(vals), key=vals.count)
            span = np.zeros(sub.shape[1], bool); span[col[0]:col[-1] + 1] = True
            sub[y][span & (chroma[y] <= 60)] = mode     # corners outside the span keep their shape
        a[cy0:cy1, cx0:cx1, :3] = sub
    else:
        a = blank.copy()
    parts = [(st["box"], text, "center")]
    if st.get("split"):
        head, tail = text.rsplit(" ", 1)
        parts = [(st["split"][0], head, "right"), (st["split"][1], tail, "left")]
    for (x0, y0, x1, y1), t, align in parts:
        h, w = y1 - y0, x1 - x0
        cov = R.fit(t, st["cap"], w - 2, h - 2, "center" if align == "right" else align, st.get("lead"),
                    not st.get("lead"))            # one baseline for every plate (Naoetsu sits as high as Uragawara)
        full = np.zeros((h, w))
        if align == "right":
            full[1:1 + cov.shape[0], w - 1 - cov.shape[1]:w - 1] = cov[:, :w - 2]
        else:
            full[1:1 + cov.shape[0], 1:1 + cov.shape[1]] = cov
        alpha = np.clip((full - 0.1) / 0.6, 0, 1)[..., None]
        reg = a[y0:y1, x0:x1, :3].astype(float)
        a[y0:y1, x0:x1, :3] = (reg * (1 - alpha) + np.array(st["fill"]) * alpha).round().astype(np.uint8)
    return a


def _draw(a, box, text, cap, rgb):
    x0, y0, x1, y1 = box
    h, w = y1 - y0, x1 - x0
    cov = R.fit(text, cap, w - 2, h - 2, "center")
    full = np.zeros((h, w)); full[1:1 + cov.shape[0], 1:1 + cov.shape[1]] = cov
    alpha = np.clip((full - 0.1) / 0.6, 0, 1)[..., None]
    reg = a[y0:y1, x0:x1, :3].astype(float)
    a[y0:y1, x0:x1, :3] = (reg * (1 - alpha) + np.array(rgb) * alpha).round().astype(np.uint8)


def paint_haku(rgba, text):
    """OBJstart33: the red 特急 badge (x 8-32) and the white name box (x 32-120), each cleared row by row (the
    split-flap line on row 20 survives), then the DDG64 "Ltd" white on red and "Hakutaka" black on white."""
    a = rgba.copy()
    sub = a[4:36, 8:32, :3].astype(int)                  # badge: the design is red, the text is not
    chroma = sub.max(2) - sub.min(2)
    for y in range(sub.shape[0]):
        col = np.nonzero(chroma[y] > 60)[0]
        if len(col) < 2:
            continue
        vals = [tuple(p) for p in sub[y][col]]
        mode = max(set(vals), key=vals.count)
        span = np.zeros(sub.shape[1], bool); span[col[0]:col[-1] + 1] = True
        sub[y][span & (chroma[y] <= 60)] = mode
    a[4:36, 8:32, :3] = sub
    sub = a[5:35, 33:119, :3].astype(int)                 # name box: dark ink out, each row's own light tone back
    L = lum(sub)
    for y in range(sub.shape[0]):
        keep = [tuple(p) for p in sub[y][L[y] >= 120]]
        if keep:
            mode = max(set(keep), key=keep.count)
            sub[y][L[y] < 120] = mode
    a[5:35, 33:119, :3] = sub
    badge, name = text
    _draw(a, (9, 6, 31, 34), badge, 12, WHITE)
    _draw(a, (34, 7, 118, 33), name, 20, BLACK)
    return a


def to1555(rgba):
    return P.pack_argb1555(rgba)


# --- VQ texture pages ------------------------------------------------------------------------------------

def vq_read(cg, off):
    """PVRT VQ 256x256 at off -> (codebook (256, 4) u16, index grid (128, 128) u8)."""
    d = off + 16
    cb = np.frombuffer(cg, "<u2", 256 * 4, d).reshape(256, 4).copy()
    raw = np.frombuffer(cg, "u1", 128 * 128, d + 2048)
    s = P.twiddle_table(128)
    idx = raw[((s[None, :] << 1) | s[:, None])].copy()          # idx[by, bx]
    return cb, idx


def vq_write(cg, off, cb, idx):
    s = P.twiddle_table(128)
    raw = np.zeros(128 * 128, np.uint8)
    raw[((s[None, :] << 1) | s[:, None])] = idx
    cg[off + 16:off + 16 + 2048] = cb.astype("<u2").tobytes()
    cg[off + 16 + 2048:off + 16 + 2048 + 16384] = raw.tobytes()


def quads(tile):
    """(16, 16) u16 tile -> (8, 8, 4) quads in codebook order TL, BL, TR, BR."""
    return np.stack([tile[0::2, 0::2], tile[1::2, 0::2], tile[0::2, 1::2], tile[1::2, 1::2]], -1)


def tile_px(cb, idx, slot):
    ty, tx = divmod(slot, 16)
    q = cb[idx[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8]]
    t = np.zeros((16, 16), np.uint16)
    t[0::2, 0::2] = q[..., 0]; t[1::2, 0::2] = q[..., 1]; t[0::2, 1::2] = q[..., 2]; t[1::2, 1::2] = q[..., 3]
    return t


def q_rgb(q):
    """u16 quads (..., 4) -> float features (..., 16): A, R, G, B per texel."""
    q = q.astype(np.int64)
    return np.concatenate([((q >> 15) & 1) * 31, (q >> 10) & 31, (q >> 5) & 31, q & 31], -1).astype(float)


def fit_codes(blocks, k, rng=np.random.RandomState(7)):
    """Unique new quads -> at most k centroid quads (u16), Lloyd's k-means with farthest-first seeding."""
    feats = q_rgb(blocks)
    if len(blocks) <= k:
        return blocks.copy()
    cent = [feats[0]]
    dmin = ((feats - cent[0]) ** 2).sum(1)
    for _ in range(k - 1):
        cent.append(feats[int(dmin.argmax())]); dmin = np.minimum(dmin, ((feats - cent[-1]) ** 2).sum(1))
    cent = np.array(cent)
    for _ in range(20):
        lab = ((feats[:, None, :] - cent[None]) ** 2).sum(2).argmin(1)
        for j in range(k):
            if (lab == j).any():
                cent[j] = feats[lab == j].mean(0)
    A_ = (np.clip(cent[:, 0:4], 0, 31) > 15).astype(np.int64)
    R_ = np.clip(cent[:, 4:8], 0, 31).round().astype(np.int64)
    G_ = np.clip(cent[:, 8:12], 0, 31).round().astype(np.int64)
    B_ = np.clip(cent[:, 12:16], 0, 31).round().astype(np.int64)
    return ((A_ << 15) | (R_ << 10) | (G_ << 5) | B_).astype(np.uint16)


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
    freeable = sorted(t for t, u in users.items() if u <= set(PLATES) and t // 256 in (45, 46, 47))

    pages = {p: vq_read(cg, ents[p][0]) for p in sorted({t // 256 for t in freeable})}
    existing = {}                                  # any VQ texture's tile can be reused: a record mixes textures
    for p, (o, s_) in enumerate(ents):
        if cg[o + 9] == 3:
            cb, idx = pages.get(p) or vq_read(cg, o)
            for s in range(256):
                existing.setdefault(tile_px(cb, idx, s).tobytes(), p * 256 + s)

    blank = np.asarray(sp.render("OBJstart13")).copy()     # the game's empty plate
    new = {}
    for name, (text, num, st) in PLATES.items():
        rgba = np.asarray(sp.render(name)).copy()
        out = paint_plate(rgba, text, st, blank)
        new[name] = to1555(out)
        if preview:
            os.makedirs(preview, exist_ok=True)
            Image.fromarray(P._unpack(new[name], 0), "RGBA").save(os.path.join(preview, name + ".png"))

    placed, ids_for, pool = {}, {}, list(freeable)
    kept = set()
    for name, v in new.items():
        w, h, _ = sp.tilemap(name)
        for k in range(w * h):
            px = v[(k // w) * 16:(k // w) * 16 + 16, (k % w) * 16:(k % w) * 16 + 16].tobytes()
            if px in existing and existing[px] in freeable:
                kept.add(existing[px])
    pool = [t for t in freeable if t not in kept]
    assigned = {}                                  # tile id -> (16, 16) u16 pixels to encode
    for name, v in new.items():
        w, h, _ = sp.tilemap(name)
        ids = []
        for k in range(w * h):
            tile = v[(k // w) * 16:(k // w) * 16 + 16, (k % w) * 16:(k % w) * 16 + 16]
            key = tile.tobytes()
            if key not in placed:
                if key in existing:
                    placed[key] = existing[key]
                else:
                    if not pool:
                        need = len({v2[(k2 // w2) * 16:(k2 // w2) * 16 + 16, (k2 % w2) * 16:(k2 % w2) * 16 + 16].tobytes()
                                    for n2, v2 in new.items() for w2, h2, _ in [sp.tilemap(n2)] for k2 in range(w2 * h2)}
                                   - set(existing))
                        raise SystemExit("out of CG1 tile slots: %d new tiles, %d slots free (%d freed, %d kept)"
                                         % (need, len(freeable) - len(kept), len(freeable), len(kept)))
                    t = pool.pop(0); placed[key] = t; assigned[t] = tile
            ids.append(placed[key])
        ids_for[name] = ids

    for p, (cb, idx) in pages.items():
        mine = {t % 256 for t in freeable if t // 256 == p}
        keep_codes = set()
        for s in range(256):
            if s not in mine:
                ty, tx = divmod(s, 16)
                keep_codes.update(idx[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8].ravel().tolist())
        free_codes = [c for c in range(256) if c not in keep_codes]
        slots = {t % 256: tile for t, tile in assigned.items() if t // 256 == p}
        blocks = np.array(sorted({tuple(q) for tile in slots.values() for q in quads(tile).reshape(-1, 4)}), np.uint16)
        cands = cb[sorted(keep_codes)] if keep_codes else np.zeros((0, 4), np.uint16)
        exact = {tuple(q) for q in cands}
        todo = np.array([b for b in blocks if tuple(b) not in exact], np.uint16).reshape(-1, 4)
        cents = fit_codes(todo, len(free_codes)) if len(todo) else np.zeros((0, 4), np.uint16)
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
    print("%d plates, %d slots freed, %d kept, %d rewritten" % (len(PLATES), len(freeable), len(kept), len(assigned)))


if __name__ == "__main__":
    if len(sys.argv) not in (6, 7):
        sys.exit(__doc__)
    main(*sys.argv[1:])
