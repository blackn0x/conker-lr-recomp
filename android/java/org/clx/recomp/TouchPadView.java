package org.clx.recomp;

import android.content.Context;
import android.content.SharedPreferences;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.RectF;
import android.hardware.input.InputManager;
import android.view.HapticFeedbackConstants;
import android.view.InputDevice;
import android.view.MotionEvent;
import android.view.View;

/* On-screen controls, drawn over SDL's surface. Each change goes to the
 * native side (src/android.c), which the input layer merges into pad 1 as it
 * does the keyboard. Hidden while a physical gamepad is connected; a touch
 * brings it back. The small button at the top centre turns the controls off
 * (only it stays on screen) and on again; the choice is kept.
 *
 * Buttons are a 16-bit mask in the order of xinput_device.c's k_pad_ctl:
 * up down left right start back lthumb rthumb (the Xbox wButtons bits) and
 * A B X Y black white LT RT (the analog buttons, pressed = 255). */
public class TouchPadView extends View implements InputManager.InputDeviceListener {
    static native void nativeState(int buttons, float lx, float ly, float rx, float ry);

    static final int UP = 0, DOWN = 1, LEFT = 2, RIGHT = 3, START = 4, BACK = 5,
            LTHUMB = 6, RTHUMB = 7, A = 8, B = 9, X = 10, Y = 11,
            BLACK = 12, WHITE = 13, LT = 14, RT = 15;

    /* A round or rectangular button: centre and size in units of the
     * screen height, x from the left (or the right edge when negative). */
    static final class Btn {
        final int bit; final String label; final float cx, cy, r; final boolean rect; final int color;
        float px, py, pr;               /* in pixels, set by layout() */
        Btn(int bit, String label, float cx, float cy, float r, boolean rect, int color) {
            this.bit = bit; this.label = label; this.cx = cx; this.cy = cy; this.r = r;
            this.rect = rect; this.color = color;
        }
    }

    private final Btn[] btns = {
        new Btn(A,      "A",  -0.30f, 0.84f, 0.075f, false, 0xFF5BBF4A),
        new Btn(B,      "B",  -0.15f, 0.70f, 0.075f, false, 0xFFD9443A),
        new Btn(X,      "X",  -0.45f, 0.70f, 0.075f, false, 0xFF3A7BD9),
        new Btn(Y,      "Y",  -0.30f, 0.56f, 0.075f, false, 0xFFE0C23A),
        new Btn(BLACK,  "Bk", -0.52f, 0.90f, 0.050f, false, 0xFF404040),
        new Btn(WHITE,  "Wh", -0.08f, 0.90f, 0.050f, false, 0xFFE8E8E8),
        new Btn(LT,     "LT",  0.14f, 0.10f, 0.070f, true,  0xFFB0B0B0),
        new Btn(RT,     "RT", -0.14f, 0.10f, 0.070f, true,  0xFFB0B0B0),
        new Btn(BACK,   "Back", 0f,   0.08f, 0.045f, true,  0xFFB0B0B0),
        new Btn(START,  "Start", 0f,  0.08f, 0.045f, true,  0xFFB0B0B0),
        new Btn(UP,     "",    0.52f, 0.58f, 0.050f, true,  0xFFB0B0B0),
        new Btn(DOWN,   "",    0.52f, 0.82f, 0.050f, true,  0xFFB0B0B0),
        new Btn(LEFT,   "",    0.40f, 0.70f, 0.050f, true,  0xFFB0B0B0),
        new Btn(RIGHT,  "",    0.64f, 0.70f, 0.050f, true,  0xFFB0B0B0),
        new Btn(LTHUMB, "L3",  0.10f, 0.45f, 0.045f, false, 0xFFB0B0B0),
        new Btn(RTHUMB, "R3", -0.10f, 0.45f, 0.045f, false, 0xFFB0B0B0),
    };

    /* A stick follows the finger that lands in its zone: the touch-down
     * point is the centre, the drag is the deflection. */
    static final class Stick {
        int pointer = -1;
        float ox, oy, x, y;             /* centre and knob, pixels */
        float vx, vy;                   /* -1..1, y down */
        float homeX, homeY;             /* where it is drawn while idle */
    }

    private final Stick left = new Stick(), right = new Stick();
    private final int[] btnPointer = new int[16];   /* pointer holding each button, or -1 */
    private final Paint fill = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint ring = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint text = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF rect = new RectF();
    private float stickRadius;
    private int sentButtons = -1;
    private float sentLx, sentLy, sentRx, sentRy;
    private boolean hidden;             /* drawn nothing; a touch shows it */
    private boolean off;                /* turned off with the toggle: only it is drawn */
    private float toggleX, toggleY, toggleR;
    private final SharedPreferences prefs;

