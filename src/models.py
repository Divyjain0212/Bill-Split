from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ConfidenceLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FieldConfidence(BaseModel):
    value: Decimal | str | None = None
    score: float = Field(ge=0, le=1)
    source: str = "ocr"


class AssignmentMode(StrEnum):
    ONE = "one"
    SELECTED = "selected"
    EVERYONE = "everyone"


class LineItem(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    name: str = Field(min_length=1)
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)
    assigned_to: list[str] = Field(default_factory=list)
    assignment_mode: AssignmentMode = AssignmentMode.SELECTED
    confidence: dict[str, FieldConfidence] = Field(default_factory=dict)

    @property
    def subtotal(self) -> Decimal:
        return self.quantity * self.unit_price

    @model_validator(mode="after")
    def validate_assignment(self) -> LineItem:
        if self.assignment_mode != AssignmentMode.EVERYONE and not self.assigned_to:
            raise ValueError("An item must be assigned to at least one person")
        return self


class Bill(BaseModel):
    currency: str = "INR"
    line_items: list[LineItem] = Field(min_length=1)
    tax: Decimal = Field(default=Decimal("0"), ge=0)
    service_charge: Decimal = Field(default=Decimal("0"), ge=0)
    discount: Decimal = Field(default=Decimal("0"), ge=0)
    printed_subtotal: Decimal | None = Field(default=None, ge=0)
    printed_total: Decimal | None = Field(default=None, ge=0)
    confidence: dict[str, FieldConfidence] = Field(default_factory=dict)
    review_confirmed: bool = False

    @property
    def item_subtotal(self) -> Decimal:
        return sum((item.subtotal for item in self.line_items), Decimal("0"))

    @property
    def calculated_total(self) -> Decimal:
        return self.item_subtotal + self.tax + self.service_charge - self.discount

    @property
    def total_mismatch(self) -> Decimal | None:
        if self.printed_total is None:
            return None
        return self.printed_total - self.calculated_total
