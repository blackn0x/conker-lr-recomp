/* Button icons in the style of the pad in hand (button_glyphs=switch|xbox|ps).
 *
 * Conker draws its button icons from small DXT5 textures: the face buttons
 * (A green, B red, X blue, Y yellow, 32x32: text tags {A}..{Y} and the pause
 * board), the triggers ({L} {R}, 64x64) and six frames of a thumbstick
 * ({JOYSTICK}, 64x64). Found with RECOMP_TEX_DUMP in the pause menu and in a
 * text line holding every button tag; identified here by the hash of their
 * decoded pixels (nv2a_tex_hash), so any code that draws them is covered.
 * Our own glyphs (tools/make_glyphs.py) replace them by position: the Xbox
 * bottom button is the Switch's B and PlayStation's cross, and so on, as our
 * Switch input maps buttons by position (xinput_nx.c). */
#include "clx_settings.h"
#include "clx_glyphs.h"

#include <stdint.h>
#include <stdio.h>

uint64_t nv2a_tex_hash(uint32_t w, uint32_t h, const uint32_t *argb);   /* nv2a_pb_exec.c */

static const struct { uint64_t hash; uint8_t sw, ps; const char *what; } k_icons[] = {
    { 0x8ed39c7c2236f710ull, G_SW_B,  G_PS_CROSS,    "A (bottom)" },
    { 0x88e558833202f82bull, G_SW_A,  G_PS_CIRCLE,   "B (right)" },
    { 0xd3712c0b8c068c34ull, G_SW_Y,  G_PS_SQUARE,   "X (left)" },
    { 0x87544c442f306ef5ull, G_SW_X,  G_PS_TRIANGLE, "Y (top)" },
    { 0xc0d2fad48ed248adull, G_SW_ZL, G_PS_L2,       "left trigger" },
    { 0xf9f4a966c7bc1aceull, G_SW_ZR, G_PS_R2,       "right trigger" },
    { 0x936e1b56fc7fb244ull, G_STICK, G_STICK,       "stick" },
    { 0xc675dd504025ce78ull, G_STICK, G_STICK,       "stick" },
    { 0xc8f5451829ab7d2dull, G_STICK, G_STICK,       "stick" },
    { 0xcfd4d4893f83d98cull, G_STICK, G_STICK,       "stick" },
    { 0xfee2a68c4527a2bfull, G_STICK, G_STICK,       "stick" },
    { 0xff58563da7c62c9aull, G_STICK, G_STICK,       "stick" },
};

/* nv2a_tex_hook: a decoded texture level, before the renderer uploads it. */
void clx_buttons_hook(uint32_t va, uint32_t color, uint32_t w, uint32_t h, uint32_t *argb)
{
    static unsigned logged;
    uint64_t hs;
    unsigned i, x, y;

    (void)va;
    if (color != 0x0F || w != h || (w != 32 && w != 64))
        return;
    hs = nv2a_tex_hash(w, h, argb);
    for (i = 0; i < sizeof k_icons / sizeof k_icons[0]; i++) {
        if (k_icons[i].hash != hs)
            continue;
        {
            int g = g_clx.glyphs == 2 ? k_icons[i].ps : k_icons[i].sw;
            const uint32_t *src = k_glyphs[g].px;
            uint32_t n = k_glyphs[g].size;
            for (y = 0; y < h; y++)                  /* nearest, if the sizes differ */
                for (x = 0; x < w; x++)
                    argb[y * w + x] = src[(y * n / h) * n + x * n / w];
        }
        if (!(logged & (1u << i))) {
            logged |= 1u << i;
            printf("[buttons] Xbox %s icon drawn in %s style\n", k_icons[i].what,
                   g_clx.glyphs == 2 ? "PlayStation" : "Switch");
        }
        return;
    }
}
