#!/usr/bin/env python3
"""Grey out KEY CONFIGURE in SYSTEM/MENU.PVM, for the Tokyo BS Guide mod, which fixes the
controls and skips that OPTION row (01a148_option.c).

    /usr/bin/python3 grey_key_configure.py <MENU.PVM> <output MENU.PVM> [preview.png]

Run on the original sheet for the mod layer (tokyo-bs-guide/disc), on the translation's for
the English mod (tokyo-bs-guide-en/disc). The OPTION buttons sit on the sheet twice, picked
(bright) and not (dark); both KEY CONFIGURE buttons become their own brightness pulled
toward grey, alpha kept, so the row reads as disabled.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
import numpy as np
from PIL import Image
from dc import pvr_codec as P

BUTTONS = [(167, 407, 331, 443), (167, 447, 331, 483)]   # picked, not picked (x0, y0, x1, y1)


def main(src, dst, preview=None):
    d = bytearray(open(src, "rb").read())
    off, w, h, pf = P.find_chunk(bytes(d), 0)
    a = P.decode_argb4444(bytes(d), off, w, h).astype(np.float32)
    for x0, y0, x1, y1 in BUTTONS:
        box = a[y0:y1 + 1, x0:x1 + 1]
        lum = box[..., 0] * 0.299 + box[..., 1] * 0.587 + box[..., 2] * 0.114
        grey = lum * 0.5 + 64.0
        for c in range(3):
            box[..., c] = np.where(box[..., 3] > 0, grey, box[..., c])
    img = np.clip(a, 0, 255).astype(np.uint8)
    d[off:off + w * h * 2] = P.encode_argb4444(img)
    if len(d) != os.path.getsize(src):
        raise SystemExit("file size changed")
    open(dst, "wb").write(bytes(d))
    if preview:
        Image.fromarray(img).convert("RGB").crop((0, 380, 520, 500)).save(preview)
    print("wrote %s" % dst)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(*sys.argv[1:4])
