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


def test_indian_table_receipt_parses_columns_and_combines_taxes():
    bill = parse_ocr_text(
        "YOUR RESTAURANT\n"
        "ITEM QTY UNIT TOTAL\n"
        "1. Masala Dosa 1 ₹145.00 ₹145.00\n"
        "2. Paneer Roll 1 ₹120.00 ₹120.00\n"
        "3. Tea 2 ₹45.00 ₹90.00\n"
        "4. Gulab Jamun 1 ₹110.00 ₹110.00\n"
        "SUBTOTAL ₹465.00\n"
        "CGST (2.5%) ₹11.63\n"
        "SGST (2.5%) ₹11.63\n"
        "GRAND TOTAL ₹488.26"
    )

    assert bill.currency == "INR"
    assert [(item.name, item.quantity, item.unit_price) for item in bill.line_items] == [
        ("Masala Dosa", Decimal("1"), Decimal("145.00")),
        ("Paneer Roll", Decimal("1"), Decimal("120.00")),
        ("Tea", Decimal("2"), Decimal("45.00")),
        ("Gulab Jamun", Decimal("1"), Decimal("110.00")),
    ]
    assert bill.item_subtotal == Decimal("465.00")
    assert bill.tax == Decimal("23.26")
    assert bill.printed_total == Decimal("488.26")
    assert bill.total_mismatch == Decimal("0.00")
