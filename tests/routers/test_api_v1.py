import logging
import uuid

from fastapi.testclient import TestClient
import pytest

from tests.helpers import access_token_cookie, create_test_user
from tests.test_isbn_import import make_isbn
from ubiblio import api_tokens, crud, models, schemas
from ubiblio.database import SessionLocal
from ubiblio.routers import api_v1
from ubiblio.routers.books import service


@pytest.fixture
def client():
    from ubiblio.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def make_token():
    created = []

    def make(scope="read"):
        with create_test_user(is_admin=True) as user:
            db = SessionLocal()
            try:
                row, token = api_tokens.create_token(db, f"test-{scope}", scope, user.id)
                created.append(row.id)
            finally:
                db.close()
        return {"Authorization": f"Bearer {token}"}, row.id, token

    return make


@pytest.fixture
def books():
    """A shelf of books with a unique name, so tests do not see each other's data."""
    shelf = f"Regał {uuid.uuid4().hex[:6]}"
    tag = uuid.uuid4().hex[:6]
    titles = [f"Łódź {tag}", f"Solaris {tag}", f"Żółć {tag}", f"Lalka {tag}"]
    db = SessionLocal()
    try:
        for i, title in enumerate(titles):
            crud.createBook(db, schemas.BookCreate(title=title, author="Stanisław Lem" if i == 1 else "Anna Nowak",
                                                   shelf=shelf, owned=True, summary="Opis"))
        crud.createBook(db, schemas.BookCreate(title=f"Życzenie {tag}", shelf=shelf, owned=False))
    finally:
        db.close()
    return {"shelf": shelf, "tag": tag, "titles": titles}


class TestAuth:
    def test_missing_token(self, client):
        r = client.get("/api/v1/books")

        assert r.status_code == 401
        assert r.headers["www-authenticate"] == "Bearer"

    def test_wrong_token(self, client):
        assert client.get("/api/v1/books", headers={"Authorization": "Bearer ubt_nope"}).status_code == 401

    def test_cookie_login_is_not_accepted(self, client):
        with create_test_user(is_admin=True) as user:
            with access_token_cookie(client, user):
                assert client.get("/api/v1/books").status_code == 401

    def test_read_token_cannot_write(self, client, make_token, books):
        headers, _, _ = make_token("read")

        assert client.get("/api/v1/books", headers=headers).status_code == 200
        r = client.post("/api/v1/books", headers=headers, json={"title": "X"})
        assert r.status_code == 403
        assert client.patch("/api/v1/books/1", headers=headers, json={"shelf": "B"}).status_code == 403

    def test_revoked_token_stops_working_immediately(self, client, make_token):
        headers, token_id, _ = make_token("write")
        assert client.get("/api/v1/stats", headers=headers).status_code == 200

        db = SessionLocal()
        try:
            api_tokens.revoke_token(db, token_id)
        finally:
            db.close()

        assert client.get("/api/v1/stats", headers=headers).status_code == 401

    def test_only_the_hash_is_stored(self, make_token):
        _, token_id, token = make_token()
        db = SessionLocal()
        try:
            row = db.get(models.apiToken, token_id)
        finally:
            db.close()
        assert row.tokenHash == api_tokens.hash_token(token)
        assert token not in row.tokenHash

    def test_rate_limit(self, client, make_token, monkeypatch):
        monkeypatch.setattr(api_v1, "API_RATE_LIMIT_PER_MIN", 2)
        headers, _, _ = make_token()

        codes = [client.get("/api/v1/stats", headers=headers).status_code for _ in range(3)]

        assert codes == [200, 200, 429]

    def test_calls_are_logged_without_the_token(self, client, make_token, caplog):
        headers, _, token = make_token()

        with caplog.at_level(logging.INFO, logger="ubiblio.api"):
            client.get("/api/v1/stats", headers=headers)

        assert "token=test-read GET /api/v1/stats -> 200" in caplog.text
        assert token not in caplog.text

    def test_no_delete_routes(self, client, make_token):
        headers, _, _ = make_token("write")
        paths = {(route.path, method) for route in api_v1.router.routes for method in route.methods}

        assert not [p for p in paths if p[1] == "DELETE"]
        assert client.delete("/api/v1/books/1", headers=headers).status_code == 405


