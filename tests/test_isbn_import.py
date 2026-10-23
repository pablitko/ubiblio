import random

import pytest

from ubiblio import crud, isbn_import, models
from ubiblio.database import SessionLocal
from ubiblio.isbn import _isbn13_check_digit


def make_isbn():
    """A random valid Polish ISBN-13, unique enough to avoid clashes in the shared test DB."""
    first12 = "97883" + "".join(random.choice("0123456789") for _ in range(7))
    return first12 + _isbn13_check_digit(first12)


def lookup_from(known):
    def lookup(isbn):
        if isbn in known:
            value = known[isbn]
            if isinstance(value, Exception):
                raise value
            return value
        raise LookupError(isbn)
    return lookup


def run(isbns, lookup, **kwargs):
    job = isbn_import.create_job(isbns, **kwargs)
    sleeps = []
    isbn_import.run_job(job, SessionLocal, lookup, delay=0.5, sleep=sleeps.append)
    return job, sleeps


def get_book(book_id):
    db = SessionLocal()
    try:
        return crud.getBookById(db, book_id)
    finally:
        db.close()


class TestParseInput:
    def test_one_per_line_skips_blanks_and_comments(self):
        assert isbn_import.parse_isbn_input("978-83-7779-209-4\n\n# półka 1\n 830802534X \n") == [
            "978-83-7779-209-4", "830802534X"]

    def test_csv_with_isbn_column(self):
        text = "title,ISBN\nLalka,9788377792094\n\"Solaris, wyd. 2\",830802534X\nbez,\n"
        assert isbn_import.parse_isbn_input(text) == ["9788377792094", "830802534X"]


class TestRunJob:
    def test_all_found(self):
        a, b = make_isbn(), make_isbn()
        lookup = lookup_from({a: {"Title": "Lalka", "Author": "Bolesław Prus", "Summary": "S"},
                              b: {"Title": "Solaris", "Author": "Stanisław Lem", "Summary": ""}})

        job, sleeps = run([a, b], lookup, library="Dom", shelf="A1", collection="Klasyka")

        assert job.state == "done"
        assert [r["status"] for r in job.results] == ["added", "added"]
        assert sleeps == [0.5]
        book = get_book(job.results[0]["bookId"])
        assert (book.title, book.author, book.ISBN) == ("Lalka", "Bolesław Prus", a)
        assert (book.library, book.shelf, book.collection) == ("Dom", "A1", "Klasyka")
        assert (book.owned, book.withdrawn, book.ebook) == (True, False, False)

    def test_unknown_books_are_saved_to_complete(self):
        isbn = make_isbn()

        job, _ = run([isbn], lookup_from({}), shelf="B2")

        [result] = job.results
        assert result["status"] == "not_found"
        book = get_book(result["bookId"])
        assert book.title == f"ISBN {isbn}"
        assert book.notes == isbn_import.TO_COMPLETE_NOTE
        assert book.shelf == "B2"
        assert book.owned is True
        db = SessionLocal()
        try:
            assert book.id in [b.id for b in isbn_import.books_to_complete(db)]
        finally:
            db.close()

    def test_lookup_failure_still_saves_the_book(self):
        isbn = make_isbn()

        job, _ = run([isbn], lookup_from({isbn: RuntimeError("boom")}))

        [result] = job.results
        assert result["status"] == "not_found"
        assert "boom" in result["error"]
        assert result["bookId"] is not None

    def test_duplicates_in_list_and_in_database(self):
        a = make_isbn()
        lookup = lookup_from({a: {"Title": "Lalka", "Author": "", "Summary": ""}})
        run([a], lookup)

        job, sleeps = run([a, a], lookup)

        assert [r["status"] for r in job.results] == ["duplicate", "duplicate"]
        assert job.results[0]["title"] == "Lalka"
        assert sleeps == []
        db = SessionLocal()
        try:
            assert db.query(models.Book).filter(models.Book.ISBN == a).count() == 1
        finally:
            db.close()

    def test_isbn10_matches_existing_isbn13(self):
        lookup = lookup_from({"9788308025345": {"Title": "Solaris", "Author": "", "Summary": ""}})
        db = SessionLocal()
        try:
            db.query(models.Book).filter(models.Book.ISBN == "9788308025345").delete()
            db.commit()
        finally:
            db.close()
        run(["9788308025345"], lookup)

        job, _ = run(["83-08-02534-X"], lookup)

        assert job.results[0]["status"] == "duplicate"

    def test_invalid_isbn(self):
        job, _ = run(["12345", "9788377792095"], lookup_from({}))

        assert [r["status"] for r in job.results] == ["invalid", "invalid"]
        assert all(r["bookId"] is None for r in job.results)

    def test_counts_and_report(self):
        a = make_isbn()
        job, _ = run([a, "bad"], lookup_from({a: {"Title": "Zażółć, gęślą", "Author": "Ł", "Summary": ""}}))

        assert job.counts() == {"added": 1, "not_found": 0, "duplicate": 0, "invalid": 1, "error": 0}
        lines = isbn_import.report_csv(job).splitlines()
        assert lines[0] == "input,isbn,status,title,author,bookId,error"
        assert lines[1].startswith(f'{a},{a},added,"Zażółć, gęślą",Ł,')
        assert lines[2].startswith("bad,,invalid,,,,")
