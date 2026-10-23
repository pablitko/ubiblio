import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ubiblio import crud, models
from ubiblio.text import normalize_text

BOOKS = [
    # title, author, owned, ebook
    ("Solaris", "Stanisław Lem", True, False),
    ("Lalka", "Bolesław Prus", True, False),
    ("Łódź i okolice", "Żaneta Łęcka", True, False),
    ("ŻÓŁĆ", "Anonim", True, True),
    ("Pan Tadeusz", "Adam Mickiewicz", True, True),
    ("Dziady", "Adam Mickiewicz", False, False),  # wishlist: never in search
    ("Zielona książka", None, True, False),
]


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'search.db'}")
    models.Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    for title, author, owned, ebook in BOOKS:
        session.add(models.Book(title=title, author=author, owned=owned, ebook=ebook, withdrawn=False))
    session.commit()
    yield session
    session.close()
    engine.dispose()


def titles(result):
    books, count = result
    assert count == len(books)
    return [b.title for b in books]


class TestCurrentBehaviour:
    """Behaviour that the rewrite must keep (ASCII terms, filters, paging)."""

    def test_title_or_author(self, db):
        assert titles(crud.searchBooks(db, "solaris", "solaris", 0, False, False)) == ["Solaris"]
        assert titles(crud.searchBooks(db, "mickiewicz", "mickiewicz", 0, False, False)) == ["Pan Tadeusz"]

    def test_percent_lists_all_owned_books(self, db):
        assert len(titles(crud.searchBooks(db, "%", "%", 0, False, False))) == 6

    def test_ebook_filters(self, db):
        assert titles(crud.searchBooks(db, "%", "%", 0, True, False)) == ["Pan Tadeusz", "ŻÓŁĆ"]
        assert "Pan Tadeusz" not in titles(crud.searchBooks(db, "%", "%", 0, False, True))
        assert len(titles(crud.searchBooks(db, "%", "%", 0, True, True))) == 6

    def test_by_author_and_by_title(self, db):
        assert titles(crud.searchBooksbyAuthor(db, "prus", 0, False, False)) == ["Lalka"]
        assert titles(crud.searchBooksbyTitle(db, "LALKA", 0, False, False)) == ["Lalka"]
        assert titles(crud.searchBooksbyTitle(db, "Mickiewicz", 0, False, False)) == []

    def test_paging(self, db):
        page1, count = crud.searchBooks(db, "%", "%", 0, False, False, limit=4)
        page2, _ = crud.searchBooks(db, "%", "%", 4, False, False, limit=4)
        assert count == 6
        assert len(page1) == 4 and len(page2) == 2
        assert not {b.id for b in page1} & {b.id for b in page2}


class TestPolishCharacters:
    @pytest.mark.parametrize("term", ["Łódź", "łódź", "ŁÓDŹ", "lodz", "LODZ"])
    def test_case_and_diacritics_insensitive(self, db, term):
        assert titles(crud.searchBooksbyTitle(db, term, 0, False, False)) == ["Łódź i okolice"]

    @pytest.mark.parametrize("term", ["żółć", "Żółć", "zolc"])
    def test_uppercase_title(self, db, term):
        assert titles(crud.searchBooksbyTitle(db, term, 0, False, False)) == ["ŻÓŁĆ"]

    def test_author(self, db):
        assert titles(crud.searchBooksbyAuthor(db, "łęcka", 0, False, False)) == ["Łódź i okolice"]
        assert titles(crud.searchBooksbyAuthor(db, "stanislaw", 0, False, False)) == ["Solaris"]
        assert titles(crud.searchBooks(db, "MICKIEWICZ", "MICKIEWICZ", 0, False, False)) == ["Pan Tadeusz"]

    def test_polish_sort_order(self, db):
        result = titles(crud.searchBooks(db, "%", "%", 0, False, False))
        assert result.index("Łódź i okolice") < result.index("Pan Tadeusz")


class TestNormalizeText:
    @pytest.mark.parametrize("raw, expected", [
        ("Żółć", "zolc"), ("ŁÓDŹ", "lodz"), ("Gęślą Jaźń", "gesla jazn"), ("Straße", "strasse"), (None, None),
    ])
    def test_normalize(self, raw, expected):
        assert normalize_text(raw) == expected
