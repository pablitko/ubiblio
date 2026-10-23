from fastapi.testclient import TestClient
import pytest

from tests.helpers import access_token_cookie, create_test_user
from ubiblio import crud
from ubiblio.database import SessionLocal
from ubiblio.dependencies import authenticate_user


@pytest.fixture
def client():
    from ubiblio.main import app

    with TestClient(app) as c:
        yield c


def set_password(username, password):
    db = SessionLocal()
    try:
        assert crud.update_password(db, username, password)
    finally:
        db.close()


def post(client, user, current, new, confirm=None):
    with access_token_cookie(client, user):
        return client.post("/auth/password", data={
            "current": current, "new": new, "confirm": new if confirm is None else confirm,
        })


class TestChangePassword:
    def test_page_needs_login(self, client):
        r = client.get("/auth/password", follow_redirects=False)
        assert r.status_code == 302

    def test_page_shows_form(self, client):
        with create_test_user() as user:
            with access_token_cookie(client, user):
                r = client.get("/auth/password")
        assert r.status_code == 200
        assert 'name="current"' in r.text

    def test_changes_password(self, client):
        with create_test_user() as user:
            set_password(user.username, "stare-haslo")
            r = post(client, user, "stare-haslo", "nowe-haslo-łódź")

            assert r.status_code == 200
            assert 'style="color: green"' in r.text
            assert authenticate_user(user.username, "nowe-haslo-łódź")
            assert not authenticate_user(user.username, "stare-haslo")

    def test_non_admin_can_change_own_password(self, client):
        with create_test_user(is_admin=False) as user:
            set_password(user.username, "stare-haslo")
            post(client, user, "stare-haslo", "nowe-haslo-123")
            assert authenticate_user(user.username, "nowe-haslo-123")

    @pytest.mark.parametrize("current, new, confirm", [
        ("zle-haslo", "nowe-haslo-123", None),       # wrong current password
        ("stare-haslo", "krotkie", None),             # shorter than 8 characters
        ("stare-haslo", "nowe-haslo-123", "inne-haslo-123"),  # confirmation differs
        ("", "nowe-haslo-123", None),                 # no current password
    ])
    def test_rejected_keeps_old_password(self, client, current, new, confirm):
        with create_test_user() as user:
            set_password(user.username, "stare-haslo")
            r = post(client, user, current, new, confirm)

            assert r.status_code == 200
            assert 'style="color: red"' in r.text
            assert authenticate_user(user.username, "stare-haslo")

    def test_changes_only_own_password(self, client):
        with create_test_user() as user, create_test_user() as other:
            set_password(user.username, "stare-haslo")
            set_password(other.username, "haslo-innego")
            post(client, user, "stare-haslo", "nowe-haslo-123")
            assert authenticate_user(other.username, "haslo-innego")
