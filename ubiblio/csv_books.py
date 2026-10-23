"""CSV import and export of the books table.

Files with a header row are mapped by column name (see SPEC_COLUMNS). Files without
a header are read with the legacy layout written by older versions of /exportcsv.
"""
import csv
import re
import sqlite3
from dataclasses import dataclass, field

# Column order of the CSV specification; only `title` is required on import.
SPEC_COLUMNS = [
    "title", "author", "summary", "genre", "library", "shelf", "collection",
    "ISBN", "notes", "owned", "withdrawn", "ebook", "customField1", "customField2",
]
# withdrawnBy is not in the specification, but exporting without it would lose data.
EXPORT_COLUMNS = SPEC_COLUMNS + ["withdrawnBy"]
IMPORT_COLUMNS = EXPORT_COLUMNS + ["id"]

# Headerless files: `SELECT * FROM books` from older exports. The first 13 columns are
# the same in every schema; the order of the last three depends on whether the database
# was created fresh or migrated by crud.updateDB, so they are ignored.
LEGACY_COLUMNS = [
    "id", "title", "author", "summary", "genre", "library", "shelf", "collection",
    "ISBN", "notes", "owned", "withdrawn", "withdrawnBy",
]

BOOL_DEFAULTS = {"owned": True, "withdrawn": False, "ebook": False}
TRUE_VALUES = {"1", "true", "tak"}
FALSE_VALUES = {"0", "false", "nie"}


@dataclass
class ImportReport:
    added: int = 0
    skipped: list = field(default_factory=list)  # (row number, reason)
    errors: list = field(default_factory=list)  # (row number, reason)
    ignored_columns: list = field(default_factory=list)


def clean_isbn(value):
    """Strip separators so '978-83-240-1234-5' and '9788324012345' compare equal."""
    return re.sub(r"[^0-9X]", "", (value or "").upper())


def _text_key(value):
    return " ".join((value or "").casefold().split())


def _dedup_keys(isbn, title, author):
    """Keys a book is known under: ISBN (if any) and title+author."""
    keys = {("title_author", _text_key(title), _text_key(author))}
    if clean_isbn(isbn):
        keys.add(("isbn", clean_isbn(isbn)))
    return keys


def _lookup_key(isbn, title, author):
    """Key used to decide if an incoming row is a duplicate: ISBN when present."""
    if clean_isbn(isbn):
        return ("isbn", clean_isbn(isbn))
    return ("title_author", _text_key(title), _text_key(author))


def parse_bool(value, default):
    text = (value or "").strip().casefold()
    if text == "":
        return default
    if text in TRUE_VALUES:
        return True
    if text in FALSE_VALUES:
        return False
    raise ValueError(f"invalid boolean value {value!r}")


def _is_header(row):
    return any(cell.strip().casefold() == "title" for cell in row)


def _read_rows(f, report):
    """Yield (row number, dict) for every non-empty row of the file."""
    reader = csv.reader(f)
    first = next(reader, None)
    if first is None:
        return
    if _is_header(first):
        by_name = {name.casefold(): name for name in IMPORT_COLUMNS}
        columns = []
        for cell in first:
            name = by_name.get(cell.strip().casefold())
            if name is None and cell.strip():
                report.ignored_columns.append(cell.strip())
            columns.append(name)
        rows = reader
        start = 2
    else:
        columns = LEGACY_COLUMNS
        rows = [first, *reader]
        start = 1
    for number, row in enumerate(rows, start=start):
        if not any(cell.strip() for cell in row):
            continue
        yield number, {
            name: value.strip()
            for name, value in zip(columns, row)
            if name is not None
        }


def import_csv(filename, db_location):
    """Add books from a CSV file, skipping duplicates. Returns an ImportReport."""
    report = ImportReport()
    conn = sqlite3.connect(db_location)
    try:
        known = set()
        for isbn, title, author in conn.execute("SELECT ISBN, title, author FROM books"):
            known |= _dedup_keys(isbn, title, author)

        new_books = []
        try:
            with open(filename, "r", encoding="utf-8-sig", newline="") as f:
                for number, row in _read_rows(f, report):
                    title = row.get("title", "")
                    if not title:
                        report.errors.append((number, "missing title"))
                        continue
                    try:
                        flags = {
                            name: parse_bool(row.get(name), default)
                            for name, default in BOOL_DEFAULTS.items()
                        }
                    except ValueError as e:
                        report.errors.append((number, str(e)))
                        continue
                    isbn, author = row.get("ISBN", ""), row.get("author", "")
                    if _lookup_key(isbn, title, author) in known:
                        report.skipped.append((number, f"duplicate: {title}"))
                        continue
                    known |= _dedup_keys(isbn, title, author)
                    book = {name: row.get(name) or None for name in EXPORT_COLUMNS}
                    book.update(flags)
                    new_books.append(book)
        except UnicodeDecodeError:
            report.errors.append((0, "file is not UTF-8 encoded"))
            return report

        placeholders = ", ".join("?" for _ in EXPORT_COLUMNS)
        with conn:
            conn.executemany(
                f"INSERT INTO books ({', '.join(EXPORT_COLUMNS)}) VALUES ({placeholders})",
                [[book[name] for name in EXPORT_COLUMNS] for book in new_books],
            )
        report.added = len(new_books)
        return report
    finally:
        conn.close()


def export_csv(f, db_location):
    """Write all books to the file object `f` as CSV with a header row."""
    conn = sqlite3.connect(db_location)
    try:
        rows = conn.execute(f"SELECT {', '.join(EXPORT_COLUMNS)} FROM books ORDER BY id")
        writer = csv.writer(f)
        writer.writerow(EXPORT_COLUMNS)
        for row in rows:
            writer.writerow(
                _export_value(name, value) for name, value in zip(EXPORT_COLUMNS, row)
            )
    finally:
        conn.close()


def _export_value(name, value):
    if value is None:
        return ""
    if name in BOOL_DEFAULTS:
        try:
            return int(parse_bool(str(value), None))
        except ValueError:
            return value
    return value
