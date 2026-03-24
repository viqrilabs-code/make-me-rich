from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.common import ORMModel


class GoalPlanResponse(BaseModel):
    target_amount: float
    remaining_gap: float
    days_remaining: int
    daily_required_pace: float
    urgency_score: float
    mode_suggestion: str


class GoalBase(BaseModel):
    initial_capital: float = Field(gt=0)
    target_multiplier: float = Field(ge=1.0, le=2.0)
    start_date: date | None = None
    target_date: date | None = None
    target_days: int | None = Field(default=None, ge=1, le=3650)
    status: str = "active"

    @model_validator(mode="after")
    def validate_dates(self) -> "GoalBase":
        if not self.target_date and not self.target_days:
            self.target_days = 90
        if not self.start_date:
            self.start_date = date.today()
        if not self.target_date and self.target_days:
            self.target_date = self.start_date.fromordinal(
                self.start_date.toordinal() + self.target_days
            )
        return self


class GoalCreate(GoalBase):
    pass


class GoalUpdate(BaseModel):
    initial_capital: float | None = Field(default=None, gt=0)
    target_multiplier: float | None = Field(default=None, ge=1.0, le=2.0)
    start_date: date | None = None
    target_date: date | None = None
    target_days: int | None = Field(default=None, ge=1, le=3650)
    status: str | None = None

    @field_validator("status")
    @classmethod
    def normalize_status(cls, value: str | None) -> str | None:
        return value.lower() if value else value


class GoalResponse(ORMModel):
    id: int
    initial_capital: float
    target_multiplier: float
    target_amount: float
    start_date: date
    target_date: date
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    plan: GoalPlanResponse | None = None
