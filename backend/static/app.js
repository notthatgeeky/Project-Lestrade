/**
 * Dashboard — Main Application Logic
 *
 * Handles WebSocket connection to the backend, renders participant cards,
 * updates the confidence timeline chart, and populates the explainability log.
 */

(function () {
  'use strict';

  // ─── DOM References ────────────────────────────────────────────
  const setupPanel = document.getElementById('setupPanel');
  const monitorView = document.getElementById('monitorView');
  const setupInterviewId = document.getElementById('setupInterviewId');
  const setupServerUrl = document.getElementById('setupServerUrl');
  const btnStartMonitor = document.getElementById('btnStartMonitor');
  const connDot = document.querySelector('.conn-dot');
  const connText = document.querySelector('.conn-text');
  const meetingTimer = document.getElementById('meetingTimer');
  const infoInterviewId = document.getElementById('infoInterviewId');
  const infoExpectedName = document.getElementById('infoExpectedName');
  const infoParticipantCount = document.getElementById('infoParticipantCount');
  const participantList = document.getElementById('participantList');
  const logEntries = document.getElementById('logEntries');

  // ─── State ─────────────────────────────────────────────────────
  let ws = null;
  let interviewId = '';
  let chart = null;
  let participants = {};
  let startTimeMs = null;
  let timerInterval = null;

  // ─── URL Params ────────────────────────────────────────────────
  const urlParams = new URLSearchParams(window.location.search);
  const paramInterview = urlParams.get('interview');
  if (paramInterview) {
    setupInterviewId.value = paramInterview;
  }

  // ─── Connect ───────────────────────────────────────────────────
  btnStartMonitor.addEventListener('click', () => {
    interviewId = setupInterviewId.value.trim();
    if (!interviewId) {
      setupInterviewId.style.borderColor = '#ef4444';
      setupInterviewId.focus();
      return;
    }

    const serverUrl = setupServerUrl.value.trim();
    const wsUrl = `${serverUrl}${interviewId}`;

    connectWebSocket(wsUrl);
  });

  function connectWebSocket(url) {
    console.log('[Dashboard] Connecting to', url);
    btnStartMonitor.textContent = 'Connecting...';
    btnStartMonitor.disabled = true;

    try {
      ws = new WebSocket(url);
    } catch (e) {
      console.error('WebSocket creation failed:', e);
      btnStartMonitor.textContent = 'Connect to Session';
      btnStartMonitor.disabled = false;
      return;
    }

    ws.onopen = () => {
      console.log('[Dashboard] Connected');
      setConnectionStatus(true);
      showMonitorView();

      // Start heartbeat
      setInterval(() => {
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send('ping');
        }
      }, 10000);
    };

    ws.onclose = () => {
      console.log('[Dashboard] Disconnected');
      setConnectionStatus(false);
    };

    ws.onerror = (err) => {
      console.error('[Dashboard] WebSocket error:', err);
      setConnectionStatus(false);
      btnStartMonitor.textContent = 'Retry Connection';
      btnStartMonitor.disabled = false;
    };

    ws.onmessage = (event) => {
      if (event.data === 'pong') return;

      try {
        const msg = JSON.parse(event.data);
        handleMessage(msg);
      } catch (e) {
        console.warn('Failed to parse message:', e);
      }
    };
  }

  // ─── Message Handlers ─────────────────────────────────────────

  function handleMessage(msg) {
    switch (msg.type) {
      case 'full_state':
        handleFullState(msg.data);
        break;
      case 'participant_join':
        handleParticipantUpdate(msg.data);
        break;
      case 'participant_update':
        handleParticipantUpdate(msg.data);
        break;
      case 'participant_leave':
        handleParticipantLeave(msg.data);
        break;
      case 'score_update':
        handleScoreUpdate(msg.data);
        break;
      default:
        console.log('[Dashboard] Unknown message type:', msg.type);
    }
  }

  function handleFullState(data) {
    infoInterviewId.textContent = data.interview_id || interviewId;
    infoExpectedName.textContent = data.expected_candidate_name || '—';

    if (data.start_time_ms) {
      startTimeMs = data.start_time_ms;
      startTimer();
    }

    if (data.participants) {
      for (const [pid, pData] of Object.entries(data.participants)) {
        participants[pid] = pData;
        renderParticipantCard(pData);
        if (chart && pData.candidate_probability !== undefined) {
          chart.addPoint(
            pid,
            pData.current_display_name || 'Unknown',
            pData.candidate_probability,
            Date.now()
          );
        }
      }
      updateParticipantCount();
    }
  }

  function handleParticipantUpdate(data) {
    if (!data || !data.id) return;
    participants[data.id] = data;
    renderParticipantCard(data);
    updateParticipantCount();

    if (chart) {
      chart.addPoint(
        data.id,
        data.current_display_name || 'Unknown',
        data.candidate_probability || 0,
        Date.now()
      );
    }
  }

  function handleParticipantLeave(data) {
    if (!data || !data.participant_id) return;
    const card = document.getElementById(`card-${data.participant_id}`);
    if (card) {
      card.style.opacity = '0.4';
      const nameEl = card.querySelector('.participant-name');
      if (nameEl) nameEl.textContent += ' (left)';
    }
  }

  function handleScoreUpdate(data) {
    if (!data || !data.participant) return;

    const p = data.participant;
    participants[p.id] = p;
    renderParticipantCard(p);

    // Update chart
    if (chart) {
      chart.addPoint(
        p.id,
        p.current_display_name || 'Unknown',
        p.candidate_probability,
        Date.now()
      );
    }

    // Add log entry
    if (data.explanation) {
      addLogEntry(data.explanation, data.old_score, p.candidate_probability);
    }
  }

  // ─── Rendering ─────────────────────────────────────────────────

  function renderParticipantCard(p) {
    let card = document.getElementById(`card-${p.id}`);
    const isCandidate = p.candidate_probability >= 0.65;
    const scorePercent = Math.round(p.candidate_probability * 100);

    // Determine score color
    let scoreColor;
    if (scorePercent >= 85) scoreColor = 'var(--accent-emerald)';
    else if (scorePercent >= 65) scoreColor = 'var(--accent-indigo)';
    else if (scorePercent >= 40) scoreColor = 'var(--accent-amber)';
    else scoreColor = 'var(--text-muted)';

    const html = `
      <div class="participant-header">
        <span class="participant-name">${escapeHtml(p.current_display_name || 'Unknown')}</span>
        <span class="confidence-badge badge-${p.confidence_band}">${p.confidence_band}</span>
      </div>
      <div class="score-bar-container">
        <div class="score-bar-header">
          <span class="score-label">Candidate Score</span>
          <span class="score-value" style="color: ${scoreColor}">${scorePercent}%</span>
        </div>
        <div class="score-bar-track">
          <div class="score-bar-fill" style="width: ${scorePercent}%"></div>
        </div>
      </div>
      <div class="participant-meta">
        <span class="meta-chip"><span class="icon">🎤</span> ${Math.round(p.speaking_ratio * 100)}% speaking</span>
        <span class="meta-chip"><span class="icon">${p.camera_on ? '📹' : '📷'}</span> Camera ${p.camera_on ? 'ON' : 'OFF'}</span>
        ${p.speaking_turn_count ? `<span class="meta-chip"><span class="icon">💬</span> ${p.speaking_turn_count} turns</span>` : ''}
      </div>
    `;

    if (card) {
      card.innerHTML = html;
      card.className = `participant-card${isCandidate ? ' is-candidate' : ''}`;
    } else {
      // Remove empty state
      const emptyState = participantList.querySelector('.empty-state');
      if (emptyState) emptyState.remove();

      card = document.createElement('div');
      card.id = `card-${p.id}`;
      card.className = `participant-card${isCandidate ? ' is-candidate' : ''}`;
      card.innerHTML = html;
      participantList.appendChild(card);
    }

    // Re-sort cards by score (highest first)
    sortParticipantCards();
  }

  function sortParticipantCards() {
    const cards = Array.from(participantList.querySelectorAll('.participant-card'));
    cards.sort((a, b) => {
      const aId = a.id.replace('card-', '');
      const bId = b.id.replace('card-', '');
      const aScore = participants[aId]?.candidate_probability || 0;
      const bScore = participants[bId]?.candidate_probability || 0;
      return bScore - aScore;
    });
    cards.forEach((card) => participantList.appendChild(card));
  }

  function addLogEntry(explanation, oldScore, newScore) {
    // Remove empty state
    const emptyState = logEntries.querySelector('.empty-state');
    if (emptyState) emptyState.remove();

    const isPositive = newScore > oldScore;
    const entry = document.createElement('div');
    entry.className = `log-entry ${isPositive ? 'positive' : 'negative'}`;

    const now = new Date();
    const timeStr = now.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });

    entry.innerHTML = `
      <div class="log-timestamp">${timeStr}</div>
      <div class="log-text">${escapeHtml(explanation)}</div>
    `;

    // Prepend (newest first)
    logEntries.insertBefore(entry, logEntries.firstChild);

    // Keep max 50 entries
    while (logEntries.children.length > 50) {
      logEntries.removeChild(logEntries.lastChild);
    }
  }

  // ─── Helpers ───────────────────────────────────────────────────

  function showMonitorView() {
    setupPanel.classList.add('hidden');
    monitorView.classList.remove('hidden');

    // Initialize chart
    chart = new ScoreChart('scoreChart');
  }

  function setConnectionStatus(connected) {
    if (connected) {
      connDot.classList.add('connected');
      connText.textContent = 'Connected';
    } else {
      connDot.classList.remove('connected');
      connText.textContent = 'Disconnected';
    }
  }

  function updateParticipantCount() {
    infoParticipantCount.textContent = Object.keys(participants).length;
  }

  function startTimer() {
    if (timerInterval) clearInterval(timerInterval);
    timerInterval = setInterval(() => {
      const elapsed = Math.floor((Date.now() - startTimeMs) / 1000);
      const min = Math.floor(elapsed / 60).toString().padStart(2, '0');
      const sec = (elapsed % 60).toString().padStart(2, '0');
      meetingTimer.textContent = `${min}:${sec}`;
    }, 1000);
  }

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
})();
