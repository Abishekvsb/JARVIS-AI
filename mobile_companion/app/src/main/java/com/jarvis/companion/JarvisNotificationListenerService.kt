package com.jarvis.companion

import android.app.Notification
import android.content.Context
import android.content.SharedPreferences
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit

class JarvisNotificationListenerService : NotificationListenerService() {

    private val TAG = "JarvisNotifService"
    private val client = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .writeTimeout(5, TimeUnit.SECONDS)
        .readTimeout(5, TimeUnit.SECONDS)
        .build()

    private val JSON_MEDIA_TYPE = "application/json; charset=utf-8".toMediaType()

    override fun onNotificationPosted(sbn: StatusBarNotification?) {
        if (sbn == null) return

        val pkg = sbn.packageName ?: ""
        val extras = sbn.notification.extras ?: return

        // Resolve app name
        val appName = when {
            pkg.contains("whatsapp") -> "WhatsApp"
            pkg.contains("telegram") -> "Telegram"
            pkg.contains("instagram") -> "Instagram"
            pkg.contains("messaging") || pkg.contains("mms") || pkg.contains("sms") -> "SMS"
            else -> return // Only monitor permitted messaging apps
        }

        // Extract title (sender) and text (content)
        val sender = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString()?.trim() ?: ""
        val content = extras.getCharSequence(Notification.EXTRA_TEXT)?.toString()?.trim() ?: ""

        if (sender.isEmpty() || content.isEmpty()) return

        // Read configured server URL and token from SharedPreferences
        val prefs: SharedPreferences = getSharedPreferences("jarvis_prefs", Context.MODE_PRIVATE)
        val serverIp = prefs.getString("server_ip", "") ?: ""
        val token = prefs.getString("auth_token", "") ?: ""

        if (serverIp.isEmpty()) {
            Log.w(TAG, "JARVIS server IP not configured.")
            return
        }

        val url = "http://$serverIp:8000/api/notifications/ingest"

        // Build JSON payload
        val payload = JSONObject().apply {
            put("app", appName)
            put("sender", sender)
            put("content", content)
            put("timestamp", System.currentTimeMillis() / 1000.0)
        }

        val body = payload.toString().toRequestBody(JSON_MEDIA_TYPE)
        val reqBuilder = Request.Builder().url(url).post(body)
        if (token.isNotEmpty()) {
            reqBuilder.addHeader("X-Jarvis-Token", token)
        }

        // Send asynchronously to local JARVIS server
        client.newCall(reqBuilder.build()).enqueue(object : okhttp3.Callback {
            override fun onFailure(call: okhttp3.Call, e: java.io.IOException) {
                Log.e(TAG, "Failed to stream notification to JARVIS: ${e.message}")
            }

            override fun onResponse(call: okhttp3.Call, response: okhttp3.Response) {
                response.use {
                    Log.i(TAG, "Notification streamed to JARVIS successfully: ${response.code}")
                }
            }
        })
    }
}
