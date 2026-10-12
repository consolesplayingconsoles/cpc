#!/usr/bin/env python3
"""Drive a game in RetroArch without touching the Mac: RetroArch's network commands (memory,
pause, frame step, screenshot) and its network gamepad (player 1), both over UDP. Stdlib only.

Every call needs RA_SESSION="<session name>". The name gives the session its own pair of ports
(56000-56799, the same every time), so each session runs its own RetroArch and never talks to
another's. The instance's files (its ports config, screenshots) live in build/retroarch/<port>/,
and RetroArch never saves retroarch.cfg on quit.

    retroarch.py launch IMAGE [CORE]  start RetroArch in the background with IMAGE; the core comes
                                      from the file type (.gdi/.cdi/.chd Flycast, .md/.gen/.smd/.bin
                                      Genesis Plus GX) or CORE (a core name, e.g. flycast)
    retroarch.py port                 this session's command and gamepad ports
    retroarch.py status               playing/paused and the content
    retroarch.py quit                 close this session's RetroArch
    retroarch.py read ADDR [N]        N bytes (default 4) at a console address, e.g. 0C2A44A8
    retroarch.py word ADDR / float ADDR / vec ADDR   a 32-bit word, a float, three floats
    retroarch.py write ADDR HEXBYTES
    retroarch.py pause                toggle pause
    retroarch.py step [N]             advance N frames (paused)
    retroarch.py shot                 take a screenshot, print its path
    retroarch.py press BUTTON [FRAMES]  hold a button for FRAMES frames (default 6), then let go
    retroarch.py hold BUTTON / release BUTTON|all
    retroarch.py stick X Y            left stick, -1..1 each (0 0 centres it)

Buttons use the console's own names: Dreamcast A B X Y START UP DOWN LEFT RIGHT L R; Mega Drive
A B C X Y Z START MODE and the D-pad; any other core takes RetroPad names. Addresses are the
console's: Dreamcast 8C/AC/0C addresses all work, Mega Drive RAM is FF0000-FFFFFF.
"""
import glob
import json
import os
import socket
import struct
import subprocess
import sys
import time
import zlib

HOST = '127.0.0.1'
RA = '/Applications/RetroArch.app'
CORES = os.path.expanduser('~/Library/Application Support/RetroArch/cores')
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SESSION = os.environ.get('RA_SESSION', '').strip()
SLOT = zlib.crc32(SESSION.lower().encode()) % 400
CMD_PORT = 56000 + SLOT * 2
PAD_PORT = CMD_PORT + 1                           # network_remote_base_port + player 1
OWN = os.path.join(REPO, 'build', 'retroarch', str(CMD_PORT))
SHOTS = os.path.join(OWN, 'screenshots')
INSTANCE = os.path.join(OWN, 'instance.json')

# RetroPad ids (RETRO_DEVICE_ID_JOYPAD_*)
RP = {'B': 0, 'Y': 1, 'SELECT': 2, 'START': 3, 'UP': 4, 'DOWN': 5, 'LEFT': 6, 'RIGHT': 7,
      'A': 8, 'X': 9, 'L': 10, 'R': 11, 'L2': 12, 'R2': 13, 'L3': 14, 'R3': 15}
DPAD = {k: RP[k] for k in ('START', 'UP', 'DOWN', 'LEFT', 'RIGHT')}
SYSTEMS = {
    # Flycast: RetroPad B/A/Y/X are Dreamcast A/B/X/Y, the triggers are L2/R2.
    'dc': {'core': 'flycast', 'ext': ('.gdi', '.cdi', '.chd'), 'ram': 0x0C000000, 'mask': 0x1FFFFFFF,
           'pad': dict(DPAD, A=RP['B'], B=RP['A'], X=RP['Y'], Y=RP['X'], L=RP['L2'], R=RP['R2'])},
    # Genesis Plus GX, 6-button pad: Y=A B=B A=C L=X X=Y R=Z, Select=Mode.
    'md': {'core': 'genesis_plus_gx', 'ext': ('.md', '.gen', '.smd', '.bin'), 'ram': 0xFF0000, 'mask': 0xFFFFFF,
           'swap16': True,
           'pad': dict(DPAD, A=RP['Y'], B=RP['B'], C=RP['A'], X=RP['L'], Y=RP['X'], Z=RP['R'], MODE=RP['SELECT'])},
}
JOYPAD, ANALOG = 1, 5                             # RETRO_DEVICE_JOYPAD, RETRO_DEVICE_ANALOG


