"""Text normalization for search: case- and diacritic-insensitive, including Polish ł."""
import unicodedata

# Letters that do not decompose under NFKD
_EXTRA = str.maketrans({"ł": "l", "Ł": "L", "đ": "d", "Đ": "D", "ø": "o", "Ø": "O"})


def normalize_text(value):
    if value is None:
        return None
    decomposed = unicodedata.normalize("NFKD", str(value).translate(_EXTRA))
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()
