/* Keyboard as pad 1 on a PC (SDL2), merged with a real pad there.
 *
 * Default layout (an Xbox pad's controls):
 *   W A S D          left stick            arrows, I J K L   right stick (camera)
 *   Space            A                     E                 B
 *   Q                X                     R                 Y
 *   Z                white                 X                 black
 *   Left Shift       left trigger          Left Ctrl         right trigger
 *   Enter            START                 Esc               BACK (the menu)
 *   C                left stick click      V                 right stick click
 *   1 2 3 4          d-pad up/down/left/right
 *
 * xbox_keys_bind("a", "Return") replaces a control's keys with one key (SDL
 * key names, as SDL_GetScancodeFromName); a port reads them from its options
 * file (key_a=Return). */
#ifndef SDL_KEYS_H
#define SDL_KEYS_H

#include "xinput_xbox.h"
#include <stdint.h>

/* Control names: up down left right start back lthumb rthumb a b x y black
 * white lt rt ls_up ls_down ls_left ls_right rs_up rs_down rs_left rs_right.
 * Returns 1 when both names were known. */
int xbox_keys_bind(const char *control, const char *key);

/* ORs the keys held in keystate (indexed by SDL scancode, n entries) into s;
 * 1 when any mapped key is held. Pure: tested without a window. */
int xbox_keys_apply(const uint8_t *keystate, int n, XBOX_INPUT_STATE *s);

/* Back to the default layout above. */
void xbox_keys_reset(void);
/* For a remap screen: a key newly pressed in keystate since the last call, by
 * its SDL name (SDL_GetScancodeName); 1 if there is one. */
int xbox_keys_poll_new(const uint8_t *keystate, int n, char *out, int len);

/* Pads (xinput_device.c, SDL path): bind a control to an SDL input ("a",
 * "leftshoulder", "lefttrigger", "+leftx", "-lefty"); back to the defaults;
 * pad 1's name (NULL: none) and how many are attached; make the next
 * attached pad pad 1; an input newly pressed on pad 1, by name. */
int xbox_pad_bind(const char *control, const char *input);
void xbox_pad_reset(void);
const char *xbox_pad_name(void);
int xbox_pad_count(void);
void xbox_pad_cycle(void);
int xbox_pad_poll_new(char *out, int n);

#endif
