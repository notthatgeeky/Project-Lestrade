/**
 * Sherlock — Google Meet DOM Scraper (Content Script)
 *
 * Injected into Google Meet pages. Tracks:
 * 1. Participant roster (join, leave, rename, camera state)
 * 2. Active speaker changes
 * 3. Live captions/transcript
 *
 * All events are sent to the service worker via chrome.runtime.sendMessage().
 */

(function () {
  'use strict';

  // Avoid double-injection
  if (window.__sherlockInjected) return;
  window.__sherlockInjected = true;

  // ─── State ─────────────────────────────────────────────────────
  const knownParticipants = new Map(); // platformId → {name, cameraOn, isMuted}
  let activeSpeakerId = null;
  let speakingStartMs = null;
  let lastCaptionText = '';
  let observers = [];
  let pollInterval = null;
  let isMonitoring = false;

  // ─── Logging ───────────────────────────────────────────────────
  function log(msg, ...args) {
    console.log(`[Sherlock] ${msg}`, ...args);
  }

  // ─── Event Emission ────────────────────────────────────────────
  function emitEvent(type, payload = {}, participantId = null) {
    const event = {
      type,
      participant_id: participantId,
      timestamp_ms: Date.now(),
      payload,
    };

    try {
      chrome.runtime.sendMessage(event);
    } catch (e) {
      // Extension context invalidated (e.g. extension reloaded)
      log('Failed to send event:', e.message);
      stopMonitoring();
    }
  }

  // ─── Participant Discovery ─────────────────────────────────────

  /**
   * Scan the DOM for participant information.
   * Google Meet renders participants in the video grid and the sidebar roster.
   * We use multiple strategies to find them.
   */
  function scanParticipants() {
    const currentParticipants = new Map();

    // Strategy 1: Look for elements with data-participant-id
    document.querySelectorAll('[data-participant-id]').forEach((el) => {
      const pid = el.getAttribute('data-participant-id');
      if (!pid) return;

      // Try to extract display name from various locations
      let name = '';

      // Check data-tooltip, aria-label, or inner text
      const nameEl = el.querySelector('[data-tooltip]');
      if (nameEl) {
        name = nameEl.getAttribute('data-tooltip') || '';
      }
      if (!name) {
        const ariaEl = el.querySelector('[aria-label]');
        if (ariaEl) {
          name = ariaEl.getAttribute('aria-label') || '';
        }
      }
      if (!name) {
        // Fallback: look for visible text nodes
        const spans = el.querySelectorAll('span');
        for (const span of spans) {
          const text = span.textContent.trim();
          if (text && text.length > 1 && text.length < 100) {
            name = text;
            break;
          }
        }
      }

      // Detect camera state
      const video = el.querySelector('video');
      const cameraOn = video
        ? video.srcObject !== null && video.readyState > 0
        : false;

      currentParticipants.set(pid, { name, cameraOn });
    });

    // Strategy 2: If Strategy 1 finds nothing, look for video tiles
    if (currentParticipants.size === 0) {
      document.querySelectorAll('[data-requested-participant-id]').forEach((el) => {
        const pid = el.getAttribute('data-requested-participant-id');
        if (!pid) return;

        let name = el.getAttribute('aria-label') || '';
        const cameraOn = !!el.querySelector('video');

        currentParticipants.set(pid, { name, cameraOn });
      });
    }

    // Diff against known state
    // New participants
    for (const [pid, info] of currentParticipants) {
      if (!knownParticipants.has(pid)) {
        knownParticipants.set(pid, { ...info });
        log(`Participant joined: ${info.name} (${pid})`);
        emitEvent('PARTICIPANT_JOIN', {
          display_name: info.name,
          camera_on: info.cameraOn,
          platform_id: pid,
        }, pid);
      } else {
        const old = knownParticipants.get(pid);

        // Check for rename
        if (old.name !== info.name && info.name) {
          log(`Participant renamed: ${old.name} → ${info.name}`);
          emitEvent('PARTICIPANT_RENAME', {
            old_name: old.name,
            new_name: info.name,
          }, pid);
          old.name = info.name;
        }

        // Check for camera state change
        if (old.cameraOn !== info.cameraOn) {
          emitEvent('PARTICIPANT_STATE_CHANGE', {
            camera_on: info.cameraOn,
          }, pid);
          old.cameraOn = info.cameraOn;
        }
      }
    }

    // Departed participants
    for (const [pid, info] of knownParticipants) {
      if (!currentParticipants.has(pid)) {
        log(`Participant left: ${info.name} (${pid})`);
        emitEvent('PARTICIPANT_LEAVE', {
          display_name: info.name,
        }, pid);
        knownParticipants.delete(pid);
      }
    }
  }

  // ─── Active Speaker Detection ──────────────────────────────────

  /**
   * Detect which participant is currently speaking.
   * Google Meet highlights the active speaker's tile with a colored border.
   */
  function detectActiveSpeaker() {
    // Look for speaking indicators — Meet uses various visual cues
    let currentSpeaker = null;

    // Strategy: Find the tile with a speaking indicator (animated border)
    document.querySelectorAll('[data-participant-id]').forEach((el) => {
      // Check for active speaker visual indicators
      const hasSpeakingBorder = el.querySelector('.Aq7Aje, .IisKdb') !== null;
      const hasActiveSpeaker = el.classList.contains('cZG6je') ||
        el.querySelector('[data-is-speaking="true"]') !== null;

      // Also check for audio level indicator
      const audioIndicator = el.querySelector('svg[class*="speak"], .eDY5Ob');

      if (hasSpeakingBorder || hasActiveSpeaker || audioIndicator) {
        currentSpeaker = el.getAttribute('data-participant-id');
      }
    });

    // Fallback: check data-requested-participant-id tiles
    if (!currentSpeaker) {
      document.querySelectorAll('[data-requested-participant-id]').forEach((el) => {
        if (el.classList.toString().includes('speak') ||
            el.querySelector('[data-is-speaking="true"]')) {
          currentSpeaker = el.getAttribute('data-requested-participant-id');
        }
      });
    }

    // Handle speaker transitions
    if (currentSpeaker !== activeSpeakerId) {
      // Previous speaker stopped
      if (activeSpeakerId) {
        emitEvent('SPEAKING_STOP', {
          duration_ms: Date.now() - (speakingStartMs || Date.now()),
        }, activeSpeakerId);
      }

      // New speaker started
      if (currentSpeaker) {
        speakingStartMs = Date.now();
        emitEvent('SPEAKING_START', {}, currentSpeaker);
      }

      activeSpeakerId = currentSpeaker;
    }
  }

  // ─── Caption / Transcript Capture ──────────────────────────────

  let captionDebounceTimer = null;
  let pendingCaptionText = '';
  let pendingCaptionSpeaker = '';

  /**
   * Set up a MutationObserver on the caption/subtitle container.
   */
  function setupCaptionObserver() {
    // Google Meet caption containers — try multiple selectors
    const captionSelectors = [
      '.iOzk7',           // Primary caption area
      '.a4cQT',           // Alternative caption container
      '[jscontroller] div[class*="caption"]',
      'div[aria-live="polite"]',
    ];

    for (const selector of captionSelectors) {
      const container = document.querySelector(selector);
      if (container) {
        log('Caption container found:', selector);

        const observer = new MutationObserver((mutations) => {
          for (const mutation of mutations) {
            processCaptionMutation(container);
          }
        });

        observer.observe(container, {
          childList: true,
          characterData: true,
          subtree: true,
        });

        observers.push(observer);
        return true;
      }
    }
    return false;
  }

  function processCaptionMutation(container) {
    // Extract speaker name and text from the caption container
    let speaker = '';
    let text = '';

    // Try to find speaker name element
    const speakerEl = container.querySelector('.zs7s8d, .KcIKyf, [class*="speaker"]');
    if (speakerEl) {
      speaker = speakerEl.textContent.trim();
    }

    // Extract caption text
    const textEls = container.querySelectorAll('.iTTPOb span, .bh44bd, [class*="caption"] span');
    if (textEls.length > 0) {
      text = Array.from(textEls).map((el) => el.textContent).join(' ').trim();
    } else {
      text = container.textContent.trim();
    }

    if (!text || text === lastCaptionText) return;

    pendingCaptionText = text;
    pendingCaptionSpeaker = speaker;

    // Debounce: wait 500ms for final text
    clearTimeout(captionDebounceTimer);
    captionDebounceTimer = setTimeout(() => {
      if (pendingCaptionText && pendingCaptionText !== lastCaptionText) {
        // Find participant ID for this speaker
        let speakerPid = null;
        if (pendingCaptionSpeaker) {
          for (const [pid, info] of knownParticipants) {
            if (info.name && (
              pendingCaptionSpeaker.includes(info.name) ||
              info.name.includes(pendingCaptionSpeaker)
            )) {
              speakerPid = pid;
              break;
            }
          }
        }

        emitEvent('TRANSCRIPT_CHUNK', {
          speaker_name: pendingCaptionSpeaker,
          text: pendingCaptionText,
          is_final: true,
        }, speakerPid || activeSpeakerId);

        lastCaptionText = pendingCaptionText;
      }
    }, 500);
  }

  // ─── Monitoring Lifecycle ──────────────────────────────────────

  function startMonitoring() {
    if (isMonitoring) return;
    isMonitoring = true;
    log('Monitoring started');

    // Initial scan
    scanParticipants();

    // Poll for participant changes every 2 seconds
    // (MutationObserver can miss some changes in complex DOMs)
    pollInterval = setInterval(() => {
      scanParticipants();
      detectActiveSpeaker();
    }, 2000);

    // Try to set up caption observer (may need retry if captions aren't enabled yet)
    if (!setupCaptionObserver()) {
      log('Caption container not found, will retry...');
      const captionRetry = setInterval(() => {
        if (setupCaptionObserver()) {
          clearInterval(captionRetry);
        }
      }, 5000);
    }

    // Set up a general MutationObserver on the meeting container for faster detection
    const meetingContainer = document.querySelector('[data-call-id]') ||
      document.querySelector('[data-meeting-title]') ||
      document.body;

    const mainObserver = new MutationObserver(() => {
      scanParticipants();
    });

    mainObserver.observe(meetingContainer, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['data-participant-id', 'data-is-speaking', 'class'],
    });

    observers.push(mainObserver);
  }

  function stopMonitoring() {
    if (!isMonitoring) return;
    isMonitoring = false;
    log('Monitoring stopped');

    clearInterval(pollInterval);
    observers.forEach((obs) => obs.disconnect());
    observers = [];
    clearTimeout(captionDebounceTimer);
  }

  // ─── Message Handling from Service Worker ──────────────────────

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === 'START_MONITORING') {
      startMonitoring();
      sendResponse({ status: 'started' });
    } else if (message.type === 'STOP_MONITORING') {
      stopMonitoring();
      sendResponse({ status: 'stopped' });
    } else if (message.type === 'GET_STATUS') {
      sendResponse({
        isMonitoring,
        participantCount: knownParticipants.size,
        activeSpeaker: activeSpeakerId,
      });
    }
    return true; // Keep channel open for async responses
  });

  // ─── Auto-start when meeting is detected ───────────────────────

  function waitForMeeting() {
    const checkInterval = setInterval(() => {
      const isMeeting = document.querySelector('[data-call-id]') ||
        document.querySelector('[data-meeting-title]') ||
        document.querySelector('[data-participant-id]');

      if (isMeeting) {
        clearInterval(checkInterval);
        log('Meeting detected, ready for monitoring');
        // Don't auto-start — wait for user to click Start in popup
        chrome.runtime.sendMessage({ type: 'MEETING_DETECTED' });
      }
    }, 2000);
  }

  waitForMeeting();
  log('Content script loaded on', window.location.href);
})();
