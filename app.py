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


def money_input(label: str, value: Decimal) -> Decimal:
    return Decimal(str(st.number_input(label, min_value=0.0, value=float(value), step=0.01, format="%.2f")))


def review_panel(bill: Bill) -> tuple[Bill, list[str]] | None:
    st.subheader("Review extracted bill")
    st.caption("Correct OCR fields and assign every item before confirming the bill.")
    detected_people = bill.guest_count or 2
    guest_count = int(st.number_input("Number of people", min_value=1, value=detected_people, step=1))
    st.info(f"Receipt indicates {bill.guest_count or 'an unknown number of'} guest(s). Enter the names below.")
    people = [
        st.text_input(f"Person {index + 1} name", value=f"Person {index + 1}", key=f"member_{index}").strip()
        for index in range(guest_count)
    ]
    if any(not name for name in people) or len(set(people)) != len(people):
        st.warning("Enter a different name for every person before confirming.")
        return None

    with st.form("review_bill"):
        edited_items: list[LineItem] = []
        for index, item in enumerate(bill.line_items):
            st.markdown(f"**Item {index + 1}**")
            name = st.text_input("Name", value=item.name, key=f"name_{index}")
            quantity = Decimal(str(st.number_input("Quantity", min_value=0.01, value=float(item.quantity), step=0.01, key=f"qty_{index}")))
            unit_price = money_input("Unit price", item.unit_price)
            assignees = st.multiselect("Eaten by", people, default=[person for person in item.assigned_to if person in people], key=f"people_{index}")
            everyone = st.checkbox("Everyone", value=False, key=f"everyone_{index}")
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
            tax = money_input("GST / tax", bill.tax)
        with col2:
            service_charge = money_input("Service charge", bill.service_charge)
        with col3:
            discount = money_input("Discount", bill.discount)
        printed_total = money_input("Printed total", bill.printed_total or bill.calculated_total)
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

if uploaded and st.button("Read bill", type="primary"):
    suffix = Path(uploaded.name).suffix or ".jpg"
    with NamedTemporaryFile(delete=False, suffix=suffix) as temporary_file:
        temporary_file.write(uploaded.getvalue())
        image_path = temporary_file.name
    try:
        text, confidence = extract_text(image_path)
        st.session_state.bill = parse_ocr_text(text, confidence)
        st.session_state.raw_ocr = text
        st.session_state.pop("breakdown", None)
    except (FileNotFoundError, ValueError) as error:
        st.error(str(error))

if "bill" in st.session_state:
    with st.expander("Raw OCR text"):
        st.text(st.session_state.raw_ocr)
    reviewed_result = review_panel(st.session_state.bill)
    if reviewed_result:
        bill, people = reviewed_result
        st.session_state.bill = bill
        st.session_state.breakdown = calculate_breakdown(bill, people)
        st.session_state.people = people

    if "breakdown" in st.session_state:
        bill = st.session_state.bill
        breakdown = st.session_state.breakdown
        st.success("Review confirmed. The calculation uses consumption-weighted charges.")
        if bill.total_mismatch is not None and bill.total_mismatch != 0:
            st.warning(f"Printed total differs from calculated total by {bill.total_mismatch:.2f}.")
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