    public TouchPadView(Context ctx) {
        super(ctx);
        java.util.Arrays.fill(btnPointer, -1);
        ring.setStyle(Paint.Style.STROKE);
        ring.setColor(Color.WHITE);
        text.setColor(Color.WHITE);
        text.setTextAlign(Paint.Align.CENTER);
        text.setFakeBoldText(true);
        setAlpha(0.55f);
        setHapticFeedbackEnabled(true);
        prefs = ctx.getSharedPreferences("touchpad", Context.MODE_PRIVATE);
        off = prefs.getBoolean("off", false);
        InputManager im = (InputManager) ctx.getSystemService(Context.INPUT_SERVICE);
        im.registerInputDeviceListener(this, null);
        updatePadConnected();
    }

    private static boolean isGamepad(InputDevice d) {
        if (d == null || d.isVirtual())
            return false;
        int s = d.getSources();
        return (s & InputDevice.SOURCE_GAMEPAD) == InputDevice.SOURCE_GAMEPAD
            || (s & InputDevice.SOURCE_JOYSTICK) == InputDevice.SOURCE_JOYSTICK;
    }

    private void updatePadConnected() {
        boolean any = false;
        for (int id : InputDevice.getDeviceIds())
            any |= isGamepad(InputDevice.getDevice(id));
        /* Still VISIBLE while hidden: an invisible view gets no touches. */
        if (any)
            release();
        hidden = any;
        invalidate();
    }

    @Override public void onInputDeviceAdded(int id) { updatePadConnected(); }
    @Override public void onInputDeviceRemoved(int id) { updatePadConnected(); }
    @Override public void onInputDeviceChanged(int id) { updatePadConnected(); }

    @Override
    protected void onSizeChanged(int w, int h, int ow, int oh) {
        float u = h;
        for (Btn b : btns) {
            b.px = b.cx < 0 ? w + b.cx * u : b.cx * u;
            b.py = b.cy * u;
            b.pr = b.r * u;
        }
        /* Back and Start sit either side of the top centre. */
        btns[8].px = w / 2f - 0.10f * u;
        btns[9].px = w / 2f + 0.10f * u;
        toggleX = w / 2f;
        toggleY = 0.20f * u;
        toggleR = 0.040f * u;
        stickRadius = 0.13f * u;
        left.homeX = 0.20f * u;  left.homeY = 0.74f * u;
        right.homeX = w - 0.62f * u; right.homeY = 0.40f * u;
        text.setTextSize(0.045f * u);
        ring.setStrokeWidth(0.006f * u);
    }

    private Btn hit(float x, float y) {
        for (Btn b : btns) {
            float dx = x - b.px, dy = y - b.py, slop = b.pr * 1.25f;
            if (b.rect ? Math.abs(dx) < slop * 1.4f && Math.abs(dy) < slop
                       : dx * dx + dy * dy < slop * slop)
                return b;
        }
        return null;
    }

