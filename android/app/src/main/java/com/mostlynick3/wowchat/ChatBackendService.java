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

/** Hosts the Python backend on localhost:5950. A logged-out app stays
 *  closable; Python promotes the service to foreground only on session. */
public class ChatBackendService extends Service {
    private static final String CHANNEL_ID = "wowchat_backend";
    private static final int NOTIFICATION_ID = 1;
    private static boolean sBackendStarted = false;
    private static ChatBackendService sInstance;

    private PowerManager.WakeLock mWakeLock;

    @Override
    public void onCreate() {
        super.onCreate();
        sInstance = this;
        createNotificationChannel();
        startBackend();
    }

    /** Called from Python (Chaquopy) on session state changes. */
    public static void setSessionActive(boolean active, String title,
                                        String text) {
        ChatBackendService svc = sInstance;
        if (svc == null) {
            return;
        }
        if (active) {
            svc.startForegroundNotification(title, text);
            svc.acquireWakeLock();
        } else {
            svc.releaseWakeLock();
            svc.stopForeground(Service.STOP_FOREGROUND_REMOVE);
        }
    }

    private void createNotificationChannel() {
        NotificationManager nm = getSystemService(NotificationManager.class);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                    CHANNEL_ID, "Chat connection",
                    NotificationManager.IMPORTANCE_LOW);
            channel.setDescription("Keeps the chat session connected");
            nm.createNotificationChannel(channel);
        }
    }

    private void startForegroundNotification(String title, String text) {
        Intent open = new Intent(this, MainActivity.class);
        open.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP);
        PendingIntent contentIntent = PendingIntent.getActivity(
                this, 0, open,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);

        Notification.Builder builder = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                ? new Notification.Builder(this, CHANNEL_ID)
                : new Notification.Builder(this);
        Notification notification = builder
                .setContentTitle(title != null && !title.isEmpty()
                        ? title : "WoW Chat Client")
                .setContentText(text != null ? text : "Keeping your chat connection alive")
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
        if (mWakeLock != null && mWakeLock.isHeld()) {
            return;
        }
        PowerManager pm = getSystemService(PowerManager.class);
        mWakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK,
                "wowchat:backend");
        mWakeLock.setReferenceCounted(false);
        mWakeLock.acquire();
    }

    private void releaseWakeLock() {
        if (mWakeLock != null && mWakeLock.isHeld()) {
            mWakeLock.release();
        }
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

    /** Not START_STICKY: after the user clears the app it must stay gone. */
    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        return START_NOT_STICKY;
    }

    @Override
    public void onDestroy() {
        sInstance = null;
        releaseWakeLock();
        stopForeground(Service.STOP_FOREGROUND_REMOVE);
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
