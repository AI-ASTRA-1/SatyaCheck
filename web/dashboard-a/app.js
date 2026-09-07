/**
 * SATYACHECK — Web Dashboard A
 * Fallback response surface for real-time voice clone scam warning.
 * Consumes AppMessage discriminated union from contracts/risk.py:
 * - SessionStart: { kind: "session_start", ... }
 * - RiskUpdate:   { kind: "risk_update", ... }
 * - CallEnded:    { kind: "call_ended", ... }
 */

(function () {
  'use strict';

  // DOM Elements
  const elBtnThemeToggle = document.getElementById('btn-theme-toggle');
  const elThemeIcon = document.getElementById('theme-icon');
  const elThemeLabel = document.getElementById('theme-label');
  const elConnDot = document.getElementById('connection-dot');
  const elConnText = document.getElementById('connection-text');
  const elWsInput = document.getElementById('ws-url-input');
  const elBtnReconnect = document.getElementById('btn-reconnect');
  const elBanner = document.getElementById('disconnected-banner');
  const elBtnRetry = document.getElementById('btn-banner-retry');

  // Call session bar
  const elSessionPulse = document.getElementById('session-pulse');
  const elSessionState = document.getElementById('session-state-text');
  const elStreamId = document.getElementById('session-stream-id');
  const elCallId = document.getElementById('session-call-id');
  const elProtectedNum = document.getElementById('session-protected-num');
  const elSequence = document.getElementById('session-sequence');

  // Live Risk Card
  const elVerdictBadge = document.getElementById('verdict-badge');
  const elRiskScore = document.getElementById('risk-score-value');
  const elGaugeFill = document.getElementById('gauge-fill-circle');
  const elRiskLevelBadge = document.getElementById('risk-level-badge');
  const elConfidenceVal = document.getElementById('confidence-val');
  const elConfidenceProgress = document.getElementById('confidence-progress');
  const elLastUpdate = document.getElementById('last-update-time');

  // AI Checks
  const checksList = ['machine_fingerprint', 'speaker_identity', 'prosody', 'stt_llm'];
  const checkElements = {};
  checksList.forEach((chk) => {
    checkElements[chk] = {
      card: document.getElementById(`check-${chk}`),
      status: document.getElementById(`status-${chk}`),
    };
  });

  // Reasons
  const elReasonsContainer = document.getElementById('reasons-container');
  const elReasonsBadge = document.getElementById('reasons-count-badge');

  // Call Ended Card
  const elCallEndedCard = document.getElementById('call-ended-card');
  const elEndedVerdict = document.getElementById('ended-verdict');
  const elEndedLevel = document.getElementById('ended-level');
  const elEndedScore = document.getElementById('ended-score');
  const elEndedDuration = document.getElementById('ended-duration');
  const elEndedFingerprint = document.getElementById('ended-fingerprint');
  const elEndedMerkle = document.getElementById('ended-merkle');
  const elEndedRecordId = document.getElementById('ended-record-id');

  // History feed
  const elHistoryFeed = document.getElementById('history-feed-list');
  const elHistoryEmpty = document.getElementById('history-empty-msg');
  const elHistoryCount = document.getElementById('history-item-count');
  const elBtnClearHistory = document.getElementById('btn-clear-history');

  // Gauge circumference: 2 * PI * 68 ≈ 427.26
  const GAUGE_CIRCUMFERENCE = 2 * Math.PI * 68;

  // App State
  let socket = null;
  let isConnected = false;
  let reconnectTimer = null;
  let historyItems = [];
  const MAX_HISTORY = 100;

  // Reason code labels and hazard classification
  const REASON_METADATA = {
    fingerprint_synthetic: { label: 'Waveform Synthetic (XLS-R)', hazard: 'synthetic-hazard' },
    fingerprint_genuine: { label: 'Waveform Natural', hazard: 'genuine-safe' },
    voiceprint_no_enrolment: { label: 'No Enrolment (Neutral)', hazard: '' },
    voiceprint_no_match: { label: 'Impersonation Mismatch', hazard: 'synthetic-hazard' },
    voiceprint_match: { label: 'Voiceprint Match', hazard: 'genuine-safe' },
    voiceprint_match_synthetic: { label: 'Enrolled Voice Clone Attack', hazard: 'synthetic-hazard' },
    prosody_anomaly: { label: 'Prosodic Pitch Anomaly', hazard: 'synthetic-hazard' },
    prosody_normal: { label: 'Prosody Normal', hazard: 'genuine-safe' },
    script_risk_high: { label: 'Scam Coercion Script Detected', hazard: 'synthetic-hazard' },
    script_risk_absent: { label: 'Script Low Risk', hazard: 'genuine-safe' },
    context_high_risk: { label: 'Context Risk Anomaly', hazard: 'synthetic-hazard' },
    context_low_risk: { label: 'Context Normal', hazard: 'genuine-safe' },
    insufficient_audio: { label: 'Accumulating Audio Window', hazard: '' },
    degraded_check: { label: 'Degraded AI Signal (Noise/Window)', hazard: 'degraded-warn' },
  };

  /** Initialize Connection */
  function connectWebSocket() {
    if (socket) {
      try {
        socket.close();
      } catch (e) {
        // ignore
      }
    }

    const wsUrl = elWsInput.value.trim() || 'ws://127.0.0.1:8765';
    setConnectionState('connecting');

    try {
      socket = new WebSocket(wsUrl);

      socket.onopen = function () {
        setConnectionState('connected');
        clearTimeout(reconnectTimer);
      };

      socket.onmessage = function (event) {
        try {
          const message = JSON.parse(event.data);
          handleAppMessage(message);
        } catch (err) {
          console.error('[Dashboard A] Failed to parse message JSON:', err, event.data);
        }
      };

      socket.onerror = function () {
        // Socket error handled in onclose
      };

      socket.onclose = function () {
        setConnectionState('disconnected');
        // Clear live active state on disconnect so it does not freeze
        showDisconnectedState();
        scheduleReconnect();
      };
    } catch (err) {
      setConnectionState('disconnected');
      showDisconnectedState();
      scheduleReconnect();
    }
  }

  function scheduleReconnect() {
    clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(connectWebSocket, 3000);
  }

  function setConnectionState(state) {
    elConnDot.className = 'status-dot ' + state;
    if (state === 'connected') {
      isConnected = true;
      elConnText.textContent = 'Live Connected';
      elBanner.classList.add('hidden');
    } else if (state === 'connecting') {
      isConnected = false;
      elConnText.textContent = 'Connecting...';
      elBanner.classList.remove('hidden');
    } else {
      isConnected = false;
      elConnText.textContent = 'Disconnected';
      elBanner.classList.remove('hidden');
    }
  }

  function showDisconnectedState() {
    elSessionPulse.className = 'pulse-indicator idle';
    elSessionState.textContent = 'Disconnected from Stream Engine';
  }

  /**
   * Main AppMessage Dispatcher (contracts/risk.py)
   */
  function handleAppMessage(msg) {
    if (!msg || !msg.kind) return;

    switch (msg.kind) {
      case 'session_start':
        handleSessionStart(msg);
        break;
      case 'risk_update':
        handleRiskUpdate(msg);
        break;
      case 'call_ended':
        handleCallEnded(msg);
        break;
      default:
        console.warn('[Dashboard A] Unknown message kind:', msg.kind);
    }

    addHistoryEntry(msg);
  }

  /**
   * 1. Session Start Handler
   */
  function handleSessionStart(msg) {
    elCallEndedCard.classList.add('hidden');

    elStreamId.textContent = msg.stream_id || '—';
    elCallId.textContent = msg.call_id || '—';
    elProtectedNum.textContent = msg.protected_number || 'Enrolled User';
    elSequence.textContent = '#0 (Scanning)';

    elSessionPulse.className = 'pulse-indicator active';
    elSessionState.textContent = 'Live Audio Ingestion (Scanning...)';

    // Reset risk display
    updateRiskDisplay({
      score: 0,
      verdict: 'unknown',
      risk_level: 'low',
      confidence: 0,
      timestamp: msg.started_at,
      reasons: [],
      contributing_checks: [],
      degraded_checks: [],
    });
  }

  /**
   * 2. Live Risk Update Handler (~1 tick/sec)
   */
  function handleRiskUpdate(msg) {
    elSequence.textContent = `#${msg.sequence}`;
    elStreamId.textContent = msg.stream_id;
    elCallId.textContent = msg.call_id;

    if (msg.risk_level === 'critical' || msg.risk_level === 'high') {
      elSessionPulse.className = 'pulse-indicator alert';
      elSessionState.textContent = 'Threat Warning Raised';
    } else {
      elSessionPulse.className = 'pulse-indicator active';
      elSessionState.textContent = 'Monitoring Call Stream';
    }

    updateRiskDisplay(msg);
  }

  /**
   * 3. Call Ended Handler
   */
  function handleCallEnded(msg) {
    elSessionPulse.className = 'pulse-indicator idle';
    elSessionState.textContent = 'Call Ended';

    // Render Stage 07 summary card
    elCallEndedCard.classList.remove('hidden');
    elEndedVerdict.textContent = (msg.final_verdict || '').toUpperCase();
    elEndedLevel.textContent = (msg.final_level || '').toUpperCase();
    elEndedScore.textContent = `${msg.final_score} / 100`;
    elEndedDuration.textContent = `${(msg.duration_seconds || 0).toFixed(1)}s`;

    if (msg.alert_fingerprint) {
      elEndedFingerprint.textContent = msg.alert_fingerprint;
      elEndedFingerprint.className = 'val mono hash';
    } else {
      elEndedFingerprint.textContent = 'None (Safe / No Alert)';
      elEndedFingerprint.className = 'val';
    }

    elEndedMerkle.textContent = msg.merkle_root || 'None';
    elEndedRecordId.textContent = msg.sealed_record_id || 'None';
  }

  /**
   * Update Live Risk View Components
   */
  function updateRiskDisplay(data) {
    const score = Math.max(0, Math.min(100, data.score || 0));
    const verdict = data.verdict || 'unknown';
    const riskLevel = data.risk_level || 'low';
    const confidence = Math.max(0, Math.min(1, data.confidence || 0));

    // 1. Score & Gauge
    elRiskScore.textContent = score;
    const dashOffset = GAUGE_CIRCUMFERENCE * (1 - score / 100);
    elGaugeFill.style.strokeDashoffset = dashOffset;

    // Set gauge color according to risk level directly (renders RiskLevel, not derived)
    const levelColors = {
      low: 'var(--risk-low)',
      medium: 'var(--risk-medium)',
      high: 'var(--risk-high)',
      critical: 'var(--risk-critical)',
    };
    elGaugeFill.style.stroke = levelColors[riskLevel] || 'var(--risk-low)';

    // 2. Verdict Badge
    elVerdictBadge.textContent = `VERDICT: ${verdict.toUpperCase()}`;
    elVerdictBadge.className = `verdict-tag verdict-${verdict}`;

    // 3. Risk Level Badge
    elRiskLevelBadge.textContent = riskLevel.toUpperCase();
    elRiskLevelBadge.className = `risk-level-badge level-${riskLevel}`;

    // 4. Confidence
    const confPercent = Math.round(confidence * 100);
    elConfidenceVal.textContent = `${confPercent}%`;
    elConfidenceProgress.style.width = `${confPercent}%`;

    // 5. Timestamp
    if (data.timestamp) {
      const d = new Date(data.timestamp);
      elLastUpdate.textContent = d.toLocaleTimeString() + '.' + String(d.getMilliseconds()).padStart(3, '0');
    }

    // 6. 4 AI Checks Status
    const contributing = new Set(data.contributing_checks || []);
    const degraded = new Set(data.degraded_checks || []);

    checksList.forEach((chk) => {
      const elements = checkElements[chk];
      if (!elements) return;

      if (degraded.has(chk)) {
        elements.card.className = 'check-item degraded';
        elements.status.className = 'check-status-pill degraded';
        elements.status.textContent = 'Degraded';
      } else if (contributing.has(chk)) {
        elements.card.className = 'check-item contributing';
        elements.status.className = 'check-status-pill contributing';
        elements.status.textContent = 'Contributing';
      } else {
        elements.card.className = 'check-item';
        elements.status.className = 'check-status-pill neutral';
        elements.status.textContent = 'Idle';
      }
    });

    // 7. Reasons Container
    const reasons = data.reasons || [];
    elReasonsBadge.textContent = `${reasons.length} Active`;

    if (reasons.length === 0) {
      elReasonsContainer.innerHTML = '<span class="empty-placeholder">No threat reasons active in current window.</span>';
    } else {
      elReasonsContainer.innerHTML = '';
      reasons.forEach((r) => {
        const meta = REASON_METADATA[r] || { label: r, hazard: '' };
        const tag = document.createElement('span');
        tag.className = `reason-tag ${meta.hazard}`.trim();
        tag.textContent = `${meta.label} [${r}]`;
        elReasonsContainer.appendChild(tag);
      });
    }
  }

  /**
   * Alert History Feed
   */
  function addHistoryEntry(msg) {
    if (elHistoryEmpty) {
      elHistoryEmpty.remove();
    }

    historyItems.unshift(msg);
    if (historyItems.length > MAX_HISTORY) {
      historyItems.pop();
    }

    elHistoryCount.textContent = `${historyItems.length} items`;

    const entry = document.createElement('div');
    const timeStr = new Date(msg.timestamp || msg.started_at || msg.ended_at || Date.now()).toLocaleTimeString();

    if (msg.kind === 'session_start') {
      entry.className = 'history-entry kind-session_start';
      entry.innerHTML = `
        <div class="entry-header">
          <span class="entry-kind" style="color: #38bdf8;">SESSION START</span>
          <span class="entry-time">${timeStr}</span>
        </div>
        <div class="entry-body">
          <span class="entry-score-tag">Stream: ${msg.stream_id}</span>
          <span class="entry-reasons">Protected: ${msg.protected_number || 'Enrolled User'}</span>
        </div>
      `;
    } else if (msg.kind === 'risk_update') {
      entry.className = `history-entry level-${msg.risk_level}`;
      const reasonsSnippet = (msg.reasons || []).join(', ') || 'Normal window';
      entry.innerHTML = `
        <div class="entry-header">
          <span class="entry-kind">TICK #${msg.sequence} · ${msg.verdict.toUpperCase()}</span>
          <span class="entry-time">${timeStr}</span>
        </div>
        <div class="entry-body">
          <span class="entry-score-tag">Score: ${msg.score} [${msg.risk_level.toUpperCase()}]</span>
          <span class="entry-reasons" title="${reasonsSnippet}">${reasonsSnippet}</span>
        </div>
      `;
    } else if (msg.kind === 'call_ended') {
      entry.className = 'history-entry kind-call_ended';
      entry.innerHTML = `
        <div class="entry-header">
          <span class="entry-kind" style="color: #c084fc;">CALL CONCLUDED</span>
          <span class="entry-time">${timeStr}</span>
        </div>
        <div class="entry-body">
          <span class="entry-score-tag">Final Score: ${msg.final_score} [${msg.final_verdict.toUpperCase()}]</span>
          <span class="entry-reasons">${msg.alert_fingerprint ? 'Alert Sealed' : 'Safe Call'}</span>
        </div>
      `;
    }

    elHistoryFeed.insertBefore(entry, elHistoryFeed.firstChild);
  }

  function clearHistory() {
    historyItems = [];
    elHistoryFeed.innerHTML = '<div class="history-empty" id="history-empty-msg"><span>Awaiting stream telemetry updates...</span></div>';
    elHistoryCount.textContent = '0 items';
  }

  function initTheme() {
    const savedTheme = localStorage.getItem('satyacheck_theme') || 'dark';
    applyTheme(savedTheme);
  }

  function applyTheme(theme) {
    if (theme === 'bright') {
      document.body.classList.remove('theme-dark');
      document.body.classList.add('theme-bright');
      if (elThemeIcon) elThemeIcon.textContent = '🌙';
      if (elThemeLabel) elThemeLabel.textContent = 'Dark';
    } else {
      document.body.classList.remove('theme-bright');
      document.body.classList.add('theme-dark');
      if (elThemeIcon) elThemeIcon.textContent = '☀️';
      if (elThemeLabel) elThemeLabel.textContent = 'Bright';
    }
  }

  function toggleTheme() {
    const isBright = document.body.classList.contains('theme-bright');
    const newTheme = isBright ? 'dark' : 'bright';
    localStorage.setItem('satyacheck_theme', newTheme);
    applyTheme(newTheme);
  }

  // Event Listeners
  if (elBtnThemeToggle) {
    elBtnThemeToggle.addEventListener('click', toggleTheme);
  }
  elBtnReconnect.addEventListener('click', connectWebSocket);
  elBtnRetry.addEventListener('click', connectWebSocket);
  elBtnClearHistory.addEventListener('click', clearHistory);

  // Auto-connect on load
  window.addEventListener('DOMContentLoaded', () => {
    initTheme();
    connectWebSocket();
  });
})();
