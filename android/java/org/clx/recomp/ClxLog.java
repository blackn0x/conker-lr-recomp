package org.clx.recomp;

import android.os.Build;
import android.os.Environment;

import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

/* Java exceptions nobody caught, written beside the native logs in
 * Download/ConkerLR-logs/ (src/android.c writes the native ones) before the
 * process ends. */
final class ClxLog {
    static final String DATA_DIR = "/storage/emulated/0/ConkerLR";
    static final String LOG_DIR = Environment.getExternalStoragePublicDirectory(
            Environment.DIRECTORY_DOWNLOADS).getAbsolutePath() + "/ConkerLR-logs";

    private ClxLog() {}

    static void install(final String where) {
        final Thread.UncaughtExceptionHandler prev = Thread.getDefaultUncaughtExceptionHandler();
        Thread.setDefaultUncaughtExceptionHandler((t, e) -> {
            write(where, t, e);
            if (prev != null)
                prev.uncaughtException(t, e);
        });
    }

    static void write(String where, Thread t, Throwable e) {
        String stamp = new SimpleDateFormat("yyyy-MM-dd_HH-mm-ss", Locale.US).format(new Date());
        File dir = new File(LOG_DIR);
        dir.mkdirs();
        try (PrintWriter w = new PrintWriter(new FileWriter(new File(dir, stamp + "_java_crash.txt")))) {
            w.println("Conker: Live & Reloaded, Android: Java exception in " + where
                    + ", thread " + t.getName());
            w.println("device: " + Build.MANUFACTURER + " " + Build.MODEL + ", Android "
                    + Build.VERSION.RELEASE + " (API " + Build.VERSION.SDK_INT + ")");
            e.printStackTrace(w);
        } catch (Exception ignored) {
            /* no storage access: logcat still has it */
        }
    }
}
