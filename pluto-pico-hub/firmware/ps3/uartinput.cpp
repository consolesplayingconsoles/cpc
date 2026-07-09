#include "addons/uartinput.h"
#include "storagemanager.h"
#include "hardware/uart.h"
#include "hardware/gpio.h"
#include "pico/bootrom.h"
#include "pico/time.h"

// --- CPC UART input ---------------------------------------------------------
// uart0 on GP0 (TX, our replies) / GP1 (RX, the Pi's commands).
// Wire frame: 0xAA 0x55 <dpad> <btnL> <btnH> <xor>
//   xor   = dpad ^ btnL ^ btnH   (reject garbage)
//   dpad  = bit0 UP, bit1 DOWN, bit2 LEFT, bit3 RIGHT
//   btnL  = buttons  0..7  (B1 B2 B3 B4 L1 R1 L2 R2)
//   btnH  = buttons  8..15 (S1 S2 L3 R3 A1 A2 A3 A4)
// Control frame: dpad == 0xFF -> btnL is a command:
//   0x01 = reboot to BOOTSEL (remote reflash, no physical button)
// Onboard LED (GP25) flashes LED_FLASH_MS on every byte received over UART:
// an activity light AND a live forward-link probe. Data arriving -> it pulses;
// a dead/loose RX wire -> it stays dark (RX is pulled high so noise can't fake
// a byte). Idle = a brief blip every few seconds (still-alive reassurance), so a
// quiet board is never mistaken for a dead one; fully dark = actually dead.
// ---------------------------------------------------------------------------
#define UART_ID      uart0
#define UART_TX_PIN  0
#define UART_RX_PIN  1
#define UART_BAUD    115200
#define LED_PIN      25      // PICO_DEFAULT_LED_PIN (onboard LED)
#define LED_FLASH_MS 90
#define IDLE_BLIP_MS 3000   // idle "still alive" blip period (ms)

bool UartInput::available() {
    return true;  // always on for now (no proto/web-config dependency)
}

void UartInput::setup() {
    uart_init(UART_ID, UART_BAUD);
    gpio_set_function(UART_TX_PIN, GPIO_FUNC_UART);
    gpio_set_function(UART_RX_PIN, GPIO_FUNC_UART);
    gpio_pull_up(UART_RX_PIN);   // idle-high when unwired so noise can't fake RX
    gpio_init(LED_PIN);
    gpio_set_dir(LED_PIN, GPIO_OUT);
    rxState = 0;
    heldDpad = 0;
    heldButtons = 0;
    // liveness banner so the Pi can confirm the reverse link end-to-end
    uart_puts(UART_ID, "CPC-UARTINPUT-READY\n");
}

void UartInput::postprocess(bool sent) {
    // Rumble output: read haptic strength from gamepad state, relay to Pi on change.
    // Frame: 0xAA 0x55 0xFE <left> <right> <xor>  (0xFE = rumble marker)
    Gamepad *gamepad = Storage::getInstance().GetGamepad();
    uint8_t L = (uint8_t)(gamepad->auxState.haptics.leftActuator.intensity  >> 8);
    uint8_t R = (uint8_t)(gamepad->auxState.haptics.rightActuator.intensity >> 8);
    if (L != lastRumbleL || R != lastRumbleR) {
        lastRumbleL = L;
        lastRumbleR = R;
        uint8_t frame[6] = {0xAA, 0x55, 0xFE, L, R, (uint8_t)(0xFE ^ L ^ R)};
        uart_write_blocking(UART_ID, frame, sizeof(frame));
    }
}

void UartInput::preprocess() {
    static uint32_t lastRxMs = 0;

    while (uart_is_readable(UART_ID)) {
        uint8_t b = (uint8_t) uart_getc(UART_ID);
        lastRxMs = to_ms_since_boot(get_absolute_time());   // mark RX activity
        switch (rxState) {
            case 0: rxState = (b == 0xAA) ? 1 : 0; break;
            case 1: rxState = (b == 0x55) ? 2 : (b == 0xAA ? 1 : 0); break;
            case 2: f_dpad = b; rxState = 3; break;
            case 3: f_btnL = b; rxState = 4; break;
            case 4: f_btnH = b; rxState = 5; break;
            case 5: f_lx   = b; rxState = 6; break;
            case 6: f_ly   = b; rxState = 7; break;
            case 7: f_rx   = b; rxState = 8; break;
            case 8: f_ry   = b; rxState = 9; break;
            case 9: {
                if (b == (uint8_t)(f_dpad ^ f_btnL ^ f_btnH ^ f_lx ^ f_ly ^ f_rx ^ f_ry)) {
                    if (f_dpad == 0xFF) {
                        if (f_btnL == 0x01) reset_usb_boot(0, 0);  // -> BOOTSEL
                    } else {
                        heldDpad    = f_dpad & 0x0F;
                        heldButtons = (uint16_t)f_btnL | ((uint16_t)f_btnH << 8);
                        heldLx = f_lx; heldLy = f_ly;
                        heldRx = f_rx; heldRy = f_ry;
                    }
                }
                rxState = 0;
                break;
            }
            default: rxState = 0; break;
        }
    }

    // LED: a bright flash on RX activity (the forward-link probe); otherwise a
    // brief "still alive" blip every IDLE_BLIP_MS, so a dark-from-no-input LED
    // is never mistaken for a dead board.
    uint32_t nowMs = to_ms_since_boot(get_absolute_time());
    gpio_put(LED_PIN, (nowMs - lastRxMs < LED_FLASH_MS) || ((nowMs % IDLE_BLIP_MS) < 50));

    // GP2040 sources the d-pad from state.dpadOriginal (process() overwrites
    // state.dpad from it each frame); buttons read state.buttons directly. So
    // the d-pad must be written to dpadOriginal, the buttons to buttons.
    Gamepad *gamepad = Storage::getInstance().GetGamepad();
    if (heldDpad & 0x01) gamepad->state.dpadOriginal |= GAMEPAD_MASK_UP;
    if (heldDpad & 0x02) gamepad->state.dpadOriginal |= GAMEPAD_MASK_DOWN;
    if (heldDpad & 0x04) gamepad->state.dpadOriginal |= GAMEPAD_MASK_LEFT;
    if (heldDpad & 0x08) gamepad->state.dpadOriginal |= GAMEPAD_MASK_RIGHT;
    gamepad->state.buttons |= heldButtons;
    gamepad->state.lx = (uint16_t)heldLx << 8;
    gamepad->state.ly = (uint16_t)heldLy << 8;
    gamepad->state.rx = (uint16_t)heldRx << 8;
    gamepad->state.ry = (uint16_t)heldRy << 8;
}
