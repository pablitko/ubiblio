import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from tools import make_pl_templates
from ubiblio import messages

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"


def english_templates():
    return sorted(p.name for p in TEMPLATES.glob("*.html"))


class TestPolishTemplates:
    @pytest.mark.parametrize("name", english_templates())
    def test_every_template_has_a_polish_copy_that_is_up_to_date(self, name):
        missing = set()
        expected = make_pl_templates.translate_file(TEMPLATES / name, missing)

        actual = (TEMPLATES / "PL" / name).read_text(encoding="utf-8")

        assert missing == set(), f"untranslated strings: {missing}"
        assert actual.replace("\r\n", "\n") == expected.replace("\r\n", "\n"), \
            "templates/PL is out of date: run python tools/make_pl_templates.py"

    def test_functional_attribute_values_are_not_translated(self):
        scan = (TEMPLATES / "PL" / "scanIsbn.html").read_text(encoding="utf-8")
        config = (TEMPLATES / "PL" / "config.html").read_text(encoding="utf-8")

        assert 'value="continuous"' in scan and 'value="confirm"' in scan
        assert '<option value="True">Tak</option>' in config
        assert "{{ config.version }}" in config


class TestMessages:
    def test_english_by_default(self, monkeypatch):
        monkeypatch.setattr(messages, "LANGUAGE", "")
        assert messages._("No ISBNs given.") == "No ISBNs given."

    def test_polish_with_placeholders(self, monkeypatch):
        monkeypatch.setattr(messages, "LANGUAGE", "PL")
        assert messages._("No ISBNs given.") == "Nie podano żadnego numeru ISBN."
        assert messages._("Too many photos ({count}); the limit is {limit}.", count=30, limit=20) == \
            "Za dużo zdjęć (30); limit to 20."

    def test_unknown_message_falls_back_to_english(self, monkeypatch):
        monkeypatch.setattr(messages, "LANGUAGE", "PL")
        assert messages._("Something new {x}", x=1) == "Something new 1"


APP_CHECK = textwrap.dedent("""
    import os, sys, tempfile
    os.environ.update(LANGUAGE="PL", USE_REDIS="false", SECRET_KEY="x",
                      DB_LOCATION=os.path.join(tempfile.mkdtemp(), "pl.db"),
                      SIGNING_KEY_FILE=os.path.join(tempfile.mkdtemp(), "s.txt"),
                      VERIFY_KEY_FILE=os.path.join(tempfile.mkdtemp(), "v.txt"))
    sys.path.insert(0, ".")
    from fastapi.testclient import TestClient
    from ubiblio.main import app
    from ubiblio import crud
    from ubiblio.database import SessionLocal
    from tests.helpers import access_token_cookie, create_test_user
    db = SessionLocal(); crud.initConfig(db); db.close()
    with TestClient(app) as client:
        assert "Zaloguj" in client.get("/").text
        with create_test_user(is_admin=True) as user, access_token_cookie(client, user):
            pages = {"/searchbooks": "Szukaj", "/scan_isbn": "Skanowanie ISBN", "/import_isbn": "Import książek po ISBN",
                     "/backups": "Kopie zapasowe", "/config": "Ustawienia biblioteki", "/import_photos": "Import ze zdjęć"}
            for url, text in pages.items():
                r = client.get(url)
                assert r.status_code == 200, (url, r.status_code)
                assert text in r.text, url
            r = client.post("/import_isbn", data={"isbns": ""})
            assert "Nie podano żadnego numeru ISBN." in r.text
    print("OK")
""")


def test_app_runs_in_polish():
    result = subprocess.run([sys.executable, "-c", APP_CHECK], cwd=ROOT, capture_output=True, text=True,
                            encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=120)

    assert result.returncode == 0, result.stderr[-3000:]
    assert result.stdout.strip().endswith("OK")
