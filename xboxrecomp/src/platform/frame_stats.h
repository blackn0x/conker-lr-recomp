/* RECOMP_FRAME_STATS=1: one "[ft]" line per second in the log, the cost of
 * an average frame split by where it goes:
 *
 *   [ft] 47 fps, frame 21.3 avg / 35.0 max ms | cpu per frame: game 12.1
 *        exec 8.3 rec 9.0 pres 0.4 | game fence wait 3.0 | gpu 14.2 / 19.0 |
 *        rec slot wait 1.2, acquire 0.1 | 750 draws, 0 programs, 2 textures
 *
 * cpu = the thread's own CPU time (Horizon thread ticks, Linux
 * CLOCK_THREAD_CPUTIME) over the second, divided by the frames; the other
 * times are wall time per frame, avg / max over the second. */
#ifndef FRAME_STATS_H
#define FRAME_STATS_H

#include <stdint.h>

enum { FS_T_GAME, FS_T_EXEC, FS_T_REC, FS_T_PRES, FS_T_N };      /* threads */
enum { FS_GAME_WAIT, FS_GPU, FS_SLOT_WAIT, FS_ACQUIRE, FS_N };    /* times */

int  fs_on(void);
void fs_thread(int which);            /* the calling thread is `which` */
void fs_add(int stat, uint64_t ns);
/* GPU timestamps wanted: the [ft] line, or Android's performance hints. */
int  fs_want_gpu(void);
/* The frame rate the title runs at, the budget for the performance hints. */
void fs_target_fps(int fps);
/* Once per presented frame, from the renderer's flip. */
void fs_frame(unsigned draws, unsigned programs, unsigned textures);

#endif
