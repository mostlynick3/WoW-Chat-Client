package com.mostlynick3.wowchat;

import android.app.Activity;
import android.os.Bundle;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.Socket;

/** Single-activity host: runs the Python backend on localhost:5950 and
 *  shows the same web UI as the desktop client in a WebView. */
public class MainActivity extends Activity {
    private static final String URL = "http://127.0.0.1:5950/";
    private static final int PORT = 5950;
    private static boolean sPythonStarted = false;

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
        startBackend();
        waitForServerThenLoad();
    }

    /** Flask app.run() blocks, so the backend lives on its own thread. */
    private void startBackend() {
        final Activity self = this;
        new Thread(() -> {
            if (!sPythonStarted) {
                Python.start(new AndroidPlatform(self));
                sPythonStarted = true;
            }
            Python.getInstance().getModule("android_main").callAttr("start");
        }).start();
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
