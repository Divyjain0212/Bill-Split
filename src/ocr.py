from __future__ import annotations

import os
from pathlib import Path

import cv2
import pytesseract
from PIL import Image
from pytesseract import Output

DEFAULT_TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def configure_tesseract() -> str:
    command = os.getenv("BILL_SPLIT_TESSERACT_CMD", DEFAULT_TESSERACT_PATH)
    pytesseract.pytesseract.tesseract_cmd = command
    if not Path(command).exists():
        raise FileNotFoundError(
            f"Tesseract was not found at {command}. Install Tesseract OCR or set BILL_SPLIT_TESSERACT_CMD."
        )
    return command


def preprocess_image(image_path: str | Path):
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError(f"Could not read image: {image_path}")
    grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(grayscale, None, 10, 7, 21)
    return cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]


def extract_text(image_path: str | Path) -> tuple[str, float]:
    configure_tesseract()
    processed = preprocess_image(image_path)
    data = pytesseract.image_to_data(processed, output_type=Output.DICT, config="--psm 6")
    words = [text.strip() for text in data["text"] if text.strip()]
    confidences = [float(value) for value, text in zip(data["conf"], data["text"]) if text.strip() and float(value) >= 0]
    average_confidence = sum(confidences) / len(confidences) / 100 if confidences else 0.0
    return " ".join(words), average_confidence
