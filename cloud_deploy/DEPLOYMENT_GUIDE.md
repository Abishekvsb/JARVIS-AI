# JARVIS 24/7 Cloud Deployment Guide

This guide explains how to deploy the JARVIS Backend to an always-on cloud server so it operates 24/7 independently of your laptop.

---

## Architecture Diagram

```
📱 ANDROID MOBILE PHONE
    │
    │ (Secure HTTPS via 4G/5G/Wi-Fi)
    ▼
☁️ CLOUD JARVIS BACKEND (Koyeb / Fly.io / VPS)
    ├── Notification Ingestion & Deduplication
    ├── Rule-Based Auto-Reply Engine (<1ms, $0 cost)
    ├── Multi-Turn Context & Dialogue Memory
    ├── Optional Cloud AI (Claude API / Groq / Gemini)
    └── Persistent Storage (`/app/data`)
    │
    │ Returns JSON instruction: {"auto_replied": true, "auto_reply_text": "Good morning!"}
    ▼
📱 ANDROID COMPANION / MACRODROID
    │
    └── Dispatches real reply into WhatsApp via Android Notification RemoteInput!
        (Directly from phone to recipient — Laptop can be OFF!)

💻 OPTIONAL WINDOWS LAPTOP HUD
    └── Connects to https://<YOUR_CLOUD_DOMAIN> whenever you turn it on
```

---

## Option 1: Koyeb (Recommended — 100% FREE & Never Sleeps)

Koyeb provides a free web service tier that runs 24/7 and **does NOT spin down or sleep** (unlike Render or Heroku).

### Step-by-Step Deployment (3 Minutes):
1. **Sign up at [Koyeb.com](https://www.koyeb.com)** (Free, no credit card required for GitHub sign-up).
2. Click **Create App** $\rightarrow$ **GitHub**.
3. Select your repository: `Abishekvsb/JARVIS-AI`.
4. Configure Build:
   - **Builder**: `Dockerfile`
   - **Dockerfile location**: `cloud_deploy/Dockerfile`
   - **Port**: `8000`
5. Configure Environment Variables:
   - `JARVIS_SECRET_KEY`: `your_custom_secret_key`
   - `JARVIS_PAIRING_PIN`: `280506` (or any 6-digit PIN)
   - `ANTHROPIC_API_KEY`: *(Optional - only if you want Claude AI for complex queries)*
6. Click **Deploy**.
7. In ~2 minutes, Koyeb will give you your live HTTPS domain:
   `https://<your-app-name>.koyeb.app`

---

## Option 2: Linux Cloud VPS (Hetzner / DigitalOcean / AWS Lightsail)

If you have a Linux VPS (Ubuntu 22.04 / 24.04):
- Cost: ~$3.50 – $4.00 / month.
- Static IP, 100% uptime, zero sleep.

### 1-Line Deployment:
```bash
git clone https://github.com/Abishekvsb/JARVIS-AI.git
cd JARVIS-AI
docker compose -f cloud_deploy/docker-compose.yml up -d --build
```
Your JARVIS backend is immediately running 24/7 on port 8000!

---

## Connecting Your Android Mobile to Cloud JARVIS

Once your cloud backend is live at `https://<YOUR_APP_DOMAIN>`:

### Using MacroDroid (Zero-Compile Setup):
1. In your **JARVIS Notification Stream** macro on Android:
2. Change the **HTTP Request URL** to:
   `https://<YOUR_APP_DOMAIN>/api/notifications/ingest`
   *(e.g., `https://jarvis-backend-abishek.koyeb.app/api/notifications/ingest`)*
3. **Headers**:
   - `Content-Type: application/json`
   - `X-Jarvis-PIN: 280506`
4. **Body**:
   ```json
   {
     "app": "[notification_app_name]",
     "sender": "[notification_title]",
     "content": "[notification_text]",
     "timestamp": [system_time]
   }
   ```
5. Save.

### Using Native Android Companion (`mobile_companion`):
1. Open the companion app on your phone.
2. Enter your Cloud Domain (e.g. `jarvis-backend-abishek.koyeb.app`) and PIN `280506`.
3. Tap **AUTHENTICATE**.

---

## How Automatic Greeting Replies Work When Laptop is OFF

1. Arun sends you `"Good morning"` on WhatsApp.
2. Your phone's screen/notification shade receives the WhatsApp alert.
3. Android companion streams the notification to `https://<YOUR_CLOUD_DOMAIN>/api/notifications/ingest`.
4. Cloud `AutoReplyEngine` evaluates the message:
   - Master Auto-Reply: `ON`
   - Greeting match: `"Good morning"` $\rightarrow$ `"Good morning! Have a great day."`
   - Cooldown: Contact cooldown recorded.
   - Response: `{"auto_replied": true, "auto_reply_text": "Good morning! Have a great day."}`
5. Android companion receives the response and triggers the **Android Notification Action RemoteInput**.
6. **WhatsApp transmits the reply directly from your phone!**
7. **Your laptop is 100% powered off and untouched.**

