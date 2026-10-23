import csv
import io
import sqlite3

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ubiblio import crud, csv_books, models

HEADER = ",".join(csv_books.SPEC_COLUMNS)


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "books.db"
    engine = create_engine(f"sqlite:///{path}")
    models.Base.metadata.create_all(bind=engine)
    engine.dispose()
    return str(path)


@pytest.fixture
def write_csv(tmp_path):
    def write(text, name="books.csv", encoding="utf-8"):
        path = tmp_path / name
        path.write_text(text, encoding=encoding, newline="")
        return str(path)

    return write


def fetch_books(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in conn.execute("SELECT * FROM books ORDER BY id")]
    finally:
        conn.close()


class TestImportWithHeader:
    def test_maps_columns_by_name_in_any_order(self, db_path, write_csv):
        path = write_csv("ISBN,author,title,shelf\n978-83-240-1234-5,Stanisław Lem,Solaris,A1\n")

        report = csv_books.import_csv(path, db_path)

        assert report.added == 1
        [book] = fetch_books(db_path)
        assert book["title"] == "Solaris"
        assert book["author"] == "Stanisław Lem"
        assert book["ISBN"] == "978-83-240-1234-5"
        assert book["shelf"] == "A1"

    def test_defaults_owned_true_withdrawn_and_ebook_false(self, db_path, write_csv):
        path = write_csv("title\nSolaris\n")

        csv_books.import_csv(path, db_path)

        [book] = fetch_books(db_path)
        assert (book["owned"], book["withdrawn"], book["ebook"]) == (1, 0, 0)

    def test_header_is_case_insensitive_and_strips_bom(self, db_path, write_csv):
        path = write_csv("﻿Title,AUTHOR,isbn\nSolaris,Lem,123\n")

        report = csv_books.import_csv(path, db_path)

        assert report.added == 1
        [book] = fetch_books(db_path)
        assert (book["title"], book["author"], book["ISBN"]) == ("Solaris", "Lem", "123")

    def test_reports_unknown_columns(self, db_path, write_csv):
        path = write_csv("title,rating\nSolaris,5\n")

        report = csv_books.import_csv(path, db_path)

        assert report.added == 1
        assert report.ignored_columns == ["rating"]

    def test_quoted_fields_with_commas(self, db_path, write_csv):
        path = write_csv('title,author,summary\n"Ogniem i mieczem","Sienkiewicz, Henryk","Tom 1, cz. 2"\n')

        csv_books.import_csv(path, db_path)

        [book] = fetch_books(db_path)
        assert book["author"] == "Sienkiewicz, Henryk"
        assert book["summary"] == "Tom 1, cz. 2"

    def test_polish_characters(self, db_path, write_csv):
        path = write_csv("title,author\nZażółć gęślą jaźń,Żeromski Łukasz\n")

        csv_books.import_csv(path, db_path)

        [book] = fetch_books(db_path)
        assert book["title"] == "Zażółć gęślą jaźń"
        assert book["author"] == "Żeromski Łukasz"

    def test_missing_title_is_an_error(self, db_path, write_csv):
        path = write_csv("title,author\n,Lem\nSolaris,Lem\n")

        report = csv_books.import_csv(path, db_path)

        assert report.added == 1
        assert report.errors == [(2, "missing title")]

    def test_skips_blank_lines(self, db_path, write_csv):
        path = write_csv("title\n\nSolaris\n,,\n")

        report = csv_books.import_csv(path, db_path)

        assert report.added == 1
        assert report.errors == []

    def test_non_utf8_file_is_an_error(self, db_path, write_csv):
        path = write_csv("title\nZażółć\n", encoding="cp1250")

        report = csv_books.import_csv(path, db_path)

        assert report.added == 0
        assert report.errors == [(0, "file is not UTF-8 encoded")]
        assert fetch_books(db_path) == []

    def test_imported_books_are_visible_in_search(self, db_path, write_csv):
        path = write_csv("title,author\nSolaris,Stanisław Lem\n")
        csv_books.import_csv(path, db_path)

        engine = create_engine(f"sqlite:///{db_path}")
        db = sessionmaker(bind=engine)()
        try:
            for only_ebooks, no_ebooks in [(False, False), (False, True)]:
                result, count = crud.searchBooks(db, "Solaris", "Solaris", 0, only_ebooks, no_ebooks)
                assert count == 1
                assert result[0].title == "Solaris"
        finally:
            db.close()
            engine.dispose()


class TestBooleans:
    @pytest.mark.parametrize("value, expected", [
        ("1", 1), ("0", 0), ("true", 1), ("FALSE", 0), ("Tak", 1), ("NIE", 0), (" tak ", 1),
    ])
    def test_accepted_values(self, db_path, write_csv, value, expected):
        path = write_csv(f"title,owned,withdrawn,ebook\nSolaris,{value},{value},{value}\n")

        csv_books.import_csv(path, db_path)

        [book] = fetch_books(db_path)
        assert (book["owned"], book["withdrawn"], book["ebook"]) == (expected,) * 3

    def test_invalid_value_is_an_error(self, db_path, write_csv):
        path = write_csv("title,owned\nSolaris,maybe\n")

        report = csv_books.import_csv(path, db_path)

        assert report.added == 0
        assert report.errors == [(2, "invalid boolean value 'maybe'")]


