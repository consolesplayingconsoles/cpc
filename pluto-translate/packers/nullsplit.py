#!/usr/bin/env python3
"""`nullsplit` packer -- write side for SCP/CMD script containers (STORY.PAC).

Reader (`parsers/nullsplit.py`) finds dialogue as Shift-JIS runs; this puts the
Catalan back by INDEX REWRITE, one level deeper than ptrtable:

  STORY.PAC = container of SCP scenario records (sector-aligned, 0x800).
    SCP = section table -> [ASM script][CMD command stream]   (CMD is always last).
      CMD = `CMD\\0` + u32 size + u32 POINTER TABLE -> contiguous variable-size
            commands; ~1 in 7 carry text (`02 ff <spk>` + SJIS).

Safe because the script addresses commands BY INDEX through the CMD pointer table
(verified: internal "byte offsets" are all coincidental spans), so growing a text
command and bumping the later table entries preserves control flow.

Two modes:
  * grow=False  -- THE ONLY VIABLE MODE. Keep each scenario's size CONSTANT, greedily
    fill its trailing zero-slack line-by-line; lines that don't fit stay Japanese.
    Coverage ~40% (slack-bound, confirmed on screen 2026-06-28: loads + accents +
    placement). Two musts: (a) CLAMP each run to its command boundary -- the reader
    over-reads ~4B past a 04ff into the next command (see local_by below); (b) the
    encoder paginates (box=15, 04ff every 2 lines) so text fits the box. Past 40% needs
    a half-width font (halve byte cost), NOT relocation. `pack(orig, [], grow=False) == orig`.
  * grow=True   -- ABANDONED. Grows scenarios + re-concatenates sector-aligned (would be
    100%) but the game locates scenarios by HARDCODED offsets, not by scanning `SCP\\0`,
    so the rebuild CRASHES (confirmed 2026-06-28). Kept only as a round-trip identity check.

Per scenario we rewrite: the CMD pointer table, the `CMD\\0` size, the SCP section
table's CMD size, and rec0's u32 script-length marker. ASM is untouched.

    pack(orig, blocks, encode, box=13, grow=False) -> (bytes, stats)
"""
import struct, bisect

LB = b"\x01\xff"          # in-box line break
PB = b"\x04\xff"          # page break (wait-for-input); the game's box holds ~2 lines/page


def _scp_records(d):
    out, i = [], 0
    while True:
        j = d.find(b"SCP\x00", i)
        if j < 0:
            break
        out.append(j); i = j + 4
    return out


def budget(orig):
    """Static per-scenario fit budget for the box-budget UI (computed at EXTRACT time, not a
    live endpoint). Returns {"scenes": [{"scene": idx, "slack": bytes}], "starts": [offset,...]}.
    `slack` = the spare bytes a scenario can absorb (Catalan expansion ceiling, keeping it
    0x800-aligned so the others don't move). `starts` lets the UI map a block offset -> scene by
    bisect. The live fill (sum of encoded Catalan) is measured against `slack` on save."""
    recs = _scp_records(orig)
    bounds = [(recs[i], recs[i + 1] if i + 1 < len(recs) else len(orig))
              for i in range(len(recs))]
    scenes = []
    for idx, (s, e) in enumerate(bounds):
        secs = _sections(orig, s)
        slack = 0
        if secs and orig[s + secs[-1][0]:s + secs[-1][0] + 4] == b"CMD\x00":
            coff, csz = secs[-1]
            slack = e - (s + coff + csz)
        scenes.append({"scene": idx, "slack": slack})
    return {"scenes": scenes, "starts": recs}


