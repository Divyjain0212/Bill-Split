from decimal import Decimal

import pytest

from src.calculator import calculate_shares
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


def test_calculation_requires_review_confirmation():
    bill = reviewed_bill()
    bill.review_confirmed = False

    with pytest.raises(ValueError, match="reviewed"):
        calculate_shares(bill, ["Asha", "Ben"])
