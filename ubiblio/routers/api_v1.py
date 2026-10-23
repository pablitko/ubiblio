"""JSON API for scripts and the MCP server. Bearer tokens only (no cookies), so it is not open to CSRF.

There is deliberately no endpoint that deletes books, restores backups or manages users.
"""
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .. import api_tokens, isbn_import, models, schemas
from ..database import SessionLocal
from ..text import normalize_text
from ..vars import API_RATE_LIMIT_PER_MIN
from .books import service

router = APIRouter(prefix="/api/v1", tags=["api"])

MAX_LIMIT = 50


# --------------------------------------------------------------------------
# Authentication, rate limit
# --------------------------------------------------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


_calls: dict[int, deque] = defaultdict(deque)


def _rate_limited(token_id: int) -> bool:
    now = time.monotonic()
    calls = _calls[token_id]
    while calls and now - calls[0] > 60:
        calls.popleft()
    if len(calls) >= API_RATE_LIMIT_PER_MIN:
        return True
    calls.append(now)
    return False


def api_user(scope: str):
    def dependency(request: Request, db: Annotated[Session, Depends(get_db)]) -> models.apiToken:
        header = request.headers.get("Authorization", "")
        kind, _, token = header.partition(" ")
        row = api_tokens.find_token(db, token.strip()) if kind.lower() == "bearer" else None
        if row is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or missing token",
                                headers={"WWW-Authenticate": "Bearer"})
        request.state.api_token_name = row.name
        if not api_tokens.allows(row, scope):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"token scope '{row.scope}' does not allow {scope}")
        if _rate_limited(row.id):
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "rate limit exceeded", headers={"Retry-After": "60"})
        return row
    return dependency


ReadToken = Annotated[models.apiToken, Depends(api_user("read"))]
WriteToken = Annotated[models.apiToken, Depends(api_user("write"))]
DB = Annotated[Session, Depends(get_db)]


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------
class BookOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str | None
    author: str | None = None
    ISBN: str | None = None
    library: str | None = None
    shelf: str | None = None
    collection: str | None = None
    genre: str | None = None
    notes: str | None = None
    owned: bool | None = None
    withdrawn: bool | None = None
    publisher: str | None = None
    publishedYear: int | None = None
    pages: int | None = None
    language: str | None = None
    dateAdded: datetime | None = None
    lastVerified: datetime | None = None


class BookDetailOut(BookOut):
    summary: str | None = None
    withdrawnBy: str | None = None


class BookList(BaseModel):
    total: int
    limit: int
    offset: int
    books: list[BookOut]


class BookIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=500)
    author: str | None = Field(default=None, max_length=500)
    summary: str | None = Field(default=None, max_length=10000)
    genre: str | None = Field(default=None, max_length=200)
    library: str | None = Field(default=None, max_length=200)
    shelf: str | None = Field(default=None, max_length=200)
    collection: str | None = Field(default=None, max_length=200)
    ISBN: str | None = Field(default=None, max_length=32)
    notes: str | None = Field(default=None, max_length=2000)
    owned: bool = True
    publisher: str | None = Field(default=None, max_length=300)
    publishedYear: int | None = Field(default=None, ge=0, le=2100)
    pages: int | None = Field(default=None, ge=0, le=100000)
    language: str | None = Field(default=None, max_length=20)


class ByIsbnIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    isbn: str = Field(max_length=32)
    library: str = Field(default="", max_length=200)
    shelf: str = Field(default="", max_length=200)
    collection: str = Field(default="", max_length=200)


class ByIsbnOut(BaseModel):
    status: str
    book: BookOut


class BookPatch(BaseModel):
    """Only location and description fields can be changed through the API."""
    model_config = ConfigDict(extra="forbid")
    shelf: str | None = Field(default=None, max_length=200)
    library: str | None = Field(default=None, max_length=200)
    collection: str | None = Field(default=None, max_length=200)
    genre: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------
def _contains(column, term):
    return func.ub_norm(column).like("%" + normalize_text(term) + "%")


