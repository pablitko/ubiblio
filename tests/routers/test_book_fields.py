import uuid

from fastapi.testclient import TestClient
import pytest

from tests.helpers import access_token_cookie, create_test_user
from ubiblio import crud, models, schemas
from ubiblio.database import SessionLocal


@pytest.fixture
def client():
    from ubiblio.main import app

    db = SessionLocal()
    try:
        crud.initConfig(db)
    finally:
        db.close()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def admin(client):
    with create_test_user(is_admin=True) as user:
        with access_token_cookie(client, user):
            yield user


def find(title):
    db = SessionLocal()
    try:
        return db.query(models.Book).filter(models.Book.title == title).one()
    finally:
        db.close()


class TestNewFieldsInForms:
    def test_add_book_saves_metadata_and_date_added(self, client, admin):
        title = f"Książka {uuid.uuid4().hex[:8]}"

        r = client.post("/add_book", data={"title": title, "publisher": "Czytelnik", "publishedYear": "1984",
                                           "pages": "312", "language": "pol", "owned": "True", "withdrawn": "False"},
                        follow_redirects=False)

        assert r.status_code == 303
        book = find(title)
        assert (book.publisher, book.publishedYear, book.pages, book.language) == ("Czytelnik", 1984, 312, "pol")
        assert book.dateAdded is not None

    def test_edit_keeps_date_added_and_withdrawn_by(self, client, admin):
        title = f"Edycja {uuid.uuid4().hex[:8]}"
        db = SessionLocal()
        try:
            crud.createBook(db, schemas.BookCreate(title=title, owned=True, withdrawn=True, withdrawnBy="ania"))
        finally:
            db.close()
        book = find(title)

        client.post(f"/update_book/{book.id}", data={"title": title, "pages": "100", "owned": "True", "withdrawn": "True"})

        edited = find(title)
        assert edited.pages == 100
        assert (edited.dateAdded, edited.withdrawnBy) == (book.dateAdded, "ania")

    def test_details_page_shows_new_fields(self, client, admin):
        title = f"Szczegóły {uuid.uuid4().hex[:8]}"
        db = SessionLocal()
        try:
            crud.createBook(db, schemas.BookCreate(title=title, owned=True, publisher="Znak", publishedYear=2001))
        finally:
            db.close()

        r = client.get(f"/bookDetails/{find(title).id}")

        assert "Znak" in r.text
        assert "2001" in r.text


class TestDatabaseVersion:
    def test_new_database_is_current_version(self, client, admin):
        assert crud.getVersion() == crud.CURRENT_DB_VERSION

    def test_saving_config_does_not_change_version(self, client, admin):
        client.post("/config", data={"version": "1.0.1", "coverImages": "False", "genres": "Sci-Fi"})

        assert crud.getVersion() == crud.CURRENT_DB_VERSION
