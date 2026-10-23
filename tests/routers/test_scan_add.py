from fastapi.testclient import TestClient
import pytest

from tests.helpers import access_token_cookie, create_test_user
from tests.test_isbn_import import make_isbn
from ubiblio import crud
from ubiblio.database import SessionLocal
from ubiblio.routers.books import service


@pytest.fixture
def client():
    from ubiblio.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def admin(client):
    with create_test_user(is_admin=True) as user:
        with access_token_cookie(client, user):
            yield user


@pytest.fixture
def lookup(monkeypatch):
    calls = []

    def fake(isbn):
        calls.append(isbn)
        if isbn.endswith("0"):
            raise LookupError(isbn)
        return {"Title": f"Książka {isbn}", "Author": "Łucja Żak", "Summary": ""}

    monkeypatch.setattr(service, "lookup_book_metadata_by_isbn", fake)
    return calls


def isbn_ending(digit_ok):
    while True:
        isbn = make_isbn()
        if isbn.endswith("0") != digit_ok:
            return isbn


class TestScanAdd:
    def test_adds_book_with_location(self, client, admin, lookup):
        isbn = isbn_ending(True)

        r = client.post("/api/scan_add", json={"isbn": isbn, "library": "Dom", "shelf": "Regał 2", "collection": ""})

        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "added"
        assert body["title"] == f"Książka {isbn}"
        assert body["author"] == "Łucja Żak"
        db = SessionLocal()
        try:
            book = crud.getBookById(db, body["bookId"])
        finally:
            db.close()
        assert (book.ISBN, book.library, book.shelf, book.collection, book.owned) == (isbn, "Dom", "Regał 2", None, True)

    def test_second_scan_is_duplicate(self, client, admin, lookup):
        isbn = isbn_ending(True)
        first = client.post("/api/scan_add", json={"isbn": isbn}).json()

        second = client.post("/api/scan_add", json={"isbn": isbn}).json()

        assert second["status"] == "duplicate"
        assert second["bookId"] == first["bookId"]
        assert second["title"] == first["title"]
        assert lookup == [isbn]

    def test_not_found_is_saved_to_complete(self, client, admin, lookup):
        isbn = isbn_ending(False)

        body = client.post("/api/scan_add", json={"isbn": isbn}).json()

        assert body["status"] == "not_found"
        assert body["title"] == f"ISBN {isbn}"
        assert body["bookId"] is not None

    def test_invalid_isbn_is_not_looked_up(self, client, admin, lookup):
        body = client.post("/api/scan_add", json={"isbn": "5901234123457"}).json()

        assert body["status"] == "invalid"
        assert body["bookId"] is None
        assert lookup == []

    def test_unknown_fields_rejected(self, client, admin, lookup):
        r = client.post("/api/scan_add", json={"isbn": isbn_ending(True), "owned": False})

        assert r.status_code == 422

    def test_requires_admin(self, client, lookup):
        with create_test_user() as user:
            with access_token_cookie(client, user):
                r = client.post("/api/scan_add", json={"isbn": isbn_ending(True)})

        assert r.status_code == 403
        assert lookup == []

    def test_scan_page_has_continuous_mode(self, client, admin):
        r = client.get("/scan_isbn")

        assert r.status_code == 200
        assert "/api/scan_add" in r.text
        assert 'id="modeConfirm"' in r.text
