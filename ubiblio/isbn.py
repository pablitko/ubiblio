"""ISBN normalization: everything is stored and compared as ISBN-13 without separators."""
import re


def _isbn10_valid(digits):
    total = sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(digits))
    return total % 11 == 0


def _isbn13_check_digit(first12):
    total = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(first12))
    return str((10 - total % 10) % 10)


def normalize_isbn(raw):
    """Return the ISBN-13 for `raw` (ISBN-10 or ISBN-13, with or without separators).

    Raises ValueError for anything that is not a valid ISBN.
    """
    digits = re.sub(r"[\s\-]", "", (raw or "")).upper()
    if re.fullmatch(r"\d{9}[\dX]", digits):
        if not _isbn10_valid(digits):
            raise ValueError(f"invalid ISBN-10 checksum: {raw!r}")
        first12 = "978" + digits[:9]
        return first12 + _isbn13_check_digit(first12)
    if re.fullmatch(r"\d{13}", digits):
        if not digits.startswith(("978", "979")):
            raise ValueError(f"not an ISBN (EAN-13 without 978/979 prefix): {raw!r}")
        if _isbn13_check_digit(digits[:12]) != digits[12]:
            raise ValueError(f"invalid ISBN-13 checksum: {raw!r}")
        return digits
    raise ValueError(f"not an ISBN: {raw!r}")


def isbn13_to_10(isbn13):
    """ISBN-10 form of a 978-prefixed ISBN-13, or None (979 has no ISBN-10)."""
    if not isbn13.startswith("978"):
        return None
    body = isbn13[3:12]
    check = (11 - sum((10 - i) * int(c) for i, c in enumerate(body)) % 11) % 11
    return body + ("X" if check == 10 else str(check))


def comparable_isbn(raw):
    """Key for duplicate detection: ISBN-13 when valid, else the raw value without separators."""
    try:
        return normalize_isbn(raw)
    except ValueError:
        return re.sub(r"[^0-9X]", "", (raw or "").upper())
