"""Turn an uploaded file (untrusted) into brief text with honest page boundaries."""

from __future__ import annotations

import io
from email import policy
from email.parser import BytesParser

from .errors import DomainError

MAX_BYTES = 5 * 1024 * 1024
MAX_PAGES = 30
ALLOWED = {".pdf": "application/pdf", ".txt": "text/plain", ".md": "text/markdown", ".eml": "message/rfc822"}


def _ext(filename: str) -> str:
    name = filename.lower()
    return name[name.rfind("."):] if "." in name else ""


def parse(filename: str, data: bytes) -> tuple[str, list[int], int, str]:
    """Return (text, page_breaks, pages, mime). page_breaks are char offsets where pages 2..n start."""
    ext = _ext(filename)
    if ext not in ALLOWED:
        raise DomainError(422, "UNSUPPORTED_FILE", "Upload a .pdf, .eml, .txt or .md file.", {"field": "file"})
    if len(data) == 0:
        raise DomainError(422, "EMPTY_FILE", "The file is empty.", {"field": "file"})
    if len(data) > MAX_BYTES:
        raise DomainError(422, "FILE_TOO_LARGE", "Files must be 5 MB or smaller.", {"field": "file"})
    if ext == ".pdf":
        if not data.startswith(b"%PDF"):
            raise DomainError(422, "UNSUPPORTED_FILE", "This file is not a valid PDF.", {"field": "file"})
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError

        try:
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                raise DomainError(422, "ENCRYPTED_PDF", "Password-protected PDFs are not supported.", {"field": "file"})
            if len(reader.pages) > MAX_PAGES:
                raise DomainError(422, "TOO_MANY_PAGES", f"PDFs are limited to {MAX_PAGES} pages.", {"field": "file"})
            pages = [(p.extract_text() or "").strip() for p in reader.pages]
        except PdfReadError as e:
            raise DomainError(422, "UNREADABLE_PDF", "The PDF could not be read. Re-export it or paste the text.",
                              {"field": "file"}) from e
        text, breaks = "", []
        for i, page in enumerate(pages):
            if i:
                text += "\n\n"
                breaks.append(len(text))
            text += page
        if len(text.strip()) < 20:
            raise DomainError(422, "NO_TEXT", "No extractable text — this looks like a scanned PDF. Scanned PDFs are "
                              "not supported; paste the text instead.", {"field": "file"})
        return text, breaks, len(pages), ALLOWED[ext]
    if ext == ".eml":
        msg = BytesParser(policy=policy.default).parsebytes(data)
        body = msg.get_body(preferencelist=("plain",))
        if body is None:
            raise DomainError(422, "NO_TEXT", "The email has no plain-text body.", {"field": "file"})
        text = f"Subject: {msg.get('subject', '')}\nFrom: {msg.get('from', '')}\nDate: {msg.get('date', '')}\n\n"
        text += body.get_content().strip()
        return text, [], 1, ALLOWED[ext]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    if len(text.strip()) < 20:
        raise DomainError(422, "NO_TEXT", "The file has too little text to analyse.", {"field": "file"})
    return text, [], 1, ALLOWED[ext]
