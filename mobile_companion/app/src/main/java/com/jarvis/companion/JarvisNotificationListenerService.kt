package com.jarvis.companion

import android.app.Notification
import android.app.RemoteInput
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.os.Bundle
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
                response.use { resp ->
                    if (!resp.isSuccessful) {
                        Log.w(TAG, "Ingest failed with HTTP ${resp.code}")
                        return
                    }
                    try {
                        val respBody = resp.body?.string() ?: ""
                        val respObj = JSONObject(respBody)
                        val notifObj = respObj.optJSONObject("notification")
                        
                        // If JARVIS server decided to auto-reply, dispatch the reply via Android RemoteInput
                        if (notifObj != null && notifObj.optBoolean("auto_replied", false)) {
                            val replyText = notifObj.optString("auto_reply_text", "")
                            if (replyText.isNotEmpty()) {
                                trySendInlineReply(sbn, replyText)
                            }
                        }
                    } catch (e: Exception) {
                        Log.e(TAG, "Error parsing server response: ${e.message}")
                    }
                }
            }
        })
    }

    /**
     * Dispatch an automated reply directly into the notification's RemoteInput action
     * (e.g. WhatsApp / Telegram inline reply without opening the app).
     */
    private fun trySendInlineReply(sbn: StatusBarNotification, replyText: String) {
        val notification = sbn.notification ?: return
        val actions = notification.actions ?: return

        for (action in actions) {
            val remoteInputs = action.remoteInputs ?: continue
            for (ri in remoteInputs) {
                val intent = Intent()
                val bundle = Bundle()
                bundle.putCharSequence(ri.resultKey, replyText)
                RemoteInput.addResultsToIntent(arrayOf(ri), intent, bundle)
                try {
                    action.actionIntent.send(this, 0, intent)
                    Log.i(TAG, "Successfully dispatched inline reply to ${sbn.packageName}: '$replyText'")
                    return
                } catch (e: Exception) {
                    Log.e(TAG, "Failed to send inline reply intent: ${e.message}")
                }
            }
        }
        Log.w(TAG, "No suitable RemoteInput action found on notification for ${sbn.packageName}")
    }
}