def cmd(text, reply=True, timeout=1.0):
    """One network command; the answer, or None (RetroArch does not answer most commands)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        s.sendto(text.encode(), (HOST, CMD_PORT))
        if not reply:
            return None
        return s.recv(65536).decode().strip()
    except (socket.timeout, ConnectionRefusedError):     # not listening (yet)
        return None
    finally:
        s.close()


def instance():
    """What this session launched on its port: its record, or exit."""
    try:
        with open(INSTANCE) as f:
            rec = json.load(f)
    except (OSError, ValueError):
        sys.exit('no RetroArch launched by "%s" on port %d (retroarch.py launch IMAGE)' % (SESSION, CMD_PORT))
    if rec.get('session', '').lower() != SESSION.lower():
        sys.exit('port %d belongs to session "%s": pick another RA_SESSION name' % (CMD_PORT, rec.get('session')))
    return rec


def system():
    return SYSTEMS.get(instance().get('system'))


def address(addr):
    sysdef = system()
    return addr & sysdef['mask'] if sysdef else addr


CHUNK = 2048            # Flycast answers up to 3,000 bytes a read (a 3,500-byte reply never comes)
_ram_only = []          # set once the core has shown it has no memory map (READ_CORE_RAM only)


def _raw(addr, n):
    sysdef, addr = system(), address(addr)
    out = bytearray()
    while len(out) < n:
        k, a = min(CHUNK, n - len(out)), addr + len(out)
        tries = [] if _ram_only else [('READ_CORE_MEMORY', a)]
        if sysdef:
            tries.append(('READ_CORE_RAM', a - sysdef['ram']))
        for _ in range(3):                        # a busy machine drops or delays answers
            got = None
            for name, at in tries:
                r = cmd('%s %x %d' % (name, at, k))
                if r and r.split()[2:3] != ['-1'] and len(r.split()) == k + 2:
                    got = bytes(int(b, 16) for b in r.split()[2:])
                    if name == 'READ_CORE_RAM' and not _ram_only:
                        _ram_only.append(1)
                    break
            if got is not None:
                break
        else:
            sys.exit('read failed at %08X (is the game running?)' % a)
        out += got
    return bytes(out)


def read(addr, n):
    """Bytes at a console address, in the order the CPU sees them.

    A 16-bit console's work RAM is often held, and exposed, byte-swapped: on the Mega Drive
    a read of $FFFB00 hands back the byte the game wrote at $FFFB01. Reading from an even
    address and swapping each pair back costs nothing and stops every reading being a trap.
    """
    sysdef = system()
    if not (sysdef and sysdef.get('swap16') and address(addr) >= sysdef['ram']):
        return _raw(addr, n)
    lo = addr & ~1
    pad_bytes = addr - lo
    size = (pad_bytes + n + 1) & ~1
    data = bytearray(_raw(lo, size))
    for i in range(0, len(data) - 1, 2):
        data[i], data[i + 1] = data[i + 1], data[i]
    return bytes(data[pad_bytes:pad_bytes + n])


def write(addr, data):
    """In 256-byte commands; without a memory map each WRITE_CORE_MEMORY waits out a timeout, so
    once the core has shown it has none, straight to WRITE_CORE_RAM."""
    sysdef, addr = system(), address(addr)
    for i in range(0, len(data), 256):
        a, hexes = addr + i, ' '.join('%02x' % b for b in data[i:i + 256])
        r = None if _ram_only else cmd('WRITE_CORE_MEMORY %x %s' % (a, hexes))
        if (r is None or r.split()[2:3] == ['-1']) and sysdef:
            if not _ram_only:
                _ram_only.append(1)
            cmd('WRITE_CORE_RAM %x %s' % (a - sysdef['ram'], hexes), reply=False)


def pad(device, index, ident, state):
    """One network gamepad message: port, device, index, id, state (20 bytes with padding)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.sendto(struct.pack('<iiiiHxx', 0, device, index, ident, state & 0xFFFF), (HOST, PAD_PORT))
    s.close()


def buttons():
    sysdef = system()
    return sysdef['pad'] if sysdef else RP


def button(name, down):
    names = buttons()
    if name.upper() not in names:
        sys.exit('no button %s here: %s' % (name, ' '.join(names)))
    pad(JOYPAD, 0, names[name.upper()], 1 if down else 0)


