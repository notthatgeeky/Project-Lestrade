"""
Sherlock Simulation Harness

Deterministic replay system for testing the Bayesian Candidate Identification engine
without running a live Google Meet browser session.
"""
import sys
import os
import json
import asyncio
from typing import List, Dict, Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'backend')))

from engine.session_manager import InterviewSession
from models import IngestEvent

class SimulationHarness:
    def __init__(self, expected_candidate_name: str):
        self.session = InterviewSession(
            interview_id="sim_interview_123",
            expected_candidate_name=expected_candidate_name
        )
        self.events_replayed = 0

    async def replay_event(self, event_dict: Dict[str, Any]):
        """Inject a single event into the session."""
        # Convert index-based participant identifier or direct ID
        # The JSON cases can use platform_id directly in the payload/participant_id
        # Let's map participant_idx to standard platform_ids like "platform_p{idx}"
        p_idx = event_dict.get("participant_idx")
        platform_id = event_dict.get("participant_id")
        
        if p_idx is not None and not platform_id:
            platform_id = f"platform_p{p_idx}"
            
        event = IngestEvent(
            interview_id=self.session.interview_id,
            type=event_dict["type"],
            participant_id=platform_id,
            timestamp_ms=event_dict["timestamp_ms"],
            payload=event_dict.get("payload", {})
        )
        
        # We override standard persistence tasks since this is a pure simulation
        # and we don't want real sqlite writes to block or clutter the dev DB
        await self.session.process_event(event)
        self.events_replayed += 1

    async def run_simulation(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        """Run a complete simulation case."""
        # Initialize session state using the test case expected candidate metadata
        expected_candidate_name = case_data["interview_metadata"]["expected_candidate_name"]
        self.session = InterviewSession(
            interview_id=case_data["test_case_id"],
            expected_candidate_name=expected_candidate_name
        )
        
        # Sort events just in case they are out of order
        events = sorted(case_data["events"], key=lambda e: e["timestamp_ms"])
        
        for event in events:
            await self.replay_event(event)
            
        # Compile results
        results = []
        for pid, p in self.session.participants.items():
            results.append({
                "platform_id": pid,
                "display_name": p.current_display_name,
                "probability": p.candidate_probability,
                "confidence_band": p.confidence_band,
                "speaking_ratio": p.speaking_ratio,
                "camera_on_ratio": p.camera_on_ratio
            })
            
        # Sort by probability descending
        results = sorted(results, key=lambda r: r["probability"], reverse=True)
        
        # Determine success
        expected_idx = case_data["expected_candidate_participant_idx"]
        expected_platform_id = f"platform_p{expected_idx}"
        
        identified_candidate_pid = results[0]["platform_id"] if results else None
        success = (identified_candidate_pid == expected_platform_id)
        
        return {
            "test_case_id": case_data["test_case_id"],
            "success": success,
            "identified_candidate": results[0] if results else None,
            "expected_candidate_platform_id": expected_platform_id,
            "all_participants": results
        }
