/* Experimental Windows fallback: refresh XInputGetState from the existing host report.
 * The guest USB enumeration/handles remain intact; CLX_NATIVE_PAD=0 keeps
 * the original guest implementation. Disabled unless CLX_NATIVE_PAD=1.
 */
#include "recomp_types.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdatomic.h>
extern void sub_0055BDF8_gen(void);
extern int usb_gamepad_report(int dev, uint8_t *out, int max);

void sub_0055BDF8(void)
{
    const char *e = getenv("CLX_NATIVE_PAD");
    static atomic_uint packet;
    static atomic_uint told;
    uint32_t handle = MEM32(g_esp + 4), out = MEM32(g_esp + 8);
    uint8_t report[20];
    int slot, host = 0, found = 0;
    if (!(e && *e == '1')) { sub_0055BDF8_gen(); return; }
    /* This title stores its open XInput handles in logical player order.
     * Enumeration can start at player 3; host pad 0 is the first open one. */
    for (slot = 0; slot < 4; slot++) {
        uint32_t candidate = MEM32(0x00806A48u + (unsigned)slot * 4);
        if (!candidate) continue;
        if (candidate == handle) { found = 1; break; }
        host++;
    }
    if (!found || host >= 2 || out < 0x10000u || out > 0x04000000u - 22 ||
        usb_gamepad_report(host, report, sizeof report) != 20) {
        g_eax = 1167;
    } else {
        MEM32(out) = atomic_fetch_add_explicit(&packet, 1, memory_order_relaxed) + 1;
        memcpy((void *)XBOX_PTR(out + 4), report + 2, 18);
        g_eax = 0;
        if (atomic_fetch_add_explicit(&told, 1, memory_order_relaxed) < 6)
            fprintf(stderr, "[native-pad] logical=%d host=%d packet=%u buttons=%02X%02X A=%u\n",
                    slot, host, MEM32(out), report[3], report[2], report[4]);
    }
    g_esp += 12;  /* stdcall: ret 8 */
}
