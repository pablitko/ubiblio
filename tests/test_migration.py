"""Migration 1.0.1 -> 1.1.0, using a dump made by the upstream 1.0.1 code (tests/fixtures/db_1_0_1.sql)."""
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ubiblio import crud, models, schemas

DUMP = Path(__file__).parent / "fixtures" / "db_1_0_1.sql"
OLD_COLUMNS = ["id", "title", "author", "summary", "genre", "library", "shelf", "collection", "ISBN",
               "notes", "owned", "withdrawn", "withdrawnBy", "customField1", "customField2", "ebook"]
NEW_COLUMNS = [name for name, _ in crud.BOOK_COLUMNS_1_1_0]


@pytest.fixture
def old_db(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(DUMP.read_text(encoding="utf-8"))
    conn.close()
    monkeypatch.setattr(crud, "DB_LOCATION", str(path))
    return str(path)


def rows(path, columns):
    conn = sqlite3.connect(path)
    try:
        quoted = ", ".join(f'"{c}"' for c in columns)
        return conn.execute(f"SELECT {quoted} FROM books ORDER BY id").fetchall()
    finally:
        conn.close()


def columns(path):
    conn = sqlite3.connect(path)
    try:
        return [row[1] for row in conn.execute("PRAGMA table_info('books')")]
    finally:
        conn.close()


def session(path):
    return sessionmaker(bind=create_engine(f"sqlite:///{path}"))()


class TestMigration:
    def test_fixture_is_version_1_0_1(self, old_db):
        assert crud.getVersion() == "1.0.1"
        assert columns(old_db) == OLD_COLUMNS

    def test_adds_columns_keeps_data_and_fills_date_added(self, old_db):
        before = rows(old_db, OLD_COLUMNS)

        crud.updateDBVersion(None, "1.0.1")

        assert crud.getVersion() == crud.CURRENT_DB_VERSION == "1.1.0"
        assert columns(old_db) == OLD_COLUMNS + NEW_COLUMNS
        assert rows(old_db, OLD_COLUMNS) == before
        added = rows(old_db, ["dateAdded", "lastVerified", "publisher"])
        assert len(added) == 3
        assert all(date_added and last is None and publisher is None for date_added, last, publisher in added)

    def test_is_idempotent(self, old_db):
        crud.updateDBVersion(None, "1.0.1")
        dates = rows(old_db, ["dateAdded"])

        crud.updateDBVersion(None, "1.0.1")

        assert columns(old_db) == OLD_COLUMNS + NEW_COLUMNS
        assert rows(old_db, ["dateAdded"]) == dates

    def test_1_0_0_goes_through_all_steps(self, old_db):
        conn = sqlite3.connect(old_db)
        conn.execute("ALTER TABLE config DROP COLUMN genres")
        conn.execute("UPDATE config SET version = '1.0.0'")
        conn.commit()
        conn.close()

        crud.updateDBVersion(None, "1.0.0")

        assert crud.getVersion() == "1.1.0"
        assert "dateAdded" in columns(old_db)
        conn = sqlite3.connect(old_db)
        assert "Sci-Fi" in conn.execute("SELECT genres FROM config").fetchone()[0]
        conn.close()

    def test_orm_works_after_migration(self, old_db):
        crud.updateDBVersion(None, "1.0.1")
        db = session(old_db)
        try:
            lalka = crud.getBookById(db, 1)
            assert (lalka.title, lalka.author, lalka.dateAdded is not None) == ("Lalka", "Bolesław Prus", True)
            assert crud.createBook(db, schemas.BookCreate(title="Nowa", owned=True, publisher="PIW", publishedYear=1970, pages=320)) == "True"
            new = db.query(models.Book).filter(models.Book.title == "Nowa").one()
            assert new.dateAdded is not None
            assert (new.publisher, new.publishedYear, new.pages) == ("PIW", 1970, 320)
            result, count = crud.searchBooks(db, "Solaris", "Solaris", 0, False, False)
            assert count == 1
        finally:
            db.close()

    def test_restore_old_backup_into_new_database_then_migrate(self, tmp_path, monkeypatch):
        path = tmp_path / "new.db"
        engine = create_engine(f"sqlite:///{path}")
        models.Base.metadata.create_all(bind=engine)
        engine.dispose()
        monkeypatch.setattr(crud, "DB_LOCATION", str(path))

        crud.wipeAndRestore(str(DUMP))

        assert crud.getVersion() == "1.0.1"
        assert columns(str(path)) == OLD_COLUMNS
        crud.updateDBVersion(None, crud.getVersion())
        assert crud.getVersion() == "1.1.0"
        assert [r[0] for r in rows(str(path), ["title"])] == ["Lalka", "Solaris", "Zażółć gęślą jaźń"]


class TestBookUpdatesKeepUnlistedFields:
    """Edits merge only the given fields (previously the whole row was replaced and missing fields became NULL)."""

    @pytest.fixture
    def db(self, old_db):
        crud.updateDBVersion(None, "1.0.1")
        db = session(old_db)
        yield db
        db.close()

    def test_form_edit_keeps_withdrawn_by_and_new_fields(self, db):
        book = crud.getBookById(db, 3)
        date_added = book.dateAdded
        db.query(models.Book).filter(models.Book.id == 3).update({"publisher": "Znak"})
        db.commit()

        crud.updateBook(db, schemas.Book(id=3, title="Zażółć", owned=True, withdrawn=True))

        db.expire_all()
        book = crud.getBookById(db, 3)
        assert book.title == "Zażółć"
        assert (book.withdrawnBy, book.publisher, book.dateAdded) == ("ania", "Znak", date_added)

    def test_return_clears_withdrawn_by(self, db):
        crud.bookReturn(db, schemas.Book(id=3, title="Zażółć gęślą jaźń", withdrawn=False, withdrawnBy=None))

        db.expire_all()
        book = crud.getBookById(db, 3)
        assert (book.withdrawn, book.withdrawnBy) == (False, None)
        assert book.dateAdded is not None
