"""
Sherlock Backend — Database Row Helpers

Utility functions for mapping between DB rows and Pydantic models.
"""
import json
from typing import Optional, Dict, Any, List


def row_to_dict(row) -> Dict[str, Any]:
    """Convert an aiosqlite.Row to a dictionary."""
    if row is None:
        return {}
    return dict(row)


def parse_json_field(value: Optional[str], default=None):
    """Parse a JSON string field from SQLite."""
    if value is None:
        return default if default is not None else {}
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default if default is not None else {}


def serialize_json_field(value) -> str:
    """Serialize a Python object to JSON string for SQLite storage."""
    return json.dumps(value, default=str)


def participant_row_to_response(row: Dict[str, Any]) -> Dict[str, Any]:
    """Transform a participant DB row into an API response dict."""
    result = dict(row)
    result["display_name_history"] = parse_json_field(
        result.get("display_name_history"), default=[]
    )
    result["camera_on"] = bool(result.get("camera_on", 0))
    result["is_identified_candidate"] = bool(
        result.get("is_identified_candidate", 0)
    )
    return result
