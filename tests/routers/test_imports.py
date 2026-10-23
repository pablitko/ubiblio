from fastapi.testclient import TestClient
import pytest

from tests.helpers import access_token_cookie, create_test_user
from tests.test_isbn_import import make_isbn
from ubiblio.routers.books import service


@pytest.fixture
def client(monkeypatch):
    from ubiblio.main import app

    monkeypatch.setattr("ubiblio.routers.imports.METADATA_DELAY_S", 0)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def admin(client):
    with create_test_user(is_admin=True) as user:
        with access_token_cookie(client, user):
            yield user


class TestImportIsbn:
    def test_form_requires_admin(self, client):
        with create_test_user() as user:
            with access_token_cookie(client, user):
                assert client.get("/import_isbn").status_code == 403

    def test_form(self, client, admin):
        r = client.get("/import_isbn")

        assert r.status_code == 200
        assert 'action="/import_isbn"' in r.text

    def test_import_text_and_file(self, client, admin, monkeypatch):
        a, b = make_isbn(), make_isbn()
        monkeypatch.setattr(service, "lookup_book_metadata_by_isbn",
                            lambda isbn: {"Title": f"T{isbn}", "Author": "A", "Summary": ""})

        r = client.post(
            "/import_isbn",
            data={"isbns": a, "shelf": "A1"},
            files={"file": ("list.csv", f"title,ISBN\nx,{b}\n".encode("utf-8"), "text/csv")},
            follow_redirects=False,
        )

        assert r.status_code == 303
        job_id = r.headers["location"].rsplit("/", 1)[1]
        status = client.get(f"/import_isbn/status/{job_id}").json()
        assert status["state"] == "done"
        assert status["counts"]["added"] == 2
        assert [x["title"] for x in status["results"]] == [f"T{a}", f"T{b}"]

        page = client.get(f"/import_isbn/job/{job_id}")
        assert page.status_code == 200
        report = client.get(f"/import_isbn/report/{job_id}")
        assert report.headers["content-type"].startswith("text/csv")
        assert f"T{a}" in report.text

    def test_empty_input_shows_error(self, client, admin):
        r = client.post("/import_isbn", data={"isbns": "  \n"})

        assert r.status_code == 200
        assert "No ISBNs given." in r.text

    def test_unknown_job(self, client, admin):
        assert client.get("/import_isbn/status/nope").status_code == 404


class TestToComplete:
    def test_lists_books_saved_without_metadata(self, client, admin, monkeypatch):
        isbn = make_isbn()

        def not_found(isbn):
            raise LookupError(isbn)

        monkeypatch.setattr(service, "lookup_book_metadata_by_isbn", not_found)
        client.post("/import_isbn", data={"isbns": isbn})

        r = client.get("/to_complete")

        assert r.status_code == 200
        assert f"ISBN {isbn}" in r.text