def measure(orig, blocks, encode, box=15):
    """Per-scene Catalan EXPANSION the build will actually pay -- the meter's authoritative `used`.
    Same per-block cost as pack(grow=False): clamp each run to its command, encode via `_newrun`
    (pages + the game's control bytes + trailing transition), minus the clamped jpBytes. Returns
    {"scene": {scene_index: bytes}, "line": {block_offset: bytes}} -- the per-scene total for the box
    meter AND the per-line expansion so the UI can show the running cumulative toward slack. This is
    why the numbers must come from here, not a UI estimate that ignores the control bytes."""
    recs = _scp_records(orig)
    bounds = [(recs[i], recs[i + 1] if i + 1 < len(recs) else len(orig))
              for i in range(len(recs))]
    items = sorted(((int(b["offset"], 16) if isinstance(b["offset"], str) else b["offset"]), b)
                   for b in blocks if (b.get("ca") or "").strip())
    keys = [k for k, _ in items]
    scene, line = {}, {}
    for idx, (s, e) in enumerate(bounds):
        scene[idx] = 0
        secs = _sections(orig, s)
        if not secs or orig[s + secs[-1][0]:s + secs[-1][0] + 4] != b"CMD\x00":
            continue
        coff, csz = secs[-1]
        cmd_abs = s + coff
        cmd = orig[cmd_abs:cmd_abs + csz]
        first = struct.unpack_from("<I", cmd, 8)[0]
        if first < 12 or first > len(cmd):
            continue
        ntbl = (first - 8) // 4
        cb = sorted(struct.unpack_from("<%dI" % ntbl, cmd, 8)) + [len(cmd)]
        lo, hi = bisect.bisect_left(keys, cmd_abs), bisect.bisect_left(keys, cmd_abs + csz)
        for k, b in items[lo:hi]:
            rel = k - cmd_abs
            ce = cb[bisect.bisect_right(cb, rel)]
            jpb = min(b["jpBytes"], ce - rel)
            exp = len(_newrun(b["ca"], encode, box, cmd[rel:rel + jpb])) - jpb
            scene[idx] += exp
            line[b["offset"]] = exp
    return {"scene": scene, "line": line}


def _sections(d, base):
    hdr = struct.unpack_from("<8I", d, base)
    secs, k = [], 2
    while k + 1 < 8 and hdr[k] != 0:
        secs.append((hdr[k], hdr[k + 1])); k += 2
    return secs


def _wrap(text, width):
    out, cur = [], ""
    for w in text.split(" "):
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= width:
            cur += " " + w
        else:
            out.append(cur); cur = w
    if cur:
        out.append(cur)
    return out


MID = LB + PB + LB        # 01ff 04ff 01ff — the game's page-break grammar (line, page, line)


def _enc(ca, encode, width, height=3):
    """Wrap to the box WIDTH (01ff line breaks) and paginate to the box HEIGHT, joining pages
    with the game's native `01ff 04ff 01ff` grammar — NOT a bare 04ff, which fails to advance
    the box and bleeds one message into the next. ~2-line box keeps the text in place. The
    message-end transition to the next speaker is restored by `_tail` (see `_newrun`)."""
    lines = _wrap(ca, width)
    pages = [lines[i:i + height] for i in range(0, len(lines), height)]
    return MID.join(LB.join(encode(l) for l in page) for page in pages)


def _tail(run):
    """Trailing control-code suffix of an original run (01ff/04ff/00ff pairs after the last
    text byte). Re-appended to the Catalan so the box-advance into the NEXT speaker's message
    is preserved exactly, instead of the Catalan running into the next box."""
    i = len(run)
    while i >= 2 and run[i - 2:i] in (LB, PB, b"\x00\xff"):
        i -= 2
    return run[i:]


def _newrun(ca, encode, width, run, height=3):
    """Replacement bytes for one original text run: wrap to the box WIDTH, paginate at HEIGHT lines
    per box (the box holds 3; more overflows the screen), join boxes with the game's `01ff 04ff 01ff`
    page-break grammar, and re-append the run's own trailing control so the handoff to the next
    message is exact. The box COUNT is free to differ from the original -- an earlier version forced
    it to match (to dodge a hang) and that crammed 4+ lines into a 3-line box; the hang turned out to
    be the GDI rebuild, not pagination (see [[project_dc_translation_extraction]]), so pagination is
    back to natural: never more than `height` lines per box."""
    tail = _tail(run)
    lines = _wrap(ca, width)
    pages = [lines[i:i + height] for i in range(0, len(lines), height)] or [[]]
    return MID.join(LB.join(encode(l) for l in pg) for pg in pages) + tail


