/**
 * J.A.R.V.I.S. Futuristic Desktop UI Client Script
 * Stark Industries Mark VII HUD OS
 */

(function () {
  'use strict';

  // State & Element Handles
  let ws = null;
  let isListening = false;
  let currentAiState = 'IDLE';
  let emergencyStopActive = false;
  let animationFrameId = null;

  // DOM Elements
  const body = document.body;
  const aiStateBadge = document.getElementById('ai-state-badge');
  const aiStateText = document.getElementById('ai-state-text');
  const aiStateSubmsg = document.getElementById('ai-state-submessage');
  const btnPtt = document.getElementById('btn-push-to-talk');
  const pttLabel = document.getElementById('ptt-label');
  const btnEmergency = document.getElementById('btn-emergency-stop');
  const btnResetStop = document.getElementById('btn-reset-stop');
  const chatMessages = document.getElementById('chat-messages');
  const chatForm = document.getElementById('chat-form');
  const chatInput = document.getElementById('chat-input');
  const activityFeed = document.getElementById('activity-feed');
  const activityPlaceholder = document.getElementById('activity-placeholder');
  const activeActionBanner = document.getElementById('active-action-banner');
  const activeActionText = document.getElementById('active-action-text');
  const btnClearActivity = document.getElementById('btn-clear-activity');
  const chkVoiceOutput = document.getElementById('chk-voice-output');
  const footerConnStatus = document.getElementById('footer-conn-status');
  const footerTime = document.getElementById('footer-time');
  const welcomeTime = document.getElementById('welcome-time');

  // Telemetry Elements
  const quickCpu = document.getElementById('quick-cpu');
  const quickRam = document.getElementById('quick-ram');
  const quickBat = document.getElementById('quick-bat');
  const quickDisk = document.getElementById('quick-disk');
  const cpuPercent = document.getElementById('cpu-percent');
  const cpuBar = document.getElementById('cpu-bar');
  const ramPercent = document.getElementById('ram-percent');
  const ramBar = document.getElementById('ram-bar');
  const ramDetails = document.getElementById('ram-details');
  const batteryStatus = document.getElementById('battery-status');
  const batteryBar = document.getElementById('battery-bar');
  const diskFree = document.getElementById('disk-free');

  // Canvas
  const canvas = document.getElementById('waveform-canvas');
  const ctx = canvas ? canvas.getContext('2d') : null;

  // Initialize Clock
  function updateClock() {
    const now = new Date();
    const timeStr = now.toLocaleTimeString('en-GB');
    if (footerTime) footerTime.textContent = timeStr;
    if (welcomeTime && !welcomeTime.dataset.set) {
      welcomeTime.textContent = timeStr.substring(0, 5);
      welcomeTime.dataset.set = 'true';
    }
  }
  setInterval(updateClock, 1000);
  updateClock();

  // -------------------------------------------------------------------------
  // PHASE 8: AUTHENTICATION, MOBILE INFO & SERVICE WORKER
  // -------------------------------------------------------------------------
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/sw.js').catch((e) => console.log('[PWA] SW register error:', e));
    });
  }

  function getAuthToken() {
    return localStorage.getItem('jarvis_token') || '';
  }

  function authFetch(url, options = {}) {
    options.headers = options.headers || {};
    const token = getAuthToken();
    if (token) {
      if (options.headers instanceof Headers) {
        options.headers.set('X-Jarvis-Token', token);
      } else {
        options.headers['X-Jarvis-Token'] = token;
      }
    }
    return fetch(url, options);
  }

  async function checkAuthAndMobileInfo() {
    try {
      const res = await authFetch('/api/mobile/info');
      const info = await res.json();

      const quickMobile = document.getElementById('quick-mobile');
      if (quickMobile && info.local_ip) {
        const port = window.location.port ? `:${window.location.port}` : '';
        const pinPart = info.pairing_pin ? ` | PIN: ${info.pairing_pin}` : '';
        quickMobile.textContent = `${info.local_ip}${port}${pinPart}`;
      }

      const modalPairing = document.getElementById('modal-pairing');
      if (modalPairing) {
        if (!info.authenticated) {
          modalPairing.style.display = 'flex';
        } else {
          modalPairing.style.display = 'none';
        }
      }
    } catch (e) {
      console.warn('[HUD] Mobile info lookup failed:', e);
    }
  }

  const btnSubmitPin = document.getElementById('btn-submit-pin');
  const inputPairingPin = document.getElementById('input-pairing-pin');
  const pairingError = document.getElementById('pairing-error');

  if (btnSubmitPin && inputPairingPin) {
    async function submitPin() {
      const pin = inputPairingPin.value.trim();
      if (!pin) return;
      try {
        const res = await fetch('/api/auth/verify', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ pin: pin }),
        });
        const data = await res.json();
        if (data.status === 'success' && data.token) {
          localStorage.setItem('jarvis_token', data.token);
          document.cookie = `jarvis_token=${data.token}; path=/; max-age=172800; SameSite=Lax`;
          const modalPairing = document.getElementById('modal-pairing');
          if (modalPairing) modalPairing.style.display = 'none';
          addChatMessage('J.A.R.V.I.S.', 'Security clearance accepted. Neural link authorized for this device.', false);
          connectWebSocket();
        } else {
          if (pairingError) {
            pairingError.textContent = data.message || 'Invalid PIN. Access denied.';
            pairingError.style.display = 'block';
          }
        }
      } catch (err) {
        if (pairingError) {
          pairingError.textContent = 'Connection error. Check network connection.';
          pairingError.style.display = 'block';
        }
      }
    }

    btnSubmitPin.addEventListener('click', submitPin);
    inputPairingPin.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') submitPin();
    });
  }

  // -------------------------------------------------------------------------
  // WEBSOCKET MANAGEMENT
  // -------------------------------------------------------------------------
  function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log('[HUD] Neural Link Established.');
      if (footerConnStatus) {
        footerConnStatus.textContent = 'NEURAL LINK CONNECTED [127.0.0.1]';
        footerConnStatus.style.color = '#00ffaa';
      }
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        handleWsMessage(data);
      } catch (err) {
        console.error('[HUD] WS Message Parse Error:', err);
      }
    };

    ws.onclose = () => {
      console.warn('[HUD] Neural Link Disconnected. Reconnecting...');
      if (footerConnStatus) {
        footerConnStatus.textContent = 'NEURAL LINK OFFLINE — RECONNECTING...';
        footerConnStatus.style.color = '#ffaa00';
      }
      setTimeout(connectWebSocket, 2000);
    };

    ws.onerror = (err) => {
      console.error('[HUD] WS Error:', err);
    };
  }

  function handleWsMessage(data) {
    if (data.type === 'init') {
      applyTelemetry(data.telemetry);
      setAiState(data.state, data.message);
      if (data.emergency_stop) {
        setEmergencyStopUI(true);
      }
      if (data.action_history && data.action_history.length > 0) {
        renderActionHistory(data.action_history);
      }
    } else if (data.type === 'state_change') {
      setAiState(data.state, data.message);
      if (data.active_action) {
        showActiveAction(data.active_action);
      }
      if (data.emergency_stop !== undefined) {
        setEmergencyStopUI(data.emergency_stop);
      }
    } else if (data.type === 'telemetry') {
      applyTelemetry(data.telemetry);
      if (data.emergency_stop !== undefined) {
        setEmergencyStopUI(data.emergency_stop);
      }
    } else if (data.type === 'voice_toggle') {
      if (chkVoiceOutput) chkVoiceOutput.checked = data.enabled;
    }
  }

  // -------------------------------------------------------------------------
  // TELEMETRY UPDATES
  // -------------------------------------------------------------------------
  function applyTelemetry(t) {
    if (!t) return;

    // CPU
    if (t.cpu_percent) {
      if (quickCpu) quickCpu.textContent = t.cpu_percent;
      if (cpuPercent) cpuPercent.textContent = t.cpu_percent;
      const cpuVal = parseFloat(t.cpu_percent.replace('%', '')) || 0;
      if (cpuBar) cpuBar.style.width = `${Math.min(100, Math.max(0, cpuVal))}%`;
    }

    // RAM
    if (t.memory_percent) {
      if (quickRam) quickRam.textContent = t.memory_percent;
      if (ramPercent) ramPercent.textContent = t.memory_percent;
      const ramVal = parseFloat(t.memory_percent.replace('%', '')) || 0;
      if (ramBar) ramBar.style.width = `${Math.min(100, Math.max(0, ramVal))}%`;
    }
    if (t.memory_used_gb && t.memory_total_gb && ramDetails) {
      ramDetails.textContent = `${t.memory_used_gb} / ${t.memory_total_gb} Used`;
    }

    // Battery
    if (t.battery) {
      const batParts = t.battery.split('-');
      const batVal = batParts[0].trim();
      if (quickBat) quickBat.textContent = batVal;
      if (batteryStatus) batteryStatus.textContent = t.battery;
      const batNumeric = parseFloat(batVal.replace('%', '')) || 100;
      if (batteryBar) batteryBar.style.width = `${Math.min(100, Math.max(0, batNumeric))}%`;
    }

    // Disk
    if (t.disk_d_free_gb) {
      if (quickDisk) quickDisk.textContent = t.disk_d_free_gb;
      if (diskFree) diskFree.textContent = t.disk_d_free_gb;
    }

    // AI Engine in diagnostics
    const diagAi = document.getElementById('diag-ai-engine');
    if (diagAi && t.ai_provider) {
      diagAi.textContent = `${t.ai_provider} (${t.ai_model || 'qwen2.5:1.5b'})`;
    }
  }

  // -------------------------------------------------------------------------
  // AI STATE & ARC REACTOR CONTROL
  // -------------------------------------------------------------------------
  function setAiState(state, message) {
    currentAiState = state || 'IDLE';

    // Remove all previous state classes from body
    body.classList.remove(
      'state-idle',
      'state-listening',
      'state-processing',
      'state-thinking',
      'state-speaking',
      'state-executing',
      'state-error'
    );
    body.classList.add(`state-${currentAiState.toLowerCase()}`);

    // Update Badge
    if (aiStateText) {
      aiStateText.textContent = `SYSTEM ONLINE: ${currentAiState}`;
    }
    if (aiStateSubmsg && message) {
      aiStateSubmsg.textContent = message;
    }

    // Update PTT Button label if listening
    if (currentAiState === 'LISTENING') {
      if (btnPtt) btnPtt.classList.add('active-listening');
      if (pttLabel) pttLabel.textContent = '● LISTENING (SPEAK NOW)...';
    } else {
      if (btnPtt) btnPtt.classList.remove('active-listening');
      if (pttLabel) pttLabel.textContent = 'PUSH TO TALK (SPACE)';
    }
  }

  function setEmergencyStopUI(active) {
    emergencyStopActive = active;
    if (active) {
      if (btnEmergency) {
        btnEmergency.style.display = 'none';
      }
      if (btnResetStop) {
        btnResetStop.style.display = 'inline-flex';
      }
      setAiState('ERROR', 'EMERGENCY STOP ACTIVATED: All automation is halted.');
    } else {
      if (btnEmergency) {
        btnEmergency.style.display = 'inline-flex';
      }
      if (btnResetStop) {
        btnResetStop.style.display = 'none';
      }
    }
  }

  // -------------------------------------------------------------------------
  // WAVEFORM VISUALIZER (CANVAS)
  // -------------------------------------------------------------------------
  let wavePhase = 0;
  function drawWaveform() {
    if (!ctx) return;
    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);

    ctx.lineWidth = 2;

    if (currentAiState === 'LISTENING') {
      // Dynamic pulsing audio frequencies
      ctx.strokeStyle = '#00f0ff';
      ctx.shadowBlur = 10;
      ctx.shadowColor = '#00f0ff';
      ctx.beginPath();
      for (let x = 0; x < width; x += 4) {
        const y = height / 2 + Math.sin((x * 0.05) + wavePhase) * (Math.sin(x * 0.02) * 16 + 2);
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
      wavePhase += 0.15;
    } else if (currentAiState === 'SPEAKING') {
      // Harmonic voice waves
      ctx.strokeStyle = '#00ffaa';
      ctx.shadowBlur = 8;
      ctx.shadowColor = '#00ffaa';
      ctx.beginPath();
      for (let x = 0; x < width; x += 4) {
        const y = height / 2 + Math.cos((x * 0.04) + wavePhase) * 12;
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
      wavePhase += 0.1;
    } else if (currentAiState === 'ERROR') {
      // Flat red alarm line
      ctx.strokeStyle = '#ff2040';
      ctx.shadowBlur = 12;
      ctx.shadowColor = '#ff2040';
      ctx.beginPath();
      ctx.moveTo(0, height / 2);
      ctx.lineTo(width, height / 2);
      ctx.stroke();
    } else {
      // Calm ambient idle scan
      ctx.strokeStyle = 'rgba(0, 240, 255, 0.25)';
      ctx.shadowBlur = 4;
      ctx.shadowColor = '#00f0ff';
      ctx.beginPath();
      for (let x = 0; x < width; x += 6) {
        const y = height / 2 + Math.sin((x * 0.03) + wavePhase) * 4;
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
      wavePhase += 0.03;
    }

    animationFrameId = requestAnimationFrame(drawWaveform);
  }
  drawWaveform();

  // -------------------------------------------------------------------------
  // CHAT STREAM & MESSAGES
  // -------------------------------------------------------------------------
  function addChatMessage(author, text, isUser = false) {
    if (!chatMessages) return;

    const bubble = document.createElement('div');
    bubble.className = `chat-bubble ${isUser ? 'bubble-user' : 'bubble-jarvis'}`;

    const now = new Date();
    const timeStr = now.toLocaleTimeString('en-GB').substring(0, 5);

    bubble.innerHTML = `
      <div class="bubble-header">
        <span class="bubble-author ${isUser ? '' : 'glow-cyan'}">${author}</span>
        <span class="bubble-time">${timeStr}</span>
      </div>
      <div class="bubble-content">${escapeHtml(text)}</div>
    `;

    chatMessages.appendChild(bubble);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;')
      .replace(/\n/g, '<br>');
  }

  // Handle Text Chat Submission
  if (chatForm) {
    chatForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const text = chatInput ? chatInput.value.trim() : '';
      if (!text) return;

      if (chatInput) chatInput.value = '';

      // Add to UI
      addChatMessage('YOU', text, true);

      // Call API
      try {
        const res = await authFetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: text,
            speak: chkVoiceOutput ? chkVoiceOutput.checked : true,
          }),
        });

        if (res.status === 401) {
          const modalPairing = document.getElementById('modal-pairing');
          if (modalPairing) modalPairing.style.display = 'flex';
          addChatMessage('SYSTEM', 'Device pairing required. Enter PIN to continue.', false);
          return;
        }

        const data = await res.json();
        if (data.reply) {
          addChatMessage('J.A.R.V.I.S.', data.reply, false);
        }
      } catch (err) {
        console.error('[HUD] Chat error:', err);
        addChatMessage('SYSTEM', `Communication error: ${err.message}`, false);
      }
    });
  }

  // -------------------------------------------------------------------------
  // VOICE PUSH-TO-TALK (DESKTOP & MOBILE MEDIA RECORDER)
  // -------------------------------------------------------------------------
  let mediaRecorder = null;
  let audioChunks = [];
  const isTouchDevice = ('ontouchstart' in window) || navigator.maxTouchPoints > 0;

  async function triggerPushToTalk() {
    if (isListening) return;
    isListening = true;

    setAiState('LISTENING', 'Microphone active. Recording speech...');

    try {
      const res = await authFetch('/api/voice/listen', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          max_seconds: 12.0,
          speak: chkVoiceOutput ? chkVoiceOutput.checked : true,
        }),
      });

      const data = await res.json();
      if (data.user_text) {
        const langTag = data.detected_lang ? ` [${data.detected_lang.toUpperCase()}]` : '';
        addChatMessage(`YOU (SPOKEN${langTag})`, data.user_text, true);
      }
      if (data.reply) {
        addChatMessage('J.A.R.V.I.S.', data.reply, false);
      }
    } catch (err) {
      console.error('[HUD] Voice error:', err);
      addChatMessage('SYSTEM', `Voice capture failed: ${err.message}`, false);
    } finally {
      isListening = false;
    }
  }

  if (btnPtt) {
    if (isTouchDevice && navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
      // Mobile Touch PTT: Record directly from mobile mic
      btnPtt.addEventListener('touchstart', async (e) => {
        e.preventDefault();
        if (isListening) return;
        try {
          const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
          mediaRecorder = new MediaRecorder(stream);
          audioChunks = [];
          mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) audioChunks.push(event.data);
          };
          mediaRecorder.start();
          isListening = true;
          btnPtt.classList.add('touch-ptt-active');
          setAiState('LISTENING', 'Mobile microphone recording...');
        } catch (err) {
          console.error('[MOBILE VOICE] Mic access denied:', err);
          addChatMessage('SYSTEM', `Microphone access denied: ${err.message}`, false);
        }
      });

      btnPtt.addEventListener('touchend', async (e) => {
        e.preventDefault();
        if (!mediaRecorder || mediaRecorder.state !== 'recording') return;
        btnPtt.classList.remove('touch-ptt-active');
        setAiState('PROCESSING', 'Processing mobile voice stream...');

        mediaRecorder.onstop = async () => {
          const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
          const formData = new FormData();
          formData.append('audio', audioBlob, 'mobile_speech.webm');
          formData.append('speak', chkVoiceOutput ? chkVoiceOutput.checked : true);

          try {
            const res = await authFetch('/api/voice/mobile-upload', {
              method: 'POST',
              body: formData,
            });
            const data = await res.json();
            if (data.user_text) {
              addChatMessage(`YOU (MOBILE)`, data.user_text, true);
            }
            if (data.reply) {
              addChatMessage('J.A.R.V.I.S.', data.reply, false);
            }
            if (data.audio_url) {
              const replyAudio = new Audio(data.audio_url);
              replyAudio.play().catch((e) => console.log('[MOBILE AUDIO] Autoplay blocked:', e));
            }
          } catch (err) {
            console.error('[MOBILE VOICE] Upload error:', err);
            addChatMessage('SYSTEM', `Voice upload error: ${err.message}`, false);
          } finally {
            isListening = false;
          }
        };

        mediaRecorder.stop();
        mediaRecorder.stream.getTracks().forEach((track) => track.stop());
      });
    } else {
      // Desktop Click PTT
      btnPtt.addEventListener('click', () => {
        triggerPushToTalk();
      });
    }
  }

  // -------------------------------------------------------------------------
  // EMERGENCY STOP CONTROLS
  // -------------------------------------------------------------------------
  async function triggerEmergencyStop() {
    try {
      const res = await authFetch('/api/emergency-stop/trigger', { method: 'POST' });
      const data = await res.json();
      setEmergencyStopUI(true);
      addChatMessage('SYSTEM ALERT', data.message || 'EMERGENCY STOP ACTIVATED.', false);
    } catch (err) {
      console.error('[HUD] Emergency stop failed:', err);
    }
  }

  async function resetEmergencyStop() {
    try {
      const res = await authFetch('/api/emergency-stop/reset', { method: 'POST' });
      const data = await res.json();
      setEmergencyStopUI(false);
      setAiState('IDLE', 'Emergency stop reset. Systems restored.');
      addChatMessage('SYSTEM', data.message || 'Emergency stop reset.', false);
    } catch (err) {
      console.error('[HUD] Reset stop failed:', err);
    }
  }

  if (btnEmergency) {
    btnEmergency.addEventListener('click', triggerEmergencyStop);
  }
  if (btnResetStop) {
    btnResetStop.addEventListener('click', resetEmergencyStop);
  }

  // -------------------------------------------------------------------------
  // KEYBOARD SHORTCUTS
  // -------------------------------------------------------------------------
  window.addEventListener('keydown', (e) => {
    // If Space is pressed and not in chat input -> trigger PTT
    if (e.code === 'Space' && document.activeElement !== chatInput) {
      e.preventDefault();
      triggerPushToTalk();
    }
    // If Esc is pressed -> trigger Emergency Stop
    if (e.code === 'Escape') {
      triggerEmergencyStop();
    }
  });

  // -------------------------------------------------------------------------
  // AUTOMATION ACTIVITY FEED
  // -------------------------------------------------------------------------
  function showActiveAction(act) {
    if (!activeActionBanner || !activeActionText) return;
    if (!act) {
      activeActionBanner.style.display = 'none';
      return;
    }
    activeActionBanner.style.display = 'flex';
    activeActionText.textContent = `${act.tool}: ${act.message || 'Running...'}`;
  }

  function renderActionHistory(history) {
    if (!activityFeed) return;
    if (activityPlaceholder) activityPlaceholder.style.display = 'none';

    activityFeed.innerHTML = '';
    history.forEach((item) => {
      appendActivityCard(item, false);
    });
  }

  function appendActivityCard(item, prepend = true) {
    if (!activityFeed) return;
    if (activityPlaceholder) activityPlaceholder.style.display = 'none';

    const card = document.createElement('div');
    const statusClass = (item.status || 'success').toLowerCase();
    card.className = `activity-card status-${statusClass}`;

    const paramStr = item.input && Object.keys(item.input).length > 0
      ? JSON.stringify(item.input).replace(/["{}]/g, '')
      : '';

    card.innerHTML = `
      <div class="activity-top-row">
        <span class="activity-tool">${escapeHtml(item.tool || 'ACTION')}</span>
        <span class="activity-status status-badge-${statusClass}">${item.status || 'OK'}</span>
      </div>
      <div class="activity-msg">${escapeHtml(item.message || paramStr)}</div>
    `;

    if (prepend && activityFeed.firstChild) {
      activityFeed.insertBefore(card, activityFeed.firstChild);
    } else {
      activityFeed.appendChild(card);
    }
  }

  if (btnClearActivity) {
    btnClearActivity.addEventListener('click', () => {
      if (activityFeed) activityFeed.innerHTML = '';
      if (activityPlaceholder) activityPlaceholder.style.display = 'block';
    });
  }

  // Voice Toggle Checkbox
  if (chkVoiceOutput) {
    chkVoiceOutput.addEventListener('change', () => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: 'toggle_voice_output',
          enabled: chkVoiceOutput.checked,
        }));
      }
    });
  }

  // Check mobile pairing & connect on load
  checkAuthAndMobileInfo();
  connectWebSocket();

})();

