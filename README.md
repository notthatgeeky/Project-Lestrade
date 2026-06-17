# Sherlock — Candidate Identification & Interview Fraud Platform

Sherlock detects real-time interview fraud and resolves the "Candidate Identification Problem" across virtual meeting platforms. 

This repository contains the **Phase 1 MVP**, focusing on candidate identification using a multi-modal Bayesian sensor fusion engine. The platform is designed to be lightweight, self-hosted, cost-efficient, and runs entirely locally without expensive API keys or cloud dependencies.

---

## Repository Structure

*   `extension/`: Manifest V3 Chrome Extension that scrapes the Google Meet DOM for roster changes, active speaker updates, and captions.
*   `backend/`: FastAPI server running a Python-based sensor fusion engine, WebSocket routers, and async SQLite (`aiosqlite`) database.
    *   `backend/static/`: Pure JS/CSS live-monitoring dashboard.
*   `tests/`: Unit tests and a deterministic simulation harness to validate candidate identification accuracy over simulated meeting logs.

---

##  How It Works

Sherlock does not rely on simple heuristics like display names (which can be spoofed or generic). Instead, it models candidate identification as a **Bayesian inference problem**, calculating the probability $P(\text{Candidate} \mid \text{Evidence})$ in real-time.

Signals processed in Phase 1:
1.  **Metadata (Display Name)**: Fuzzy Jaro-Winkler & Token-Set comparison against calendar metadata.
2.  **Behavioral Speaking density**: Evaluates candidate speech ratios against Beta distributions.
3.  **Semantic Transcription Role**: Classifies captions into answering/asking profiles using keyword-based heuristics.
4.  **Visual Status**: Camera-on active state tracking.

Signals decay and adapt over time: name match weights decay after the first few minutes, while speaking density and semantic conversational profiles grow to dominate confidence scores.

---

##  Getting Started

### Prerequisites
*   Python 3.9+
*   Google Chrome (or Chromium-based browser)

### 1. Set up the Backend
Navigate to the `backend/` directory:
```bash
pip install fastapi uvicorn aiosqlite pydantic rapidfuzz scipy websockets
python main.py
```
This launches the backend and serves the dashboard on `http://localhost:8000`.

### 2. Load the Extension
1.  Open Chrome and navigate to `chrome://extensions/`.
2.  Enable **Developer mode** (toggle in the top-right).
3.  Click **Load unpacked** and select the `extension/` folder in this repository.

### 3. Run a Meeting Monitor
1.  Join a Google Meet meeting room.
2.  Click the Sherlock extension icon. Enter the expected candidate name (e.g. `Aarav Sharma`) and click **Start Monitoring**.
3.  Open the dashboard at `http://localhost:8000/dashboard/` (or click "Open Dashboard" in the extension popup footer) to observe live probabilities, state changes, and timeline plots.

---

##  Testing

We use `pytest` alongside a deterministic simulation harness running mock JSON event streams.

To install test dependencies:
```bash
pip install pytest pytest-asyncio
```

To run all unit and simulation tests:
```bash
python -m pytest tests/ -v
```
All tests should output a `PASSED` status.
