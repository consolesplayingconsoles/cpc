/*
 * CPC Chat — native Wii homebrew.  Step 1: it lives.
 *
 * No operating system underneath this. devkitPPC + libogc talking straight to
 * the hardware: bring up video, open a text console, draw the CPC banner, and
 * idle until HOME. Every later step (wifi, HTTP, render, keyboard, send) builds
 * on this exact shell.
 */
#include <stdio.h>
#include <stdlib.h>
#include <gccore.h>
#include <wiiuse/wpad.h>

static void *xfb = NULL;          /* external framebuffer */
static GXRModeObj *rmode = NULL;  /* chosen video mode     */

static void video_init(void) {
    VIDEO_Init();
    WPAD_Init();

    rmode = VIDEO_GetPreferredMode(NULL);
    xfb   = MEM_K0_TO_K1(SYS_AllocateFramebuffer(rmode));

    /* libogc's stdio console renders straight into the framebuffer. */
    console_init(xfb, 20, 20, rmode->fbWidth, rmode->xfbHeight,
                 rmode->fbWidth * VI_DISPLAY_PIX_SZ);

    VIDEO_Configure(rmode);
    VIDEO_SetNextFramebuffer(xfb);
    VIDEO_SetBlack(FALSE);
    VIDEO_Flush();
    VIDEO_WaitVSync();
    if (rmode->viTVMode & VI_NON_INTERLACE) VIDEO_WaitVSync();
}

int main(int argc, char **argv) {
    video_init();

    printf("\x1b[2;0H");                                  /* row 2, col 0 */
    printf("  CPC :: consoles playing consoles\n");
    printf("  -------------------------------------\n\n");
    printf("  wii homebrew chat\n");
    printf("  step 1: it lives. no OS, just metal.\n\n");
    printf("  press HOME to exit.\n");

    while (1) {
        WPAD_ScanPads();
        if (WPAD_ButtonsDown(0) & WPAD_BUTTON_HOME) break;
        VIDEO_WaitVSync();
    }
    return 0;
}
