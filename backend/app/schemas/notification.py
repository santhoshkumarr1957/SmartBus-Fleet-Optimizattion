"""Pydantic schemas for Stage 9: Notifications and Alert Management.

Defines schemas for notification items, acknowledgement and resolution actions,
alert summary metrics, and evaluation refresh responses.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class NotificationResponse(BaseModel):
    """Full representation of a transit operational or simulation alert."""

    id: int
    alert_type: str = Field(
        ...,
        description="CRITICAL_ROUTE_LOAD, HIGH_ROUTE_LOAD, BUS_BREAKDOWN, ROUTE_DISRUPTION, REALLOCATION_OPPORTUNITY, or SIMULATION_NOTICE",
    )
    severity: str = Field(
        ...,
        description="CRITICAL, HIGH, WARNING, or INFO",
    )
    title: str = Field(..., description="Short headline summarizing the event")
    description: str = Field(..., description="Detailed explanation of the incident")
    source: str = Field(
        default="LIVE",
        description="LIVE or SIMULATION",
    )
    status: str = Field(
        default="ACTIVE",
        description="ACTIVE, ACKNOWLEDGED, or RESOLVED",
    )
    dedup_key: str = Field(
        ...,
        description="Deterministic incident fingerprint for duplicate suppression",
    )

    # Correlated entity references
    route_id: Optional[int] = None
    route_number: Optional[str] = None
    bus_id: Optional[int] = None
    bus_number: Optional[str] = None

    # Review workflow fields
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    notes: Optional[str] = None

    # Timestamps
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NotificationActionRequest(BaseModel):
    """Payload to acknowledge or resolve an active alert."""

    dispatcher_id: Optional[str] = Field(
        default="DISPATCHER-1",
        description="Identifier of the acknowledging or resolving transit dispatcher",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Operational remarks, field notes, or resolution justification",
    )


class NotificationSummaryResponse(BaseModel):
    """Aggregate counters for notifications by status, severity, and source."""

    total_alerts: int = Field(..., description="Total count of all recorded alerts")
    active_count: int = Field(..., description="Number of currently ACTIVE alerts requiring attention")
    acknowledged_count: int = Field(..., description="Number of ACKNOWLEDGED alerts")
    resolved_count: int = Field(..., description="Number of RESOLVED alerts")
    critical_count: int = Field(..., description="Number of active or acknowledged CRITICAL alerts")
    high_count: int = Field(..., description="Number of active or acknowledged HIGH alerts")
    warning_count: int = Field(..., description="Number of active or acknowledged WARNING alerts")
    info_count: int = Field(..., description="Number of active or acknowledged INFO alerts")
    live_active_count: int = Field(..., description="Number of active LIVE operational alerts")
    simulation_count: int = Field(..., description="Number of SIMULATION alerts")
    last_evaluated_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp of the most recent evaluation sweep",
    )


class NotificationRefreshResponse(BaseModel):
    """Summary result returned after evaluating current operational conditions."""

    evaluated_at: datetime
    new_alerts_created: int
    existing_alerts_updated: int
    total_active_alerts: int
    critical_alerts_count: int
    message: str