class TestDuplicates:
    def test_reimporting_same_file_adds_nothing(self, db_path, write_csv):
        path = write_csv("title,author,ISBN\nSolaris,Lem,9788324012345\nPan Tadeusz,Mickiewicz,\n")

        first = csv_books.import_csv(path, db_path)
        second = csv_books.import_csv(path, db_path)

        assert first.added == 2
        assert second.added == 0
        assert [row for row, _ in second.skipped] == [2, 3]
        assert len(fetch_books(db_path)) == 2

    def test_isbn_compared_without_separators(self, db_path, write_csv):
        path = write_csv("title,ISBN\nSolaris,978-83-240-1234-5\nSolaris (inne),9788324012345\n")

        report = csv_books.import_csv(path, db_path)

        assert report.added == 1
        assert report.skipped == [(3, "duplicate: Solaris (inne)")]

    def test_same_title_different_isbn_is_not_a_duplicate(self, db_path, write_csv):
        path = write_csv("title,author,ISBN\nSolaris,Lem,111\nSolaris,Lem,222\n")

        report = csv_books.import_csv(path, db_path)

        assert report.added == 2

    def test_without_isbn_compares_title_and_author_ignoring_case(self, db_path, write_csv):
        path = write_csv("title,author\nŻółć,Łukasz  Nowak\nżółć,łukasz nowak\nŻółć,Inny Autor\n")

        report = csv_books.import_csv(path, db_path)

        assert report.added == 2
        assert [row for row, _ in report.skipped] == [3]

    def test_without_isbn_matches_existing_book_with_isbn(self, db_path, write_csv):
        csv_books.import_csv(write_csv("title,author,ISBN\nSolaris,Lem,111\n", "a.csv"), db_path)

        report = csv_books.import_csv(write_csv("title,author\nsolaris,lem\n", "b.csv"), db_path)

        assert report.added == 0
        assert len(report.skipped) == 1


class TestLegacyHeaderless:
    def test_old_12_column_file(self, db_path, write_csv):
        path = write_csv(
            "7,Solaris,Lem,Opis,Sci-Fi,Dom,A1,Kolekcja,123,uwagi,1,0\n"
            "8,Lalka,Prus,,Classic,Dom,A2,,,,0,1\n"
        )

        report = csv_books.import_csv(path, db_path)

        assert report.added == 2
        solaris, lalka = fetch_books(db_path)
        assert (solaris["title"], solaris["author"], solaris["summary"], solaris["genre"]) == ("Solaris", "Lem", "Opis", "Sci-Fi")
        assert (solaris["library"], solaris["shelf"], solaris["collection"], solaris["ISBN"]) == ("Dom", "A1", "Kolekcja", "123")
        assert (solaris["notes"], solaris["owned"], solaris["withdrawn"]) == ("uwagi", 1, 0)
        assert (lalka["owned"], lalka["withdrawn"], lalka["ebook"]) == (0, 1, 0)

    def test_old_export_from_select_star(self, db_path, write_csv, tmp_path):
        # Produce a file the way /exportcsv did before the header was added.
        source = tmp_path / "source.db"
        engine = create_engine(f"sqlite:///{source}")
        models.Base.metadata.create_all(bind=engine)
        engine.dispose()
        conn = sqlite3.connect(source)
        conn.execute(
            "INSERT INTO books (title, author, ISBN, owned, withdrawn, withdrawnBy, ebook) "
            "VALUES ('Solaris', 'Lem', '123', 1, 1, 'Ania', 0)"
        )
        conn.commit()
        rows = conn.execute("SELECT * FROM books").fetchall()
        conn.close()
        buffer = io.StringIO()
        csv.writer(buffer).writerows(rows)
        path = write_csv(buffer.getvalue())

        report = csv_books.import_csv(path, db_path)

        assert report.added == 1
        [book] = fetch_books(db_path)
        assert (book["title"], book["author"], book["ISBN"]) == ("Solaris", "Lem", "123")
        assert (book["owned"], book["withdrawn"], book["withdrawnBy"]) == (1, 1, "Ania")


class TestExport:
    def test_header_and_round_trip(self, db_path, write_csv, tmp_path):
        source = write_csv(
            "title,author,ISBN,owned,withdrawn,ebook,customField1\n"
            '"Zażółć, gęślą",Łukasz,123,1,0,1,x\n',
            "in.csv",
        )
        csv_books.import_csv(source, db_path)

        buffer = io.StringIO(newline="")
        csv_books.export_csv(buffer, db_path)

        rows = list(csv.reader(io.StringIO(buffer.getvalue())))
        assert rows[0] == csv_books.EXPORT_COLUMNS
        exported = dict(zip(rows[0], rows[1]))
        assert exported["title"] == "Zażółć, gęślą"
        assert (exported["owned"], exported["withdrawn"], exported["ebook"]) == ("1", "0", "1")
        assert exported["customField1"] == "x"
        assert exported["summary"] == ""

        other_db = tmp_path / "other.db"
        engine = create_engine(f"sqlite:///{other_db}")
        models.Base.metadata.create_all(bind=engine)
        engine.dispose()
        report = csv_books.import_csv(write_csv(buffer.getvalue(), "out.csv"), str(other_db))
        assert report.added == 1
        assert report.ignored_columns == []
        [book] = fetch_books(str(other_db))
        assert (book["title"], book["author"], book["ebook"], book["customField1"]) == ("Zażółć, gęślą", "Łukasz", 1, "x")
