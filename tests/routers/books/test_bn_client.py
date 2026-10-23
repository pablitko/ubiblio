import json
from pathlib import Path
from urllib.parse import urlencode

import responses

from ubiblio.isbn import isbn13_to_10

from ubiblio.routers.books.book_metadata_client import BookMetadataClient, parse_bn_marc

FIXTURES = Path(__file__).parents[2] / "fixtures" / "bn"


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def bn_url(isbn):
    return f"{BookMetadataClient.BN_API}?{urlencode({'isbnIssn': isbn, 'limit': 1})}"


class TestBnByIsbn:
    @responses.activate
    def test_isbn13_record(self):
        responses.add(responses.GET, bn_url("9788377792094"), json=fixture("9788377792094.json"))

        book, status = BookMetadataClient().bn_by_isbn("9788377792094")

        assert status == 200
        assert book == {"Title": "Lalka", "Author": "Bolesław Prus", "Summary": ""}
        assert len(responses.calls) == 1
        assert responses.calls[0].request.headers["User-Agent"] == BookMetadataClient.USER_AGENT

    @responses.activate
    def test_falls_back_to_isbn10_for_old_books(self):
        responses.add(responses.GET, bn_url("9788308025345"), json=fixture("empty.json"))
        responses.add(responses.GET, bn_url("830802534X"), json=fixture("830802534X.json"))

        book, status = BookMetadataClient().bn_by_isbn("9788308025345")

        assert status == 200
        assert book["Title"] == "Solaris"
        assert book["Author"] == "Stanisław Lem"
        assert len(responses.calls) == 2

    @responses.activate
    def test_not_found(self):
        responses.add(responses.GET, bn_url("9788308049810"), json=fixture("empty.json"))
        responses.add(responses.GET, bn_url(isbn13_to_10("9788308049810")), json=fixture("empty.json"))

        assert BookMetadataClient().bn_by_isbn("9788308049810") == ({}, 404)

    @responses.activate
    def test_server_error(self):
        responses.add(responses.GET, bn_url("9790260000438"), status=503)

        assert BookMetadataClient().bn_by_isbn("9790260000438") == ({}, 503)


class TestParseBnMarc:
    def test_title_with_subtitle_and_several_isbd_marks(self):
        marc = {"fields": [{"245": {"subfields": [{"a": "Pan Tadeusz, czyli Ostatni zajazd na Litwie :"}, {"b": "historia szlachecka /"}, {"c": "Adam Mickiewicz."}]}}]}

        book = parse_bn_marc(marc)

        assert book["Title"] == "Pan Tadeusz, czyli Ostatni zajazd na Litwie : historia szlachecka"
        assert book["Author"] == "Adam Mickiewicz"

    def test_main_entry_preferred_over_statement(self):
        marc = {"fields": [
            {"100": {"subfields": [{"a": "Sienkiewicz, Henryk"}, {"d": "(1846-1916)"}]}},
            {"245": {"subfields": [{"a": "Quo vadis /"}, {"c": "H. Sienkiewicz ; il. J. Kowalski."}]}},
        ]}

        assert parse_bn_marc(marc)["Author"] == "Henryk Sienkiewicz"

    def test_empty_record(self):
        assert parse_bn_marc({}) == {"Title": "", "Author": "", "Summary": ""}