def _rebuild_cmd(cmd, cmd_abs, local_by, encode, box):
    """Rebuild a CMD section with the Catalan spliced in + the table/markers repointed.
    `local_by`: {cmd-relative text offset -> block}. Returns (new_cmd_bytes, n_placed)."""
    first = struct.unpack_from("<I", cmd, 8)[0]
    ntbl = (first - 8) // 4
    tbl = list(struct.unpack_from("<%dI" % ntbl, cmd, 8))
    cstarts = tbl + [len(cmd)]
    new_cmds, placed = [], 0
    for i in range(ntbl):
        cs, ce = cstarts[i], cstarts[i + 1]
        rels = sorted(r for r in local_by if cs <= r < ce)     # ALL text runs in this command
        if not rels:
            new_cmds.append(cmd[cs:ce]); continue
        nb, pos = bytearray(), cs
        for r in rels:
            b = local_by[r]
            nb += cmd[pos:r]                                    # bytes before this run
            nb += _newrun(b["ca"], encode, box, cmd[r:r + b["jpBytes"]])   # Catalan + kept tail
            pos = r + b["jpBytes"]                              # skip the original run
        nb += cmd[pos:ce]                                       # command tail
        new_cmds.append(bytes(nb)); placed += len(rels)
    delta = sum(len(c) for c in new_cmds) - (len(cmd) - first)
    new_tbl, off = [0] * ntbl, first
    for i in range(ntbl):
        new_tbl[i] = off; off += len(new_cmds[i])
    nc = bytearray(cmd[:8])
    for v in new_tbl:
        nc += struct.pack("<I", v)
    for c in new_cmds:
        nc += c
    struct.pack_into("<I", nc, 4, len(nc))                     # CMD size field
    # rec0's first u32 is a script-length / end marker ONLY when it points near the CMD
    # end; for most scenarios it's an ordinary param in range, which must NOT be bumped.
    m = struct.unpack_from("<I", cmd, first)[0]
    if len(cmd) - 64 <= m <= len(cmd):
        struct.pack_into("<I", nc, first, m + delta)
    return bytes(nc), placed


