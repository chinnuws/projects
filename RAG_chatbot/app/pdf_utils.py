from pypdf import PdfReader, PdfWriter
from typing import List, Optional
from io import BytesIO

def extract_text_from_pdf(file):
    reader = PdfReader(file)
    text = ' '
    for page in reader.pages:
        text = text + page.extract_text()
    return text