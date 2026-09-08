from decimal import Decimal

import pytest

from src.calculator import calculate_breakdown, calculate_shares
from src.models import AssignmentMode, Bill, LineItem


def reviewed_bill() -> Bill:
    return Bill(
        line_items=[
            LineItem(name="Biryani", quantity=Decimal("2"), unit_price=Decimal("300"), assigned_to=["Asha", "Ben"]),
            LineItem(name="Coke", quantity=Decimal("1"), unit_price=Decimal("80"), assigned_to=["Cara"]),
            LineItem(name="Naan", quantity=Decimal("2"), unit_price=Decimal("60"), assignment_mode=AssignmentMode.EVERYONE),
        ],
        tax=Decimal("80"),
        service_charge=Decimal("40"),
        review_confirmed=True,
    )


def test_tax_and_service_charge_follow_consumption():
    shares = calculate_shares(reviewed_bill(), ["Asha", "Ben", "Cara", "Dev"])

    assert shares == {
        "Asha": Decimal("379.50"),
        "Ben": Decimal("379.50"),
        "Cara": Decimal("126.50"),
        "Dev": Decimal("34.50"),
    }


def test_everyone_item_is_split_across_all_people():
    bill = reviewed_bill()
    bill.line_items[2].assignment_mode = AssignmentMode.EVERYONE

    shares = calculate_shares(bill, ["Asha", "Ben", "Cara", "Dev"])

    assert sum(shares.values(), Decimal("0")) == Decimal("920.00")


def test_breakdown_reconciles_each_charge_to_the_bill():
    breakdown = calculate_breakdown(reviewed_bill(), ["Asha", "Ben", "Cara", "Dev"])

    assert sum(row["subtotal"] for row in breakdown.values()) == Decimal("800.00")
    assert sum(row["tax"] for row in breakdown.values()) == Decimal("80.00")
    assert sum(row["service_charge"] for row in breakdown.values()) == Decimal("40.00")
    assert sum(row["total"] for row in breakdown.values()) == Decimal("920.00")


def test_receipt_style_assignment_allocates_tax_from_consumed_items():
    bill = Bill(
        currency="USD",
        line_items=[
            LineItem(name="Salad", quantity=Decimal("2"), unit_price=Decimal("12"), assigned_to=["Divy", "Sanyam"]),
            LineItem(name="Salmon", quantity=Decimal("1"), unit_price=Decimal("22"), assigned_to=["Divy"]),
            LineItem(name="Cheesecake", quantity=Decimal("1"), unit_price=Decimal("7.50"), assignment_mode=AssignmentMode.EVERYONE),
            LineItem(name="Water", quantity=Decimal("2"), unit_price=Decimal("3"), assignment_mode=AssignmentMode.EVERYONE),
        ],
        tax=Decimal("3.80"),
        printed_subtotal=Decimal("47.50"),
        printed_total=Decimal("51.30"),
        review_confirmed=True,
    )

    breakdown = calculate_breakdown(bill, ["Divy", "Sanyam"])

    assert breakdown["Divy"] == {
        "subtotal": Decimal("40.75"),
        "tax": Decimal("2.60"),
        "service_charge": Decimal("0.00"),
        "discount": Decimal("0.00"),
        "total": Decimal("43.35"),
    }
    assert breakdown["Sanyam"]["tax"] == Decimal("1.20")
    assert bill.calculated_total == Decimal("63.30")
    assert bill.total_mismatch == Decimal("-12.00")


def test_calculation_requires_review_confirmation():
    bill = reviewed_bill()
    bill.review_confirmed = False

    with pytest.raises(ValueError, match="reviewed"):
        calculate_shares(bill, ["Asha", "Ben"])
