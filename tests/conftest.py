"""Pytest loads this before test modules so env is set before `ubiblio.vars` is imported."""
import os
import tempfile

# Rate limiting uses Redis + FastAPILimiter.init(); tests skip that unless you opt in.
os.environ["USE_REDIS"] = "false"

# Keep tests away from the real ./sql_app.db and key files. `ubiblio.vars` reads these
# at import time, so they must be set here, before anything imports the app.
_TEST_DIR = tempfile.mkdtemp(prefix="ubiblio-tests-")
os.environ.setdefault("DB_LOCATION", os.path.join(_TEST_DIR, "test.db"))
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("SIGNING_KEY_FILE", os.path.join(_TEST_DIR, "sign_key.txt"))
os.environ.setdefault("VERIFY_KEY_FILE", os.path.join(_TEST_DIR, "verify_key.txt"))


def pytest_configure(config):
    """
    Ensure the SQLite schema exists before any test runs.

    Tests that go through ``TestClient(app)`` get the schema for free because
    ``ubiblio.main`` calls ``Base.metadata.create_all`` at import time, but tests
    that exercise lower-level helpers (e.g. ``tests/dependencies/test_auth.py``)
    don't import ``ubiblio.main``. On a clean CI checkout there's no ``sql_app.db``,
    so they fail with "no such table: users". Importing the schema here is enough
    to make either path work.
    """
    from ubiblio import models
    from ubiblio.database import engine

    models.Base.metadata.create_all(bind=engine)
