import re
from typing import Optional

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"\+?\d[\d\-()\s]{8,}\d")
SSN_RE = re.compile(r"\b\d{3}-?\d{2}-?\d{4}\b")
DOB_RE = re.compile(r"\b(?:\d{1,2}[/-]){2}\d{2,4}\b")


def scrub_pii(text: str) -> str:
    scrubbed = EMAIL_RE.sub("[redacted-email]", text)
    scrubbed = PHONE_RE.sub("[redacted-phone]", scrubbed)
    scrubbed = SSN_RE.sub("[redacted-ssn]", scrubbed)
    scrubbed = DOB_RE.sub("[redacted-date]", scrubbed)
    return re.sub(r"\s+", " ", scrubbed).strip()


def normalize_phone(phone: str) -> Optional[str]:
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    if len(digits) == 10:
        return f"+1{digits}"
    if phone.startswith("+") and len(digits) >= 10:
        return f"+{digits}"
    return None


def format_display_phone(phone: Optional[str]) -> str:
    if not phone:
        return "(555) 123-4567"
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return phone
