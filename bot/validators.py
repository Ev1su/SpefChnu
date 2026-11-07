import re
from datetime import datetime


def validate_full_name(value: str) -> bool:
    parts = value.strip().split()
    if len(parts) < 2:
        return False
    pattern = re.compile(r"^[А-ЯІЇЄҐа-яіїєґA-Za-z'’᾽-]+(?:-[А-ЯІЇЄҐа-яіїєґA-Za-z'’᾽-]+)*$", re.UNICODE)
    return all(pattern.fullmatch(part) for part in parts)


def normalize_full_name(value: str) -> str | None:
    if not validate_full_name(value):
        return None
    def title_part(part: str) -> str:
        pieces = re.split(r"([-])", part)
        normalized = "".join((p.title() if p not in {"-"} else p) for p in pieces)
        normalized = normalized.replace("'", "'").replace("’", "’")
        return normalized
    return " ".join(title_part(part) for part in value.strip().split())


def validate_birth_date(value: str) -> bool:
    try:
        birth = datetime.strptime(value.strip(), "%d.%m.%Y").date()
    except ValueError:
        return False
    today = datetime.now().date()
    if birth > today:
        return False
    age = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
    return 16 <= age <= 35


def normalize_phone(value: str) -> str | None:
    text = value or ""
    cleaned = re.sub(r"[\s()\-]", "", text)
    if cleaned.startswith("+"):
        if not re.fullmatch(r"\+380\d{9}", cleaned):
            return None
        return cleaned
    if re.fullmatch(r"380\d{9}", cleaned):
        return "+" + cleaned
    if re.fullmatch(r"0\d{9}", cleaned):
        return "+38" + cleaned
    return None


def normalize_instagram(value: str) -> str | None:
    text = value.strip()
    text = re.sub(r"^https?://", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^www\.instagram\.com/", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^instagram\.com/", "", text, flags=re.IGNORECASE)
    text = text.lstrip("@").split("?")[0].strip("/")
    if re.fullmatch(r"[A-Za-z0-9._]{1,30}", text, re.ASCII):
        return "@" + text
    return None


def normalize_telegram(value: str) -> str | None:
    text = value.strip().lstrip("@")
    if re.fullmatch(r"[A-Za-z0-9_]{5,32}", text, re.ASCII):
        return "@" + text
    return None
