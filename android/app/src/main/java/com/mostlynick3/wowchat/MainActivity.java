package com.mostlynick3.wowchat;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.PowerManager;
import android.provider.Settings;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.Socket;

/** WebView host for the desktop web UI. A logged-out app stays closable;
 *  Python preserves the backend in background only during a session. */
public class MainActivity extends Activity {
    private static final String URL = "http://127.0.0.1:5950/";
    private static final int PORT = 5950;

    private WebView mWebView;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        mWebView = new WebView(this);
        setContentView(mWebView);
        WebSettings s = mWebView.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        mWebView.setWebViewClient(new WebViewClient());
        startBackendService();
        requestBackgroundPermissions();
        waitForServerThenLoad();
    }

    /** Nothing is pinned while logged out. */
    private void startBackendService() {
        startService(new Intent(this, ChatBackendService.class));
    }

    /** The foreground notification needs POST_NOTIFICATIONS on 13+, and
     *  Doze can still suspend the network unless this app is exempt from
     *  battery optimization. Ask once. */
    private void requestBackgroundPermissions() {
        if (Build.VERSION.SDK_INT >= 33
                && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(
                    new String[]{Manifest.permission.POST_NOTIFICATIONS}, 1);
        }

        PowerManager pm = getSystemService(PowerManager.class);
        if (pm.isIgnoringBatteryOptimizations(getPackageName())) {
            return;
        }
        SharedPreferences prefs = getPreferences(MODE_PRIVATE);
        if (prefs.getBoolean("asked_battery_exemption", false)) {
            return;
        }
        prefs.edit().putBoolean("asked_battery_exemption", true).apply();
        Intent intent = new Intent(
                Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS);
        intent.setData(Uri.parse("package:" + getPackageName()));
        startActivity(intent);
    }

    /** The server needs a moment (interpreter + imports); poll the port
     *  and load the UI as soon as it answers. */
    private void waitForServerThenLoad() {
        new Thread(() -> {
            for (int i = 0; i < 120; i++) {
                try (Socket sock = new Socket()) {
                    sock.connect(new InetSocketAddress("127.0.0.1", PORT), 500);
                    runOnUiThread(() -> mWebView.loadUrl(URL));
                    return;
                } catch (IOException e) {
                    try {
                        Thread.sleep(500);
                    } catch (InterruptedException ie) {
                        return;
                    }
                }
            }
        }).start();
    }

    @Override
    public void onBackPressed() {
        if (mWebView != null && mWebView.canGoBack()) {
            mWebView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onDestroy() {
        if (mWebView != null) {
            mWebView.destroy();
            mWebView = null;
        }
        super.onDestroy();
    }
}