class TestRead:
    def test_list_filters_and_paging(self, client, make_token, books):
        headers, _, _ = make_token()

        page = client.get("/api/v1/books", headers=headers, params={"shelf": books["shelf"], "limit": 2}).json()
        rest = client.get("/api/v1/books", headers=headers, params={"shelf": books["shelf"], "limit": 2, "offset": 2}).json()

        assert page["total"] == 4  # the wishlist book is not listed
        assert len(page["books"]) == 2 and len(rest["books"]) == 2
        assert {b["id"] for b in page["books"]}.isdisjoint({b["id"] for b in rest["books"]})
        assert "summary" not in page["books"][0]

    def test_limit_is_capped(self, client, make_token):
        headers, _, _ = make_token()

        assert client.get("/api/v1/books", headers=headers, params={"limit": 51}).status_code == 422

    @pytest.mark.parametrize("q", ["łódź", "LODZ", "żółć", "zolc"])
    def test_polish_search(self, client, make_token, books, q):
        headers, _, _ = make_token()

        r = client.get("/api/v1/books", headers=headers, params={"q": f"{q} {books['tag']}", "shelf": books["shelf"]})

        assert r.json()["total"] == 1

    def test_author_filter(self, client, make_token, books):
        headers, _, _ = make_token()

        r = client.get("/api/v1/books", headers=headers, params={"author": "stanislaw lem", "shelf": books["shelf"]})

        assert [b["title"] for b in r.json()["books"]] == [books["titles"][1]]

    def test_get_book_includes_summary(self, client, make_token, books):
        headers, _, _ = make_token()
        book_id = client.get("/api/v1/books", headers=headers, params={"shelf": books["shelf"]}).json()["books"][0]["id"]

        r = client.get(f"/api/v1/books/{book_id}", headers=headers)

        assert r.status_code == 200
        assert r.json()["summary"] == "Opis"
        assert client.get("/api/v1/books/99999999", headers=headers).status_code == 404

    def test_stats(self, client, make_token, books):
        headers, _, _ = make_token()

        body = client.get("/api/v1/stats", headers=headers).json()

        assert body["books"] >= 4
        assert {"shelf": books["shelf"], "books": 4} in body["shelves"]


class TestWrite:
    def test_create_book(self, client, make_token):
        headers, _, _ = make_token("write")
        title = f"Nowa {uuid.uuid4().hex[:6]}"

        r = client.post("/api/v1/books", headers=headers, json={"title": title, "author": "Wisława Szymborska", "pages": 120})

        assert r.status_code == 201
        assert (r.json()["title"], r.json()["owned"], r.json()["pages"]) == (title, True, 120)
        assert r.json()["dateAdded"] is not None

    def test_create_rejects_unknown_fields(self, client, make_token):
        headers, _, _ = make_token("write")

        assert client.post("/api/v1/books", headers=headers, json={"title": "X", "withdrawnBy": "ktoś"}).status_code == 422

    def test_by_isbn_is_idempotent(self, client, make_token, monkeypatch):
        headers, _, _ = make_token("write")
        isbn = make_isbn()
        monkeypatch.setattr(service, "lookup_book_metadata_by_isbn",
                            lambda i: {"Title": f"T{i}", "Author": "A", "Summary": "", "Publisher": "Znak"})

        first = client.post("/api/v1/books/by-isbn", headers=headers, json={"isbn": isbn, "shelf": "A1"})
        second = client.post("/api/v1/books/by-isbn", headers=headers, json={"isbn": isbn})

        assert first.status_code == 201 and first.json()["status"] == "added"
        assert first.json()["book"]["publisher"] == "Znak"
        assert second.status_code == 200 and second.json()["status"] == "duplicate"
        assert second.json()["book"]["id"] == first.json()["book"]["id"]

    def test_by_isbn_invalid(self, client, make_token):
        headers, _, _ = make_token("write")

        assert client.post("/api/v1/books/by-isbn", headers=headers, json={"isbn": "123"}).status_code == 422

    def test_patch_only_allowed_fields(self, client, make_token, books):
        headers, _, _ = make_token("write")
        book_id = client.get("/api/v1/books", headers=headers, params={"shelf": books["shelf"]}).json()["books"][0]["id"]

        ok = client.patch(f"/api/v1/books/{book_id}", headers=headers, json={"shelf": "Półka B", "notes": "przeniesiona"})
        bad = client.patch(f"/api/v1/books/{book_id}", headers=headers, json={"title": "Inny tytuł"})

        assert ok.status_code == 200
        assert (ok.json()["shelf"], ok.json()["notes"]) == ("Półka B", "przeniesiona")
        assert ok.json()["title"].startswith(("Łódź", "Lalka", "Solaris", "Żółć"))
        assert bad.status_code == 422

    def test_verify(self, client, make_token, books):
        headers, _, _ = make_token("write")
        book_id = client.get("/api/v1/books", headers=headers, params={"shelf": books["shelf"]}).json()["books"][0]["id"]

        r = client.post(f"/api/v1/books/{book_id}/verify", headers=headers)

        assert r.status_code == 200
        assert r.json()["lastVerified"] is not None


class TestTokenAdminPage:
    def test_create_shows_token_once_and_revoke(self, client):
        with create_test_user(is_admin=True) as user:
            with access_token_cookie(client, user):
                created = client.post("/api_tokens", data={"name": "skrypt", "scope": "write"})
                token = created.text.split('word-break: break-all;">')[1].split("</code>")[0]
                listing = client.get("/api_tokens")
        assert token.startswith("ubt_")
        assert token not in listing.text
        assert client.get("/api/v1/stats", headers={"Authorization": f"Bearer {token}"}).status_code == 200

        db = SessionLocal()
        try:
            row = db.query(models.apiToken).filter(models.apiToken.tokenHash == api_tokens.hash_token(token)).one()
        finally:
            db.close()
        with create_test_user(is_admin=True) as user:
            with access_token_cookie(client, user):
                client.post(f"/api_tokens/{row.id}/revoke")
        assert client.get("/api/v1/stats", headers={"Authorization": f"Bearer {token}"}).status_code == 401

    def test_page_requires_admin(self, client):
        with create_test_user() as user:
            with access_token_cookie(client, user):
                assert client.get("/api_tokens").status_code == 403
