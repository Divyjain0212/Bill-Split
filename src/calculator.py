from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from .models import AssignmentMode, Bill

CENT = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def calculate_shares(bill: Bill, people: list[str]) -> dict[str, Decimal]:
    """Calculate each person's share after proportional tax and service charge."""
    if not people:
        raise ValueError("At least one person is required")
    if not bill.review_confirmed:
        raise ValueError("The bill must be reviewed before calculation")

    valid_people = set(people)
    base_by_person: dict[str, Decimal] = defaultdict(Decimal)
    for item in bill.line_items:
        recipients = valid_people if item.assignment_mode == AssignmentMode.EVERYONE else set(item.assigned_to)
        recipients &= valid_people
        if not recipients:
            raise ValueError(f"Item '{item.name}' has no valid recipients")
        share = item.subtotal / len(recipients)
        for person in recipients:
            base_by_person[person] += share

    assigned_subtotal = sum(base_by_person.values(), Decimal("0"))
    if assigned_subtotal <= 0:
        raise ValueError("Assigned subtotal must be greater than zero")

    result: dict[str, Decimal] = {}
    for person in people:
        proportion = base_by_person[person] / assigned_subtotal
        result[person] = _money(
            base_by_person[person]
            + bill.tax * proportion
            + bill.service_charge * proportion
            - bill.discount * proportion
        )
    return result
