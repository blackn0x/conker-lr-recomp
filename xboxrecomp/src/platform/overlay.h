/* An RGBA overlay drawn over the presented frame (a port's settings menu).
 *
 * The painter (any thread) draws into a back buffer of OVL_W x OVL_H pixels
 * and publishes it; the renderer takes the published image when it changed
 * and blends it over the whole picture, scaled (straight alpha). Text is a
 * 5x7 bitmap font, upper case (lower case is drawn as upper case). */
#ifndef OVERLAY_H
#define OVERLAY_H

#include <stdint.h>

#define OVL_W 640
#define OVL_H 360

/* Colours as 0xAABBGGRR (bytes R, G, B, A in memory). */
#define OVL_RGBA(r, g, b, a) ((uint32_t)(r) | (uint32_t)(g) << 8 | (uint32_t)(b) << 16 | (uint32_t)(a) << 24)

void ovl_begin(void);                                     /* back buffer to transparent */
void ovl_rect(int x, int y, int w, int h, uint32_t rgba);
void ovl_text(int x, int y, int scale, uint32_t rgba, const char *s);
int  ovl_text_width(int scale, const char *s);
void ovl_publish(int visible);                            /* show (1) or hide (0) */

/* Renderer side: 0 = hidden. Otherwise 1, and when the image changed since
 * *gen also copies it (OVL_W * OVL_H * 4 bytes) to dst and returns 2. */
int ovl_take(unsigned *gen, void *dst);

/* The renderers' FPS counter: -1 = RECOMP_FPS_OSD decides (read once), else
 * 0/1, changed at run time by a menu. */
extern volatile int ovl_fps_osd;

/* Leave the game now (window closed, a menu's EXIT): the port's
 * recomp_quit_hook first (save its settings), then stdio flushed and the
 * process ended -- the title's host threads would keep a plain return alive.
 * On the Switch through exit() (its atexit handler ends the applet cleanly). */
extern void (*recomp_quit_hook)(void);
void recomp_host_quit(const char *why);

#endif