    private void press(int pointer, float x, float y) {
        Btn b = hit(x, y);
        int w = getWidth();
        if (b != null) {
            if (btnPointer[b.bit] < 0)
                performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY);
            btnPointer[b.bit] = pointer;
        } else if (x < w * 0.40f && left.pointer < 0) {
            grab(left, pointer, x, y);
        } else if (x >= w * 0.40f && right.pointer < 0) {
            grab(right, pointer, x, y);
        }
    }

    private void grab(Stick s, int pointer, float x, float y) {
        s.pointer = pointer;
        s.ox = s.x = x;
        s.oy = s.y = y;
        s.vx = s.vy = 0;
    }

    private void move(Stick s, float x, float y) {
        float dx = x - s.ox, dy = y - s.oy, d = (float) Math.hypot(dx, dy);
        if (d > stickRadius) {
            dx *= stickRadius / d;
            dy *= stickRadius / d;
        }
        s.x = s.ox + dx;
        s.y = s.oy + dy;
        s.vx = dx / stickRadius;
        s.vy = dy / stickRadius;
    }

    private void lift(int pointer) {
        for (int i = 0; i < 16; i++)
            if (btnPointer[i] == pointer)
                btnPointer[i] = -1;
        for (Stick s : new Stick[] { left, right })
            if (s.pointer == pointer) {
                s.pointer = -1;
                s.vx = s.vy = 0;
            }
    }

    private void release() {
        java.util.Arrays.fill(btnPointer, -1);
        left.pointer = right.pointer = -1;
        left.vx = left.vy = right.vx = right.vy = 0;
        send();
    }

    private boolean onToggle(float x, float y) {
        float dx = x - toggleX, dy = y - toggleY, slop = toggleR * 1.4f;
        return dx * dx + dy * dy < slop * slop;
    }

    @Override
    public boolean onTouchEvent(MotionEvent e) {
        int am = e.getActionMasked(), ai = e.getActionIndex();
        if ((am == MotionEvent.ACTION_DOWN || am == MotionEvent.ACTION_POINTER_DOWN)
                && !hidden && onToggle(e.getX(ai), e.getY(ai))) {
            off = !off;
            prefs.edit().putBoolean("off", off).apply();
            release();
            performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY);
            invalidate();
            return true;
        }
        if (off)
            return am == MotionEvent.ACTION_DOWN && onToggle(e.getX(ai), e.getY(ai));
        if (hidden) {
            hidden = false;
            invalidate();
            return true;
        }
        int i = e.getActionIndex();
        switch (e.getActionMasked()) {
        case MotionEvent.ACTION_DOWN:
        case MotionEvent.ACTION_POINTER_DOWN:
            press(e.getPointerId(i), e.getX(i), e.getY(i));
            break;
        case MotionEvent.ACTION_MOVE:
            for (int p = 0; p < e.getPointerCount(); p++) {
                int id = e.getPointerId(p);
                float x = e.getX(p), y = e.getY(p);
                if (left.pointer == id) move(left, x, y);
                else if (right.pointer == id) move(right, x, y);
                else {
                    /* A finger sliding between buttons (the d-pad, the
                     * face buttons) takes the one it is now on. */
                    Btn b = hit(x, y);
                    boolean holding = false;
                    for (int k = 0; k < 16; k++)
                        if (btnPointer[k] == id) {
                            holding = true;
                            if (b == null || b.bit != k)
                                btnPointer[k] = -1;
                        }
                    if (holding && b != null && btnPointer[b.bit] != id) {
                        btnPointer[b.bit] = id;
                        performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY);
                    }
                }
            }
            break;
        case MotionEvent.ACTION_UP:
        case MotionEvent.ACTION_POINTER_UP:
            lift(e.getPointerId(i));
            break;
        case MotionEvent.ACTION_CANCEL:
            release();
            break;
        }
        send();
        invalidate();
        return true;
    }

    private void send() {
        int bits = 0;
        for (int k = 0; k < 16; k++)
            if (btnPointer[k] >= 0)
                bits |= 1 << k;
        if (bits == sentButtons && left.vx == sentLx && left.vy == sentLy
                && right.vx == sentRx && right.vy == sentRy)
            return;
        sentButtons = bits;
        sentLx = left.vx; sentLy = left.vy; sentRx = right.vx; sentRy = right.vy;
        nativeState(bits, left.vx, left.vy, right.vx, right.vy);
    }

    @Override
    protected void onDraw(Canvas c) {
        if (hidden)
            return;
        fill.setColor(0xFF808080);
        fill.setAlpha(off ? 60 : 110);
        c.drawCircle(toggleX, toggleY, toggleR, fill);
        c.drawCircle(toggleX, toggleY, toggleR, ring);
        text.setTextSize(toggleR * 0.75f);
        c.drawText(off ? "Pad" : "Hide", toggleX, toggleY - (text.descent() + text.ascent()) / 2, text);
        text.setTextSize(0.045f * getHeight());
        if (off)
            return;
        for (Btn b : btns) {
            boolean down = btnPointer[b.bit] >= 0;
            fill.setColor(b.color);
            fill.setAlpha(down ? 230 : 110);
            if (b.rect) {
                rect.set(b.px - b.pr * 1.4f, b.py - b.pr, b.px + b.pr * 1.4f, b.py + b.pr);
                c.drawRoundRect(rect, b.pr * 0.4f, b.pr * 0.4f, fill);
                c.drawRoundRect(rect, b.pr * 0.4f, b.pr * 0.4f, ring);
            } else {
                c.drawCircle(b.px, b.py, b.pr, fill);
                c.drawCircle(b.px, b.py, b.pr, ring);
            }
            if (!b.label.isEmpty())
                c.drawText(b.label, b.px, b.py - (text.descent() + text.ascent()) / 2, text);
        }
        drawStick(c, left, "L");
        drawStick(c, right, "Cam");
    }

    private void drawStick(Canvas c, Stick s, String label) {
        float ox = s.pointer >= 0 ? s.ox : s.homeX, oy = s.pointer >= 0 ? s.oy : s.homeY;
        float kx = s.pointer >= 0 ? s.x : ox, ky = s.pointer >= 0 ? s.y : oy;
        fill.setColor(0xFF808080);
        fill.setAlpha(70);
        c.drawCircle(ox, oy, stickRadius, fill);
        c.drawCircle(ox, oy, stickRadius, ring);
        fill.setColor(0xFFE0E0E0);
        fill.setAlpha(s.pointer >= 0 ? 220 : 130);
        c.drawCircle(kx, ky, stickRadius * 0.45f, fill);
        c.drawText(label, kx, ky - (text.descent() + text.ascent()) / 2, text);
    }
}
