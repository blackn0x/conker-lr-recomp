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

/* The right-stick deflection for this camera and frame, in the camera input
 * block's own units (-63..63, the range the game divides by 63). Each camera
 * receives it once per rendered frame. */
int clx_mouse_stick(uint32_t camera, int *rx, int *ry);

/* Preferred names used by the renderer. */
void clx_mouse_motion(int dx, int dy);
void clx_mouse_frame(SDL_Window *window);

#endif
