from __future__ import annotations

import re
from decimal import Decimal

from .models import Bill, FieldConfidence, LineItem

MONEY = r"(?:\d+[,.]?\d*)"
SUMMARY_PATTERNS = {
    "printed_subtotal": re.compile(rf"\bsub\s*total\b\D*({MONEY})", re.IGNORECASE),
    "tax": re.compile(rf"\b(?:gst|tax|vat)\b\D*({MONEY})", re.IGNORECASE),
    "service_charge": re.compile(rf"\bservice\s*charge\b\D*({MONEY})", re.IGNORECASE),
    "discount": re.compile(rf"\bdiscount\b\D*({MONEY})", re.IGNORECASE),
    "printed_total": re.compile(rf"\b(?:grand\s*)?total\b\D*({MONEY})", re.IGNORECASE),
}
ITEM_PATTERN = re.compile(rf"^(.+?)\s+(?:(\d+(?:\.\d+)?)\s*[xX*]\s*)?({MONEY})$")


def _amount(value: str) -> Decimal:
    return Decimal(value.replace(",", ""))


def parse_ocr_text(text: str, confidence: float = 0.0) -> Bill:
    summaries: dict[str, Decimal] = {}
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
                summaries[field_name] = _amount(match.group(1))
                confidence_fields[field_name] = FieldConfidence(value=summaries[field_name], score=confidence)
                matched_summary = True
                break
        if matched_summary:
            continue
        item_match = ITEM_PATTERN.match(line)
        if item_match and not re.search(r"receipt|invoice|bill|date|phone|thank", line, re.IGNORECASE):
            name, quantity, unit_price = item_match.groups()
            quantity_value = Decimal(quantity or "1")
            item = LineItem(
                name=name.strip(),
                quantity=quantity_value,
                unit_price=_amount(unit_price),
                assigned_to=["Unassigned"],
                confidence={
                    "name": FieldConfidence(value=name.strip(), score=confidence),
                    "quantity": FieldConfidence(value=quantity_value, score=confidence),
                    "unit_price": FieldConfidence(value=_amount(unit_price), score=confidence),
                },
            )
            lines.append(item)

    if not lines:
        raise ValueError("No line items could be identified in the OCR text")
    return Bill(line_items=lines, confidence=confidence_fields, **summaries)
