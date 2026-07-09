#ifndef _UartInput_H
#define _UartInput_H

#include "gpaddon.h"
#include <cstdint>

// CPC: drive GP2040-CE's gamepad state from an external host (the Pi) over UART.
// The host streams frames; this addon holds the latest state and applies it
// every input cycle, exactly like a physical-button addon would.
#define UartInputName "UartInput"

class UartInput : public GPAddon {
public:
    virtual bool available();
    virtual void setup();
    virtual void process() {}
    virtual void preprocess();
    virtual void postprocess(bool sent);
    virtual void reinit() {}
    virtual std::string name() { return UartInputName; }
private:
    // frame parser state
    uint8_t rxState = 0;
    uint8_t f_dpad = 0, f_btnL = 0, f_btnH = 0;
    uint8_t f_lx = 0, f_ly = 0, f_rx = 0, f_ry = 0;
    // latest held inputs
    uint8_t  heldDpad = 0;
    uint16_t heldButtons = 0;
    uint8_t  heldLx = 0x80, heldLy = 0x80, heldRx = 0x80, heldRy = 0x80;
    // last sent rumble so we only TX on change
    uint8_t lastRumbleL = 0;
    uint8_t lastRumbleR = 0;
};

#endif  // _UartInput_H
