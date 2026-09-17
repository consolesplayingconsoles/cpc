#!/usr/bin/env python3
"""Build a Universal Dreamcast Patcher `.dcp` from the LIVE translation state -- runs on the Lab (Mac).

A `.dcp` is a zip holding one `<disc path>.xdelta` (VCDIFF) per changed file, the layout UDP's own
"Build Patch" tab writes (verified: every delta of the released v0.6-Beta decodes with xdelta3, lzma
secondary compression). This rebuilds the exact files translate.sh splices into the image -- the text
packers (build_patch.py), the glyph font (fon_codec.py), the committed textures and the SOD banner
chunk -- diffs each against the original, and zips the deltas. It has to run where `xdelta3` is
(Homebrew `xdelta` on the Lab); Batocera has none.

    make_dcp.py <game-name | state.json> <originals-root> <textures-dir> <out.dcp> [api_base]

<originals-root> = the disc's extracted files (e.g. STORY.PAC, DOUGU/ITEMTBL.PAC). Every delta is decoded
back and byte-compared with its patched file before the zip is written; any mismatch aborts.
"""
import sys, os, re, io, glob, json, shutil, hashlib, zipfile, tempfile, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))                  # pluto-translate
sys.path.insert(0, HERE)                                    # dc
import build_patch, fon_codec, texture_targets
from splice_pac_chunk import nth_pvrt_offset

XDELTA = shutil.which("xdelta3")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def xdelta(args):
    r = subprocess.run([XDELTA] + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode != 0:
        raise SystemExit("xdelta3 %s failed: %s" % (" ".join(args[:2]), r.stderr.decode(errors="replace").strip()))


def window(size):
    """Source window big enough to hold the whole original, so a same-size patch deltas to a few KB
    (the default 64 MB window would miss matches in STORYGRA.PAC, ~465 MB)."""
    return str(max(size, 1 << 26))


def main():
    if len(sys.argv) < 5:
        raise SystemExit("usage: make_dcp.py <game-name | state.json> <originals-root> <textures-dir> <out.dcp> [api_base]")
    if not XDELTA:
        raise SystemExit("xdelta3 not found (brew install xdelta)")
    state_arg, orig_root, tex_dir, out_dcp = sys.argv[1:5]
    api_base = sys.argv[5] if len(sys.argv) > 5 else "http://localhost:7700"
    if not os.path.isdir(orig_root):
        raise SystemExit("no originals at %s" % orig_root)

    work = tempfile.mkdtemp(prefix="dcp-")
    try:
        patch = os.path.join(work, "patch")
        os.makedirs(patch)
        # 1. text files from the live state -- the same script translate.sh runs on the box
        r = subprocess.run([sys.executable, os.path.join(HERE, "build_patch.py"), state_arg, orig_root, patch, api_base],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        print(r.stdout.decode(errors="replace").rstrip())
        if r.returncode != 0:
            raise SystemExit("build_patch.py failed")
        lang = build_patch._lang(build_patch.load_state(state_arg, api_base))

        # 2. glyph font (only games that ship S18RM04.FON)
        font = os.path.join(orig_root, "S18RM04.FON")
        if os.path.isfile(font):
            open(os.path.join(patch, "S18RM04.FON"), "wb").write(
                fon_codec.build_patched_font(open(font, "rb").read(), lang))

        # 3. committed textures, onto the same disc copies translate.sh patches (shared helper)
        tex_glob = glob.escape(tex_dir)            # project dirs carry "[ca]"/"[en]", which glob reads as a char class
        for tex in sorted(glob.glob(os.path.join(tex_glob, "*.PVR")) + glob.glob(os.path.join(tex_glob, "*.PVM"))):
            for rel, data in texture_targets.targets(orig_root, tex):
                dst = os.path.join(patch, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                open(dst, "wb").write(data)

        # 4. PAC chunks shipped as <PAC>_c<index>.bin (the SOD banner): a copy of the PAC with that chunk
        #    written at the same offset splice_pac_chunk.py uses (n-th PVRT + 16)
        for chunk in sorted(glob.glob(os.path.join(tex_glob, "*_c*.bin"))):
            m = re.match(r"^(.+)_c(\d+)\.bin$", os.path.basename(chunk))
            pac = os.path.join(orig_root, m.group(1) + ".PAC") if m else ""
            if not (m and os.path.isfile(pac)):
                continue
            j = nth_pvrt_offset(pac, int(m.group(2)))
            if j < 0:
                raise SystemExit("chunk #%s not found in %s" % (m.group(2), pac))
            dst = os.path.join(patch, os.path.basename(pac))
            if not os.path.exists(dst):
                shutil.copyfile(pac, dst)
            with open(dst, "r+b") as f:
                f.seek(j + 16)
                f.write(open(chunk, "rb").read())

        # 5. one verified delta per file that actually changed
        deltas = []
        for dirpath, _, files in os.walk(patch):
            for fn in files:
                p = os.path.join(dirpath, fn)
                rel = os.path.relpath(p, patch).replace(os.sep, "/")
                o = os.path.join(orig_root, rel)
                if not os.path.isfile(o):
                    print("  (no original for %s -- left out)" % rel)
                    continue
                want = sha256(p)
                if os.path.getsize(o) == os.path.getsize(p) and sha256(o) == want:
                    continue
                d = os.path.join(work, "deltas", rel + ".xdelta")
                os.makedirs(os.path.dirname(d), exist_ok=True)
                w = window(os.path.getsize(o))
                xdelta(["-e", "-f", "-9", "-S", "lzma", "-B", w, "-s", o, p, d])
                back = d + ".check"
                xdelta(["-d", "-f", "-B", w, "-s", o, d, back])
                if sha256(back) != want:
                    raise SystemExit("VERIFY FAILED: %s delta does not rebuild the patched file" % rel)
                os.remove(back)
                deltas.append((rel, d))

        if not deltas:
            raise SystemExit("nothing differs from the originals -- no patch written")
        os.makedirs(os.path.dirname(os.path.abspath(out_dcp)), exist_ok=True)
        tmp_zip = out_dcp + ".tmp"
        with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED) as z:
            for rel, d in sorted(deltas):
                z.write(d, rel + ".xdelta")
        os.replace(tmp_zip, out_dcp)
        print("  dcp: %d deltas, %d B -> %s" % (len(deltas), os.path.getsize(out_dcp), out_dcp))
        for rel, d in sorted(deltas):
            print("    %-22s %8d B" % (rel, os.path.getsize(d)))
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
