# uBiblio – notes for Claude

Fork of https://github.com/seanboyce/ubiblio (branch `dev`), adapted for inventorying paper books (mostly Polish) and hosting on Mikrus. The full plan is in `../ubiblio-plan-wdrozenia.md`.

## Layout
- `ubiblio/main.py` – FastAPI app, creates the schema on import.
- `ubiblio/crud.py` – database access (SQLAlchemy sessions and raw `sqlite3`), schema migrations (`updateDB`, `updateDBVersion`, version in table `config`).
- `ubiblio/csv_books.py` – CSV import/export of books (header mapped by name, legacy headerless files, duplicate detection).
- `ubiblio/routers/` – `admin.py` (backups, CSV, config), `auth.py`, `files.py`, `federation.py`, `reading_lists.py`, `books/` (book pages, metadata lookup by ISBN in `service.py` and `book_metadata_client.py`).
- `ubiblio/vars.py` – environment variables, read at import time.
- `templates/` – Jinja templates; `templates/FR/` is a full French copy selected by `LANGUAGE=FR`. Change both when editing a template.
- `export/` – backups and CSV files (paths are relative to the working directory).
- `tests/` – pytest; helpers in `tests/helpers/` (`create_test_user`, `access_token_cookie`).

## Running
```
py -3 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt -r requirements-test.txt
.venv\Scripts\python -m pytest -q
```
Developed on Python 3.14 locally (upstream targets 3.10-3.12).

`tests/conftest.py` points `DB_LOCATION`, `SECRET_KEY` and the signing key files at a temp directory, so tests never touch `./sql_app.db`.

Local app (data in `config/`, which is gitignored; `openssl` is not on PATH on Windows, so set `SECRET_KEY`):
```
$env:DB_LOCATION=".\config\sql_app.db"; $env:SECRET_KEY="dev-local-only"
$env:SIGNING_KEY_FILE=".\config\sign_key.txt"; $env:VERIFY_KEY_FILE=".\config\verify_key.txt"
$env:USE_REDIS="false"; $env:CREATE_ADMIN_USER="True"; $env:ADMIN_USERNAME="admin"; $env:ADMIN_PASSWORD="admin"
.venv\Scripts\python -m uvicorn ubiblio.main:app --port 8765
```
Then open `/user-setup/` once and log in.

## Rules
1. One phase of the plan = one branch = one small PR. If anything goes upstream, say that AI was used (CONTRIBUTING.md).
2. Tests first; no real network calls in tests (mock `requests`, see `tests/routers/books/test_book_metadata_client.py`).
3. No heavy new dependencies (target ~100 MB RAM).
4. Every schema change = migration in `crud.updateDBVersion` + SQL backup before migrating + a test on a 1.0.1 database.
5. Before changing existing behaviour, add a test describing the current behaviour.
6. Stay backwards compatible: old headerless CSV exports and old `.sql` backups must still load.
7. Anything that adds books must set `owned=True`, otherwise they are invisible in search (`crud.searchBooks*` filters `owned == True`).
8. `crud.createBook` returns the strings `"True"`/`"False"` and swallows exceptions – check the result.

## CSV format
```
title,author,summary,genre,library,shelf,collection,ISBN,notes,owned,withdrawn,ebook,customField1,customField2[,withdrawnBy]
```
Only `title` is required. `owned` defaults to 1, `withdrawn` and `ebook` to 0. Booleans: `1/0/true/false/tak/nie`, case-insensitive. UTF-8 (BOM allowed). Export adds `withdrawnBy` as the last column. Duplicates: same ISBN ignoring separators, or (without ISBN) same title+author ignoring case and extra whitespace.

## ISBN and metadata
- `ubiblio/isbn.py`: `normalize_isbn` (ISBN-10/13 -> ISBN-13, checksum validated). New code stores ISBN-13 without separators; `comparable_isbn` is the duplicate-detection key.
- Metadata sources and order: `METADATA_SOURCES` (default `bn,google,openlibrary,wikipedia`); BN is moved last for ISBNs outside 978-83. Google Books runs only with `GB_API`.
- BN (`data.bn.org.pl`) matches `isbnIssn` literally and stores pre-2007 books as ISBN-10, so `bn_by_isbn` queries ISBN-13 and then ISBN-10. Real responses are in `tests/fixtures/bn/`.
- Bulk import (`/import_isbn`, `ubiblio/isbn_import.py`): background job, state in process memory (`JOBS`) – run a single worker. `METADATA_DELAY_S` (default 1.0) between lookups. Unknown books are saved as `ISBN <n>` with note `do-uzupelnienia` and listed at `/to_complete`.
- Continuous scanning: `templates/scanIsbn.html` posts each barcode to `POST /api/scan_add` (JSON, admin) without reloading; same code ignored for 3 s, EAN-13/ISBN checksum checked in the browser. The old confirm-each-book flow is the "Confirm each book" mode. The camera needs HTTPS (except on localhost).
