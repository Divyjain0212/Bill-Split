from decimal import Decimal

from src.parser import parse_ocr_text


def test_parser_creates_unconfirmed_bill_from_receipt_text():
    bill = parse_ocr_text(
        "GUESTS: 2\nBiryani 2 x 300\nCoke $80\nSubtotal $680\nGST $34\nService Charge $20\nGrand Total $734",
        confidence=0.82,
    )

    assert bill.review_confirmed is False
    assert bill.currency == "USD"
    assert bill.line_items[0].subtotal == Decimal("600")
    assert bill.line_items[1].unit_price == Decimal("80")
    assert bill.guest_count == 2
    assert bill.currency == "USD"
    assert bill.tax == Decimal("34")
    assert bill.service_charge == Decimal("20")
    assert bill.printed_total == Decimal("734")
    assert bill.confidence["tax"].score == 0.82


def test_restaurant_receipt_detects_two_guests_and_wrong_total():
    bill = parse_ocr_text(
        "GUESTS: 2\n"
        "2X CAESAR SALAD $24.00\n"
        "GRILLED SALMON $22.00\n"
        "CHEESECAKE $7.50\n"
        "2X SPARKLING WATER $6.00\n"
        "SUBTOTAL: $47.50\n"
        "TAX: $3.80\n"
        "TOTAL: $51.30"
    )

    assert bill.guest_count == 2
    assert len(bill.line_items) == 4
    assert bill.item_subtotal == Decimal("59.50")
    assert bill.total_mismatch == Decimal("-12.00")
    assert [(item.name, item.quantity, item.unit_price) for item in bill.line_items] == [
        ("CAESAR SALAD", Decimal("2"), Decimal("12.00")),
        ("GRILLED SALMON", Decimal("1"), Decimal("22.00")),
        ("CHEESECAKE", Decimal("1"), Decimal("7.50")),
        ("SPARKLING WATER", Decimal("2"), Decimal("3.00")),
    ]
