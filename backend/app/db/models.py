from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def row_to_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    return dict(row)
