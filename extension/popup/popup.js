/**
 * Sherlock Extension Popup — UI Logic
 */
document.addEventListener('DOMContentLoaded', () => {
  const serverUrl = document.getElementById('serverUrl');
  const interviewId = document.getElementById('interviewId');
  const candidateName = document.getElementById('candidateName');
  const btnConnect = document.getElementById('btnConnect');
  const btnDisconnect = document.getElementById('btnDisconnect');
  const configSection = document.getElementById('configSection');
  const statsSection = document.getElementById('statsSection');
  const statusDot = document.getElementById('statusDot');
  const statusText = document.getElementById('statusText');
  const eventCountEl = document.getElementById('eventCount');
  const bufferSizeEl = document.getElementById('bufferSize');
  const activeInterviewEl = document.getElementById('activeInterview');
  const openDashboard = document.getElementById('openDashboard');

  let statusPollInterval = null;

  // Load saved settings
  chrome.storage.local.get(['serverUrl', 'interviewId', 'candidateName'], (data) => {
    if (data.serverUrl) serverUrl.value = data.serverUrl;
    if (data.candidateName) candidateName.value = data.candidateName;
  });

  // Check initial status
  updateStatus();

  // ─── Connect ─────────────────────────────────────
  btnConnect.addEventListener('click', () => {
    const settings = {
      serverUrl: serverUrl.value.trim(),
      interviewId: interviewId.value.trim() || undefined,
      candidateName: candidateName.value.trim(),
    };

    // Save settings
    chrome.storage.local.set({
      serverUrl: settings.serverUrl,
      candidateName: settings.candidateName,
    });

    chrome.runtime.sendMessage({
      type: 'CONNECT',
      serverUrl: settings.serverUrl,
      interviewId: settings.interviewId,
      expectedCandidateName: settings.candidateName,
    }, (response) => {
      if (response && response.interviewId) {
        interviewId.value = response.interviewId;
      }
      showConnectedUI();
    });
  });

  // ─── Disconnect ──────────────────────────────────
  btnDisconnect.addEventListener('click', () => {
    chrome.runtime.sendMessage({ type: 'DISCONNECT' }, () => {
      showDisconnectedUI();
    });
  });

  // ─── Dashboard Link ──────────────────────────────
  openDashboard.addEventListener('click', (e) => {
    e.preventDefault();
    const baseUrl = serverUrl.value.replace('ws://', 'http://').replace('wss://', 'https://');
    const dashUrl = baseUrl.replace(/\/ws\/ingest.*/, '');
    const id = interviewId.value || '';
    chrome.tabs.create({ url: `${dashUrl}/dashboard/index.html?interview=${id}` });
  });

  // ─── UI State ────────────────────────────────────
  function showConnectedUI() {
    btnConnect.classList.add('hidden');
    btnDisconnect.classList.remove('hidden');
    configSection.classList.add('hidden');
    statsSection.classList.remove('hidden');
    statusDot.classList.add('connected');
    statusDot.classList.remove('connecting');
    statusText.textContent = 'Connected';

    // Poll for stats
    statusPollInterval = setInterval(updateStatus, 2000);
  }

  function showDisconnectedUI() {
    btnConnect.classList.remove('hidden');
    btnDisconnect.classList.add('hidden');
    configSection.classList.remove('hidden');
    statsSection.classList.add('hidden');
    statusDot.classList.remove('connected', 'connecting');
    statusText.textContent = 'Disconnected';

    clearInterval(statusPollInterval);
  }

  function updateStatus() {
    chrome.runtime.sendMessage({ type: 'GET_STATUS' }, (response) => {
      if (chrome.runtime.lastError) return;
      if (!response) return;

      if (response.isConnected) {
        showConnectedUI();
        eventCountEl.textContent = response.eventCount || 0;
        bufferSizeEl.textContent = response.bufferSize || 0;
        activeInterviewEl.textContent = response.interviewId || '—';
      }
    });
  }
});
