#include <genesis.h>

int main(bool hardReset)
{
    VDP_init();

    // stop SGDK's joypad driver from touching the ports; we read raw ourselves
    JOY_setSupport(PORT_1, JOY_SUPPORT_OFF);
    JOY_setSupport(PORT_2, JOY_SUPPORT_OFF);

    volatile u8 *data1 = (u8*)0xA10003;   // controller-1 data
    volatile u8 *ctrl1 = (u8*)0xA10009;   // controller-1 direction
    volatile u8 *data2 = (u8*)0xA10005;   // controller-2 data
    volatile u8 *ctrl2 = (u8*)0xA1000B;   // controller-2 direction
    *ctrl1 = 0x00;                        // all lines = inputs
    *ctrl2 = 0x00;

    VDP_drawText("CPC PORT TEST", 2, 1);
    VDP_drawText("       U D L R B C", 2, 4);   // bit0..bit5 labels

    char hex[4];
    while (TRUE)
    {
        u8 v1 = *data1;
        u8 v2 = *data2;
        u16 i;

        intToHex(v1, hex, 2);
        VDP_drawText("P1:", 2, 6);
        VDP_drawText(hex, 6, 6);
        for (i = 0; i < 6; i++)
            VDP_drawText((v1 & (1 << i)) ? "1" : "0", 9 + i * 2, 6);

        intToHex(v2, hex, 2);
        VDP_drawText("P2:", 2, 8);
        VDP_drawText(hex, 6, 8);
        for (i = 0; i < 6; i++)
            VDP_drawText((v2 & (1 << i)) ? "1" : "0", 9 + i * 2, 8);

        VDP_waitVSync();
    }
    return 0;
}
