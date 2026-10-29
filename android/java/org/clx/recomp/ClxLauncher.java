package org.clx.recomp;

import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.Settings;
import android.view.Gravity;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.io.File;

/* First screen: storage access, the game folder and the GPU, checked before
 * the game starts. Built in code: the APK has no layout resources. */
public class ClxLauncher extends Activity {
    private TextView status;
    private Button grant, start;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        ClxLog.install("launcher");

        int pad = (int) (16 * getResources().getDisplayMetrics().density);
        LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        col.setPadding(pad, pad, pad, pad);

        TextView title = new TextView(this);
        title.setText("Conker: Live & Reloaded (Xbox recomp)");
        title.setTextSize(22);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        col.addView(title);

        status = new TextView(this);
        status.setTextSize(15);
        status.setPadding(0, pad, 0, pad);
        col.addView(status);

        grant = new Button(this);
        grant.setText("Allow all files access");
        grant.setOnClickListener(v -> askStorage());
        col.addView(grant);

        start = new Button(this);
        start.setText("Start");
        start.setOnClickListener(v -> startActivity(new Intent(this, ClxActivity.class)));
        col.addView(start);

        ScrollView sv = new ScrollView(this);
        sv.addView(col);
        setContentView(sv);
    }

    @Override
    protected void onResume() {
        super.onResume();
        refresh();
    }

    private static boolean storageOk() {
        return Environment.isExternalStorageManager();
    }

    private void askStorage() {
        try {
            startActivity(new Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION,
                    Uri.parse("package:" + getPackageName())));
        } catch (Exception e) {
            startActivity(new Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION));
        }
    }

    private void refresh() {
        boolean storage = storageOk();
        File xbe = new File(ClxLog.DATA_DIR + "/game/default.xbe");
        boolean game = storage && xbe.isFile();
        PackageManager pm = getPackageManager();
        boolean vk13 = pm.hasSystemFeature(PackageManager.FEATURE_VULKAN_HARDWARE_VERSION, 0x403000);
        boolean arm64 = false;
        for (String abi : Build.SUPPORTED_ABIS)
            arm64 |= abi.equals("arm64-v8a");

        StringBuilder s = new StringBuilder();
        s.append(storage ? "✓ All files access\n" : "✗ All files access: needed for the game folder and the logs\n");
        s.append(game ? "✓ Game found: " : "✗ No game: copy your unpacked disc so this file exists:\n   ")
         .append(xbe.getPath()).append('\n');
        s.append(vk13 ? "✓ Vulkan 1.3\n" : "! The system does not report Vulkan 1.3; the game will probably not start\n");
        if (!arm64)
            s.append("✗ Not an arm64 device\n");
        s.append("\nControls: on screen, or a Bluetooth or USB gamepad (the touch controls hide while one is connected).");
        s.append("\nSettings: ").append(ClxLog.DATA_DIR).append("/clx_options.txt and clx_env.txt");
        s.append("\nLogs (one folder per start, crash reports included):\n   ").append(ClxLog.LOG_DIR);
        s.append("\nAttach the newest folder to a bug report.");
        status.setText(s.toString());
        status.setGravity(Gravity.START);
        grant.setEnabled(!storage);
        start.setEnabled(game && arm64);
    }
}
