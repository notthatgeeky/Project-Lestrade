/**
 * Sherlock — Service Worker (Background Script)
 *
 * Orchestrates communication between the content script and the backend.
 * Maintains a WebSocket connection to the Sherlock Ingestion Gateway.
 * Buffers events during disconnection and replays on reconnect.
 */

// ─── State ─────────────────────────────────────────────────────────
let ws = null;
let wsUrl = 'ws://localhost:8000/ws/ingest';
let interviewId = '';
let expectedCandidateName = '';
let isConnected = false;
let eventBuffer = [];
const MAX_BUFFER_SIZE = 1000;
let heartbeatInterval = null;
let reconnectTimeout = null;
let reconnectDelay = 1000;
let eventCount = 0;

// ─── WebSocket Management ──────────────────────────────────────────

function connect() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return;
  }

  const url = `${wsUrl}?interview_id=${encodeURIComponent(interviewId)}&expected_candidate_name=${encodeURIComponent(expectedCandidateName)}`;
  console.log('[Sherlock SW] Connecting to', url);

  try {
    ws = new WebSocket(url);
  } catch (e) {
    console.error('[Sherlock SW] Failed to create WebSocket:', e);
    scheduleReconnect();
    return;
  }

  ws.onopen = () => {
    console.log('[Sherlock SW] Connected');
    isConnected = true;
    reconnectDelay = 1000; // Reset backoff

    // Replay buffered events
    if (eventBuffer.length > 0) {
      console.log(`[Sherlock SW] Replaying ${eventBuffer.length} buffered events`);
      for (const evt of eventBuffer) {
        ws.send(evt);
      }
      eventBuffer = [];
    }

    // Start heartbeat
    heartbeatInterval = setInterval(() => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send('ping');
      }
    }, 5000);
  };

  ws.onclose = (event) => {
    console.log('[Sherlock SW] Disconnected:', event.code, event.reason);
    isConnected = false;
    clearInterval(heartbeatInterval);
    scheduleReconnect();
  };

  ws.onerror = (error) => {
    console.error('[Sherlock SW] WebSocket error:', error);
    isConnected = false;
  };

  ws.onmessage = (event) => {
    // Handle server responses (acks, commands)
    if (event.data === 'pong') return;

    try {
      const msg = JSON.parse(event.data);
      console.log('[Sherlock SW] Server message:', msg);
    } catch (e) {
      // Non-JSON response
    }
  };
}

function disconnect() {
  if (ws) {
    ws.close(1000, 'User disconnected');
    ws = null;
  }
  isConnected = false;
  eventCount = 0;
  eventBuffer = [];
  clearInterval(heartbeatInterval);
  clearTimeout(reconnectTimeout);
}

function scheduleReconnect() {
  if (!interviewId) return; // Don't reconnect if no active session

  clearTimeout(reconnectTimeout);
  reconnectTimeout = setTimeout(() => {
    reconnectDelay = Math.min(reconnectDelay * 2, 30000); // Exponential backoff
    connect();
  }, reconnectDelay);
}

// ─── Event Routing ─────────────────────────────────────────────────

function sendEvent(event) {
  const message = JSON.stringify({
    interview_id: interviewId,
    ...event,
  });

  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(message);
    eventCount++;
  } else {
    // Buffer the event
    eventBuffer.push(message);
    if (eventBuffer.length > MAX_BUFFER_SIZE) {
      eventBuffer.shift(); // Drop oldest
    }
  }
}

// ─── Message Handling ──────────────────────────────────────────────

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  switch (message.type) {
    case 'CONNECT': {
      // From popup: start a monitoring session
      wsUrl = message.serverUrl || 'ws://localhost:8000/ws/ingest';
      interviewId = message.interviewId || crypto.randomUUID();
      expectedCandidateName = message.expectedCandidateName || '';
      connect();

      // Tell content script to start monitoring
      chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
        if (tabs[0]) {
          chrome.tabs.sendMessage(tabs[0].id, { type: 'START_MONITORING' });
        }
      });

      sendResponse({
        status: 'connecting',
        interviewId,
      });
      break;
    }

    case 'DISCONNECT': {
      // From popup: stop monitoring
      chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
        if (tabs[0]) {
          chrome.tabs.sendMessage(tabs[0].id, { type: 'STOP_MONITORING' });
        }
      });
      disconnect();
      sendResponse({ status: 'disconnected' });
      break;
    }

    case 'GET_STATUS': {
      sendResponse({
        isConnected,
        interviewId,
        eventCount,
        bufferSize: eventBuffer.length,
      });
      break;
    }

    case 'MEETING_DETECTED': {
      // From content script: a meeting was detected on the page
      console.log('[Sherlock SW] Meeting detected on tab');
      break;
    }

    default: {
      // Forward all other events (from content script) to the backend
      if (message.type && message.timestamp_ms) {
        sendEvent(message);
      }
      break;
    }
  }

  return true; // Keep channel open
});

console.log('[Sherlock SW] Service worker loaded');

# refactor
