from io import BytesIO


def extract_text_from_uploaded_file(uploaded_file) -> str:
    """Read text from a supported uploaded file."""

    name = uploaded_file.name.lower()
    content = uploaded_file.read()

    if name.endswith(".txt"):
        return content.decode("utf-8", errors="ignore")

    if name.endswith(".pdf"):
        try:
            from PyPDF2 import PdfReader

            reader = PdfReader(BytesIO(content))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception:
            return "".join(chr(byte) for byte in content if byte < 128)

    if name.endswith(".docx"):
        try:
            from docx import Document

            document = Document(BytesIO(content))
            return "\n".join(paragraph.text for paragraph in document.paragraphs)
        except Exception:
            return ""

    if name.endswith(".rtf"):
        try:
            from striprtf.striprtf import rtf_to_text

            return rtf_to_text(content.decode("utf-8", errors="ignore"))
        except Exception:
            return ""

    return ""

