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


def _inr_candidates(value: Decimal) -> list[Decimal]:
    text = str(value)
    candidates = [value]
    if len(text.split(".", 1)[0]) >= 3 and text[0].isdigit():
        candidates.append(Decimal(text[1:]))
    return list(dict.fromkeys(candidates))


def _table_amounts(raw_values: list[str], currency: str, quantity: Decimal) -> tuple[Decimal, Decimal]:
    values = [_amount(value) for value in raw_values]
    corrected = [
        value[1:] if currency == "INR" and value[:1].isdigit() and len(value.split(".", 1)[0]) >= 3 else value
        for value in raw_values
    ]
    corrected_values = [_amount(value) for value in corrected]
    if len(values) == 2 and quantity * values[0] == values[1]:
        if values[0] >= Decimal("1000") and quantity * corrected_values[0] == corrected_values[1]:
            return corrected_values[0], corrected_values[1]
        return values[0], values[1]
    if len(corrected_values) == 2 and quantity * corrected_values[0] == corrected_values[1]:
        return corrected_values[0], corrected_values[1]
    total = corrected_values[-1] if corrected_values[-1] != values[-1] else values[-1]
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
    tax_components: list[Decimal] = []
    incomplete_table_indices: list[int] = []
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
            tax_components.append(tax_amount)
            summaries["tax"] = sum(tax_components, Decimal("0"))
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
        incomplete_table = False
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
                    incomplete_table = len(raw_values) == 1
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
        if incomplete_table:
            incomplete_table_indices.append(len(lines) - 1)

    if not lines:
        raise ValueError("No line items could be identified in the OCR text")
    printed_subtotal = summaries.get("printed_subtotal")
    printed_total = summaries.get("printed_total")
    if currency == "INR" and isinstance(printed_subtotal, Decimal):
        suspicious = [
            (index, item)
            for index, item in enumerate(lines)
            if item.subtotal >= Decimal("1000")
        ]
        if len(suspicious) == 1:
            suspicious_index, suspicious_item = suspicious[0]
            known_subtotal = sum(
                item.subtotal for index, item in enumerate(lines) if index != suspicious_index
            )
            subtotal_candidates = [
                candidate for candidate in _inr_candidates(printed_subtotal)
                if candidate >= known_subtotal and candidate - known_subtotal < Decimal("1000")
            ]
            if subtotal_candidates:
                normalized_subtotal = min(subtotal_candidates)
                suspicious_item.unit_price = (
                    normalized_subtotal - known_subtotal
                ) / suspicious_item.quantity
                summaries["printed_subtotal"] = normalized_subtotal
                printed_subtotal = normalized_subtotal
                tax_candidates = [Decimal("0")]
                for component in tax_components:
                    tax_candidates = [
                        current + candidate
                        for current in tax_candidates
                        for candidate in _inr_candidates(component)
                    ]
                if isinstance(printed_total, Decimal):
                    total_candidates = _inr_candidates(printed_total)
                    matching_tax = [
                        tax for tax in tax_candidates
                        if any(total == normalized_subtotal + tax for total in total_candidates)
                    ]
                    if matching_tax:
                        summaries["tax"] = min(matching_tax)
                        summaries["printed_total"] = normalized_subtotal + min(matching_tax)
                        printed_total = summaries["printed_total"]
    if currency == "INR" and isinstance(printed_subtotal, Decimal) and isinstance(printed_total, Decimal):
        known_subtotal = sum(
            item.subtotal for index, item in enumerate(lines) if index not in incomplete_table_indices
        )
        tax_candidates = [Decimal("0")]
        for component in tax_components:
            tax_candidates = [
                current + candidate
                for current in tax_candidates
                for candidate in _inr_candidates(component)
            ]
        consistent_values = [
            (subtotal, total, tax)
            for subtotal in _inr_candidates(printed_subtotal)
            for total in _inr_candidates(printed_total)
            for tax in tax_candidates
            if subtotal >= known_subtotal
            and total == subtotal + tax
        ]
        if consistent_values:
            normalized_subtotal, normalized_total, normalized_tax = consistent_values[0]
            summaries["printed_subtotal"] = normalized_subtotal
            summaries["printed_total"] = normalized_total
            summaries["tax"] = normalized_tax
            printed_subtotal = normalized_subtotal
    if printed_subtotal is not None and len(incomplete_table_indices) == 1:
        incomplete_index = incomplete_table_indices[0]
        known_subtotal = sum(
            item.subtotal for index, item in enumerate(lines) if index != incomplete_index
        )
        recovered_total = printed_subtotal - known_subtotal
        if recovered_total > 0:
            incomplete_item = lines[incomplete_index]
            incomplete_item.unit_price = recovered_total / incomplete_item.quantity
    if tax_components and summaries.get("printed_subtotal") is not None and summaries.get("printed_total") is not None:
        expected_tax = (
            summaries["printed_total"]
            - summaries["printed_subtotal"]
            + summaries.get("discount", Decimal("0"))
            - summaries.get("service_charge", Decimal("0"))
        )
        corrected_components = [
            Decimal(str(component)[1:])
            if currency == "INR" and str(component).split(".", 1)[0][:1].isdigit()
            and len(str(component).split(".", 1)[0]) >= 3
            else component
            for component in tax_components
        ]
        if sum(corrected_components, Decimal("0")) == expected_tax:
            summaries["tax"] = expected_tax
    if currency == "INR" and isinstance(summaries.get("printed_subtotal"), Decimal):
        suspicious = [(index, item) for index, item in enumerate(lines) if item.subtotal >= Decimal("1000")]
        if len(suspicious) == 1:
            suspicious_index, suspicious_item = suspicious[0]
            known_subtotal = sum(
                item.subtotal for index, item in enumerate(lines) if index != suspicious_index
            )
            subtotal_candidates = [
                candidate for candidate in _inr_candidates(summaries["printed_subtotal"])
                if candidate >= known_subtotal and candidate - known_subtotal < Decimal("1000")
            ]
            if subtotal_candidates:
                normalized_subtotal = min(subtotal_candidates)
                suspicious_item.unit_price = (
                    normalized_subtotal - known_subtotal
                ) / suspicious_item.quantity
                summaries["printed_subtotal"] = normalized_subtotal
                if tax_components:
                    tax_candidates = [Decimal("0")]
                    for component in tax_components:
                        tax_candidates = [
                            current + candidate
                            for current in tax_candidates
                            for candidate in _inr_candidates(component)
                        ]
                    total_candidates = _inr_candidates(summaries.get("printed_total", Decimal("0")))
                    matching_tax = [
                        tax for tax in tax_candidates
                        if any(total == normalized_subtotal + tax for total in total_candidates)
                    ]
                    if matching_tax:
                        summaries["tax"] = min(matching_tax)
                        summaries["printed_total"] = normalized_subtotal + min(matching_tax)
    return Bill(currency=currency, line_items=lines, confidence=confidence_fields, **summaries)
