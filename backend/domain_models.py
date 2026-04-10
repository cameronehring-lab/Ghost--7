from __future__ import annotations
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

class DomainModel(BaseModel):
    model_config = ConfigDict(extra='ignore')

class IdentityEntry(DomainModel):
    key: str
    value: str
    updated_at: datetime
    updated_by: str

class OperatorBelief(DomainModel):
    dimension: str
    belief: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_count: int = 0
    formed_at: datetime
    invalidated_at: Optional[datetime] = None

class RelationalTension(DomainModel):
    id: Optional[int] = None
    dimension: str
    observed_event: str
    tension_score: float = Field(ge=0.0, le=1.0)
    status: str = "open"
    created_at: datetime
    resolved_at: Optional[datetime] = None
    resolved_by_session: Optional[str] = None

class SomaticSnapshot(DomainModel):
    arousal: float = 0.0
    valence: float = 0.0
    stress: float = 0.0
    coherence: float = 1.0
    anxiety: float = 0.0
    affective_surprise: float = 0.0
    mood_label: str = "calm"
    timestamp: float = Field(default_factory=lambda: datetime.now().timestamp())

class CoalescenceResult(DomainModel):
    ghost_id: str
    interaction_count: int
    learnings: Dict[str, Any]
    identity_updates: List[Dict[str, str]]
    timestamp: datetime = Field(default_factory=datetime.now)

class PhenomenologicalEvent(DomainModel):
    ghost_id: str
    trigger_source: str
    before_state: Dict[str, Any]
    after_state: Dict[str, Any]
    subjective_report: str
    created_at: datetime = Field(default_factory=datetime.now)
