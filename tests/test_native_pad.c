/* Local ABI/packing regression for the diagnostic input bridge. */
#include "../src/clx_native_pad.c"
#include <assert.h>
RECOMP_TLS RecompRegs _rr[1];
ptrdiff_t g_xbox_mem_offset;
static int polled = -1;
void sub_0055BDF8_gen(void) { abort(); }
int usb_gamepad_report(int dev, uint8_t *out, int max) {
    assert(max == 20); polled = dev;
    memset(out, 0, max); out[1] = 20; out[2] = 0x10; out[4] = 255;
    out[16] = 0x2e; out[17] = 0xfb; /* signed -1234 */
    return 20;
}
static void run(uint32_t h, uint32_t out) {
    g_esp = 0xf00000; MEM32(g_esp + 4) = h; MEM32(g_esp + 8) = out;
    g_ebx = 123; g_esi = 456; g_edi = 789;
    sub_0055BDF8();
    assert(g_esp == 0xf0000c && g_ebx == 123 && g_esi == 456 && g_edi == 789);
}
int main(void) {
    g_xbox_mem_offset = (ptrdiff_t)calloc(16*1024*1024,1);
    assert(g_xbox_mem_offset);
    _putenv("CLX_NATIVE_PAD=1");
    MEM32(0x806a48+8) = 0x80000289;
    MEM8(0xe00000+22) = 0x5a;
    run(0x80000289,0xe00000);
    assert(g_eax == 0 && polled == 0 && MEM32(0xe00000) == 1);
    assert(MEM16(0xe00000+4) == 0x10 && MEM8(0xe00000+6) == 255);
    assert((int16_t)MEM16(0xe00000+18) == -1234 && MEM8(0xe00000+22) == 0x5a);
    run(0x80000289,0xe00000); assert(MEM32(0xe00000)==2);
    MEM32(0x806a48+12) = 0x80000399;
    run(0x80000399,0xe00000); assert(polled == 1);
    run(0,0xe00000); assert(g_eax == 1167);
    run(0x80000289,0x03fffff9); assert(g_eax == 1167);
    puts("PASS native input handle mapping, fresh packets, 22-byte layout and stdcall ABI");
}
