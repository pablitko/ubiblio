import pytest

from ubiblio.isbn import comparable_isbn, isbn13_to_10, normalize_isbn


class TestNormalizeIsbn:
    @pytest.mark.parametrize("raw, expected", [
        ("9788377792094", "9788377792094"),
        ("978-83-7779-209-4", "9788377792094"),
        (" 978 83 7779 209 4 ", "9788377792094"),
        ("830802534X", "9788308025345"),
        ("83-08-02534-x", "9788308025345"),
        ("0306406152", "9780306406157"),
        ("9790260000438", "9790260000438"),
    ])
    def test_valid(self, raw, expected):
        assert normalize_isbn(raw) == expected

    @pytest.mark.parametrize("raw", [
        "", None, "abc", "12345", "9788377792095", "8308025341", "5901234123457", "97883777920944",
    ])
    def test_invalid(self, raw):
        with pytest.raises(ValueError):
            normalize_isbn(raw)


class TestIsbn13To10:
    def test_978(self):
        assert isbn13_to_10("9788308025345") == "830802534X"
        assert isbn13_to_10("9780306406157") == "0306406152"

    def test_979_has_no_isbn10(self):
        assert isbn13_to_10("9790260000438") is None


class TestComparableIsbn:
    def test_isbn10_and_isbn13_match(self):
        assert comparable_isbn("83-08-02534-X") == comparable_isbn("9788308025345")

    def test_invalid_falls_back_to_digits(self):
        assert comparable_isbn("12-34 5") == "12345"
