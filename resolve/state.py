"""Explicit shared state; row references are namespaced to avoid collisions."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from .impact import Impact


class Action(str, Enum):
    POST_FIX = "post_fix"
    LINK_ISSUE = "link_issue"
    OPEN_ISSUE = "open_issue"
    ESCALATE = "escalate"


@dataclass
class Evidence:
    source: str
    row_id: str
    record: dict[str, Any]
    provenance: dict[str, str] = field(default_factory=lambda: {"via": "local"})

    @property
    def id(self) -> str:
        return f"{self.source}:{self.row_id}"


@dataclass
class Claim:
    evidence_id: str
    field: str
    value: Any


@dataclass
class Proposal:
    action: Action = Action.ESCALATE
    confidence: float = 0.0
    selected_id: str | None = None
    supporting_ids: list[str] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)


@dataclass
class TaskState:
    question_id: str
    message: str
    customer_id: str
    component: str = "unknown"
    issue_type: str = "unknown"
    evidence: list[Evidence] = field(default_factory=list)
    hypothesis: Proposal = field(default_factory=Proposal)
    verified: bool = False
    gaps: list[str] = field(default_factory=list)
    retries: int = 0
    action: Action = Action.ESCALATE
    action_result: dict[str, Any] = field(default_factory=dict)
    reply_text: str = ""
    events: list[dict[str, Any]] = field(default_factory=list)
    impact: Impact | None = None
    impact_error: str | None = None

    def snapshot(self) -> dict[str, Any]:
        snapshot = asdict(self)
        snapshot["world_context"] = {
            "entities": [{"id": evidence.id, **asdict(evidence)} for evidence in self.evidence]
        }
        return snapshot

    def record_event(self, role: str, **details: Any) -> None:
        # Observable decisions and source IDs, not private model reasoning.
        self.events.append({"role": role, "attempt": self.retries, **details})
