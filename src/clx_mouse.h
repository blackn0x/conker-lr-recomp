#ifndef CLX_MOUSE_H
#define CLX_MOUSE_H

#include <stdint.h>
#include <SDL.h>

/* Native relative mouse camera for the PC port.
 *
 * The render thread owns SDL: clx_mouse_motion() receives the relative
 * motion events and clx_mouse_frame() maintains capture and fullscreen.
 * The guest camera thread consumes the accumulated angle in
 * clx_mouse_take() exactly once per rendered frame.
 *
 * clx_mouse_take() returns 1 when the mouse currently drives the camera;
 * *yaw is in radians (added to the camera's yaw angle) and *pitch is in
 * degrees (added to its pitch angle). */
int clx_mouse_take(uint32_t camera, float *yaw, float *pitch);

/* The one-frame deflection as raw USB pad axes (-32767..32767). */
int clx_mouse_pad(int *rx, int *ry);

/* Add the deflection to pad 1's 20-byte USB report (RX at 16, RY at 18), so
 * every game system (player aim, camera users, the normal player camera)
 * sees it exactly like the right stick. Used as usb_gamepad_mouse_hook. */
void clx_mouse_report(uint8_t *report);

/* Which camera is running: 0 = off (pad only), 1 = player camera,
 * 2 = weapon aim (the slower aim camera gets the aim_gain boost). */
void clx_mouse_set_mode(int mode);

/* Preferred names used by the renderer. */
void clx_mouse_motion(int dx, int dy);
void clx_mouse_frame(SDL_Window *window);

#endif
