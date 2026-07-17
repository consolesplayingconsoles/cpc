import javax.microedition.midlet.*;
import javax.microedition.lcdui.*;
import javax.microedition.io.*;
import javax.bluetooth.*;
import java.io.OutputStream;

/**
 * CPC Nokia node -- controller MIDlet ("phone is a Pluto input").
 * Captures the keypad and streams key up/down events over Bluetooth RFCOMM.
 * The counterpart (Pi bluez listener) reads the line protocol and feeds the
 * event into Pluto Control as the `nokia` source, target = pi -> pico -> DC.
 *
 * WIRE PROTOCOL (ASCII lines, \n-terminated):
 *   D <sym>   key pressed        U <sym>   key released
 *   <sym> in: UP DOWN LEFT RIGHT FIRE A B C D 0..9 STAR POUND SOFT1 SOFT2
 *             or K<rawKeyCode> when unmapped.
 * A "HELLO CpcPad\n" line is sent on connect.
 *
 * Service UUID: 11111111111111111111111111111111  (btspp server on the phone).
 */
public class CpcPad extends MIDlet {
    static final String UUID_STR = "11111111111111111111111111111111";
    private Display display;
    private PadCanvas canvas;
    volatile OutputStream out;      // set when the Pi connects
    volatile String status = "Starting...";
    volatile String last = "-";
    volatile int count = 0;

    protected void startApp() {
        if (canvas == null) {
            display = Display.getDisplay(this);
            canvas = new PadCanvas(this);
            new Thread(new Server(this)).start();
        }
        display.setCurrent(canvas);
        canvas.repaint();
    }
    protected void pauseApp() {}
    protected void destroyApp(boolean u) {}

    // Single synchronized writer: the UI thread (key events) and the server thread
    // (HELLO + heartbeat) share one OutputStream, so serialize their writes here.
    synchronized void writeLine(String s) {
        OutputStream o = out;
        if (o == null) return;
        try { o.write(s.getBytes()); o.flush(); }
        catch (Throwable t) { out = null; }   // link dropped; server loop re-accepts
    }

    void send(String sym, boolean down) {
        last = (down ? "D " : "U ") + sym;
        count++;
        writeLine((down ? "D " : "U ") + sym + "\n");
        canvas.repaint();
    }

    /** Bluetooth RFCOMM server: publish the service, accept clients, survive drops. */
    static class Server implements Runnable {
        final CpcPad m;
        Server(CpcPad m) { this.m = m; }
        public void run() {
            try {
                LocalDevice local = LocalDevice.getLocalDevice();
                try { local.setDiscoverable(DiscoveryAgent.GIAC); } catch (Throwable t) {}  // non-fatal
                String url = "btspp://localhost:" + UUID_STR + ";name=CpcPad";
                StreamConnectionNotifier notifier = (StreamConnectionNotifier) Connector.open(url);
                // Read our own assigned RFCOMM channel from the service record so the Mac
                // knows which channel to bind /dev/cu.* to (we drive it over a serial port,
                // not IOBluetooth). Connection URL looks like btspp://<addr>:<CH>;...
                String ch = "?";
                try {
                    javax.bluetooth.ServiceRecord sr = local.getRecord(notifier);
                    String u = sr.getConnectionURL(
                        javax.bluetooth.ServiceRecord.NOAUTHENTICATE_NOENCRYPT, false);
                    int c = u.indexOf(':', 8);              // skip "btspp://"
                    int s = u.indexOf(';', c);
                    if (c > 0) ch = (s > c) ? u.substring(c + 1, s) : u.substring(c + 1);
                } catch (Throwable t) { ch = "err"; }
                m.status = "Ready ch=" + ch;
                m.canvas.repaint();
                // Accept clients forever. A short/failed connection must NOT kill the server.
                while (true) {
                    StreamConnection conn = null;
                    try {
                        conn = notifier.acceptAndOpen();          // blocks for next client
                        m.out = conn.openOutputStream();
                        m.status = "Connected ch=" + ch;
                        m.canvas.repaint();
                        m.writeLine("HELLO CpcPad\n");
                        // Heartbeat: proves the link to the Mac even before a keypress, and
                        // detects a dropped link (writeLine nulls out -> loop exits).
                        OutputStream mine = m.out;
                        while (m.out == mine && mine != null) {
                            m.writeLine("PING\n");
                            try { Thread.sleep(1000); } catch (Throwable t) {}
                        }
                    } catch (Throwable t) {
                        // this connection failed; wait for the next one
                    } finally {
                        m.out = null;
                        try { if (conn != null) conn.close(); } catch (Throwable t) {}
                    }
                    m.status = "Ready ch=" + ch + " *";
                    m.canvas.repaint();
                }
            } catch (Throwable t) {
                m.status = "BT ERR " + t.getClass().getName();
                if (m.canvas != null) m.canvas.repaint();
            }
        }
    }

    /** Full-screen canvas: capture keys, echo state so you can see it live on the phone. */
    static class PadCanvas extends Canvas {
        final CpcPad m;
        PadCanvas(CpcPad m) { this.m = m; setFullScreenMode(true); }

        protected void paint(Graphics g) {
            int w = getWidth(), h = getHeight();
            g.setColor(0x101418); g.fillRect(0, 0, w, h);
            g.setColor(0x36c08a); g.drawString("CPC Nokia Pad", 4, 2, Graphics.TOP | Graphics.LEFT);
            g.setColor(0xcfd8dc);
            g.drawString(m.status, 4, 20, Graphics.TOP | Graphics.LEFT);
            g.drawString("Last: " + m.last, 4, 40, Graphics.TOP | Graphics.LEFT);
            g.drawString("Events: " + m.count, 4, 58, Graphics.TOP | Graphics.LEFT);
            g.setColor(0x5a6b74);
            g.drawString("press keys / hold to test", 4, h - 18, Graphics.TOP | Graphics.LEFT);
        }

        // Output-agnostic: report the PHYSICAL key, never a function. Number keys report
        // their digit label; every other key (volume, soft, rocker, call/end) reports its
        // raw device keyCode as K<n>. Pluto owns the mapping (2->up, 1->X, K<vol>->L, ...).
        // NO getGameAction() here -- that would let the phone impose UP/FIRE, which is the
        // output's job, not the input's.
        String sym(int keyCode) {
            switch (keyCode) {
                case KEY_NUM0: return "0"; case KEY_NUM1: return "1"; case KEY_NUM2: return "2";
                case KEY_NUM3: return "3"; case KEY_NUM4: return "4"; case KEY_NUM5: return "5";
                case KEY_NUM6: return "6"; case KEY_NUM7: return "7"; case KEY_NUM8: return "8";
                case KEY_NUM9: return "9"; case KEY_STAR: return "*"; case KEY_POUND: return "#";
            }
            return "K" + keyCode;   // device-specific: volume/soft/rocker/call -- Pluto binds by code
        }

        protected void keyPressed(int keyCode)  { m.send(sym(keyCode), true); }
        protected void keyReleased(int keyCode) { m.send(sym(keyCode), false); }
        // Some S40 builds fire keyRepeated instead of holding; treat as a fresh press.
        protected void keyRepeated(int keyCode) { m.send(sym(keyCode), true); }
    }
}
