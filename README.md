# Bill Split

Bill Split turns a bill photograph into a reviewed, structured bill and calculates what each person owes. OCR is powered by Tesseract; no chatbot or Gemini API is used.

## Current milestone

- Pydantic models for bills, line items, confidence, and assignments
- Equal allocation of tax and consumption-weighted service charge
- Validation for incorrect printed totals
- Focused calculator tests
- Tesseract preprocessing and OCR text parsing
- Streamlit upload, review, assignment, and result workflow

## Local setup

1. Install [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) on Windows.
2. Create an environment and install dependencies:

   ```powershell
   py -m venv .venv
   .venv\Scripts\activate
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. Run the tests:

   ```powershell
   pytest
   ```

Run the application:

```powershell
streamlit run app.py
```
