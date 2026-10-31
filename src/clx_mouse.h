#ifndef CLX_MOUSE_H
#define CLX_MOUSE_H

#include <stdint.h>
#include <SDL.h>

/* Native relative mouse camera for the PC port.
 *
 * The render thread owns SDL: clx_mouse_motion() receives the relative
 * motion events and clx_mouse_frame() maintains capture and fullscreen.
 * The guest camera thread calls clx_mouse_camera_active() to refresh the
 * activity timeout and check capture. Motion is delivered only through the
 * USB report, never as a second direct camera-angle adjustment. */
int clx_mouse_camera_active(void);

/* Add the deflection to pad 1's 20-byte USB report (RX at 16, RY at 18), so
 * every game system (player aim, camera users, the normal player camera)
 * sees it exactly like the right stick. Used as usb_gamepad_mouse_hook. */
void clx_mouse_report(uint8_t *report);

/* Which camera is running: 0 = off (pad only), 1 = player camera,
 * 2 = weapon aim (the slower aim camera gets the aim_gain boost).
 * Guest thread only: also applies/restores the guest's response curve. */
void clx_mouse_set_mode(int mode);

/* Preferred names used by the renderer. */
void clx_mouse_motion(int dx, int dy);
void clx_mouse_frame(SDL_Window *window);

#endif
