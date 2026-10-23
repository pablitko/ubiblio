import csv
import io
import os
import uuid

from fastapi.testclient import TestClient
import pytest

from tests.helpers import access_token_cookie, create_test_user
from ubiblio import csv_books


@pytest.fixture
def client():
    from ubiblio.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def export_file():
    os.makedirs("export", exist_ok=True)
    path = f"export/test_import_{uuid.uuid4().hex}.csv"
    try:
        yield path
    finally:
        if os.path.exists(path):
            os.remove(path)


class TestExportCsvDownload:
    def test_returns_csv_with_header(self, client):
        with create_test_user(is_admin=True) as user:
            with access_token_cookie(client, user):
                r = client.get("/exportcsv/download")

        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        assert "attachment" in r.headers["content-disposition"]
        header = next(csv.reader(io.StringIO(r.content.decode("utf-8"))))
        assert header == csv_books.EXPORT_COLUMNS

    def test_requires_admin(self, client):
        with create_test_user() as user:
            with access_token_cookie(client, user):
                r = client.get("/exportcsv/download")

        assert r.status_code == 403


class TestAddByCsv:
    def test_shows_import_report(self, client, export_file):
        title = f"Książka {uuid.uuid4().hex}"
        with open(export_file, "w", encoding="utf-8", newline="") as f:
            f.write(f"title,author\n{title},Autor\n{title},Autor\n,Bez tytułu\n")
        name = os.path.basename(export_file)

        with create_test_user(is_admin=True) as user:
            with access_token_cookie(client, user):
                r = client.get(f"/addByCSV/{name}")

        assert r.status_code == 200
        assert 'id="importReport"' in r.text
        assert "Added: <strong>1</strong>" in r.text
        assert "Skipped (duplicates): <strong>1</strong>" in r.text
        assert "Errors: <strong>1</strong>" in r.text
