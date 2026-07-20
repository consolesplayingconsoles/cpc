#include <genesis.h>

// CPC DATA LINK receiver -- reads the Pico over Mega Drive controller PORT 2.
//
// Bus (6 data lines, adapter in port 2):
//   bit0-3 (GP3-GP6) = 4-bit payload nibble / control id
//   bit4   (GP7)     = CTRL flag: 1 = framing symbol, 0 = data nibble
//   bit5   (GP8)     = CLK: Pico toggles it every transfer (self-clocked)
//
// Frame: START -> [opcode byte] -> [payload bytes...] -> END
//   each byte = two data nibbles (high nibble first)
//   START = CTRL=1, id=0x1     END = CTRL=1, id=0x2
//   opcode 0x01 = print text (payload = ASCII)
//   opcode 0x02 = render graphic (payload = 1 id byte)

#define CTRL_START 0x1
#define CTRL_END   0x2
#define OP_PRINT   0x01
#define OP_RENDER  0x02

#define TXT_ROW 9
#define TXT_COL 7
#define GFX_ROW 12
#define GFX_COL 3

static void clear_gfx(void)
{
    u16 r;
    for (r = GFX_ROW; r < GFX_ROW + 8; r++)
        VDP_clearText(GFX_COL, r, 12);
}

static void draw_graphic(u8 id)
{
    clear_gfx();
    if (id == 0)                       // smiley
    {
        VDP_drawText(" #### ",  GFX_COL, GFX_ROW + 0);
        VDP_drawText("#    #",  GFX_COL, GFX_ROW + 1);
        VDP_drawText("# oo #",  GFX_COL, GFX_ROW + 2);
        VDP_drawText("#    #",  GFX_COL, GFX_ROW + 3);
        VDP_drawText("#\\__/#", GFX_COL, GFX_ROW + 4);
        VDP_drawText(" #### ",  GFX_COL, GFX_ROW + 5);
    }
    else if (id == 1)                  // heart
    {
        VDP_drawText(" _  _ ", GFX_COL, GFX_ROW + 0);
        VDP_drawText("( \\/ )", GFX_COL, GFX_ROW + 1);
        VDP_drawText(" \\  / ", GFX_COL, GFX_ROW + 2);
        VDP_drawText("  \\/  ", GFX_COL, GFX_ROW + 3);
    }
    else
    {
        char b[4];
        intToHex(id, b, 2);
        VDP_drawText("gfx?", GFX_COL, GFX_ROW);
        VDP_drawText(b, GFX_COL + 6, GFX_ROW);
    }
}

int main(bool hardReset)
{
    VDP_init();
    JOY_setSupport(PORT_1, JOY_SUPPORT_OFF);
    JOY_setSupport(PORT_2, JOY_SUPPORT_OFF);

    volatile u8 *data2 = (u8*)0xA10005;   // PORT 2 data = our data port
    volatile u8 *ctrl2 = (u8*)0xA1000B;   // PORT 2 direction
    *ctrl2 = 0x00;                        // all lines = inputs

    VDP_drawText("CPC DATA LINK   port 2", 1, 1);
    VDP_drawText("bits 012345:", 1, 3);
    VDP_drawText("state:", 1, 5);
    VDP_drawText("op:", 1, 6);
    VDP_drawText("byte:", 1, 7);
    VDP_drawText("text:", 1, TXT_ROW);

    char txt[41];
    u16 tlen  = 0;
    u16 shown = 0;            // chars currently on the text line (for dynamic wipe)
    txt[0] = 0;

    u8 last_clk = 0xFF;
    u8 started  = 0;
    u8 have_hi  = 0;
    u8 hi       = 0;
    u8 got_op   = 0;
    u8 opcode   = 0;
    char hexb[4];

    while (TRUE)
    {
        VDP_waitVSync();

        u8 v    = *data2;
        u8 clk  = (v >> 5) & 1;   // bit5
        u8 ctrl = (v >> 4) & 1;   // bit4
        u8 nib  = v & 0x0F;       // bits0-3

        u16 i;                    // live bit indicator (kept: our scope)
        for (i = 0; i < 6; i++)
            VDP_drawText((v & (1 << i)) ? "1" : "0", 14 + i * 2, 3);

        if (clk != last_clk)      // new transfer on each CLK edge
        {
            last_clk = clk;

            if (ctrl)             // framing symbol
            {
                if (nib == CTRL_START)
                {
                    started = 1; have_hi = 0; got_op = 0; tlen = 0; txt[0] = 0;
                    VDP_clearText(TXT_COL, TXT_ROW, shown);   // wipe exactly what was shown
                    shown = 0;
                    VDP_drawText("--        ", 7, 6);
                    VDP_drawText("START     ", 8, 5);
                }
                else if (nib == CTRL_END && started)
                {
                    started = 0;
                    VDP_drawText("END       ", 8, 5);
                }
            }
            else if (started)     // data nibble
            {
                if (!have_hi) { hi = nib; have_hi = 1; }
                else
                {
                    u8 b = (hi << 4) | nib;
                    have_hi = 0;
                    intToHex(b, hexb, 2);
                    VDP_drawText(hexb, 7, 7);
                    VDP_drawText("DATA      ", 8, 5);

                    if (!got_op)
                    {
                        opcode = b; got_op = 1;
                        intToHex(b, hexb, 2);
                        VDP_drawText(hexb, 7, 6);
                    }
                    else if (opcode == OP_PRINT && tlen < 31)
                    {
                        txt[tlen++] = (char)b; txt[tlen] = 0;
                        VDP_drawText(txt, TXT_COL, TXT_ROW);
                        shown = tlen;
                    }
                    else if (opcode == OP_RENDER)
                    {
                        draw_graphic(b);   // first payload byte = graphic id
                    }
                }
            }
        }
    }
    return 0;
}
