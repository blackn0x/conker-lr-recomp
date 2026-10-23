/* Windows (MinGW) with the OpenGL pushbuffer renderer: the host hooks that
 * win32_compat.c (POSIX/Switch) provides and the renderer, kernel and APU call.
 * The Windows scheduler is left to place threads; the rest is not needed. */
#include <stdint.h>
#include <windows.h>
#include "frame_stats.h"

/* RECOMP_FRAME_STATS reads POSIX per-thread CPU clocks: not available here. */
int  fs_on(void) { return 0; }
void fs_thread(int which) { (void)which; }
void fs_add(int stat, uint64_t ns) { (void)stat; (void)ns; }
void fs_frame(unsigned draws, unsigned programs, unsigned textures)
{
    (void)draws; (void)programs; (void)textures;
}

/* Thread placement and naming for the Switch's CPU report. */
void xbox_nx_track_thread(void *entry) { (void)entry; }
void xbox_nx_retag_thread(void *entry) { (void)entry; }
void xbox_nx_pin_executor(void) { }
void xbox_nx_pin_renderer(void) { }
void xbox_nx_raise_timer_thread(void) { }
void xbox_nx_raise_host_thread(void) { }

/* The D3D8 -> D3D11 layer is not built here (a null d3d8 layer); the FMV
 * player of that layer is not used by this title. */
UINT d3d8_GetBackbufferWidth(void) { return 0; }
UINT d3d8_GetBackbufferHeight(void) { return 0; }
HRESULT d3d8_CreateTextureImpl(UINT w, UINT h, UINT levels, DWORD usage, int fmt, void **out)
{
    (void)w; (void)h; (void)levels; (void)usage; (void)fmt; (void)out;
    return E_FAIL;
}
