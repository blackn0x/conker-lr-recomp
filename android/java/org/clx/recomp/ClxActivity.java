package org.clx.recomp;

import android.app.GameManager;
import android.app.GameState;
import android.os.Build;
import android.os.Bundle;
import android.system.Os;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;

import org.libsdl.app.SDLActivity;

/* The game: SDL's activity in a process of its own (":game"), so the native
 * runtime can end with exit() and start fresh the next time. */
public class ClxActivity extends SDLActivity {
    @Override
    protected String[] getLibraries() {
        return new String[] { "SDL2", "main" };
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        ClxLog.install("game");
        ExitInfo.record(this);         /* how the last run ended, for the log */
        GpuDriver.apply(this);         /* a custom Vulkan driver, if one is picked */
        gameMode();                    /* before SDL starts the native side */
        super.onCreate(savedInstanceState);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        /* Here, on the UI thread: the game's threads cannot look up app
         * classes themselves (Rumble.java). */
        Rumble.nativeInit();
        /* The on-screen controls, over the game (TouchPadView). */
        addContentView(new TouchPadView(this), new ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
    }

    /* Game Mode (res/xml/game_mode_config.xml): only the user picks it, in the
     * phone's game dashboard or booster; an app cannot set it. Log which one
     * is on, and say the game is being played (not loading) from Android 13. */
    private void gameMode() {
        if (Build.VERSION.SDK_INT < 31)
            return;
        GameManager gm = getSystemService(GameManager.class);
        if (gm == null)
            return;
        int m = gm.getGameMode();
        try {
            /* For the log's header (src/android.c). */
            Os.setenv("CLX_GAME_MODE", m == GameManager.GAME_MODE_PERFORMANCE ? "performance"
                    : m == GameManager.GAME_MODE_BATTERY ? "battery"
                    : m == GameManager.GAME_MODE_STANDARD ? "standard" : "unsupported (" + m + ")", true);
        } catch (Exception ignored) {
        }
        if (Build.VERSION.SDK_INT >= 33)
            gm.setGameState(new GameState(false, GameState.MODE_GAMEPLAY_UNINTERRUPTIBLE));
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus)
            getWindow().getDecorView().setSystemUiVisibility(
                    View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY | View.SYSTEM_UI_FLAG_FULLSCREEN
                    | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION | View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                    | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION);
    }
}
