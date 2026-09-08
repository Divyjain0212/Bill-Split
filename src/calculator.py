from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from .models import AssignmentMode, Bill

CENT = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _allocate(values: dict[str, Decimal], total: Decimal, people: list[str]) -> dict[str, Decimal]:
    allocated = {person: _money(values[person]) for person in people}
    difference = _money(total) - sum(allocated.values(), Decimal("0"))
    if people:
        allocated[people[-1]] += difference
    return allocated


def calculate_breakdown(bill: Bill, people: list[str]) -> dict[str, dict[str, Decimal]]:
    """Calculate each person's consumption-weighted bill breakdown."""
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

    proportions = {person: base_by_person[person] / assigned_subtotal for person in people}
    base = _allocate(base_by_person, assigned_subtotal, people)
    equal_tax = bill.tax / len(people)
    tax = _allocate({person: equal_tax for person in people}, bill.tax, people)
    service_charge = _allocate(
        {person: bill.service_charge * proportions[person] for person in people},
        bill.service_charge,
        people,
    )
    discount = _allocate({person: bill.discount * proportions[person] for person in people}, bill.discount, people)
    return {
        person: {
            "subtotal": base[person],
            "tax": tax[person],
            "service_charge": service_charge[person],
            "discount": discount[person],
            "total": base[person] + tax[person] + service_charge[person] - discount[person],
        }
        for person in people
    }


def calculate_shares(bill: Bill, people: list[str]) -> dict[str, Decimal]:
    """Calculate only each person's final amount."""
    breakdown = calculate_breakdown(bill, people)
    for person in people:
        breakdown[person]["total"] = _money(breakdown[person]["total"])
    return {person: values["total"] for person, values in breakdown.items()}
