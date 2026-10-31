package org.clx.recomp;

import android.app.ActivityManager;
import android.app.ApplicationExitInfo;
import android.content.Context;
import android.os.Build;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileWriter;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.PrintWriter;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.List;
import java.util.Locale;

/* Why the game's previous run ended, as Android recorded it (low memory, an
 * ANR, a crash, a signal...). A process the system kills leaves no report of
 * its own, so the next start asks and writes the answer to
 * ConkerLR/last_exit.txt; src/android.c copies it into the new log. */
final class ExitInfo {
    static final String FILE = ClxLog.DATA_DIR + "/last_exit.txt";
    private static final int TRACE_LINES = 120;

    private ExitInfo() {}

    private static String reason(int r) {
        switch (r) {
        case ApplicationExitInfo.REASON_ANR: return "ANR (not responding)";
        case ApplicationExitInfo.REASON_CRASH: return "Java crash";
        case ApplicationExitInfo.REASON_CRASH_NATIVE: return "native crash";
        case ApplicationExitInfo.REASON_DEPENDENCY_DIED: return "dependency died";
        case ApplicationExitInfo.REASON_EXCESSIVE_RESOURCE_USAGE: return "excessive resource usage";
        case ApplicationExitInfo.REASON_EXIT_SELF: return "exited by itself";
        case ApplicationExitInfo.REASON_INITIALIZATION_FAILURE: return "initialization failure";
        case ApplicationExitInfo.REASON_LOW_MEMORY: return "low memory (killed by the system)";
        case ApplicationExitInfo.REASON_OTHER: return "other";
        case ApplicationExitInfo.REASON_PERMISSION_CHANGE: return "permission change";
        case ApplicationExitInfo.REASON_SIGNALED: return "killed by a signal";
        case ApplicationExitInfo.REASON_USER_REQUESTED: return "user requested (force stop / swiped away)";
        case ApplicationExitInfo.REASON_USER_STOPPED: return "user stopped";
        default: return "unknown (" + r + ")";
        }
    }

    static void record(Context ctx) {
        if (Build.VERSION.SDK_INT < 30)
            return;
        try {
            ActivityManager am = (ActivityManager) ctx.getSystemService(Context.ACTIVITY_SERVICE);
            List<ApplicationExitInfo> list =
                    am.getHistoricalProcessExitReasons(ctx.getPackageName(), 0, 8);
            ApplicationExitInfo last = null;
            for (ApplicationExitInfo e : list)
                if (e.getProcessName().endsWith(":game")) {
                    last = e;           /* newest first */
                    break;
                }
            if (last == null)
                return;
            SimpleDateFormat f = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US);
            try (PrintWriter w = new PrintWriter(new FileWriter(new File(FILE)))) {
                w.println("previous run ended " + f.format(new Date(last.getTimestamp()))
                        + ": " + reason(last.getReason()));
                w.println("  status " + last.getStatus() + ", importance " + last.getImportance()
                        + ", pss " + last.getPss() / 1024 + " MB, rss " + last.getRss() / 1024 + " MB");
                if (last.getDescription() != null)
                    w.println("  description: " + last.getDescription());
                /* An ANR's thread dump; a native crash's tombstone (API 31+,
                 * protobuf, not worth decoding here). */
                if (last.getReason() == ApplicationExitInfo.REASON_ANR) {
                    InputStream in = last.getTraceInputStream();
                    if (in != null) {
                        try (BufferedReader r = new BufferedReader(new InputStreamReader(in))) {
                            String line;
                            for (int n = 0; n < TRACE_LINES && (line = r.readLine()) != null; n++)
                                w.println("  | " + line);
                        }
                    }
                }
            }
        } catch (Exception e) {
            /* no storage access or no record: nothing to say */
        }
    }
}
