#!/usr/bin/env python3
"""Build the translated CDI from the LIVE state -- the CDI twin of what translate.sh does for a GDI.

    build_cdi.py <game-name | state.json> <base-cdi> <gdi-originals> <textures-dir> <out.cdi> [api_base]

Same in-place rule as the GDI build: never rebuild the image, splice each same-size file straight
into the sectors it already occupies (dc/inplace_cdi.py), so no LBA moves and the game's hardcoded
disc positions still resolve.

THE ONE THING THIS DOES DIFFERENTLY, and the reason it is a separate script: a CDI is a CONVERSION
of the GD-ROM, and the conversion edits the game. This disc's 1ST_READ.BIN carries 12 bytes of
self-boot patch that the GD-ROM's copy does not have. Build the executable from the GDI's copy and
you revert those bytes, the game looks for a GD-ROM, does not find one, and the console drops to the
BIOS -- with every file verifying perfectly on the way, because it was written exactly as asked.

So step 1 here is to read each file's ORIGINAL BYTES BACK OUT OF THE CDI and build the patch against
those. The GDI extract is only ever a locator: it says what to look for and how long it is. Anything
the conversion changed is then carried through untouched, whatever it turns out to be, on this disc
or the next one.

Textures and the PAC chunks come from the same committed textures dir translate.sh fetches, so the
GDI and CDI builds ship the same artwork.
"""
import sys, os, re, glob, shutil, tempfile, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))                  # pluto-translate
sys.path.insert(0, HERE)                                    # dc
import build_patch, fon_codec, texture_targets, inplace_cdi


def dump_originals(image, gdi_root, rels, dest):
    """Write this IMAGE's own copy of each file in `rels` to `dest`, located by the GDI copy.

    Returns (dumped, diverged): `diverged` are the files whose bytes differ from the GDI's. Those
    are exactly the ones a GDI-sourced build would silently clobber, so they are reported, not
    hidden -- if a disc ever diverges in a file we also rewrite, you want to read about it here."""
    import mmap
    dumped, diverged = [], []
    fd = os.open(image, os.O_RDONLY)
    mm = mmap.mmap(fd, 0, access=mmap.ACCESS_READ)
    try:
        for rel in rels:
            src = os.path.join(gdi_root, rel)
            if not os.path.isfile(src):
                continue
            gdi = open(src, "rb").read()
            start = inplace_cdi.find_file(mm, gdi[:inplace_cdi.USER])
            if start < 0:
                continue                                    # not on this disc; the splice will skip it too
            own = inplace_cdi.deinterleave(mm, start, 0, len(gdi))
            out = os.path.join(dest, rel)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            open(out, "wb").write(own)
            dumped.append(rel)
            if own != gdi:
                n = sum(1 for i in range(len(gdi)) if own[i] != gdi[i])
                diverged.append((rel, n))
    finally:
        mm.close(); os.close(fd)
    return dumped, diverged


def splice_set(gdi_root):
    """Every file the build rewrites: the packer sources plus the font. Texture copies are worked
    out per texture by texture_targets, and the big PACs are patched chunk-wise, not whole."""
    rels = [spec[0] for spec in build_patch.PLAN.values()]
    rels.append("S18RM04.FON")
    seen, out = set(), []
    for rel in rels:                                        # PLAN has two entries for 1ST_READ.BIN
        if rel not in seen:
            seen.add(rel); out.append(rel)
    return out


def main():
    if len(sys.argv) < 6:
        raise SystemExit("usage: build_cdi.py <game-name | state.json> <base-cdi> <gdi-originals> "
                         "<textures-dir> <out.cdi> [api_base]")
    state_arg, base_cdi, gdi_root, tex_dir, out_cdi = sys.argv[1:6]
    api_base = sys.argv[6] if len(sys.argv) > 6 else "http://localhost:7700"
    for p, what in ((base_cdi, "base CDI"), (gdi_root, "originals")):
        if not os.path.exists(p):
            raise SystemExit("no %s at %s" % (what, p))

    work = tempfile.mkdtemp(prefix="cdi-")
    try:
        orig = os.path.join(work, "orig"); patch = os.path.join(work, "patch")
        os.makedirs(orig); os.makedirs(patch)

        print("[1/5] copy base image -> %s" % out_cdi)
        os.makedirs(os.path.dirname(os.path.abspath(out_cdi)), exist_ok=True)
        shutil.copyfile(base_cdi, out_cdi)

        print("[2/5] read this image's own originals (the GDI extract only locates them)")
        rels = splice_set(gdi_root)
        # every texture's disc copies are rewritten too, so their originals must come from here as well
        tex_glob = glob.escape(tex_dir)
        textures = sorted(glob.glob(os.path.join(tex_glob, "*.PVR")) + glob.glob(os.path.join(tex_glob, "*.PVM")))
        for tex in textures:
            rels += [rel for rel, _ in texture_targets.targets(gdi_root, tex)]
        dumped, diverged = dump_originals(base_cdi, gdi_root, rels, orig)
        print("  %d files read from the image" % len(dumped))
        for rel, n in diverged:
            print("  NOTE %s differs from the GD-ROM copy by %d bytes -- patching THIS disc's version "
                  "(that is the self-boot patch; building from the other copy would revert it)" % (rel, n))
        if not diverged:
            print("  (nothing diverges from the GD-ROM copy on this disc)")

        print("[3/5] build patched files from the live state")
        r = subprocess.run([sys.executable, os.path.join(HERE, "build_patch.py"), state_arg, orig, patch, api_base],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        print(r.stdout.decode(errors="replace").rstrip())
        if r.returncode != 0:
            raise SystemExit("build_patch.py failed")
        lang = build_patch._lang(build_patch.load_state(state_arg, api_base))
        font = os.path.join(orig, "S18RM04.FON")
        if os.path.isfile(font):
            open(os.path.join(patch, "S18RM04.FON"), "wb").write(
                fon_codec.build_patched_font(open(font, "rb").read(), lang))

        print("[4/5] splice same-size files, textures and PAC chunks")
        for rel in sorted(set(splice_set(gdi_root))):
            if os.path.isfile(os.path.join(patch, rel)) and os.path.isfile(os.path.join(orig, rel)):
                inplace_cdi.patch_file(out_cdi, os.path.join(orig, rel), os.path.join(patch, rel))
        for tex in textures:
            for rel, data in texture_targets.targets(orig, tex):
                dst = os.path.join(patch, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                open(dst, "wb").write(data)
                inplace_cdi.patch_file(out_cdi, os.path.join(orig, rel), dst)
        # chunks inside the big PACs (opening lines, SOD banner): the PAC is never dumped or loaded,
        # and the splice confirms the original chunk bytes sit where expected before it writes.
        for chunk in sorted(glob.glob(os.path.join(tex_glob, "*_c*.bin"))):
            m = re.match(r"^(.+)_c(\d+)\.bin$", os.path.basename(chunk))
            pac = os.path.join(gdi_root, m.group(1) + ".PAC") if m else ""
            if m and os.path.isfile(pac):
                inplace_cdi.patch_chunk(out_cdi, pac, chunk, int(m.group(2)))

        print("[5/5] verify")
        if os.path.getsize(out_cdi) != os.path.getsize(base_cdi):
            raise SystemExit("image changed size (%d -> %d): refusing to call this a build"
                             % (os.path.getsize(base_cdi), os.path.getsize(out_cdi)))
        print("  size unchanged (%d bytes)" % os.path.getsize(out_cdi))
        print("DONE: %s" % out_cdi)
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
