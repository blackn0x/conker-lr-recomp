package org.clx.recomp;

import android.content.Context;
import android.os.Build;
import android.os.CombinedVibration;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.os.VibratorManager;
import android.view.InputDevice;

import org.libsdl.app.SDLActivity;

/* Rumble for the game's pads (src/android.c calls set() from the game's
 * threads). SDL 2.30 has no rumble for Android's own joysticks, so this
 * drives the controller's vibrators itself: pad N is the Nth physical
 * gamepad, both motors where the controller has two (low on the first, high
 * on the second, as XInput). Pad 1 without a gamepad (the touch controls)
 * vibrates the phone. */
public final class Rumble {
    static native void nativeInit();

    /* A rumble lasts until the game changes it: it only sends changes. */
    private static final long LONG_MS = 60000;

    private static final Object[] current = new Object[4];   /* per pad: what vibrates, to cancel it */

    private static InputDevice gamepad(int port) {
        int n = 0;
        for (int id : InputDevice.getDeviceIds()) {
            InputDevice d = InputDevice.getDevice(id);
            if (d == null || d.isVirtual())
                continue;
            int s = d.getSources();
            if ((s & InputDevice.SOURCE_GAMEPAD) != InputDevice.SOURCE_GAMEPAD
                    && (s & InputDevice.SOURCE_JOYSTICK) != InputDevice.SOURCE_JOYSTICK)
                continue;
            if (n++ == port)
                return d;
        }
        return null;
    }

    private static VibrationEffect effect(Vibrator v, int speed) {
        int amp = Math.max(1, Math.min(255, speed / 257));
        return VibrationEffect.createOneShot(LONG_MS,
                v.hasAmplitudeControl() ? amp : VibrationEffect.DEFAULT_AMPLITUDE);
    }

    private static void stop(int port) {
        Object o = current[port];
        if (o instanceof VibratorManager)
            ((VibratorManager) o).cancel();
        else if (o instanceof Vibrator)
            ((Vibrator) o).cancel();
        current[port] = null;
    }

    /* low / high: XInput motor speeds, 0..65535. phone: pad 1 may fall back
     * to the phone's own vibrator. */
    static synchronized void set(int port, int low, int high, boolean phone) {
        if (port < 0 || port >= current.length)
            return;
        stop(port);
        if (low == 0 && high == 0)
            return;
        InputDevice d = gamepad(port);
        if (d != null) {
            if (Build.VERSION.SDK_INT >= 31) {
                VibratorManager vm = d.getVibratorManager();
                int[] ids = vm.getVibratorIds();
                if (ids.length >= 2) {
                    CombinedVibration.ParallelCombination c = CombinedVibration.startParallel();
                    if (low > 0)
                        c.addVibrator(ids[0], effect(vm.getVibrator(ids[0]), low));
                    if (high > 0)
                        c.addVibrator(ids[1], effect(vm.getVibrator(ids[1]), high));
                    vm.vibrate(c.combine());
                    current[port] = vm;
                    return;
                }
            }
            Vibrator v = d.getVibrator();
            if (v.hasVibrator()) {
                v.vibrate(effect(v, Math.max(low, high)));
                current[port] = v;
            }
            return;
        }
        if (port != 0 || !phone)
            return;
        Context ctx = SDLActivity.getContext();
        Vibrator v = ctx == null ? null : (Vibrator) ctx.getSystemService(Context.VIBRATOR_SERVICE);
        if (v != null && v.hasVibrator()) {
            /* A phone has one motor: the stronger of the two, softened. */
            v.vibrate(effect(v, Math.max(low, high) * 3 / 4));
            current[port] = v;
        }
    }
}
