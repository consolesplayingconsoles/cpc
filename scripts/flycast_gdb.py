"""Talk to Flycast's GDB server (the GDB-enabled build, ~/Applications/Flycast GDB.app, started with
-config config:Debug.GDBEnabled=yes; port 3263). Stdlib only; any game.

    python3 scripts/flycast_gdb.py sample <seconds> <every> <out.json>   stop, read the registers, continue, repeatedly
    python3 scripts/flycast_gdb.py mem <hex address> <length>           read memory (the CPU stops for it)
    python3 scripts/flycast_gdb.py write <hex address> <hex bytes>      write those bytes (memory order), the CPU stopped for it
    python3 scripts/flycast_gdb.py dump <hex address> <hex length> <out>     save that much memory to a file (video memory too:
                                                                        A5000000, 8 MB = 800000), then let the game run
    python3 scripts/flycast_gdb.py hook <seconds> <hex address>[=name] ...   count the calls of each address by caller (pr) and r4 (when small),
                                                                        stepping over each hit so every call is seen; all breakpoints
                                                                        removed and checked at the end. Movable builds: only from about
                                                                        12 s after launch (before that the loader rewrites the code)
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
    # software breakpoints that are always taken back out: Flycast patches the instruction (38D3 -> 08C3 seen), and a `z0` that does
    # not restore it leaves the patch in RAM; the game then runs into it with no debugger and drops into the BIOS (Zombie Revenge,
    # 2026-11-13: the per-frame wait still held 08C3 after the script that set it had ended). Call these with the CPU stopped.
    def read16(s,a):
        h=s.cmd('m%X,2'%a)
        return int(h[2:4]+h[0:2],16) if h and len(h)>=4 and not h.startswith('E') else None
    def write16(s,a,v):
        return s.cmd('M%X,2:%02x%02x'%(a,v&0xFF,(v>>8)&0xFF))
    def bp_add(s,a):
        bps=s.__dict__.setdefault('bps',{})
        if a not in bps: bps[a]=s.read16(a)
        return s.cmd('Z0,%X,2'%a)
    def bp_del(s,a):
        """Take the breakpoint at a out and check the original instruction is back; rewrite it when it is not. True when it is."""
        orig=s.__dict__.setdefault('bps',{}).pop(a,None)
        s.cmd('z0,%X,2'%a)
        if orig is None: return True
        if s.read16(a)!=orig: s.write16(a,orig)
        ok=s.read16(a)==orig
        if not ok: print('[ERROR] the instruction at %08X is still patched (%s, original %04X): the game will stop there with no debugger'%(a,s.read16(a),orig))
        return ok
    def bp_clear(s):
        return all([s.bp_del(a) for a in list(s.__dict__.get('bps',{}))])
    def regs(s):
        g=s.cmd('g')
        for _ in range(3):                              # a stop reply (S02/T02...) can land after the g request: not registers
            if g and len(g)>=16*8 and all(c in '0123456789abcdefABCDEFx' for c in g): break
            g=s.recv(5) if g and g[:1] in 'ST' else s.cmd('g')
        if not g or len(g)<16*8: return None
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
        halt=None
        if rest[:1]==['--halt']: halt=rest[1]; rest=rest[2:]      # --halt <out prefix>: at the first hit save every register and the RAM (as snap does), leave the CPU stopped
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
        for ad in addrs: print('Z0 %08X:'%ad, r.bp_add(ad))
        t0=time.time(); r.send('c')
        while time.time()-t0<dur:
            st=r.recv(1)
            if st and st[:1] in 'ST':
                g=r.regs()
                if g:
                    rows.append({'t':round(time.time()-t0,2),**g})
                    if halt and g['pc'] in addrs:
                        full=r.cmd('g'); ram=bytearray()
                        for k in range(0,0x1000000,0x800):
                            h=r.cmd('m%X,800'%(0x8C000000+k),30)
                            ram+=bytes.fromhex(h) if h and not h.startswith('E') else b'\0'*0x800
                        open(halt+'.ram','wb').write(ram); json.dump({'t':round(time.time()-t0,2),'g':full,**g},open(halt+'.json','w'))
                        print('halted at %.2f s: pc %08X pr %08X r15 %08X'%(time.time()-t0,g['pc'],g['pr'],g['r'][15])); r.bp_clear(); return
                    if g['pc'] in addrs: r.bp_del(g['pc']); addrs.remove(g['pc'])     # once each: continuing over a breakpoint in place hits it again at once, forever
                r.send('c')
            elif st:
                print('packet %r at %.1f s'%(st[:40],time.time()-t0)); r.send('c')      # anything else: say so, and never leave the CPU stopped
        r.stop(); g=r.regs()
        if g: print('at the end: pc %08X pr %08X r15 %08X'%(g['pc'],g['pr'],g['r'][15]))
        r.bp_clear()
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
    elif a[0]=='hook':    # hook <seconds> <hex address>[=name] ...: count the calls of each address, by caller (pr)
        dur=float(a[1]); names={}
        for x in a[2:]:
            ad,_,n=x.partition('='); names[int(ad,16)]=n or ad
        import collections
        c=collections.Counter(); hits=0
        r.stop()
        for ad in names: print('Z0 %08X %s: %s'%(ad,names[ad],r.bp_add(ad)))
        t0=time.time(); r.send('c')
        try:
            while time.time()-t0<dur:
                st=r.recv(0.5)
                if not st or st[:1] not in 'ST': continue
                g=r.regs()
                if g and g['pc'] in names:
                    hits+=1; c[(names[g['pc']],g['pr'],g['r'][4] if g['r'][4]<0x10000 else None)]+=1      # r4 kept when it is a small number (a count)
                    ad=g['pc']; r.bp_del(ad); r.cmd('s',5); r.bp_add(ad)       # step over the call's first instruction, then set it again
                r.send('c')
        finally:
            r.stop(); ok=r.bp_clear(); r.send('c')
        print('%d hits in %.1f s; breakpoints %s'%(hits,time.time()-t0,'all removed and checked' if ok else 'NOT ALL REMOVED'))
        for (n,pr,r4),k in c.most_common(60): print('  %5dx %-24s from %08X  r4 %s'%(k,n,pr,r4 if r4 is not None else 'address'))
    elif a[0]=='dump':    # dump <hex address> <hex length> <out>: memory to a file, the CPU stopped while it is read
        ad,n,out=int(a[1],16),int(a[2],16),a[3]; data=bytearray(); t0=time.time()
        r.stop()
        for k in range(0,n,0x800):
            h=r.cmd('m%X,%X'%(ad+k,min(0x800,n-k)),30)
            data+=bytes.fromhex(h) if h and not h.startswith('E') else b'\0'*min(0x800,n-k)
        open(out,'wb').write(data); print('%d bytes from %08X in %.0f s'%(len(data),ad,time.time()-t0))
        r.send('c')
    elif a[0]=='mem':
        print(r.cmd('m%s,%s'%(a[1],a[2])))
        r.send('c')
    elif a[0]=='write':   # write <hex address> <hex bytes>: the CPU stopped, the bytes written as given (memory order), then the game runs on
        r.stop()                                   # further <address> <bytes> pairs go in the same stop
        for k in range(1,len(a)-1,2): print(r.cmd('M%X,%X:%s'%(int(a[k],16),len(a[k+1])//2,a[k+1])))
        r.send('c')
    elif a[0]=='watch':   # watch <seconds> <out.json> <hex address>: a write watchpoint (Z2) on one word; log each write (pc, pr, the word
        dur,out,ad=float(a[1]),a[2],int(a[3],16); rows=[]     # after it), continue; stop at the first nonzero word (the start-up clear writes 0)
        z=r.cmd('Z2,%X,4'%ad); print('Z2 %08X: %r'%(ad,z))
        if z!='OK':                                    # no watchpoints in this Flycast: poll instead, stopping every few ms; the pc logged
            prev=None; t0=time.time()                  # is where the CPU was when the change was seen, shortly after the write
            while time.time()-t0<dur:
                r.send('c'); time.sleep(0.003); r.stop()
                h=r.cmd('m%X,4'%ad); v=int(''.join(reversed([h[i:i+2] for i in range(0,8,2)])),16) if h and not h.startswith('E') else None
                if v!=prev:
                    g=r.regs(); rows.append({'t':round(time.time()-t0,3),'value':v,**(g or {})})
                    print('%.3f s: value %s, pc %08X pr %08X'%(time.time()-t0,'%08X'%v if v is not None else '?',g['pc'] if g else 0,g['pr'] if g else 0))
                    prev=v
                    if v and v!=0xFFFFFFFF and len(rows)>2: break
            json.dump(rows,open(out,'w')); print('changes logged',len(rows)); r.send('c'); return
        t0=time.time(); r.send('c')
        while time.time()-t0<dur:
            st=r.recv(1)
            if st and st[:1] in 'ST':
                g=r.regs(); h=r.cmd('m%X,4'%ad)
                v=int(''.join(reversed([h[i:i+2] for i in range(0,8,2)])),16) if h and not h.startswith('E') else None
                if g: rows.append({'t':round(time.time()-t0,2),'value':v,**g}); print('%.2f s: pc %08X pr %08X value %s'%(time.time()-t0,g['pc'],g['pr'],'%08X'%v if v is not None else '?'))
                if v: break
                r.send('c')
            elif st:
                print('packet %r at %.1f s'%(st[:40],time.time()-t0)); r.send('c')
        r.cmd('z2,%X,4'%ad); json.dump(rows,open(out,'w')); print('writes logged',len(rows)); r.send('c')
if __name__=='__main__': main()
