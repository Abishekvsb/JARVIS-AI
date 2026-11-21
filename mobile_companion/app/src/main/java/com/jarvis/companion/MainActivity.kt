package com.jarvis.companion

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.os.Bundle
import android.provider.Settings
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject

class MainActivity : AppCompatActivity() {

    private lateinit var etServerIp: EditText
    private lateinit var etPin: EditText
    private lateinit var btnPair: Button
    private lateinit var btnGrantPerm: Button
    private lateinit var tvStatus: TextView
    private lateinit var prefs: SharedPreferences

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        prefs = getSharedPreferences("jarvis_prefs", Context.MODE_PRIVATE)

        etServerIp = findViewById(R.id.et_server_ip)
        etPin = findViewById(R.id.et_pin)
        btnPair = findViewById(R.id.btn_pair)
        btnGrantPerm = findViewById(R.id.btn_grant_perm)
        tvStatus = findViewById(R.id.tv_status)

        etServerIp.setText(prefs.getString("server_ip", "10.198.209.73"))

        btnGrantPerm.setOnClickListener {
            // Open Android Notification Listener permission settings
            val intent = Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)
            startActivity(intent)
        }

        btnPair.setOnClickListener {
            val ip = etServerIp.text.toString().trim()
            val pin = etPin.text.toString().trim()

            if (ip.isEmpty() || pin.isEmpty()) {
                Toast.makeText(this, "Please enter Server IP and Security PIN", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

            pairWithJarvis(ip, pin)
        }
    }

    private fun pairWithJarvis(ip: String, pin: String) {
        val client = OkHttpClient()
        val json = JSONObject().apply { put("pin", pin) }
        val body = json.toString().toRequestBody("application/json; charset=utf-8".toMediaType())
        val request = Request.Builder()
            .url("http://$ip:8000/api/auth/verify")
            .post(body)
            .build()

        tvStatus.text = "Authenticating with JARVIS..."

        Thread {
            try {
                val response = client.newCall(request).execute()
                val respStr = response.body?.string() ?: ""
                val respObj = JSONObject(respStr)

                runOnUiThread {
                    if (respObj.optString("status") == "success") {
                        val token = respObj.optString("token")
                        prefs.edit()
                            .putString("server_ip", ip)
                            .putString("auth_token", token)
                            .apply()
                        tvStatus.text = "Connected and Authorized! Notifications streaming active."
                        Toast.makeText(this, "JARVIS Pairing Successful!", Toast.LENGTH_LONG).show()
                    } else {
                        tvStatus.text = "Pairing Failed: ${respObj.optString("message", "Invalid PIN")}"
                    }
                }
            } catch (e: Exception) {
                runOnUiThread {
                    tvStatus.text = "Connection Error: ${e.message}"
                }
            }
        }.start()
    }
}
