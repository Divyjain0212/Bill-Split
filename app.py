from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from tempfile import NamedTemporaryFile

import streamlit as st

from src.calculator import calculate_breakdown
from src.models import AssignmentMode, Bill, LineItem
from src.ocr import extract_text
from src.parser import parse_ocr_text

st.set_page_config(page_title="Bill Split", page_icon="₹", layout="wide")


def money_input(label: str, value: Decimal, key: str) -> Decimal:
    return Decimal(str(st.number_input(label, min_value=0.0, value=float(value), step=0.01, format="%.2f", key=key)))


def review_panel(bill: Bill, extraction_id: int) -> tuple[Bill, list[str]] | None:
    st.subheader("Review extracted bill")
    st.caption("Correct OCR fields and assign every item before confirming the bill.")
    detected_people = bill.guest_count or 2
    guest_count = int(st.number_input("Number of people", min_value=1, value=detected_people, step=1))
    st.info(f"Receipt indicates {bill.guest_count or 'an unknown number of'} guest(s). Enter the names below.")
    people = [
        st.text_input(f"Person {index + 1} name", value=f"Person {index + 1}", key=f"member_{extraction_id}_{index}").strip()
        for index in range(guest_count)
    ]
    if any(not name for name in people) or len(set(people)) != len(people):
        st.warning("Enter a different name for every person before confirming.")
        return None

    with st.form("review_bill"):
        edited_items: list[LineItem] = []
        for index, item in enumerate(bill.line_items):
            st.markdown(f"**Item {index + 1}**")
            name = st.text_input("Name", value=item.name, key=f"name_{extraction_id}_{index}")
            quantity = Decimal(str(st.number_input("Quantity", min_value=0.01, value=float(item.quantity), step=0.01, key=f"qty_{extraction_id}_{index}")))
            unit_price = money_input("Unit price", item.unit_price, key=f"unit_price_{extraction_id}_{index}")
            assignees = st.multiselect("Eaten by", people, default=[person for person in item.assigned_to if person in people], key=f"people_{extraction_id}_{index}")
            everyone = st.checkbox("Everyone", value=False, key=f"everyone_{extraction_id}_{index}")
            selected = people if everyone else assignees
            if not selected:
                st.error("Assign this item to one or more members.")
            edited_items.append(
                LineItem(
                    name=name.strip() or item.name,
                    quantity=quantity,
                    unit_price=unit_price,
                    assigned_to=selected or [people[0]],
                    assignment_mode=AssignmentMode.EVERYONE if everyone else AssignmentMode.SELECTED,
                    confidence=item.confidence,
                )
            )

        col1, col2, col3 = st.columns(3)
        with col1:
            tax = money_input("GST / tax", bill.tax, key=f"tax_{extraction_id}")
        with col2:
            service_charge = money_input("Service charge", bill.service_charge, key=f"service_charge_{extraction_id}")
        with col3:
            discount = money_input("Discount", bill.discount, key=f"discount_{extraction_id}")
        printed_total = money_input(
            "Printed total",
            bill.printed_total or bill.calculated_total,
            key=f"printed_total_{extraction_id}",
        )
        confirmed = st.form_submit_button("Confirm review and calculate", type="primary")

    if not confirmed:
        return None
    reviewed = Bill(
        currency=bill.currency,
        line_items=edited_items,
        tax=tax,
        service_charge=service_charge,
        discount=discount,
        printed_subtotal=bill.printed_subtotal,
        printed_total=printed_total,
        confidence=bill.confidence,
        review_confirmed=True,
    )
    return reviewed, people


st.title("Bill Split")
st.write("Photograph the bill, review what was read, then assign each item.")
uploaded = st.file_uploader("Upload a bill photograph", type=["jpg", "jpeg", "png", "webp"])
if st.button("Clear current extraction"):
    for key in ("bill", "raw_ocr", "breakdown", "people"):
        st.session_state.pop(key, None)
    st.session_state.extraction_id = st.session_state.get("extraction_id", 0) + 1
    st.rerun()

if uploaded and st.button("Read / replace bill", type="primary"):
    suffix = Path(uploaded.name).suffix or ".jpg"
    with NamedTemporaryFile(delete=False, suffix=suffix) as temporary_file:
        temporary_file.write(uploaded.getvalue())
        image_path = temporary_file.name
    try:
        text, confidence = extract_text(image_path)
        st.session_state.bill = parse_ocr_text(text, confidence)
        st.session_state.raw_ocr = text
        st.session_state.pop("breakdown", None)
        st.session_state.extraction_id = st.session_state.get("extraction_id", 0) + 1
    except (FileNotFoundError, ValueError) as error:
        st.error(str(error))

if "bill" in st.session_state:
    with st.expander("Raw OCR text"):
        st.text(st.session_state.raw_ocr)
    reviewed_result = review_panel(st.session_state.bill, st.session_state.get("extraction_id", 0))
    if reviewed_result:
        bill, people = reviewed_result
        st.session_state.bill = bill
        st.session_state.breakdown = calculate_breakdown(bill, people)
        st.session_state.people = people
    elif "breakdown" in st.session_state:
        st.session_state.pop("breakdown", None)

    if "breakdown" in st.session_state:
        bill = st.session_state.bill
        breakdown = st.session_state.breakdown
        st.success("Review confirmed. Tax is split equally; service charge follows consumption.")
        if bill.total_mismatch is not None and bill.total_mismatch != 0:
            st.warning(
                f"Printed total: {bill.currency} {bill.printed_total:.2f}. "
                f"Calculated total from items and tax: {bill.currency} {bill.calculated_total:.2f}. "
                f"Difference: {bill.currency} {bill.total_mismatch:.2f}."
            )
        else:
            st.info(f"Calculated total: {bill.currency} {bill.calculated_total:.2f}")
        if bill.printed_subtotal is not None and bill.printed_subtotal != bill.item_subtotal:
            st.warning(
                f"Printed subtotal: {bill.currency} {bill.printed_subtotal:.2f}. "
                f"Sum of reviewed items: {bill.currency} {bill.item_subtotal:.2f}. "
                f"Tax allocation uses the reviewed item sum."
            )
        st.caption(
            f"Reconciliation: items {bill.currency} {bill.item_subtotal:.2f} "
            f"+ tax {bill.currency} {bill.tax:.2f} "
            f"+ service charge {bill.currency} {bill.service_charge:.2f} "
            f"- discount {bill.currency} {bill.discount:.2f}"
        )
        st.subheader("What each person owes")
        for person, values in breakdown.items():
            st.metric(person, f"{bill.currency} {values['total']:.2f}")
        st.dataframe(
            [
                {
                    "Person": person,
                    "Items": f"{values['subtotal']:.2f}",
                    "GST / tax": f"{values['tax']:.2f}",
                    "Service charge": f"{values['service_charge']:.2f}",
                    "Discount": f"-{values['discount']:.2f}",
                    "Total": f"{values['total']:.2f}",
                }
                for person, values in breakdown.items()
            ],
            hide_index=True,
            use_container_width=True,
        )
