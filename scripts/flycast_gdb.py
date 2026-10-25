"""Talk to Flycast's GDB server (the GDB-enabled build, ~/Applications/Flycast GDB.app, started with
-config config:Debug.GDBEnabled=yes; port 3263). Stdlib only; any game.

    python3 scripts/flycast_gdb.py sample <seconds> <every> <out.json>   stop, read the registers, continue, repeatedly
    python3 scripts/flycast_gdb.py mem <hex address> <length>           read memory (the CPU stops for it)
    python3 scripts/flycast_gdb.py snap <seconds> <lo> <hi> <out>       run until the pc is in [lo, hi), halt, write <out>.json (every
                                                                        register) and <out>.ram (16 MB of RAM from 8C000000)
    python3 scripts/flycast_gdb.py bp <seconds> <out.json> [--after <s>] <hex address> ...   stop at each address, log the registers,
                                                                        continue. A software breakpoint is a patched instruction: one
                                                                        placed before the game is loaded is overwritten by the loader
                                                                        (0 hits), so --after runs that long first, then places them.
                                                                        Each address is logged once (its first hit), then removed.
                                                                        --in <lo> <hi> instead waits for the pc to be in [lo, hi)
"""
import socket,sys,time,json
def csum(s): return '%02x'%(sum(s.encode())&0xff)
class R:
    def __init__(s,port=3263):
        s.k=socket.create_connection(('127.0.0.1',port),timeout=10); s.buf=b''
        s.k.sendall(b'+')
    def send(s,p):
        s.k.sendall(('$%s#%s'%(p,csum(p))).encode())
    def recv(s,timeout=10):
        s.k.settimeout(timeout); end=time.time()+timeout
        while True:
            i=s.buf.find(b'$'); j=s.buf.find(b'#',i+1) if i>=0 else -1
            if i>=0 and j>=0 and len(s.buf)>=j+3:
                p=s.buf[i+1:j].decode(errors='replace'); s.buf=s.buf[j+3:]; s.k.sendall(b'+'); return p
            try: d=s.k.recv(65536)
            except socket.timeout:
                if time.time()>end: return None
                continue
            if not d: return None
            s.buf+=d.replace(b'+',b'',1) if s.buf==b'' and d.startswith(b'+') else d
    def cmd(s,p,timeout=10): s.send(p); return s.recv(timeout)
    def stop(s):
        s.k.sendall(b'\x03'); return s.recv(5)
    def regs(s):
        g=s.cmd('g'); 
        if not g: return None
        w=[g[i:i+8] for i in range(0,len(g),8)]
        le=lambda x: int(''.join(reversed([x[i:i+2] for i in range(0,8,2)])),16) if x and 'x' not in x else None
        v=[le(x) for x in w]
        return {'r':v[:16],'pc':v[16],'pr':v[17],'gbr':v[18],'vbr':v[19],'sr':v[22] if len(v)>22 else None}
def main():
    a=sys.argv[1:]; r=R()
    print('halt reason:',r.cmd('?'))
    if a[0]=='sample':
        dur,every,out=float(a[1]),float(a[2]),a[3]; rows=[]; t0=time.time()
        r.send('c')
        while time.time()-t0<dur:
            time.sleep(every); st=r.stop(); g=r.regs()
            if g: rows.append({'t':round(time.time()-t0,2),**g})
            r.send('c')
        r.stop(); json.dump(rows,open(out,'w')); print('samples',len(rows)); 
        g=r.regs(); print('last pc %08X pr %08X sr %s r15 %08X'%(g['pc'],g['pr'],hex(g['sr']) if g['sr'] is not None else None,g['r'][15]))
        r.send('c')
    elif a[0]=='bp':      # bp <seconds> <out.json> <hex address> [...]: stop at each address (software breakpoints), log the registers, continue
        dur,out=float(a[1]),a[2]; rest=a[3:]; after=0.0; rows=[]
        game=None
        if rest[:1]==['--after']: after=float(rest[1]); rest=rest[2:]
        if rest[:1]==['--in']: game=(int(rest[1],16),int(rest[2],16)); rest=rest[3:]
        addrs=[int(x,16) for x in rest]
        if after:
            r.send('c'); time.sleep(after); r.stop()
        if game:                                   # wait until the pc is in the game's own code: the loader has run by then
            t1=time.time()
            while time.time()-t1<60:
                g=r.regs()
                if g and game[0]<=(g['pc']&0x1FFFFFFF)<game[1]: print('in the game at %.1f s: pc %08X'%(time.time()-t1,g['pc'])); break
                r.send('c'); time.sleep(0.25); r.stop()
        for ad in addrs: print('Z0 %08X:'%ad, r.cmd('Z0,%X,2'%ad))
        t0=time.time(); r.send('c')
        while time.time()-t0<dur:
            st=r.recv(1)
            if st and st[:1] in 'ST':
                g=r.regs()
                if g:
                    rows.append({'t':round(time.time()-t0,2),**g})
                    if g['pc'] in addrs: r.cmd('z0,%X,2'%g['pc']); addrs.remove(g['pc'])     # once each: continuing over a breakpoint in place hits it again at once, forever
                r.send('c')
            elif st:
                print('packet %r at %.1f s'%(st[:40],time.time()-t0)); r.send('c')      # anything else: say so, and never leave the CPU stopped
        r.stop(); g=r.regs()
        if g: print('at the end: pc %08X pr %08X r15 %08X'%(g['pc'],g['pr'],g['r'][15]))
        for ad in addrs: r.cmd('z0,%X,2'%ad)
        json.dump(rows,open(out,'w')); print('breakpoint hits',len(rows),'never hit:',' '.join('%08X'%x for x in addrs)); r.send('c')
    elif a[0]=='snap':    # snap <seconds> <lo hex> <hi hex> <out prefix>: run until the pc is in [lo, hi), halt, save the registers and RAM
        dur,lo,hi,out=float(a[1]),int(a[2],16),int(a[3],16),a[4]; t0=time.time(); g=None
        r.send('c')
        while time.time()-t0<dur:
            time.sleep(0.01); r.stop(); g=r.regs()
            if g and lo<=(g['pc']&0x1FFFFFFF)<hi: break
            r.send('c'); g=None
        if not g: print('the pc never came into the range'); r.stop(); r.send('c'); return
        full=r.cmd('g'); ram=bytearray()
        for k in range(0,0x1000000,0x800):
            h=r.cmd('m%X,800'%(0x8C000000+k),30)
            ram+=bytes.fromhex(h) if h and not h.startswith('E') else b'\0'*0x800
        open(out+'.ram','wb').write(ram); json.dump({'t':round(time.time()-t0,2),'g':full,**g},open(out+'.json','w'))
        print('halted at %.2f s: pc %08X pr %08X r15 %08X; %d bytes of RAM'%(time.time()-t0,g['pc'],g['pr'],g['r'][15],len(ram)))
        r.send('c')
    elif a[0]=='mem':
        print(r.cmd('m%s,%s'%(a[1],a[2])))
        r.send('c')
main()