def _get_book(db: Session, book_id: int) -> models.Book:
    book = db.get(models.Book, book_id)
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "book not found")
    return book


@router.get("/books", response_model=BookList)
def list_books(token: ReadToken, db: DB,
               q: Annotated[str | None, Query(max_length=200, description="title or author contains")] = None,
               author: Annotated[str | None, Query(max_length=200)] = None,
               shelf: Annotated[str | None, Query(max_length=200, description="exact shelf name")] = None,
               limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 20,
               offset: Annotated[int, Query(ge=0)] = 0):
    query = db.query(models.Book).filter(models.Book.owned == True)
    if q:
        query = query.filter(or_(_contains(models.Book.title, q), _contains(models.Book.author, q)))
    if author:
        query = query.filter(_contains(models.Book.author, author))
    if shelf:
        query = query.filter(models.Book.shelf == shelf)
    total = query.with_entities(func.count()).scalar()
    books = (query.order_by(func.ub_norm(models.Book.title), models.Book.id)
             .limit(limit).offset(offset).all())
    return BookList(total=total, limit=limit, offset=offset, books=books)


@router.get("/books/to-complete", response_model=list[BookOut])
def books_to_complete(token: ReadToken, db: DB,
                      limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 20):
    return isbn_import.books_to_complete(db)[:limit]


@router.get("/books/{book_id}", response_model=BookDetailOut)
def get_book(book_id: int, token: ReadToken, db: DB):
    return _get_book(db, book_id)


@router.get("/stats")
def stats(token: ReadToken, db: DB):
    count = lambda *conditions: db.query(models.Book).filter(*conditions).with_entities(func.count()).scalar()
    shelves = (db.query(models.Book.shelf, func.count()).filter(models.Book.owned == True)
               .group_by(models.Book.shelf).order_by(func.count().desc()).limit(MAX_LIMIT).all())
    return {
        "books": count(models.Book.owned == True),
        "wishlist": count(models.Book.owned == False),
        "withdrawn": count(models.Book.withdrawn == True),
        "toComplete": len(isbn_import.books_to_complete(db)),
        "neverVerified": count(models.Book.owned == True, models.Book.lastVerified.is_(None)),
        "shelves": [{"shelf": shelf, "books": n} for shelf, n in shelves],
    }


@router.post("/books", response_model=BookOut, status_code=status.HTTP_201_CREATED)
def create_book(body: BookIn, token: WriteToken, db: DB):
    book = models.Book(**schemas.BookCreate(**body.model_dump(), withdrawn=False, ebook=False).model_dump(exclude_none=True))
    db.add(book)
    db.commit()
    db.refresh(book)
    return book


@router.post("/books/by-isbn", response_model=ByIsbnOut)
def create_book_by_isbn(body: ByIsbnIn, token: WriteToken, db: DB, response: Response):
    """Idempotent: an ISBN that is already in the library returns the existing book (200)."""
    known = isbn_import.existing_isbns(db)
    result = isbn_import.add_book_by_isbn(db, body.isbn, known, service.lookup_book_metadata_by_isbn,
                                          body.library.strip(), body.shelf.strip(), body.collection.strip())
    if result["status"] == "invalid":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, result.get("error", "invalid ISBN"))
    if result["status"] == "error":
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "could not save the book")
    if result["status"] in ("added", "not_found"):
        response.status_code = status.HTTP_201_CREATED
    return ByIsbnOut(status=result["status"], book=_get_book(db, result["bookId"]))


@router.patch("/books/{book_id}", response_model=BookOut)
def update_book(book_id: int, body: BookPatch, token: WriteToken, db: DB):
    book = _get_book(db, book_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(book, key, value)
    db.commit()
    return book


@router.post("/books/{book_id}/verify", response_model=BookOut)
def verify_book(book_id: int, token: WriteToken, db: DB):
    """Mark the book as seen on its shelf now (inventory check)."""
    book = _get_book(db, book_id)
    book.lastVerified = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    return book
