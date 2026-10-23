"""Bulk import of books from a list of ISBNs, run as a background job.

Job state lives in process memory (JOBS), so the app must run with a single worker.
"""
import csv
import io
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session

from . import crud, models, schemas
from .isbn import comparable_isbn, normalize_isbn

TO_COMPLETE_NOTE = "do-uzupelnienia"
TO_VERIFY_NOTE = "do-weryfikacji"
RESULT_STATUSES = ("added", "not_found", "duplicate", "invalid", "error")


@dataclass
class ImportJob:
    id: str
    isbns: list
    library: str = ""
    shelf: str = ""
    collection: str = ""
    state: str = "queued"  # queued, running, done, failed
    results: list = field(default_factory=list)
    created: datetime = field(default_factory=datetime.now)

    @property
    def total(self):
        return len(self.isbns)

    def counts(self):
        counts = {status: 0 for status in RESULT_STATUSES}
        for result in self.results:
            counts[result["status"]] += 1
        return counts

    def to_dict(self):
        return {
            "id": self.id,
            "state": self.state,
            "total": self.total,
            "done": len(self.results),
            "counts": self.counts(),
            "results": self.results,
        }


JOBS: dict[str, ImportJob] = {}


def parse_isbn_input(text: str) -> list[str]:
    """One ISBN per line, or CSV with an ISBN column in the header. Blank lines and '#' comments are skipped."""
    lines = [line for line in (text or "").splitlines() if line.strip() and not line.strip().startswith("#")]
    if not lines:
        return []
    header = next(csv.reader([lines[0]]))
    names = [cell.strip().casefold() for cell in header]
    if len(names) > 1 and "isbn" in names:
        column = names.index("isbn")
        rows = csv.reader(io.StringIO("\n".join(lines[1:])))
        return [row[column].strip() for row in rows if len(row) > column and row[column].strip()]
    return [line.strip() for line in lines]


def existing_isbns(db: Session) -> dict[str, int]:
    """Comparable ISBN -> book id for every book in the database that has an ISBN."""
    known = {}
    for book_id, raw in db.query(models.Book.id, models.Book.ISBN).filter(models.Book.ISBN.isnot(None)):
        key = comparable_isbn(raw)
        if key:
            known.setdefault(key, book_id)
    return known


def add_book_by_isbn(db: Session, raw: str, known: dict, lookup, library="", shelf="", collection="") -> dict:
    """Normalize, skip duplicates, look up metadata and save one book (owned=True).

    `known` (from existing_isbns) is updated with the added book. Books without metadata
    are saved with a placeholder title and the TO_COMPLETE_NOTE note, so nothing is lost.
    """
    result = {"input": raw, "isbn": "", "status": "", "title": "", "author": "", "bookId": None}
    try:
        isbn = normalize_isbn(raw)
    except ValueError as e:
        result.update(status="invalid", error=str(e))
        return result
    result["isbn"] = isbn
    if isbn in known:
        existing = crud.getBookById(db, known[isbn])
        result.update(status="duplicate", bookId=known[isbn], title=getattr(existing, "title", "") or "",
                      author=getattr(existing, "author", "") or "")
        return result

    try:
        metadata = lookup(isbn)
        status = "added"
        notes = None
    except Exception as e:
        # LookupError means no source knew the book; anything else is a lookup failure.
        # Either way the book is saved so it can be completed by hand.
        if not isinstance(e, LookupError):
            result["error"] = f"lookup failed: {e}"
        metadata = {"Title": f"ISBN {isbn}", "Author": "", "Summary": ""}
        status = "not_found"
        notes = TO_COMPLETE_NOTE

    new_book = schemas.BookCreate(
        title=metadata.get("Title") or f"ISBN {isbn}",
        author=metadata.get("Author") or None,
        summary=metadata.get("Summary") or None,
        ISBN=isbn,
        library=library or None,
        shelf=shelf or None,
        collection=collection or None,
        notes=notes,
        owned=True,
        withdrawn=False,
        ebook=False,
    )
    if crud.createBook(db, new_book) != "True":
        result.update(status="error", error="could not save the book")
        return result
    book_id = db.query(models.Book.id).filter(models.Book.ISBN == isbn).order_by(models.Book.id.desc()).scalar()
    known[isbn] = book_id
    result.update(status=status, title=new_book.title, author=new_book.author or "", bookId=book_id)
    return result


def create_job(isbns: list[str], library="", shelf="", collection="") -> ImportJob:
    job = ImportJob(id=uuid.uuid4().hex, isbns=list(isbns), library=library, shelf=shelf, collection=collection)
    JOBS[job.id] = job
    return job


def run_job(job: ImportJob, session_factory, lookup, delay: float = 0.0, sleep=time.sleep):
    """Process the job's ISBNs one by one, with `delay` seconds between external lookups."""
    job.state = "running"
    db = session_factory()
    try:
        known = existing_isbns(db)
        for index, raw in enumerate(job.isbns):
            result = add_book_by_isbn(db, raw, known, lookup, job.library, job.shelf, job.collection)
            job.results.append(result)
            looked_up = result["status"] in ("added", "not_found")
            if looked_up and delay and index < len(job.isbns) - 1:
                sleep(delay)
        job.state = "done"
    except Exception as e:
        print(e)
        job.state = "failed"
    finally:
        db.close()


def report_csv(job: ImportJob) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(["input", "isbn", "status", "title", "author", "bookId", "error"])
    for r in job.results:
        writer.writerow([r["input"], r["isbn"], r["status"], r["title"], r["author"], r["bookId"] or "", r.get("error", "")])
    return buffer.getvalue()


def books_to_complete(db: Session):
    """Books saved without metadata (ISBN import) or read from shelf photos and not yet verified."""
    return (db.query(models.Book)
            .filter(or_(models.Book.notes.like(f"%{TO_COMPLETE_NOTE}%"),
                        models.Book.notes.like(f"%{TO_VERIFY_NOTE}%")))
            .order_by(models.Book.id.desc())
            .all())
