from __future__ import annotations

import re
from decimal import Decimal

from .models import Bill, FieldConfidence, LineItem

MONEY = r"(?:[$€£₹]?\s*\d[\d,]*(?:\.\d+)?)"
SUMMARY_PATTERNS = {
    "guest_count": re.compile(r"\bguests?\b\D*(\d+)", re.IGNORECASE),
    "printed_subtotal": re.compile(rf"\bsub\s*total\b\D*({MONEY})", re.IGNORECASE),
    "tax": re.compile(rf"\b(?:gst|tax|vat)\b\D*({MONEY})", re.IGNORECASE),
    "service_charge": re.compile(rf"\bservice\s*charge\b\D*({MONEY})", re.IGNORECASE),
    "discount": re.compile(rf"\bdiscount\b\D*({MONEY})", re.IGNORECASE),
    "printed_total": re.compile(rf"\b(?:grand\s*)?total\b\D*({MONEY})", re.IGNORECASE),
}
UNIT_PRICE_PATTERN = re.compile(rf"^(.+?)\s+(\d+(?:\.\d+)?)\s*[xX*]\s*({MONEY})$")
LINE_TOTAL_PATTERN = re.compile(rf"^(?:(\d+(?:\.\d+)?)\s*[xX*]\s+)?(.+?)\s+({MONEY})$")
ITEM_STOP_WORDS = re.compile(
    r"^(?:subtotal|sub total|tax|gst|vat|total|grand total|discount|service charge)\b",
    re.IGNORECASE,
)


def _amount(value: str) -> Decimal:
    return Decimal(re.sub(r"[^\d.]", "", value.replace(",", "")))


def _is_item_candidate(line: str) -> bool:
    if ":" in line or "/" in line or re.search(r"\b(?:phone|receipt|table|server|card|type|entry|time|ref|status|tip|thank|please|www)\b", line, re.IGNORECASE):
        return False
    return bool(re.search(r"[A-Za-z]{2,}", line))


def parse_ocr_text(text: str, confidence: float = 0.0) -> Bill:
    summaries: dict[str, Decimal | int] = {}
    lines: list[LineItem] = []
    confidence_fields: dict[str, FieldConfidence] = {}

    for raw_line in text.splitlines():
        line = " ".join(raw_line.split()).strip()
        if not line:
            continue
        matched_summary = False
        for field_name, pattern in SUMMARY_PATTERNS.items():
            match = pattern.search(line)
            if match:
                value = int(match.group(1)) if field_name == "guest_count" else _amount(match.group(1))
                summaries[field_name] = value
                confidence_fields[field_name] = FieldConfidence(value=value, score=confidence)
                matched_summary = True
                break
        if matched_summary:
            continue
        if ITEM_STOP_WORDS.match(line):
            continue
        if not _is_item_candidate(line):
            continue

        unit_price_match = UNIT_PRICE_PATTERN.match(line)
        if unit_price_match:
            name, quantity, amount = unit_price_match.groups()
            quantity_value = Decimal(quantity)
            unit_price = _amount(amount)
        else:
            line_total_match = LINE_TOTAL_PATTERN.match(line)
            if not line_total_match:
                continue
            quantity, name, amount = line_total_match.groups()
            quantity_value = Decimal(quantity or "1")
            unit_price = _amount(amount) / quantity_value

        if not name.strip():
            continue
        item = LineItem(
            name=name.strip(),
            quantity=quantity_value,
            unit_price=unit_price,
            assigned_to=["Unassigned"],
            confidence={
                "name": FieldConfidence(value=name.strip(), score=confidence),
                "quantity": FieldConfidence(value=quantity_value, score=confidence),
                "unit_price": FieldConfidence(value=unit_price, score=confidence),
            },
        )
        lines.append(item)

    if not lines:
        raise ValueError("No line items could be identified in the OCR text")
    currency = "USD" if "$" in text else "INR" if "₹" in text else "EUR" if "€" in text else "GBP" if "£" in text else "INR"
    return Bill(currency=currency, line_items=lines, confidence=confidence_fields, **summaries)
