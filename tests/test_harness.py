"""
Test script to run the Simulation Harness over all test cases in tests/simulation/cases/.
"""
import sys
import os
import json
import asyncio
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from simulation.harness import SimulationHarness

def get_test_cases():
    cases_dir = os.path.join(os.path.dirname(__file__), 'simulation', 'cases')
    cases = []
    for f in os.listdir(cases_dir):
        if f.endswith('.json'):
            cases.append(os.path.join(cases_dir, f))
    return cases

@pytest.mark.asyncio
@pytest.mark.parametrize("case_path", get_test_cases())
async def test_simulation_case(case_path):
    """Run simulation case and assert success."""
    with open(case_path, 'r', encoding='utf-8') as f:
        case_data = json.load(f)
        
    harness = SimulationHarness(
        expected_candidate_name=case_data["interview_metadata"]["expected_candidate_name"]
    )
    result = await harness.run_simulation(case_data)
    
    assert result["success"] is True, (
        f"Failed test case: {result['test_case_id']}\n"
        f"Expected: {result['expected_candidate_platform_id']}\n"
        f"Identified: {result['identified_candidate']['platform_id'] if result['identified_candidate'] else 'None'}\n"
        f"All Scores: {result['all_participants']}"
    )
