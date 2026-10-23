from urllib.parse import urlencode

import pytest
import responses

from ubiblio.routers.books import service
from ubiblio.routers.books.book_metadata_client import BookMetadataClient


@pytest.fixture
def google_key(monkeypatch):
    monkeypatch.setattr("ubiblio.routers.books.book_metadata_client.GOOGLE_BOOKS_API_KEY", "k")


def google_url(isbn):
    return f"{BookMetadataClient.GOOGLE_BOOKS_API}?{urlencode({'q': f'+isbn:{isbn}', 'key': 'k'})}"


class TestGoogleBooksFixes:
    @responses.activate
    def test_no_items_is_not_found_instead_of_key_error(self, google_key):
        responses.add(responses.GET, google_url("9788377792094"), json={"kind": "books#volumes", "totalItems": 0})

        assert BookMetadataClient().google_books_by_isbn("9788377792094") == ({}, 404)

    @responses.activate
    def test_all_authors_joined(self, google_key):
        responses.add(responses.GET, google_url("9788377792094"), json={
            "items": [{"volumeInfo": {"title": "T", "authors": ["Anna Nowak", "Jan Kowalski"]}}]})

        book, _ = BookMetadataClient().google_books_by_isbn("9788377792094")

        assert book["Author"] == "Anna Nowak; Jan Kowalski"


class TestOpenLibraryFixes:
    @responses.activate
    def test_unknown_isbn_is_not_found(self):
        responses.add(responses.GET, f"{BookMetadataClient.OPEN_LIBRARY_API}/api/books", json={})

        assert BookMetadataClient().open_library_by_isbn("9788377792094") == ({}, 404)

    @responses.activate
    def test_all_authors_and_plain_string_description(self):
        isbn = "9788377792094"
        responses.add(responses.GET, f"{BookMetadataClient.OPEN_LIBRARY_API}/api/books", json={
            isbn: {"details": {"title": "T", "description": "Opis", "authors": [{"name": "A"}, {"name": "B"}]}}})

        book, status = BookMetadataClient().open_library_by_isbn(isbn)

        assert status == 200
        assert book == {"Title": "T", "Author": "A; B", "Summary": "Opis"}


class TestSourceOrder:
    def test_default_order_for_polish_isbn(self):
        assert service.metadata_source_order("9788377792094", ["bn", "google", "openlibrary", "wikipedia"]) == [
            "bn", "google", "openlibrary", "wikipedia"]

    def test_bn_last_for_foreign_isbn(self):
        assert service.metadata_source_order("9780306406157", ["bn", "google", "openlibrary"]) == [
            "google", "openlibrary", "bn"]

    def test_unknown_sources_ignored(self):
        assert service.metadata_source_order("9788377792094", ["nope", "openlibrary"]) == ["openlibrary"]


class FakeClient:
    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def __getattr__(self, method):
        def call(isbn):
            self.calls.append((method, isbn))
            answer = self.answers.get(method, ({}, 404))
            if isinstance(answer, Exception):
                raise answer
            return answer
        return call


class TestLookup:
    @pytest.fixture
    def fake(self, monkeypatch):
        def install(answers, sources=("bn", "google", "openlibrary", "wikipedia")):
            client = FakeClient(answers)
            monkeypatch.setattr(service, "BookMetadataClient", lambda: client)
            monkeypatch.setattr(service, "METADATA_SOURCES", list(sources))
            return client
        return install

    def test_first_source_with_title_wins(self, fake):
        client = fake({"bn_by_isbn": ({"Title": "Lalka", "Author": "Prus", "Summary": ""}, 200),
                       "google_books_by_isbn": ({"Title": "Other", "Author": "", "Summary": ""}, 200)})

        assert service.lookup_book_metadata_by_isbn("978-83-7779-209-4")["Title"] == "Lalka"
        assert client.calls == [("bn_by_isbn", "9788377792094")]

    def test_failing_source_does_not_stop_others(self, fake):
        client = fake({"bn_by_isbn": RuntimeError("timeout"),
                       "google_books_by_isbn": ({}, 429),
                       "open_library_by_isbn": ({"Title": "Lalka", "Author": "", "Summary": ""}, 200)})

        assert service.lookup_book_metadata_by_isbn("9788377792094")["Title"] == "Lalka"
        assert [m for m, _ in client.calls] == ["bn_by_isbn", "google_books_by_isbn", "open_library_by_isbn"]

    def test_nothing_found_raises(self, fake):
        fake({})

        with pytest.raises(LookupError):
            service.lookup_book_metadata_by_isbn("9788377792094")

    def test_isbn10_is_normalized_before_lookup(self, fake):
        client = fake({"bn_by_isbn": ({"Title": "Solaris", "Author": "", "Summary": ""}, 200)})

        service.lookup_book_metadata_by_isbn("83-08-02534-X")

        assert client.calls == [("bn_by_isbn", "9788308025345")]
