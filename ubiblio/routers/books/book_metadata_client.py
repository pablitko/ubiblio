import json
import re

import requests

from ...isbn import isbn13_to_10
from ...vars import GOOGLE_BOOKS_API_KEY


class BookMetadataClient:
    GOOGLE_BOOKS_API = "https://www.googleapis.com/books/v1/volumes"
    OPEN_LIBRARY_API = "https://openlibrary.org"
    OPEN_WIKI_API = "https://en.wikipedia.org/api/rest_v1/data/citation/mediawiki/"
    BN_API = "https://data.bn.org.pl/api/institutions/bibs.json"
    USER_AGENT = "ubiblio_bot/1.0 (https://github.com/seanboyce/ubiblio;)"
    TIMEOUT = 10

    def google_books_by_isbn(self, isbn: str) -> tuple[dict[str, str], int | None]:
        if not GOOGLE_BOOKS_API_KEY:
            return {}, None
        response = requests.get(
            self.GOOGLE_BOOKS_API,
            params={"q": f"+isbn:{isbn}", "key": GOOGLE_BOOKS_API_KEY},
            timeout=self.TIMEOUT)
        if response.ok:
            items = json.loads(response.text).get("items") or []
            if not items:
                return {}, 404
            raw_book = items[0]["volumeInfo"]
            book = {}
            book["Title"] = raw_book["title"]
            book["Author"] = "; ".join(raw_book.get("authors", []))
            book["Summary"] = raw_book.get("description", "")
            _add_details(book, publisher=raw_book.get("publisher"), year=raw_book.get("publishedDate"),
                         pages=raw_book.get("pageCount"), language=raw_book.get("language"))
            return book, 200
        return {}, response.status_code

    def open_library_by_isbn(self, isbn: str) -> tuple[dict[str, str], int]:
        url = self.OPEN_LIBRARY_API + f"/api/books?bibkeys={isbn}&format=json&jscmd=details"
        headers = {
            "User-Agent": self.USER_AGENT,
            "Accept-Encoding": "gzip",
        }
        response = requests.get(url, headers=headers, timeout=self.TIMEOUT)
        if response.ok:
            data = response.json()
            entry = data.get(isbn, {})
            book_details = entry.get("details", {})
            if not book_details.get("title"):
                return {}, 404
            description = book_details.get("description", {})
            if isinstance(description, dict):
                description = description.get("value", "")
            book = {
                "Title": book_details["title"],
                "Summary": description,
            }
            authors = book_details.get("authors", [])
            book["Author"] = "; ".join(a["name"] for a in authors if "name" in a)
            languages = [l.get("key", "").rsplit("/", 1)[-1] for l in book_details.get("languages", [])]
            _add_details(book, publisher=", ".join(book_details.get("publishers", [])),
                         year=book_details.get("publish_date"), pages=book_details.get("number_of_pages"),
                         language=languages[0] if languages else None)
            return book, 200
        else:
            return {}, response.status_code

    def open_wiki_by_isbn(self, isbn: str) -> tuple[dict[str, str], int]:
        url = self.OPEN_WIKI_API + "isbn/" + str(isbn) + ".json"
        headers = {
            "User-Agent": self.USER_AGENT,
            "Accept-Encoding": "gzip",
        }
        response = requests.get(url, headers=headers, timeout=self.TIMEOUT)
        if response.ok:
            raw_book = json.loads(response.text)[0]
            book = {}
            book["Title"] = raw_book["title"]
            book["Author"] = "; ".join(
                " ".join(raw_author).strip() for raw_author in raw_book.get("author", []))
            book["Summary"] = ""
            return book, 200
        else:
            return {}, response.status_code

    def bn_by_isbn(self, isbn: str) -> tuple[dict[str, str], int]:
        """Polish National Library (data.bn.org.pl, CC0). `isbn` is a normalized ISBN-13.

        BN matches isbnIssn literally and stores older books as ISBN-10, so both forms are tried.
        """
        headers = {"User-Agent": self.USER_AGENT}
        status = 404
        for candidate in filter(None, [isbn, isbn13_to_10(isbn)]):
            response = requests.get(
                self.BN_API, params={"isbnIssn": candidate, "limit": 1},
                headers=headers, timeout=self.TIMEOUT)
            if not response.ok:
                status = response.status_code
                continue
            bibs = response.json().get("bibs") or []
            if bibs:
                book = parse_bn_marc(bibs[0].get("marc", {}))
                if book.get("Title"):
                    return book, 200
        return {}, status


def _year(value):
    match = re.search(r"(?<!\d)(1[5-9]\d\d|20\d\d)(?!\d)", str(value or ""))
    return int(match.group(1)) if match else None


def _add_details(book, publisher=None, year=None, pages=None, language=None):
    """Add Publisher/Year/Pages/Language to `book`, only for values the source actually has."""
    if publisher:
        book["Publisher"] = _strip_isbd(str(publisher))
    if _year(year):
        book["Year"] = _year(year)
    try:
        if pages and int(pages) > 0:
            book["Pages"] = int(pages)
    except (TypeError, ValueError):
        pass
    if language:
        book["Language"] = str(language).strip().lower()


def _marc_fields(marc, tag):
    return [field[tag] for field in marc.get("fields", []) if tag in field]


def _subfields(field, code):
    return [sub[code] for sub in field.get("subfields", []) if code in sub]


def _strip_isbd(text):
    """Remove trailing ISBD punctuation such as ' /', ' :', ',' and '.'."""
    return re.sub(r"[\s/:;,.=]+$", "", text).strip()


def _invert_name(name):
    """'Prus, Bolesław' -> 'Bolesław Prus'."""
    name = _strip_isbd(name)
    if "," in name:
        last, first = name.split(",", 1)
        return f"{first.strip()} {last.strip()}"
    return name


def parse_bn_marc(marc: dict) -> dict[str, str]:
    book = {"Title": "", "Author": "", "Summary": ""}
    statement = []
    for field in _marc_fields(marc, "245")[:1]:
        parts = [_strip_isbd(p) for p in _subfields(field, "a") + _subfields(field, "b")]
        book["Title"] = " : ".join(p for p in parts if p)
        statement = _subfields(field, "c")
    authors = [_invert_name(a) for f in _marc_fields(marc, "100") for a in _subfields(f, "a")]
    if not authors and statement:
        authors = [_strip_isbd(statement[0])]
    book["Author"] = "; ".join(authors)

    control = next(iter(_marc_fields(marc, "008")), "")
    publishers = [b for tag in ("264", "260") for f in _marc_fields(marc, tag) for b in _subfields(f, "b")]
    extent = [a for f in _marc_fields(marc, "300") for a in _subfields(f, "a")]
    pages = re.search(r"(\d+)\s*(?:,\s*\[\d+\]\s*)?s\.", extent[0]) if extent else None
    language = control[35:38].strip() if len(control) >= 38 else ""
    _add_details(
        book,
        publisher=publishers[0] if publishers else None,
        year=control[7:11] if len(control) >= 11 else None,
        pages=pages.group(1) if pages else None,
        language=language if language.isalpha() else None,
    )
    return book
