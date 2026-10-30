/* Rumble when Conker is hurt (rumble_damage=1 in clx_options.txt).
 *
 * The game itself only rumbles for a few scripted events and effects
 * (0x0015A3F0 and its callers); taking a hit or a fall does nothing. This
 * watches Conker's energy -- the chocolate pieces, ob_energy: the word at
 * +0x3AE of object 0 in the object table at [0x0084A5F8], 0x6D0 bytes an
 * object; 0x0009DEFE prints it -- and pulses pad 1 when it drops. The
 * game's own Vibration setting (byte 0x0084B141) turns it off too.
 *
 * A drop only counts in play -- the globals the game's own rumble start
 * checks (0x0015A3F0: front end, pause and cutscene flags) all clear -- and
 * when the value before it had held for half a second and was a plausible
 * energy (1..6), so the title's demo, a level load or a respawn rebuilding
 * the table does not rumble. */
#include "clx_settings.h"
#include "usb/usb_gamepad.h"

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <time.h>

extern ptrdiff_t g_xbox_mem_offset;

#define OBJ_TABLE      0x0084A5F8u
#define OBJ_ENERGY     0x3AEu
#define OPT_VIBRATION  0x0084B141u
#define ENERGY_MAX     6

static const void *guest(uint32_t va)
{
    return (const void *)((uintptr_t)g_xbox_mem_offset + va);
}

/* 0x0015A3F0's early-outs: none may be set for the game to rumble. */
static int in_play(void)
{
    static const uint32_t bytes[] = { 0x008493ECu, 0x007FA273u, 0x007FA274u, 0x007FA275u,
                                      0x00862D08u };
    size_t i;
    if (*(const volatile uint32_t *)guest(0x00776574u))
        return 0;
    for (i = 0; i < sizeof bytes / sizeof bytes[0]; i++)
        if (*(const volatile uint8_t *)guest(bytes[i]))
            return 0;
    return 1;
}

static unsigned now_ms(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (unsigned)(ts.tv_sec * 1000u + ts.tv_nsec / 1000000);
}

static void damage_tick(void)
{
    static uint32_t last_table;
    static int last = -1;
    static unsigned since;
    uint32_t table;
    unsigned now;
    int e;

    if (!g_clx.rumble_damage || !g_xbox_mem_offset)
        return;
    table = *(const volatile uint32_t *)guest(OBJ_TABLE);
    now = now_ms();
    if (!table || table >= 0x04000000u) {
        last = -1;
        return;
    }
    e = *(const volatile uint16_t *)guest(table + OBJ_ENERGY);
    if (table != last_table || e > ENERGY_MAX || !in_play()) {
        last_table = table;
        last = -1;
        return;
    }
    if (e == last)
        return;
    if (last > 0 && e < last && now - since >= 500
            && *(const volatile uint8_t *)guest(OPT_VIBRATION)) {
        int dead = e == 0;
        printf("[rumble] Conker hurt: energy %d -> %d\n", last, e);
        usb_gamepad_pulse(0, dead ? 0xFFFF : 0xA000, dead ? 0xFFFF : 0xC000,
                          dead ? 700 : 280);
    }
    last = e;
    since = now;
}

void clx_pad_hook(unsigned char *report, unsigned host_buttons)
{
    damage_tick();
#if !defined(_WIN32) || defined(CLX_PC_GL)
    clx_menu_hook(report, host_buttons);
#else
    (void)report;
    (void)host_buttons;
#endif
}
