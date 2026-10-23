import json
from typing import Any

from sqlalchemy.orm import Session

from ... import crud, schemas
from ...isbn import normalize_isbn
from ...vars import METADATA_SOURCES
from .book_metadata_client import BookMetadataClient


# --------------------------------------------------------------------------
# External metadata (ISBN / title lookup)
# --------------------------------------------------------------------------
METADATA_SOURCE_METHODS = {
    "bn": ("Biblioteka Narodowa", "bn_by_isbn"),
    "google": ("Google Books", "google_books_by_isbn"),
    "openlibrary": ("Open Library", "open_library_by_isbn"),
    "wikipedia": ("Wikipedia", "open_wiki_by_isbn"),
}


def metadata_source_order(isbn: str, sources: list[str] | None = None) -> list[str]:
    """Configured source order; BN goes last for ISBNs outside the Polish 978-83 prefix."""
    order = [s for s in (sources if sources is not None else METADATA_SOURCES) if s in METADATA_SOURCE_METHODS]
    if "bn" in order and not isbn.startswith("97883"):
        order = [s for s in order if s != "bn"] + ["bn"]
    return order


def lookup_book_metadata_by_isbn(isbn: str) -> dict[str, Any]:
    """
    Resolve ISBN to Title/Author/Summary, trying the sources from METADATA_SOURCES in order.
    A failing source does not stop the others. Raises LookupError if no source returns data.
    """
    isbn = isbn.strip()
    try:
        isbn = normalize_isbn(isbn)
    except ValueError:
        pass
    client = BookMetadataClient()

    for source in metadata_source_order(isbn):
        name, method = METADATA_SOURCE_METHODS[source]
        try:
            book, response = getattr(client, method)(isbn)
            if response is not None and response != 200:
                print(name + " API failed with response: ")
                print(response)
            if book.get("Title"):
                return book
        except Exception as e:
            print(name + " API failed with response: ")
            print(e)

    raise LookupError(f"Book with isbn {isbn} not found!")


# --------------------------------------------------------------------------
# Form → schema (book fields)
# --------------------------------------------------------------------------
def book_create_from_form(form) -> schemas.BookCreate:
    return schemas.BookCreate(
        title=form.title,
        author=form.author,
        summary=form.summary,
        genre=form.genre,
        library=form.library,
        shelf=form.shelf,
        collection=form.collection,
        notes=form.notes,
        ISBN=form.ISBN,
        owned=form.owned,
        ebook=form.ebook,
        customField1=form.customField1,
        customField2=form.customField2,
        withdrawn=form.withdrawn,
    )


def book_update_from_form(book_id, form) -> schemas.Book:
    return schemas.Book(
        id=book_id,
        title=form.title,
        author=form.author,
        summary=form.summary,
        genre=form.genre,
        library=form.library,
        shelf=form.shelf,
        collection=form.collection,
        notes=form.notes,
        ISBN=form.ISBN,
        owned=form.owned,
        ebook=form.ebook,
        customField1=form.customField1,
        customField2=form.customField2,
        withdrawn=form.withdrawn,
    )


# --------------------------------------------------------------------------
# Search serialization
# --------------------------------------------------------------------------
def search_books_json(db: Session, title: str, author: str, skip: int, only_ebooks: bool, no_ebooks: bool) -> str | None:
    from fastapi.encoders import jsonable_encoder

    try:
        books = crud.searchBooks(db, str(title), str(author), int(
            skip), bool(only_ebooks), bool(no_ebooks))
        result = json.dumps(jsonable_encoder(books[0]))
        data: dict[str, Any] = {"result": result, "count": books[1]}
        return json.dumps(jsonable_encoder(data))
    except Exception as e:
        print(e)
        return None


def search_books_by_author_json(
    db: Session, author: str, skip: int, only_ebooks: bool, no_ebooks: bool
) -> str | None:
    from fastapi.encoders import jsonable_encoder

    try:
        books = jsonable_encoder(crud.searchBooksbyAuthor(
            db, str(author), int(skip), bool(only_ebooks), bool(no_ebooks)))
        result = json.dumps(jsonable_encoder(books[0]))
        data: dict[str, Any] = {"result": result, "count": books[1]}
        return json.dumps(jsonable_encoder(data))
    except Exception as e:
        print(e)
        return None


def search_books_by_title_json(
    db: Session, title: str, skip: int, only_ebooks: bool, no_ebooks: bool
) -> str | None:
    from fastapi.encoders import jsonable_encoder

    try:
        books = jsonable_encoder(crud.searchBooksbyTitle(
            db, str(title), int(skip), bool(only_ebooks), bool(no_ebooks)))
        result = json.dumps(jsonable_encoder(books[0]))
        data: dict[str, Any] = {"result": result, "count": books[1]}
        return json.dumps(jsonable_encoder(data))
    except Exception as e:
        print(e)
        return None


def book_create_from_isbn_metadata(book: dict[str, Any], isbn: str) -> schemas.BookCreate:
    return schemas.BookCreate(
        title=book["Title"],
        author=book["Author"],
        summary=book["Summary"],
        ISBN=isbn,
    )
