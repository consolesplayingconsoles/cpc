"""
bridges/uart.py -- the Pi-side UART link to the Pico (pure stdlib, no pyserial).

Opens the Pi's GPIO-header UART in raw 8N1 and writes bytes. The device comes from
the node .env (UART_DEVICE); the RIGHT port is /dev/ttyAMA0 = RP1 uart0 on pins
8/10, NOT /dev/serial0 -- that symlinks to ttyAMA10 = the SoC/Bluetooth UART, a
proven dead end. Same raw-termios technique used elsewhere, so it stays inside the
CLAUDE.md stdlib/3.6 rules and works on the constrained nodes too. The controller
bridge frames inputs on top; this layer just owns the raw byte pipe.
"""
import os
import termios

# termios attr list indices.
_IFLAG, _OFLAG, _CFLAG, _LFLAG, _ISPEED, _OSPEED, _CC = range(7)


class UartLink(object):
    name = "uart"

    def __init__(self, device="/dev/ttyAMA0", baud=115200):
        self.device = device
        self.baud = baud
        self.fd = None

    def open(self):
        fd = os.open(self.device, os.O_RDWR | os.O_NOCTTY)
        a = termios.tcgetattr(fd)
        speed = getattr(termios, "B%d" % self.baud)
        a[_ISPEED] = speed
        a[_OSPEED] = speed
        # 8N1, NO hardware flow control. CRTSCTS must be OFF: this is a 3-wire link
        # (TX/RX/GND, no RTS/CTS), so if flow control is on the kernel waits forever
        # for CTS and NOTHING transmits -- the exact failure dc-test.sh dodges with
        # `-crtscts`. Don't trust the port's inherited state; force it, like dc-test.
        # HUPCL off too (no modem lines to drop on close), matching `-hupcl`.
        a[_CFLAG] &= ~(termios.PARENB | termios.CSTOPB | termios.CSIZE
                       | getattr(termios, "CRTSCTS", 0) | getattr(termios, "HUPCL", 0))
        a[_CFLAG] |= termios.CS8 | termios.CLOCAL | termios.CREAD          # 8N1, rx on
        a[_IFLAG] &= ~(termios.IXON | termios.IXOFF | termios.IXANY | termios.INLCR | termios.ICRNL)
        a[_OFLAG] &= ~termios.OPOST                                        # raw output
        a[_LFLAG] &= ~(termios.ICANON | termios.ECHO | termios.ECHOE | termios.ISIG)
        termios.tcsetattr(fd, termios.TCSANOW, a)
        self.fd = fd
        return self

    def send(self, data):
        """Write bytes, tolerating a dead/absent Pico. A powered-off Pico (or a serial
        glitch) makes os.write raise OSError [Errno 5] -- left unhandled that crashed
        the whole hub, which then flapped under systemd's Restart=always (the "hub keeps
        being unavailable" symptom). Instead: drop the fd so the next send re-opens, and
        return False. The op just doesn't land until the link is back; the receiver stays
        up. Returns True on success."""
        if isinstance(data, str):
            data = data.encode()
        if self.fd is None:                 # dropped earlier -> try to bring it back
            try:
                self.open()
            except OSError:
                return False
        try:
            os.write(self.fd, data)
            return True
        except OSError:
            self.close()                    # device went away; re-open on the next send
            return False

    def close(self):
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None