def launch(image, core=None):
    image = os.path.abspath(image)
    if not os.path.isfile(image):
        sys.exit('no image at %s' % image)
    ext = os.path.splitext(image)[1].lower()
    name = core or next((s['core'] for s in SYSTEMS.values() if ext in s['ext']), None)
    if not name:
        sys.exit('no core known for %s files: give one (retroarch.py launch IMAGE CORE)' % ext)
    path = name if os.path.isfile(name) else os.path.join(CORES, '%s_libretro.dylib' % name)
    if not os.path.isfile(path):
        sys.exit('no core at %s' % path)
    base = os.path.basename(path).replace('_libretro.dylib', '')
    sysname = next((k for k, s in SYSTEMS.items() if base == s['core']), 'retropad')
    if cmd('GET_STATUS') is not None:
        sys.exit('RetroArch is already running on port %d (retroarch.py status)' % CMD_PORT)
    for port in (CMD_PORT, PAD_PORT):             # taken: another session whose name maps here
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.bind(('', port))
        except OSError:
            sys.exit('port %d is in use: another session name maps to it, pick another RA_SESSION' % port)
        finally:
            s.close()
    os.makedirs(SHOTS, exist_ok=True)
    cfg = os.path.join(OWN, 'ports.cfg')
    with open(cfg, 'w') as f:
        f.write('network_cmd_enable = "true"\nnetwork_cmd_port = "%d"\n'
                'network_remote_enable = "true"\nnetwork_remote_enable_user_p1 = "true"\n'
                'network_remote_base_port = "%d"\nconfig_save_on_exit = "false"\n'
                'pause_nonactive = "false"\naudio_mute_enable = "true"\nnotification_show_screenshot = "false"\nscreenshot_directory = "%s"\n'
                % (CMD_PORT, PAD_PORT, SHOTS))
    with open(INSTANCE, 'w') as f:
        json.dump({'session': SESSION, 'image': image, 'core': path, 'system': sysname}, f, indent=1)
    subprocess.check_call(['open', '-g', '-n', '-a', RA, '--args', '-L', path, image, '--appendconfig', cfg])
    for _ in range(60):                           # up to a minute for the core to come up
        time.sleep(1)
        r = cmd('GET_STATUS')
        if r and 'CONTENTLESS' not in r:
            print(r)
            return
    print('RetroArch started, no answer on port %d yet' % CMD_PORT)


def shot():
    before = set(glob.glob(os.path.join(SHOTS, '*.png')))
    cmd('SCREENSHOT', reply=False)
    for _ in range(50):
        time.sleep(0.1)
        new = set(glob.glob(os.path.join(SHOTS, '*.png'))) - before
        if new:
            path, size = max(new, key=os.path.getmtime), -1
            for _ in range(50):                   # written in pieces: wait until it settles
                time.sleep(0.2)
                now = os.path.getsize(path)
                if now and now == size:
                    return path
                size = now
            return path
    sys.exit('no screenshot appeared in %s' % SHOTS)


def main(a):
    if not a:
        sys.exit(__doc__)
    if not SESSION:
        sys.exit('set RA_SESSION="<session name>": it picks this session\'s own ports')
    c = a[0]
    if c == 'port':
        print(CMD_PORT, PAD_PORT, SESSION)
    elif c == 'launch':
        if len(a) < 2:
            sys.exit(__doc__)
        launch(a[1], a[2] if len(a) > 2 else None)
    elif c == 'status':
        instance()
        print(cmd('GET_STATUS'))
    elif c == 'quit':
        instance()
        cmd('QUIT', reply=False)                  # the first asks to confirm
        time.sleep(0.5)
        cmd('QUIT', reply=False)
        os.remove(INSTANCE)
    elif c == 'read':
        print(read(int(a[1], 16), int(a[2]) if len(a) > 2 else 4).hex())
    elif c == 'word':
        print('%08X' % struct.unpack('<I', read(int(a[1], 16), 4))[0])
    elif c == 'float':
        print(struct.unpack('<f', read(int(a[1], 16), 4))[0])
    elif c == 'vec':
        print(' '.join('%.3f' % v for v in struct.unpack('<3f', read(int(a[1], 16), 12))))
    elif c == 'write':
        write(int(a[1], 16), bytes.fromhex(a[2]))
    elif c == 'pause':
        instance()
        cmd('PAUSE_TOGGLE', reply=False)
    elif c == 'step':
        instance()
        for _ in range(int(a[1]) if len(a) > 1 else 1):
            cmd('FRAMEADVANCE', reply=False)
            time.sleep(0.02)
    elif c == 'shot':
        instance()
        print(shot())
    elif c == 'press':
        button(a[1], True)
        time.sleep((int(a[2]) if len(a) > 2 else 6) / 60.0)
        button(a[1], False)
    elif c == 'hold':
        button(a[1], True)
    elif c == 'release':
        if a[1].lower() == 'all':
            for ident in set(buttons().values()):
                pad(JOYPAD, 0, ident, 0)
            pad(ANALOG, 0, 0, 0)
            pad(ANALOG, 0, 1, 0)
        else:
            button(a[1], False)
    elif c == 'stick':
        instance()
        pad(ANALOG, 0, 0, int(float(a[1]) * 32767))
        pad(ANALOG, 0, 1, int(float(a[2]) * 32767))
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
