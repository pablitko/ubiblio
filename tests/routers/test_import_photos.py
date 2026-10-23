import io
import re
import uuid

from fastapi.testclient import TestClient
import pytest
from PIL import Image

from tests.helpers import access_token_cookie, create_test_user
from ubiblio import models
from ubiblio.database import SessionLocal
from ubiblio.routers.books.vision_client import ShelfBook

KEY = "route-test-key-SECRET"


def png(size=(60, 30)):
    out = io.BytesIO()
    Image.new("RGB", size, "white").save(out, format="PNG")
    return out.getvalue()


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
def enabled(monkeypatch):
    monkeypatch.setattr("ubiblio.vars.GEMINI_API_KEY", KEY)
    monkeypatch.setattr("ubiblio.vars.GEMINI_MODEL", "gemini-test-model")
    monkeypatch.setattr("ubiblio.vars.PHOTO_IMPORT_DELAY_S", 0)
    monkeypatch.setattr("ubiblio.vars.PHOTO_IMPORT_MAX_IMAGES", 3)
    monkeypatch.setattr("ubiblio.vars.PHOTO_IMPORT_MAX_MB", 0.5)


@pytest.fixture
def vision(monkeypatch, enabled):
    title = f"Lalka {uuid.uuid4().hex[:8]}"
    created = []

    class Fake:
        def __init__(self, api_key, model):
            created.append((api_key, model))

        def read_shelf(self, jpeg):
            return [ShelfBook(title=title, author="Bolesław Prus", confidence=0.9)]

    monkeypatch.setattr("ubiblio.routers.imports.GeminiVisionClient", Fake)
    return title, created


class TestImportPhotos:
    def test_disabled_without_key(self, client, admin, monkeypatch):
        monkeypatch.setattr("ubiblio.vars.GEMINI_API_KEY", "")

        r = client.get("/import_photos")

        assert r.status_code == 200
        assert "Photo import is disabled" in r.text
        assert "GEMINI_API_KEY" in r.text

    def test_requires_admin(self, client, enabled):
        with create_test_user() as user:
            with access_token_cookie(client, user):
                assert client.get("/import_photos").status_code == 403

    def test_form_shows_privacy_warning(self, client, admin, enabled):
        r = client.get("/import_photos")

        assert "Privacy" in r.text
        assert KEY not in r.text

    def test_rejects_non_image(self, client, admin, enabled):
        r = client.post("/import_photos", files=[("files", ("doc.jpg", b"%PDF-1.4", "image/jpeg"))])

        assert "doc.jpg: not a supported image." in r.text

    def test_rejects_too_large_file(self, client, admin, enabled):
        r = client.post("/import_photos", files=[("files", ("big.jpg", b"0" * (600 * 1024), "image/jpeg"))])

        assert "big.jpg: larger than 0.5 MB." in r.text

    def test_rejects_too_many_files(self, client, admin, enabled):
        files = [("files", (f"p{i}.png", png(), "image/png")) for i in range(4)]

        r = client.post("/import_photos", files=files)

        assert "Too many photos (4); the limit is 3." in r.text

    def test_full_flow_saves_only_after_approval(self, client, admin, vision):
        title, created = vision

        r = client.post("/import_photos", files=[("files", ("shelf.png", png(), "image/png"))],
                        data={"shelf": "A1"}, follow_redirects=False)

        assert r.status_code == 303
        job_url = r.headers["location"]
        assert created == [(KEY, "gemini-test-model")]
        page = client.get(job_url)
        assert title in page.text
        assert KEY not in page.text
        db = SessionLocal()
        try:
            assert db.query(models.Book).filter(models.Book.title == title).count() == 0
        finally:
            db.close()

        index = re.search(r'name="save_(\d+)"', page.text).group(1)
        saved = client.post(f"{job_url}/save", data={f"save_{index}": "1", f"title_{index}": title,
                                                    f"author_{index}": "Bolesław Prus"})

        assert "Saved 1 book(s)." in saved.text
        db = SessionLocal()
        try:
            book = db.query(models.Book).filter(models.Book.title == title).one()
        finally:
            db.close()
        assert (book.shelf, book.owned, book.notes) == ("A1", True, "z-zdjecia, do-weryfikacji")
