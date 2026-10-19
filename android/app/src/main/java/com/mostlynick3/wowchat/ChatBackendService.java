package com.mostlynick3.wowchat;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;

import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

/** Foreground service that owns the Python backend. The world socket is
 *  kept alive by a 30s ping loop inside Python, so the process must stay
 *  scheduled while the app is in the background: a foreground service
 *  prevents the cached-app freezer from stopping it, and the partial
 *  wake lock keeps the CPU running with the screen off. */
public class ChatBackendService extends Service {
    private static final String CHANNEL_ID = "wowchat_backend";
    private static final int NOTIFICATION_ID = 1;
    private static boolean sBackendStarted = false;

    private PowerManager.WakeLock mWakeLock;

    @Override
    public void onCreate() {
        super.onCreate();
        startForegroundNotification();
        acquireWakeLock();
        startBackend();
    }

    private void startForegroundNotification() {
        NotificationManager nm = getSystemService(NotificationManager.class);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                    CHANNEL_ID, "Chat connection",
                    NotificationManager.IMPORTANCE_LOW);
            channel.setDescription("Keeps the chat session connected");
            nm.createNotificationChannel(channel);
        }

        Intent open = new Intent(this, MainActivity.class);
        open.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP);
        PendingIntent contentIntent = PendingIntent.getActivity(
                this, 0, open,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);

        Notification.Builder builder = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                ? new Notification.Builder(this, CHANNEL_ID)
                : new Notification.Builder(this);
        Notification notification = builder
                .setContentTitle("WoW Chat Client")
                .setContentText("Keeping your chat connection alive")
                .setSmallIcon(R.drawable.wow_w)
                .setContentIntent(contentIntent)
                .setOngoing(true)
                .build();

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIFICATION_ID, notification,
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC);
        } else {
            startForeground(NOTIFICATION_ID, notification);
        }
    }

    private void acquireWakeLock() {
        PowerManager pm = getSystemService(PowerManager.class);
        mWakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK,
                "wowchat:backend");
        mWakeLock.setReferenceCounted(false);
        mWakeLock.acquire();
    }

    /** Chaquopy's interpreter and the Flask app are process-wide; only
     *  start them once even if the service is recreated. */
    private void startBackend() {
        if (sBackendStarted) {
            return;
        }
        sBackendStarted = true;
        final Service self = this;
        new Thread(() -> {
            Python.start(new AndroidPlatform(self));
            Python.getInstance().getModule("android_main").callAttr("start");
        }).start();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        if (mWakeLock != null && mWakeLock.isHeld()) {
            mWakeLock.release();
        }
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
