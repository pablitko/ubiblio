"""Read book spines from a shelf photo with the Gemini API (REST, no SDK).

API surface: Interactions API, POST https://generativelanguage.googleapis.com/v1beta/interactions
(checked against ai.google.dev on 2026-10-23). The model name comes from GEMINI_MODEL.
The API key is sent only in the x-goog-api-key header and never logged or returned.
"""
import base64
import io
import json
import re
import time

import requests
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

MAX_IMAGE_SIDE = 1600

PROMPT = (
    "Zdjęcie przedstawia półkę z książkami. Wypisz każdą książkę, której grzbiet jest widoczny "
    "i czytelny, w kolejności od lewej do prawej. Dla każdej podaj: title (tytuł dokładnie tak, "
    "jak jest napisany na grzbiecie), author (autor z grzbietu albo pusty napis, jeśli go nie widać) "
    "oraz confidence (pewność odczytu od 0 do 1). Nie zgaduj i nie uzupełniaj danych z pamięci. "
    "Pomiń grzbiety nieczytelne. Jeśli nie widać żadnej książki, zwróć pustą listę."
)

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "books": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "author": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["title", "author", "confidence"],
            },
        },
    },
    "required": ["books"],
}


class ShelfBook(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=500)
    author: str | None = Field(default=None, max_length=500)
    confidence: float = Field(ge=0, le=1)

    @field_validator("title", "author", mode="before")
    @classmethod
    def strip_text(cls, value):
        if isinstance(value, str):
            value = value.strip()
        return value

    @field_validator("author")
    @classmethod
    def empty_author_is_none(cls, value):
        return value or None


class ShelfReading(BaseModel):
    model_config = ConfigDict(extra="forbid")
    books: list[ShelfBook]


class GeminiError(Exception):
    """The request failed or the answer did not match the schema. Messages never contain the key."""


class GeminiQuotaExhausted(GeminiError):
    """Daily quota used up; retrying today will not help."""


def prepare_image(data: bytes) -> bytes:
    """Validate that `data` is an image and return it as a JPEG with the longer side <= MAX_IMAGE_SIDE.

    Raises ValueError for anything Pillow cannot open.
    """
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            img = ImageOps.exif_transpose(img)
            img = img.convert("RGB")
            img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
            out = io.BytesIO()
            img.save(out, format="JPEG", quality=85)
            return out.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as e:
        raise ValueError("not a supported image") from e


def _retry_delay(response) -> float | None:
    """RetryInfo.retryDelay from a Google API error body, in seconds."""
    try:
        for detail in response.json().get("error", {}).get("details", []):
            delay = detail.get("retryDelay")
            if delay:
                return float(re.sub(r"[^0-9.]", "", delay))
    except (ValueError, AttributeError):
        pass
    return None


def _is_daily_quota(response) -> bool:
    return "PerDay" in response.text


def _output_text(interaction: dict) -> str:
    texts = []
    for step in interaction.get("steps") or []:
        if step.get("type") != "model_output":
            continue
        for block in step.get("content") or []:
            if block.get("type") == "text" and block.get("text"):
                texts.append(block["text"])
    return "".join(texts)


class GeminiVisionClient:
    API = "https://generativelanguage.googleapis.com/v1beta/interactions"
    TIMEOUT = 90

    def __init__(self, api_key: str, model: str, max_attempts: int = 4, backoff_s: float = 2.0, sleep=time.sleep):
        self.api_key = api_key
        self.model = model
        self.max_attempts = max_attempts
        self.backoff_s = backoff_s
        self.sleep = sleep

    def read_shelf(self, jpeg: bytes) -> list[ShelfBook]:
        body = {
            "model": self.model,
            "store": False,
            "input": [
                {"type": "text", "text": PROMPT},
                {"type": "image", "data": base64.b64encode(jpeg).decode("ascii"), "mime_type": "image/jpeg"},
            ],
            "response_format": {"type": "text", "mime_type": "application/json", "schema": RESPONSE_SCHEMA},
        }
        interaction = self._post(body)
        if interaction.get("status") not in (None, "completed"):
            raise GeminiError(f"interaction ended with status {interaction.get('status')!r}")
        text = _output_text(interaction)
        try:
            return ShelfReading.model_validate(json.loads(text)).books
        except (json.JSONDecodeError, ValidationError) as e:
            raise GeminiError(f"answer does not match the schema: {type(e).__name__}") from None

    def _post(self, body: dict) -> dict:
        headers = {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = requests.post(self.API, json=body, headers=headers, timeout=self.TIMEOUT)
            except requests.RequestException as e:
                if attempt == self.max_attempts:
                    raise GeminiError(f"network error: {type(e).__name__}") from None
                self.sleep(self.backoff_s * 2 ** (attempt - 1))
                continue
            if response.ok:
                return response.json()
            if response.status_code == 429 and _is_daily_quota(response):
                raise GeminiQuotaExhausted("daily Gemini quota exhausted")
            if response.status_code == 429 or response.status_code >= 500:
                if attempt == self.max_attempts:
                    raise GeminiError(f"Gemini API returned {response.status_code} after {attempt} attempts")
                delay = _retry_delay(response) or self.backoff_s * 2 ** (attempt - 1)
                self.sleep(min(delay, 120))
                continue
            raise GeminiError(f"Gemini API returned {response.status_code}")
        raise GeminiError("no attempts made")
