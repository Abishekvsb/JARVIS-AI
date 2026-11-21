# JARVIS Android Mobile Companion & Notification Listener

This companion module connects your Android mobile phone to JARVIS running on your laptop over your local Wi-Fi network.

---

## Method 1: Instant 1-Minute Setup (Zero Coding / Zero Compile)

You can set this up on your Android phone immediately using **MacroDroid** (Free from Google Play Store):

1. **Install MacroDroid** from Google Play Store.
2. Grant **Notification Access** when prompted by Android.
3. Tap **Add Macro**:
   - **Trigger**: `Notification` $\rightarrow$ `Notification Received` $\rightarrow$ Select Apps (WhatsApp, Telegram, Instagram, Messages/SMS).
   - **Action**: `Web / HTTP` $\rightarrow$ `HTTP Request`:
     - **Request Method**: `POST`
     - **URL**: `http://<YOUR_LAPTOP_IP>:8000/api/notifications/ingest`
       *(e.g., `http://10.198.209.73:8000/api/notifications/ingest`)*
     - **Headers**:
       - `Content-Type`: `application/json`
       - `X-Jarvis-Token`: `<YOUR_AUTH_TOKEN>` *(Or enter the 6-digit PIN shown on Laptop HUD)*
     - **Body / Content (JSON)**:
       ```json
       {
         "app": "[notification_app_name]",
         "sender": "[notification_title]",
         "content": "[notification_text]",
         "timestamp": [system_time]
       }
       ```
4. Save the Macro as **"JARVIS Notification Stream"**.

Now, whenever you receive a WhatsApp message or SMS, it will instantly beam to JARVIS!

---

## Method 2: Native Android App Project (JarvisNotificationListenerService)

The full source code for the standalone Android companion app is located in this directory:

- `AndroidManifest.xml`: Declares permissions and `NotificationListenerService`.
- `app/src/main/java/com/jarvis/companion/JarvisNotificationListenerService.kt`: Intercepts WhatsApp, Telegram, SMS notifications and sends them securely via OkHttp.
- `app/src/main/java/com/jarvis/companion/MainActivity.kt`: Pairing screen (IP and PIN).

