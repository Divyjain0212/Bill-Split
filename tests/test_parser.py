from decimal import Decimal

from src.parser import parse_ocr_text


def test_parser_creates_unconfirmed_bill_from_receipt_text():
    bill = parse_ocr_text(
        "Biryani 2 x 300\nCoke 80\nSubtotal 680\nGST 34\nService Charge 20\nGrand Total 734",
        confidence=0.82,
    )

    assert bill.review_confirmed is False
    assert bill.line_items[0].subtotal == Decimal("600")
    assert bill.line_items[1].unit_price == Decimal("80")
    assert bill.tax == Decimal("34")
    assert bill.service_charge == Decimal("20")
    assert bill.printed_total == Decimal("734")
    assert bill.confidence["tax"].score == 0.82
