import uuid
from datetime import datetime, timezone

from ubiblio import crud, isbn_import, models, photo_import, schemas
from ubiblio.database import SessionLocal
from ubiblio.routers.books.vision_client import GeminiError, GeminiQuotaExhausted, ShelfBook


class FakeVision:
    """Returns the prepared answer for each photo; an exception instance is raised instead."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    def read_shelf(self, jpeg):
        self.calls.append(jpeg)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def unique(title):
    return f"{title} {uuid.uuid4().hex[:8]}"


def job_for(n, **kwargs):
    return photo_import.create_job([f"img{i}".encode() for i in range(n)], [f"p{i}.jpg" for i in range(n)], **kwargs)


class TestRunJob:
    def test_collects_candidates_and_writes_nothing(self):
        title = unique("Lalka")
        job = job_for(2)
        vision = FakeVision([[ShelfBook(title=title, author="Bolesław Prus", confidence=0.9)],
                             [ShelfBook(title=unique("Solaris"), author="", confidence=0.5)]])
        sleeps = []

        photo_import.run_job(job, vision, SessionLocal, delay=3, sleep=sleeps.append)

        assert job.state == "done"
        assert [c["photo"] for c in job.candidates] == [1, 2]
        assert job.candidates[0]["title"] == title
        assert job.candidates[1]["author"] == ""
        assert sleeps == [3]
        assert job.images == [None, None]
        db = SessionLocal()
        try:
            assert db.query(models.Book).filter(models.Book.title == title).count() == 0
        finally:
            db.close()

    def test_flags_possible_duplicates(self):
        title = unique("Pan Tadeusz")
        db = SessionLocal()
        try:
            crud.createBook(db, schemas.BookCreate(title=title, author="Adam Mickiewicz", owned=True))
        finally:
            db.close()
        job = job_for(1)

        photo_import.run_job(job, FakeVision([[ShelfBook(title=title.upper(), author=None, confidence=0.8)]]), SessionLocal)

        [candidate] = job.candidates
        assert candidate["duplicateOf"] is not None
        assert "Adam Mickiewicz" in candidate["duplicateTitle"]

    def test_error_on_one_photo_does_not_stop_the_job(self):
        job = job_for(2)

        photo_import.run_job(job, FakeVision([GeminiError("answer does not match the schema"),
                                             [ShelfBook(title=unique("Quo vadis"), confidence=0.9)]]), SessionLocal)

        assert job.state == "done"
        assert job.photo_errors == [(1, "answer does not match the schema")]
        assert len(job.candidates) == 1

    def test_daily_quota_pauses_and_resume_continues(self):
        job = job_for(3)
        first = [ShelfBook(title=unique("A"), confidence=0.9)]

        photo_import.run_job(job, FakeVision([first, GeminiQuotaExhausted("daily")]), SessionLocal)

        assert job.state == "paused"
        assert job.next_index == 1
        assert job.resume_after > datetime.now(timezone.utc)
        assert job.images[1] is not None

        vision = FakeVision([[ShelfBook(title=unique("B"), confidence=0.9)], []])
        photo_import.run_job(job, vision, SessionLocal)

        assert job.state == "done"
        assert vision.calls == [b"img1", b"img2"]
        assert len(job.candidates) == 2


class TestSaveCandidates:
    def test_saves_only_approved_with_edits(self):
        job = job_for(1, library="Dom", shelf="Regał 3", collection="")
        titles = [unique("Lalka"), unique("Solaris")]
        photo_import.run_job(job, FakeVision([[ShelfBook(title=t, author="X", confidence=0.9) for t in titles]]), SessionLocal)
        edited = titles[1] + " (poprawione)"

        db = SessionLocal()
        try:
            saved = photo_import.save_candidates(db, job, {1: (edited, "Stanisław Lem"), 7: ("nope", "")})
            again = photo_import.save_candidates(db, job, {1: (edited, "Stanisław Lem")})
            assert db.query(models.Book).filter(models.Book.title == titles[0]).count() == 0
            book = db.query(models.Book).filter(models.Book.title == edited).one()
            to_complete = [b.id for b in isbn_import.books_to_complete(db)]
        finally:
            db.close()

        assert (saved, again) == (1, 0)
        assert (book.author, book.library, book.shelf, book.collection) == ("Stanisław Lem", "Dom", "Regał 3", None)
        assert (book.owned, book.notes, book.ISBN) == (True, photo_import.PHOTO_NOTE, None)
        assert job.candidates[1]["bookId"] == book.id
        assert book.id in to_complete

    def test_empty_title_is_skipped(self):
        job = job_for(1)
        photo_import.run_job(job, FakeVision([[ShelfBook(title=unique("T"), confidence=0.9)]]), SessionLocal)
        db = SessionLocal()
        try:
            assert photo_import.save_candidates(db, job, {0: ("  ", "")}) == 0
        finally:
            db.close()


def test_next_pacific_midnight():
    now = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)

    reset = photo_import.next_pacific_midnight(now)

    assert reset > now
    assert (reset - now).total_seconds() <= 24 * 3600
    assert reset.hour == 0 and reset.minute == 0
