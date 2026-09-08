from __future__ import annotations

import re
from decimal import Decimal

from .models import Bill, FieldConfidence, LineItem

MONEY = r"(?:(?:[$€£₹]|Rs\.?|INR|USD|EUR|GBP)?\s*\d[\d,]*(?:\.\d+)?)"
SUMMARY_PATTERNS = {
    "guest_count": re.compile(r"\bguests?\b\D*(\d+)", re.IGNORECASE),
    "printed_subtotal": re.compile(rf"\bsub\s*total\b\D*({MONEY})", re.IGNORECASE),
    "tax": re.compile(rf"\b(?:gst|tax|vat)\b\D*({MONEY})", re.IGNORECASE),
    "service_charge": re.compile(rf"\bservice\s*charge\b\D*({MONEY})", re.IGNORECASE),
    "discount": re.compile(rf"\bdiscount\b\D*({MONEY})", re.IGNORECASE),
    "printed_total": re.compile(rf"\b(?:grand\s*)?total\b\D*({MONEY})", re.IGNORECASE),
}
TAX_LABEL_PATTERN = re.compile(r"\b(?:cgst|sgst|igst|gst|tax|vat)\b", re.IGNORECASE)
UNIT_PRICE_PATTERN = re.compile(rf"^(.+?)\s+(\d+(?:\.\d+)?)\s*[xX*]\s*({MONEY})$")
LINE_TOTAL_PATTERN = re.compile(rf"^(?:(\d+(?:\.\d+)?)\s*[xX*]\s+)?(.+?)\s+({MONEY})$")
TABLE_ITEM_PATTERN = re.compile(
    rf"^(?:\d+[.)]?\s*)?(.+?)\s+(\d+(?:\.\d+)?)\s+({MONEY})\s+({MONEY})$"
)
TABLE_HEADER_PATTERN = re.compile(r"\bitem\b.*\bqty\b.*\bunit\b.*\btotal\b", re.IGNORECASE)
TABLE_ROW_PATTERN = re.compile(r"^(?:\d+[.)]?\s*)?(.+?)\s+(\d+(?:\.\d+)?)\s+(.+)$")
ITEM_STOP_WORDS = re.compile(
    r"^(?:subtotal|sub total|tax|gst|vat|total|grand total|discount|service charge)\b",
    re.IGNORECASE,
)


def _amount(value: str) -> Decimal:
    return Decimal(re.sub(r"[^\d.]", "", value.replace(",", "")))


def _table_amounts(raw_values: list[str], currency: str, quantity: Decimal) -> tuple[Decimal, Decimal]:
    values = [_amount(value) for value in raw_values]
    candidates = [values]
    if currency == "INR":
        corrected = [
            value[1:] if value.startswith("3") and len(value.split(".", 1)[0]) >= 3 else value
            for value in raw_values
        ]
        candidates.insert(0, [_amount(value) for value in corrected])
    for candidate in candidates:
        if len(candidate) == 2 and quantity * candidate[0] == candidate[1]:
            return candidate[0], candidate[1]
    total = candidates[0][-1]
    return total / quantity, total


def _currency(text: str) -> str:
    if re.search(r"\$|\b(?:USD|US\$)\b", text, re.IGNORECASE):
        return "USD"
    if re.search(r"€|\bEUR\b", text, re.IGNORECASE):
        return "EUR"
    if re.search(r"£|\bGBP\b", text, re.IGNORECASE):
        return "GBP"
    if re.search(r"₹|\b(?:INR|RS)\.?\b", text, re.IGNORECASE):
        return "INR"
    return "INR"


def _is_item_candidate(line: str) -> bool:
    if ":" in line or "/" in line or re.search(r"\b(?:phone|receipt|table|server|card|type|entry|time|ref|status|tip|thank|please|www)\b", line, re.IGNORECASE):
        return False
    return bool(re.search(r"[A-Za-z]{2,}", line))


def parse_ocr_text(text: str, confidence: float = 0.0) -> Bill:
    summaries: dict[str, Decimal | int] = {}
    lines: list[LineItem] = []
    confidence_fields: dict[str, FieldConfidence] = {}
    currency = _currency(text)
    table_mode = False

    for raw_line in text.splitlines():
        line = " ".join(raw_line.split()).strip()
        if not line:
            continue
        if TABLE_HEADER_PATTERN.search(line):
            table_mode = True
            continue
        if TAX_LABEL_PATTERN.search(line):
            tax_values = re.findall(MONEY, line)
            if not tax_values:
                continue
            tax_amount = _amount(tax_values[-1])
            summaries["tax"] = summaries.get("tax", Decimal("0")) + tax_amount
            confidence_fields["tax"] = FieldConfidence(value=summaries["tax"], score=confidence)
            continue

        matched_summary = False
        for field_name, pattern in SUMMARY_PATTERNS.items():
            if field_name == "tax":
                continue
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

        table_match = TABLE_ITEM_PATTERN.match(line) if table_mode else None
        table_fields: tuple[str, str, str, str] | None = None
        if table_mode and table_match:
            table_fields = table_match.groups()
        if table_mode and not table_match:
            table_row_match = TABLE_ROW_PATTERN.match(line)
            if table_row_match:
                name, quantity_text, amount_text = table_row_match.groups()
                raw_values = re.findall(r"\d[\d,]*(?:\.\d+)?", amount_text)
                if raw_values:
                    quantity_value = Decimal(quantity_text)
                    unit_price, line_total = _table_amounts(raw_values, currency, quantity_value)
                    table_fields = (name, quantity_text, str(unit_price), str(line_total))
        if table_fields:
            name, quantity, unit_price_text, total_text = table_fields
            quantity_value = Decimal(quantity)
            unit_price, line_total = _table_amounts(
                [unit_price_text, total_text], currency, quantity_value
            )
        else:
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
    return Bill(currency=currency, line_items=lines, confidence=confidence_fields, **summaries)
