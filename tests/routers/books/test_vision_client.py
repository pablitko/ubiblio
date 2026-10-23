import base64
import io
import json
from pathlib import Path

import pytest
import responses
from PIL import Image

from ubiblio.routers.books.vision_client import (
    GeminiError, GeminiQuotaExhausted, GeminiVisionClient, MAX_IMAGE_SIDE, prepare_image,
)

FIXTURES = Path(__file__).parents[2] / "fixtures" / "gemini"
KEY = "test-key-SECRET-123"


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def answer(books_json):
    """Interaction response whose model output is the given text."""
    return {"status": "completed", "steps": [{"type": "model_output", "content": [{"type": "text", "text": books_json}]}]}


def image_bytes(fmt="PNG", size=(40, 20)):
    out = io.BytesIO()
    Image.new("RGB", size, "white").save(out, format=fmt)
    return out.getvalue()


@pytest.fixture
def sleeps():
    return []


@pytest.fixture
def client(sleeps):
    return GeminiVisionClient(KEY, "gemini-test-model", max_attempts=3, backoff_s=1, sleep=sleeps.append)


class TestReadShelf:
    @responses.activate
    def test_parses_candidates(self, client):
        responses.add(responses.POST, GeminiVisionClient.API, json=fixture("shelf_ok.json"))

        books = client.read_shelf(b"jpeg")

        assert [(b.title, b.author, b.confidence) for b in books] == [
            ("Lalka", "Bolesław Prus", 0.95), ("Solaris", None, 0.7), ("Ferdydurke", "Witold Gombrowicz", 0.4)]

    @responses.activate
    def test_request_shape_and_key_only_in_header(self, client):
        responses.add(responses.POST, GeminiVisionClient.API, json=fixture("shelf_ok.json"))

        client.read_shelf(b"jpeg-bytes")

        request = responses.calls[0].request
        assert request.headers["x-goog-api-key"] == KEY
        assert KEY not in request.url
        body = json.loads(request.body)
        assert body["model"] == "gemini-test-model"
        assert body["store"] is False
        text, image = body["input"]
        assert text["type"] == "text" and "półkę" in text["text"]
        assert image == {"type": "image", "data": base64.b64encode(b"jpeg-bytes").decode(), "mime_type": "image/jpeg"}
        assert body["response_format"]["mime_type"] == "application/json"
        assert "books" in body["response_format"]["schema"]["properties"]

    @responses.activate
    def test_empty_list(self, client):
        responses.add(responses.POST, GeminiVisionClient.API, json=answer('{"books": []}'))

        assert client.read_shelf(b"x") == []

    @pytest.mark.parametrize("text", [
        "not json",
        '{"items": []}',
        '{"books": [{"title": "", "author": "", "confidence": 0.5}]}',
        '{"books": [{"title": "T", "author": "", "confidence": 1.5}]}',
        '{"books": [{"title": "T", "author": "", "confidence": 0.5, "isbn": "1"}]}',
        '{"books": [{"author": "A", "confidence": 0.5}]}',
    ])
    @responses.activate
    def test_answer_not_matching_schema_is_an_error(self, client, text):
        responses.add(responses.POST, GeminiVisionClient.API, json=answer(text))

        with pytest.raises(GeminiError, match="schema"):
            client.read_shelf(b"x")

    @responses.activate
    def test_failed_interaction(self, client):
        responses.add(responses.POST, GeminiVisionClient.API, json={"status": "failed", "steps": []})

        with pytest.raises(GeminiError, match="failed"):
            client.read_shelf(b"x")


class TestRetries:
    @responses.activate
    def test_429_then_success_uses_retry_delay(self, client, sleeps):
        responses.add(responses.POST, GeminiVisionClient.API, json=fixture("quota_minute.json"), status=429)
        responses.add(responses.POST, GeminiVisionClient.API, json=fixture("shelf_ok.json"))

        assert len(client.read_shelf(b"x")) == 3
        assert sleeps == [7.0]

    @responses.activate
    def test_5xx_exponential_backoff_then_gives_up(self, client, sleeps):
        for _ in range(3):
            responses.add(responses.POST, GeminiVisionClient.API, json={"error": {"code": 503}}, status=503)

        with pytest.raises(GeminiError, match="503 after 3 attempts") as error:
            client.read_shelf(b"x")

        assert sleeps == [1, 2]
        assert KEY not in str(error.value)

    @responses.activate
    def test_daily_quota_is_not_retried(self, client, sleeps):
        responses.add(responses.POST, GeminiVisionClient.API, json=fixture("quota_daily.json"), status=429)

        with pytest.raises(GeminiQuotaExhausted):
            client.read_shelf(b"x")

        assert sleeps == []
        assert len(responses.calls) == 1

    @responses.activate
    def test_client_error_is_not_retried(self, client):
        responses.add(responses.POST, GeminiVisionClient.API, json={"error": {"code": 400, "message": "API key not valid"}}, status=400)

        with pytest.raises(GeminiError, match="400"):
            client.read_shelf(b"x")

        assert len(responses.calls) == 1


class TestPrepareImage:
    def test_converts_to_jpeg_and_shrinks(self):
        data = prepare_image(image_bytes("PNG", (4000, 1000)))

        with Image.open(io.BytesIO(data)) as img:
            assert img.format == "JPEG"
            assert img.size == (MAX_IMAGE_SIDE, 400)

    def test_small_image_kept_in_size(self):
        with Image.open(io.BytesIO(prepare_image(image_bytes("WEBP", (300, 200))))) as img:
            assert img.size == (300, 200)

    def test_not_an_image(self):
        with pytest.raises(ValueError):
            prepare_image(b"%PDF-1.4 not an image")
