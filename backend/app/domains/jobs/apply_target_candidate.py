from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ApplyTargetCandidate:
    destination_url: str
    target_type: str
    metadata: dict[str, Any] = field(default_factory=dict)