def pack(orig, blocks, encode, box=13, grow=False, prefer=None):
    # `prefer`: an absolute file offset marking where the game's PLAY actually starts in a
    # scenario (file order != play order). The scene at/after `prefer` fills the scenario's slack
    # FIRST, so the conversation the player sees first is the one that lands in Catalan. A per-game
    # hint (build_patch wires it); without it, fill is file order. TODO: derive play order from the
    # script to drop this hint.
    recs = _scp_records(orig)
    bounds = [(recs[i], recs[i + 1] if i + 1 < len(recs) else len(orig))
              for i in range(len(recs))]
    items = sorted(((int(b["offset"], 16) if isinstance(b["offset"], str) else b["offset"]), b)
                   for b in blocks if (b.get("ca") or "").strip())
    keys = [k for k, _ in items]
    st = dict(scn_total=0, scn_fit=0, scn_overflow=0, lines_placed=0, lines_overflow=0)

    out = bytearray() if grow else bytearray(orig)

    for (s, e) in bounds:
        secs = _sections(orig, s)
        scn = orig[s:e]
        if not secs or orig[s + secs[-1][0]:s + secs[-1][0] + 4] != b"CMD\x00":
            if grow:
                out += scn + b"\x00" * ((-len(scn)) % 0x800)
            continue
        st["scn_total"] += 1
        coff, csz = secs[-1]
        cmd_abs = s + coff
        cmd = orig[cmd_abs:cmd_abs + csz]
        first = struct.unpack_from("<I", cmd, 8)[0]
        if first < 12 or first > len(cmd):
            if grow:
                out += scn + b"\x00" * ((-len(scn)) % 0x800)
            continue
        lo, hi = bisect.bisect_left(keys, cmd_abs), bisect.bisect_left(keys, cmd_abs + csz)
        # CLAMP each block's text run to its command's end: the parser over-reads ~4 bytes
        # past a 04ff page-break into the NEXT command's header; replacing those bytes corrupts
        # the next command. Clamp jpBytes to (command end - rel) so we only touch this command.
        ntbl = (first - 8) // 4
        cb = sorted(struct.unpack_from("<%dI" % ntbl, cmd, 8)) + [len(cmd)]
        local_by = {}
        for k, b in items[lo:hi]:
            rel = k - cmd_abs
            ce = cb[bisect.bisect_right(cb, rel)]            # next command boundary > rel
            bb = dict(b); bb["jpBytes"] = min(b["jpBytes"], ce - rel)
            local_by[rel] = bb

        if grow:
            nc, placed = _rebuild_cmd(cmd, cmd_abs, local_by, encode, box)
            new_scn = bytearray(orig[s:cmd_abs]) + nc          # header + ASM unchanged, new CMD
            hdr = struct.unpack_from("<8I", new_scn, 0); k = 2
            while k + 1 < 8 and hdr[k] != 0:
                if hdr[k] == coff:
                    struct.pack_into("<I", new_scn, (k + 1) * 4, len(nc)); break
                k += 2
            new_scn += b"\x00" * ((-len(new_scn)) % 0x800)
            out += new_scn
            st["scn_fit"] += 1; st["lines_placed"] += placed
        else:
            # FIXED-POSITION: greedily fill the scenario's slack line-by-line (keep the
            # rest Japanese) instead of all-or-nothing. Maximises coverage, stays in-place.
            slack = e - (cmd_abs + len(cmd))

            def _cost(r):
                return (len(_newrun(local_by[r]["ca"], encode, box,
                                    cmd[r:r + local_by[r]["jpBytes"]])) - local_by[r]["jpBytes"])

            # WHOLE-SCENE FIRST: if every line's Catalan fits the slack, place them ALL. Earlier this
            # was blamed for a hang and reverted to a greedy prefix; the hang was actually the GDI
            # REBUILD (now delivered in-place, see [[project_dc_translation_extraction]]), so full
            # coverage is safe. Some lines are SHORTER than the Japanese, so a scene whose TOTAL fits
            # can be left partly Japanese by a prefix fill that quits before the cheap tail.
            if sum(_cost(r) for r in local_by) <= slack:
                sel = dict(local_by)
            else:
                # OVERFLOW ONLY: speaker-aware contiguous prefix -- group lines into TURNS (consecutive
                # same-speakerId), place each whole, STOP at the first that doesn't fit (unbroken run,
                # no holes). `prefer` puts the play-first scene at the front so the visible run is the
                # clean Catalan one; the rest stays Japanese until the operator condenses it to fit.
                sel, cum = {}, 0
                rels = sorted(local_by)
                if prefer is not None and cmd_abs <= prefer < cmd_abs + csz:
                    pr = prefer - cmd_abs                     # play-start, scenario-relative
                    rels = [r for r in rels if r >= pr] + [r for r in rels if r < pr]
                i = 0
                while i < len(rels):
                    spk = local_by[rels[i]].get("speakerId")
                    j = i
                    while j < len(rels) and local_by[rels[j]].get("speakerId") == spk:
                        j += 1
                    turn = rels[i:j]
                    cost = sum(_cost(r) for r in turn)
                    if cum + cost > slack:              # whole turn doesn't fit -> STOP (clean run)
                        break
                    for r in turn:
                        sel[r] = local_by[r]
                    cum += cost; i = j
            nc, placed = _rebuild_cmd(cmd, cmd_abs, sel, encode, box)
            if len(nc) - len(cmd) > slack:                     # safety; should not happen
                st["scn_overflow"] += 1; st["lines_overflow"] += len(local_by); continue
            st["scn_fit"] += 1
            st["lines_placed"] += placed
            st["lines_overflow"] += len(local_by) - len(sel)
            out[cmd_abs:cmd_abs + len(nc)] = nc
            out[cmd_abs + len(nc):e] = b"\x00" * (e - (cmd_abs + len(nc)))
            hdr = struct.unpack_from("<8I", orig, s); k = 2
            while k + 1 < 8 and hdr[k] != 0:
                if hdr[k] == coff:
                    struct.pack_into("<I", out, s + (k + 1) * 4, len(nc)); break
                k += 2
    return bytes(out), st
