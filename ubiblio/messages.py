"""Translations of messages returned from Python code (templates are translated per directory).

_(text, **values) returns the text in the language from LANGUAGE (English when there is no
translation) and fills {placeholders} with str.format.
"""
from .vars import LANGUAGE

PL = {
    # Forms
    "Please enter your username": "Podaj nazwę użytkownika",
    "A valid password is required": "Podaj prawidłowe hasło",
    "A valid password over 3 characters is required": "Hasło musi mieć więcej niż 3 znaki",
    "Something went wrong with your access link. Reload this page, or contact your library admin.":
        "Coś jest nie tak z linkiem dostępu. Odśwież stronę albo skontaktuj się z administratorem biblioteki.",
    "Validation keys require a URL to tie them to": "Klucz weryfikacyjny wymaga adresu URL",
    "At least a title is required to create a book.": "Książka musi mieć co najmniej tytuł.",
    "{name} must be a whole number.": "Pole {name} musi być liczbą całkowitą.",
    "Database version is required so as not to break the DB": "Wersja bazy jest wymagana, żeby nie uszkodzić bazy",
    "Enable Cover Images must be either True or False": "Zdjęcia okładek: wybierz Tak albo Nie",
    # Auth
    "Incorrect Email or Password": "Nieprawidłowa nazwa użytkownika lub hasło",
    "Your access code is invalid or expired.": "Kod dostępu jest nieprawidłowy lub wygasł.",
    "An error has occurred.": "Wystąpił błąd.",
    "An error has occured.": "Wystąpił błąd.",
    "Account created successfully! Please log in with your new account.": "Konto zostało utworzone. Zaloguj się na nowe konto.",
    "The form you submitted is not valid. Try your access link again, or contact the library admin.":
        "Formularz jest nieprawidłowy. Otwórz link dostępu jeszcze raz albo skontaktuj się z administratorem.",
    "Username already exists, please choose another.": "Ta nazwa użytkownika jest zajęta, wybierz inną.",
    "Only an admin can perform this action.": "Tylko administrator może to zrobić.",
    "You are not logged in. Login to view books.": "Nie jesteś zalogowany. Zaloguj się, żeby zobaczyć książki.",
    "Fail": "Nie udało się.",
    # Admin
    "Database export failed.": "Eksport bazy się nie udał.",
    "Could not list database backups.": "Nie udało się wyświetlić kopii zapasowych.",
    "Delete backup failed. There may be a file permissions issue.": "Nie udało się usunąć kopii. Sprawdź uprawnienia do plików.",
    "Error adding books -- check the search page to see what was added.": "Błąd przy dodawaniu książek. Sprawdź w wyszukiwarce, co zostało dodane.",
    "Not a valid backup": "To nie jest prawidłowa kopia zapasowa",
    "File backup failed.": "Kopia plików się nie udała.",
    "File restore failed.": "Przywracanie plików się nie udało.",
    "Could not load library configuration.": "Nie udało się wczytać ustawień biblioteki.",
    "Could not update library configuration.": "Nie udało się zapisać ustawień biblioteki.",
    "Could not promote user.": "Nie udało się nadać uprawnień administratora.",
    "Could not demote user.": "Nie udało się odebrać uprawnień administratora.",
    "Could not delete user.": "Nie udało się usunąć użytkownika.",
    "User search failed.": "Wyszukiwanie użytkowników się nie udało.",
    "Could not generate a new user code.": "Nie udało się utworzyć kodu dla nowego użytkownika.",
    "Could not load verification keys.": "Nie udało się wczytać kluczy weryfikacyjnych.",
    "Could not delete verification key.": "Nie udało się usunąć klucza weryfikacyjnego.",
    "Not a valid jpg image": "To nie jest prawidłowy obraz JPG",
    "ISBN {isbn} not found -- try another.": "Nie znaleziono ISBN {isbn}, spróbuj innego.",
    "Give the token a name and choose read or write.": "Podaj nazwę tokenu i wybierz odczyt albo zapis.",
    # CSV import report
    "missing title": "brak tytułu",
    "duplicate: {title}": "duplikat: {title}",
    "invalid boolean value {value!r}": "nieprawidłowa wartość logiczna {value!r}",
    "{name} must be a whole number, got {value!r}": "pole {name} musi być liczbą całkowitą, jest {value!r}",
    "{name} must be a date like 2026-10-23, got {value!r}": "pole {name} musi być datą w formacie 2026-10-23, jest {value!r}",
    "file is not UTF-8 encoded": "plik nie jest zapisany w UTF-8",
    # ISBN and photo import
    "Import job not found (jobs are lost when the server restarts).": "Nie znaleziono importu (importy znikają po restarcie serwera).",
    "The file is not UTF-8 encoded.": "Plik nie jest zapisany w UTF-8.",
    "No ISBNs given.": "Nie podano żadnego numeru ISBN.",
    "Too many ISBNs ({count}); the limit is {limit} per import.": "Za dużo numerów ISBN ({count}); limit to {limit} na jeden import.",
    "Photo import is disabled: set GEMINI_API_KEY and GEMINI_MODEL.": "Import ze zdjęć jest wyłączony: ustaw GEMINI_API_KEY i GEMINI_MODEL.",
    "No photos given.": "Nie wybrano zdjęć.",
    "Too many photos ({count}); the limit is {limit}.": "Za dużo zdjęć ({count}); limit to {limit}.",
    "{name}: larger than {size} MB.": "{name}: plik większy niż {size} MB.",
    "{name}: not a supported image.": "{name}: nieobsługiwany format obrazu.",
}

TRANSLATIONS = {"PL": PL}


def _(text, **values):
    text = TRANSLATIONS.get(LANGUAGE.upper(), {}).get(text, text)
    return text.format(**values) if values else text
