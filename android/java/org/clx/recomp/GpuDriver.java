package org.clx.recomp;

import android.content.Context;
import android.net.Uri;
import android.system.Os;

import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

/* A custom Vulkan driver (Mesa Turnip for Adreno) picked in the launcher.
 * The .zip is an AdrenoTools driver package: meta.json ("name",
 * "driverVersion", "libraryName") and the driver's .so. It is unpacked into
 * the app's own storage (dlopen refuses /sdcard) and libadrenotools loads it
 * when the game starts (nv2a_vk.c, vk_load). */
final class GpuDriver {
    private GpuDriver() {}

    static File dir(Context c) {
        return new File(c.getFilesDir(), "gpu_driver");
    }

    private static JSONObject meta(File d) {
        try (InputStream in = new FileInputStream(new File(d, "meta.json"))) {
            byte[] b = new byte[(int) new File(d, "meta.json").length()];
            int n = 0, r;
            while (n < b.length && (r = in.read(b, n, b.length - n)) > 0)
                n += r;
            JSONObject m = new JSONObject(new String(b, 0, n, "UTF-8"));
            return new File(d, m.getString("libraryName")).isFile() ? m : null;
        } catch (Exception e) {
            return null;
        }
    }

    /* "name version", or null for the system driver. */
    static String describe(Context c) {
        JSONObject m = meta(dir(c));
        if (m == null)
            return null;
        String s = m.optString("name", m.optString("libraryName"));
        String v = m.optString("driverVersion", "");
        return v.isEmpty() ? s : s + " " + v;
    }

    /* Unpacks the package at uri in place of the current one; returns an
     * error for the user, or null. */
    static String install(Context c, Uri uri) {
        File tmp = new File(c.getFilesDir(), "gpu_driver.tmp");
        delete(tmp);
        tmp.mkdirs();
        try (InputStream raw = c.getContentResolver().openInputStream(uri);
             ZipInputStream zip = new ZipInputStream(raw)) {
            ZipEntry e;
            byte[] buf = new byte[1 << 16];
            while ((e = zip.getNextEntry()) != null) {
                if (e.isDirectory())
                    continue;
                /* Flat: only the file name counts (no paths out of tmp). */
                String name = new File(e.getName()).getName();
                if (name.isEmpty() || name.startsWith("."))
                    continue;
                try (OutputStream out = new FileOutputStream(new File(tmp, name))) {
                    int n;
                    while ((n = zip.read(buf)) > 0)
                        out.write(buf, 0, n);
                }
            }
        } catch (IOException | RuntimeException ex) {
            delete(tmp);
            return "could not read the file: " + ex.getMessage();
        }
        if (meta(tmp) == null) {
            delete(tmp);
            return "not a driver package (needs meta.json and the .so it names, as in the AdrenoTools / Turnip releases)";
        }
        File d = dir(c);
        delete(d);
        if (!tmp.renameTo(d)) {
            delete(tmp);
            return "could not move the driver into place";
        }
        return null;
    }

    static void remove(Context c) {
        delete(dir(c));
    }

    /* In the game's process, before the native side starts. */
    static void apply(Context c) {
        File d = dir(c);
        JSONObject m = meta(d);
        try {
            if (m == null) {
                Os.unsetenv("RECOMP_VK_DRIVER_DIR");
                return;
            }
            Os.setenv("RECOMP_VK_DRIVER_DIR", d.getPath() + "/", true);
            Os.setenv("RECOMP_VK_DRIVER_LIB", m.getString("libraryName"), true);
            Os.setenv("RECOMP_VK_HOOK_DIR", c.getApplicationInfo().nativeLibraryDir + "/", true);
        } catch (Exception e) {
            android.util.Log.w("clx", "GPU driver: " + e);
        }
    }

    private static void delete(File f) {
        File[] l = f.listFiles();
        if (l != null)
            for (File x : l)
                delete(x);
        f.delete();
    }
}
