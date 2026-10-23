"""Shelf photo import: photos -> Gemini -> candidate books -> user approval -> saved books.

Nothing is written to the database until the user approves candidates (save_candidates).
Job state lives in process memory (JOBS), like isbn_import; run a single worker.
"""
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from . import crud, models, schemas
from .csv_books import _text_key
from .routers.books.vision_client import GeminiError, GeminiQuotaExhausted

PHOTO_NOTE = "z-zdjecia, do-weryfikacji"


@dataclass
class PhotoJob:
    id: str
    images: list  # prepared JPEG bytes; an entry is set to None once processed
    names: list
    library: str = ""
    shelf: str = ""
    collection: str = ""
    state: str = "queued"  # queued, running, paused, done, failed
    next_index: int = 0
    candidates: list = field(default_factory=list)
    photo_errors: list = field(default_factory=list)  # (photo number, message)
    resume_after: datetime | None = None
    created: datetime = field(default_factory=datetime.now)

    @property
    def total(self):
        return len(self.names)

    def to_dict(self):
        return {
            "id": self.id,
            "state": self.state,
            "total": self.total,
            "done": self.next_index,
            "candidates": len(self.candidates),
            "errors": [list(e) for e in self.photo_errors],
            "resumeAfter": self.resume_after.isoformat() if self.resume_after else None,
        }


JOBS: dict[str, PhotoJob] = {}


def next_pacific_midnight(now: datetime | None = None) -> datetime:
    """Gemini free-tier daily quotas reset at midnight Pacific time."""
    try:
        pacific = ZoneInfo("America/Los_Angeles")
    except ZoneInfoNotFoundError:
        # No tz database (Windows without tzdata, minimal images): standard time is close enough.
        pacific = timezone(timedelta(hours=-8))
    now = (now or datetime.now(timezone.utc)).astimezone(pacific)
    return datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), tzinfo=pacific)


def create_job(images: list[bytes], names: list[str], library="", shelf="", collection="") -> PhotoJob:
    job = PhotoJob(id=uuid.uuid4().hex, images=list(images), names=list(names),
                   library=library, shelf=shelf, collection=collection)
    JOBS[job.id] = job
    return job


def existing_titles(db: Session) -> dict:
    """Normalized title -> (book id, title, author), to flag possible duplicates."""
    titles = {}
    for book_id, title, author in db.query(models.Book.id, models.Book.title, models.Book.author):
        titles.setdefault(_text_key(title), (book_id, title, author))
    return titles


def run_job(job: PhotoJob, client, session_factory, delay: float = 0.0, sleep=time.sleep):
    """Send the remaining photos to Gemini one by one. A daily quota error pauses the job."""
    job.state = "running"
    job.resume_after = None
    db = session_factory()
    try:
        titles = existing_titles(db)
    finally:
        db.close()
    try:
        while job.next_index < job.total:
            index = job.next_index
            try:
                books = client.read_shelf(job.images[index])
            except GeminiQuotaExhausted:
                job.state = "paused"
                job.resume_after = next_pacific_midnight()
                return
            except GeminiError as e:
                job.photo_errors.append((index + 1, str(e)))
                books = []
            for book in books:
                duplicate = titles.get(_text_key(book.title))
                job.candidates.append({
                    "index": len(job.candidates),
                    "photo": index + 1,
                    "title": book.title,
                    "author": book.author or "",
                    "confidence": round(book.confidence, 2),
                    "duplicateOf": duplicate[0] if duplicate else None,
                    "duplicateTitle": f"{duplicate[1]} ({duplicate[2] or ''})" if duplicate else "",
                    "bookId": None,
                })
            job.images[index] = None
            job.next_index = index + 1
            if delay and job.next_index < job.total:
                sleep(delay)
        job.state = "done"
    except Exception as e:
        print(e)
        job.state = "failed"


def save_candidates(db: Session, job: PhotoJob, approved: dict[int, tuple[str, str]]) -> int:
    """Save approved candidates {index: (title, author)} with owned=True and PHOTO_NOTE. Returns the count."""
    saved = 0
    for index, (title, author) in sorted(approved.items()):
        if index < 0 or index >= len(job.candidates):
            continue
        candidate = job.candidates[index]
        title = title.strip()
        if candidate["bookId"] is not None or not title:
            continue
        new_book = schemas.BookCreate(
            title=title,
            author=author.strip() or None,
            library=job.library or None,
            shelf=job.shelf or None,
            collection=job.collection or None,
            notes=PHOTO_NOTE,
            owned=True,
            withdrawn=False,
            ebook=False,
        )
        if crud.createBook(db, new_book) != "True":
            continue
        candidate["bookId"] = (db.query(models.Book.id)
                               .filter(models.Book.title == new_book.title, models.Book.notes == PHOTO_NOTE)
                               .order_by(models.Book.id.desc()).scalar())
        candidate["title"], candidate["author"] = new_book.title, new_book.author or ""
        saved += 1
    return saved
