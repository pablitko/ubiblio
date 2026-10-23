"""Generate templates/PL from the English templates.

Run from the repository root after changing an English template:
    python tools/make_pl_templates.py

Only user-visible text is translated: text nodes, placeholder/title attributes, the value of
submit/button inputs, confirm('...') messages, and a short list of strings in <script> blocks.
Attribute values used by the code (option values, radio values, field names) are left alone.
Unknown strings are reported, so a new English text does not silently stay untranslated.
"""
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "templates"
TARGET = ROOT / "templates" / "PL"

T = {
    # Navigation and common
    "Menu": "Menu", "Search": "Szukaj", "Advanced Search": "Wyszukiwanie zaawansowane",
    "Browse by Genre": "Przeglądaj według gatunku", "Wishlist": "Lista życzeń", "Reading Lists": "Listy lektur",
    "Withdrawn Books": "Wypożyczone książki", "Admin": "Administracja", "Log Out": "Wyloguj",
    "Import ISBNs": "Import po ISBN", "Import from Photos": "Import ze zdjęć", "Books to Complete": "Do uzupełnienia",
    "Books to complete": "Do uzupełnienia", "Personal Library": "Domowa biblioteka", "Design:": "Projekt:",
    "Actions": "Akcje", "Add": "Dodaj", "Add Another": "Dodaj kolejną", "Back": "Wstecz", "Delete": "Usuń",
    "Download": "Pobierz", "Filename": "Nazwa pliku", "Restore": "Przywróć", "Save": "Zapisz", "Submit": "Zatwierdź",
    "Update": "Zapisz zmiany", "Upload": "Wyślij", "Refresh": "Odśwież", "Count": "Liczba", "Sum": "Suma",
    "True": "Tak", "False": "Nie", "Options:": "Opcje:", "Results": "Wyniki", "Result": "Wynik", "Row": "Wiersz",
    "Note": "Uwaga", "Approve": "Zatwierdź", "number": "numer", "here": "tutaj", "of": "z", "Are you sure?": "Na pewno?", "Error:": "Błąd:",
    "No results found": "Brak wyników", "No results yet.": "Na razie brak wyników.",
    "Enter your search here": "Wpisz, czego szukasz",
    # Book fields
    "Title": "Tytuł", "Author": "Autor", "Summary": "Opis", "Genre": "Gatunek", "Library": "Biblioteka",
    "Shelf": "Półka", "Location": "Położenie", "Collection": "Kolekcja", "ISBN": "ISBN", "Notes": "Notatki",
    "Owned": "Posiadana", "Owned:": "Posiadana:", "Withdrawn": "Wypożyczona", "Withdrawn:": "Wypożyczona:",
    "Withdrawn By": "Wypożyczona przez", "eBook": "E-book", "Publisher": "Wydawca", "Year published": "Rok wydania",
    "Pages": "Liczba stron", "Language": "Język", "Date added": "Data dodania", "Last verified": "Ostatnio sprawdzona",
    "Uncategorized": "Bez kategorii", "Select a Genre": "Wybierz gatunek",
    # Search
    "Search By:": "Szukaj według:", "Search Results": "Wyniki wyszukiwania", "Only Ebooks": "Tylko e-booki",
    "No Ebooks": "Bez e-booków", "Select a library": "Wybierz bibliotekę",
    "No federated libraries available": "Brak powiązanych bibliotek",
    # Books
    "Book Details": "Szczegóły książki", "Add a New Book": "Dodaj nową książkę",
    "Add a New Book by ISBN": "Dodaj książkę po ISBN", "Add by ISBN": "Dodaj po ISBN", "Update a Book": "Edytuj książkę",
    "Add to Reading List": "Dodaj do listy lektur", "Remove from Reading List": "Usuń z listy lektur",
    "Reading List": "Lista lektur", "Withdraw": "Wypożycz", "Return": "Zwróć", "Checkout": "Wypożycz",
    "Book List": "Lista książek", "Book Wishlist": "Lista życzeń", "No withdrawn books": "Brak wypożyczonych książek",
    "Book Image Management": "Zdjęcia książki", "No images exist for this book.": "Ta książka nie ma zdjęć.",
    "Upload an image:": "Dodaj zdjęcie:", "Upload another image:": "Dodaj kolejne zdjęcie:",
    "Ebook Files": "Pliki e-booka", "Upload ebook files:": "Dodaj pliki e-booka:",
    "No files exist for this ebook. An admin may upload some.": "Ten e-book nie ma plików. Administrator może je dodać.",
    "Admin Actions": "Akcje administratora",
    # Scanning
    "Scan": "Skanuj", "Scan Another": "Skanuj kolejną", "Scan ISBN": "Skanowanie ISBN", "Manual Entry": "Wpisz ręcznie",
    "Camera:": "Kamera:", "Select a camera...": "Wybierz kamerę...", "Save Camera": "Zapamiętaj kamerę",
    "Start Camera Scan": "Włącz skanowanie", "Stop Scan": "Zatrzymaj skanowanie",
    "Continuous: save each book automatically": "Ciągły: każda książka zapisuje się sama",
    "Confirm each book": "Zatwierdzaj każdą książkę", "Current shelf": "Bieżąca półka", "Recent scans": "Ostatnie skany",
    # ISBN import
    "Import Books by ISBN": "Import książek po ISBN", "ISBN Import": "Import po ISBN", "ISBNs:": "Numery ISBN:",
    "Or a file:": "Albo plik:", "Applied to every imported book:": "Dla wszystkich importowanych książek:",
    "Import": "Importuj", "Processed": "Przetworzono", "Download report (CSV)": "Pobierz raport (CSV)",
    "New import": "Nowy import",
    "Paste one ISBN per line, or upload a text file (one ISBN per line) or a CSV file with an":
        "Wklej numery ISBN, po jednym w wierszu, albo wyślij plik tekstowy (jeden ISBN w wierszu) lub plik CSV z kolumną",
    "column. Books are looked up one by one and saved automatically; duplicates are skipped. Books that cannot be found are saved as \"ISBN":
        ". Książki są wyszukiwane po kolei i zapisywane automatycznie, duplikaty są pomijane. Książki, których nie udało się znaleźć, zapisują się jako \"ISBN",
    "\" and listed under": "\" i trafiają na listę",
    "Books saved without full metadata (note \"do-uzupelnienia\"). Open a book, fill in the details and remove the note.":
        "Książki zapisane bez pełnych danych (notatka \"do-uzupelnienia\") albo odczytane ze zdjęć (\"do-weryfikacji\"). Otwórz książkę, uzupełnij dane i usuń notatkę.",
    "Nothing to complete.": "Nie ma nic do uzupełnienia.",
    # Photo import
    "Import Books from Shelf Photos": "Import książek ze zdjęć półek", "Shelf Photo Import": "Import ze zdjęć",
    "Photo import is disabled.": "Import ze zdjęć jest wyłączony.",
    "To enable it, create an API key in Google AI Studio (aistudio.google.com) and start uBiblio with the environment variables":
        "Aby go włączyć, utwórz klucz API w Google AI Studio (aistudio.google.com) i uruchom uBiblio ze zmiennymi środowiskowymi",
    "(the key) and": "(klucz) oraz",
    "(a current model with image input, e.g. a Flash or Flash-Lite model from ai.google.dev/gemini-api/docs/models).":
        "(aktualny model obsługujący obrazy, np. Flash lub Flash-Lite z ai.google.dev/gemini-api/docs/models).",
    "Privacy:": "Prywatność:",
    "photos are sent to Google Gemini. On the free tier Google may use submitted content to improve its products. Photograph only book spines":
        "zdjęcia trafiają do Google Gemini. W planie darmowym Google może używać przesłanych treści do ulepszania swoich produktów. Fotografuj tylko grzbiety książek",
    "no people, documents or room interiors.": "bez ludzi, dokumentów i wnętrz.",
    "Each photo is read separately and gives a list of candidate books.": "Każde zdjęcie jest odczytywane osobno i daje listę kandydatów.",
    "Nothing is saved until you approve the candidates": "Nic się nie zapisuje, dopóki nie zatwierdzisz kandydatów",
    "; saved books get the note \"z-zdjecia, do-weryfikacji\" and appear under":
        "; zapisane książki dostają notatkę \"z-zdjecia, do-weryfikacji\" i trafiają na listę",
    "Tips: one shelf per photo, camera straight in front of the spines, good light without reflections, 15":
        "Wskazówki: jedna półka na zdjęcie, aparat na wprost grzbietów, dobre światło bez odbić, 15",
    "30 spines per photo, spines readable.": "30 grzbietów na zdjęcie, grzbiety czytelne.",
    "Photos (up to": "Zdjęcia (do", "MB each):": "MB każde):", "Applied to every saved book:": "Dla wszystkich zapisanych książek:",
    "Read photos": "Odczytaj zdjęcia", "Photos read:": "Odczytane zdjęcia:",
    "The daily Gemini quota is used up. The import is paused; resume it after":
        "Dzienny limit Gemini się wyczerpał. Import jest wstrzymany; wznów go po",
    "Resume": "Wznów", "Saved": "Zapisano", "book(s).": "książek.", "Candidates": "Kandydaci",
    "Correct titles and authors if needed, untick books you do not want, then save. Possible duplicates are unticked.":
        "W razie potrzeby popraw tytuły i autorów, odznacz zbędne książki i zapisz. Możliwe duplikaty są odznaczone.",
    "Photo": "Zdjęcie", "Confidence": "Pewność", "saved": "zapisana", "possible duplicate:": "możliwy duplikat:",
    "Save selected": "Zapisz zaznaczone", "No books were read from the photos.": "Ze zdjęć nie odczytano żadnej książki.",
    "New photo import": "Nowy import ze zdjęć",
    # Backups
    "Backup Management": "Kopie zapasowe", "Backup Now": "Zrób kopię teraz", "Restore from Backup": "Przywracanie z kopii",
    "Restoring from one of the files below will wipe the database completely and re-load it from the file. You":
        "Przywrócenie jednego z plików poniżej całkowicie wyczyści bazę i wczyta ją z pliku. Tej operacji",
    "cannot": "nie da się", "undo this process.": "cofnąć.", "File Backups": "Kopie plików",
    "Below is all of your backups of ubiblio's files. This includes uploaded ebooks and images.":
        "Poniżej są wszystkie kopie plików uBiblio, w tym wgranych e-booków i zdjęć.",
    "Book List Exports": "Eksporty listy książek",
    "These are lists of books only -- for example if you want to move a bunch of books from one uBiblio library to another. Or if you just want a CSV file of your books that you can open with other appliations.":
        "To same listy książek, np. do przeniesienia książek z jednej biblioteki uBiblio do innej albo do otwarcia w arkuszu kalkulacyjnym.",
    "Create CSV": "Utwórz CSV", "Download CSV": "Pobierz CSV", "Restoring from one of these files will": "Wczytanie jednego z tych plików",
    "NOT": "NIE",
    "wipe the current database first. It will add all the books from the file to the current database. Generally it is a good idea to backup the database before attempting this.":
        "czyści bazy. Doda wszystkie książki z pliku do obecnej bazy (duplikaty są pomijane). Zanim to zrobisz, warto zrobić kopię bazy.",
    "Add to DB": "Dodaj do bazy", "Upload a Backup": "Wyślij kopię", "Upload a backup:": "Plik kopii:",
    "This will accept database backups, file backups, and book list exports, so you can use this to merge libraries, move to a new server, or move to a newer version of the application.":
        "Przyjmuje kopie bazy, kopie plików i eksporty listy książek, więc służy do łączenia bibliotek, przeprowadzki na nowy serwer albo do nowszej wersji aplikacji.",
    "This will add the books in this file to the database. Are you sure?": "Książki z tego pliku zostaną dodane do bazy. Na pewno?",
    "This will delete the current DB and replace it with the backup. Are you sure?": "Obecna baza zostanie usunięta i zastąpiona kopią. Na pewno?",
    "This will delete this backup. Are you sure?": "Ta kopia zostanie usunięta. Na pewno?",
    "This will delete this book export. Are you sure?": "Ten eksport zostanie usunięty. Na pewno?",
    "CSV import": "Import CSV", "Added:": "Dodano:", "| Skipped (duplicates):": "| Pominięto (duplikaty):",
    "| Errors:": "| Błędy:", "Ignored columns:": "Pominięte kolumny:", "Skipped:": "Pominięto:",
    # Database update
    "The Database is Out of Date": "Baza danych wymaga aktualizacji",
    "It needs to be updated before uBiblio can be used. This process is automatic, and can be done by any Administrator by clicking":
        "Trzeba ją zaktualizować, zanim uBiblio będzie działać. Aktualizacja jest automatyczna; każdy administrator może ją uruchomić, klikając",
    "Before we begin, the system will attempt to automatically backup the database in case something goes wrong. This backup will be visible in the backup management interface accessible in the main menu under \"Admin\".":
        "Przed aktualizacją system automatycznie zrobi kopię bazy na wypadek problemów. Kopia będzie widoczna w kopiach zapasowych, w menu \"Administracja\".",
    # Config and stats
    "Update Main Library Configuration": "Ustawienia biblioteki", "Database Version:": "Wersja bazy:",
    "Enable Cover Images:": "Włącz zdjęcia okładek:", "Cover Images": "Zdjęcia okładek",
    "Custom Field 1 Name (empty to disable):": "Nazwa pola własnego 1 (puste = wyłączone):",
    "Custom Field 2 Name (empty to disable):": "Nazwa pola własnego 2 (puste = wyłączone):",
    "Genres (comma-separated):": "Gatunki (oddzielone przecinkami):", "Other Settings and Features": "Inne ustawienia i funkcje",
    "Library Stats": "Statystyki biblioteki", "Select a field to query": "Wybierz pole",
    "Field to group by:": "Grupuj według pola:", "Field to sum by (non-number contents ignored)": "Pole do sumowania (wartości nieliczbowe są pomijane)",
    "Summarize!": "Podsumuj!", "Error fetching database fields. This should never happen.": "Nie udało się pobrać pól bazy. To nie powinno się zdarzyć.",
    # Users and login
    "Log In": "Zaloguj", "Log In for Access": "Zaloguj się", "Username": "Nazwa użytkownika", "Password": "Hasło",
    "Create a new account": "Utwórz konto", "User Management": "Użytkownicy", "Manage Library Users": "Zarządzaj użytkownikami",
    "User List": "Lista użytkowników", "Add New User": "Dodaj użytkownika", "New User Link": "Link dla nowego użytkownika",
    "IsAdmin": "Administrator", "Account creation link": "Link do założenia konta",
    "Right click and copy this link. Then send it to your new user. It is valid for 3 days, and will let them create a normal user account. It will only work one time.":
        "Skopiuj ten link i wyślij nowemu użytkownikowi. Jest ważny 3 dni, pozwala raz założyć zwykłe konto.",
    # Federation
    "Federation": "Federacja", "Federation Key Management": "Klucze federacji",
    "Manage Verification Keys for Federation": "Zarządzaj kluczami federacji", "Verification Key List": "Lista kluczy",
    "Verification key": "Klucz weryfikacyjny", "Verification Key (Optional)": "Klucz weryfikacyjny (opcjonalnie)",
    "Add New Key": "Dodaj klucz", "URL": "URL", "URL -- Required": "URL (wymagany)",
    "No keys to display -- Federation disabled.": "Brak kluczy, federacja wyłączona.",
    "This feature lets users of other uBiblio libraries search and view your books. They cannot withdraw, modify, or delete content on your library.":
        "Ta funkcja pozwala użytkownikom innych bibliotek uBiblio przeszukiwać i przeglądać Twoje książki. Nie mogą ich wypożyczać, zmieniać ani usuwać.",
    "Instructions: You only need to enter the URL of their library. uBiblio will try and automatically fetch their verification key (it's just a public key). uBiblio will skip this step if you specify a key yourself.":
        "Wystarczy podać URL ich biblioteki. uBiblio spróbuje samo pobrać klucz weryfikacyjny (to klucz publiczny). Jeśli podasz klucz sam, ten krok zostanie pominięty.",
    "Note: Adding another library's key will let them search and view your books. They must add your key to":
        "Uwaga: dodanie klucza innej biblioteki pozwoli jej przeszukiwać i przeglądać Twoje książki. Muszą też dodać Twój klucz do",
    "their": "swojej",
    "library for your users to be able to search their library. Before they complete that step, their library will show up in the Advanced Search options, but searches won't work.":
        "biblioteki, żeby Twoi użytkownicy mogli przeszukiwać ich bibliotekę. Do tego czasu będzie widoczna w wyszukiwaniu zaawansowanym, ale wyszukiwanie nie zadziała.",
}

# Texts that stay as they are (names, identifiers, Jinja fragments)
KEEP = {"uBiblio", "Sean Boyce", "HTML5 UP", "GEMINI_API_KEY", "GEMINI_MODEL", "{% if c.confidence"}

# Strings inside <script> blocks: (file or "*", English, Polish)
SCRIPT = [
    ("*", '"Search Results ("', '"Wyniki wyszukiwania ("'),
    ("*", '"Results ("', '"Wyniki ("'),
    ("*", '"No results found"', '"Brak wyników"'),
    ("*", ">Previous</button>", ">Poprzednia</button>"),
    ("*", ">Next</button>", ">Następna</button>"),
    ("fedBookDetails.html", "<strong>Title</strong>", "<strong>Tytuł</strong>"),
    ("fedBookDetails.html", "<strong>Author</strong>", "<strong>Autor</strong>"),
    ("fedBookDetails.html", "<strong>Summary</strong>", "<strong>Opis</strong>"),
    ("fedBookDetails.html", "<strong>Library</strong>", "<strong>Biblioteka</strong>"),
    ("fedBookDetails.html", "<strong>Shelf</strong>", "<strong>Półka</strong>"),
    ("fedBookDetails.html", "<strong>Owned</strong>", "<strong>Posiadana</strong>"),
    ("fedBookDetails.html", "<strong>Withdrawn</strong>", "<strong>Wypożyczona</strong>"),
    ("stats.html", "<th>Item</th><th>Value</th>", "<th>Pozycja</th><th>Wartość</th>"),
    ("userManagement.html", ">Set to Admin<", ">Nadaj uprawnienia administratora<"),
    ("userManagement.html", ">Set to User<", ">Odbierz uprawnienia administratora<"),
    ("userManagement.html", ">Delete</a>", ">Usuń</a>"),
    ("importIsbnJob.html", 'added: "added"', 'added: "dodana"'),
    ("importIsbnJob.html", 'not_found: "not found (saved to complete)"', 'not_found: "nie znaleziono (zapisana do uzupełnienia)"'),
    ("importIsbnJob.html", 'duplicate: "already in the library"', 'duplicate: "już jest w bibliotece"'),
    ("importIsbnJob.html", 'invalid: "invalid ISBN"', 'invalid: "nieprawidłowy ISBN"'),
    ("importIsbnJob.html", 'error: "error"', 'error: "błąd"'),
    ("importIsbnJob.html", '"Added: "', '"Dodano: "'),
    ("importIsbnJob.html", '" | Not found: "', '" | Nie znaleziono: "'),
    ("importIsbnJob.html", '" | Duplicates: "', '" | Duplikaty: "'),
    ("importIsbnJob.html", '" | Invalid: "', '" | Nieprawidłowe: "'),
    ("importIsbnJob.html", '" | Errors: "', '" | Błędy: "'),
    ("scanIsbn.html", 'added: "added"', 'added: "dodana"'),
    ("scanIsbn.html", 'duplicate: "already in the library"', 'duplicate: "już jest w bibliotece"'),
    ("scanIsbn.html", 'not_found: "not found, saved to complete"', 'not_found: "nie znaleziono, zapisana do uzupełnienia"'),
    ("scanIsbn.html", 'invalid: "invalid ISBN"', 'invalid: "nieprawidłowy ISBN"'),
    ("scanIsbn.html", 'error: "error"', 'error: "błąd"'),
    ("scanIsbn.html", 'saving: "saving..."', 'saving: "zapisywanie..."'),
    ("scanIsbn.html", 'networkError: "network error, try again"', 'networkError: "błąd sieci, spróbuj ponownie"'),
    ("scanIsbn.html", 'rejected: "Ignored misread barcode: "', 'rejected: "Pominięto błędnie odczytany kod: "'),
    ("scanIsbn.html", 'count: " this session"', 'count: " w tej sesji"'),
    ("scanIsbn.html", "'<option value=\"\">Select a camera...</option>'", "'<option value=\"\">Wybierz kamerę...</option>'"),
    ("scanIsbn.html", "'Please select a camera first'", "'Najpierw wybierz kamerę'"),
    ("scanIsbn.html", "'Initializing camera...'", "'Uruchamianie kamery...'"),
    ("scanIsbn.html", "'Camera ready. Point at barcode...'", "'Kamera gotowa. Skieruj ją na kod kreskowy...'"),
    ("scanIsbn.html", "'Error accessing cameras: '", "'Brak dostępu do kamery: '"),
    ("scanIsbn.html", "'Error: '", "'Błąd: '"),
]

ATTRS = ("placeholder", "title")


def translate_text(core, missing, where):
    key = " ".join(core.split())
    if key in KEEP or not re.search(r"[A-Za-z]{2}", key):
        return core
    if key in T:
        return T[key]
    missing.add((key, where))
    return core


class Translator(HTMLParser):
    def __init__(self, source, name, missing):
        super().__init__(convert_charrefs=False)
        self.source = source
        self.name = name
        self.missing = missing
        self.edits = []
        self.in_script = 0
        lines = source.splitlines(keepends=True)
        self.line_offsets = [0]
        for line in lines:
            self.line_offsets.append(self.line_offsets[-1] + len(line))

    def abs_pos(self):
        line, col = self.getpos()
        return self.line_offsets[line - 1] + col

    def handle_starttag(self, tag, attrs):
        start = self.abs_pos()
        raw = self.get_starttag_text()
        if tag in ("script", "style"):
            self.in_script += 1
        new = raw
        attr = dict(attrs)
        names = list(ATTRS)
        if tag == "input" and (attr.get("type") or "").lower() in ("submit", "button"):
            names.append("value")
        for name in names:
            value = attr.get(name)
            if value and "{{" not in value:
                translated = translate_text(value, self.missing, self.name)
                if translated != value:
                    new = new.replace(f'{name}="{value}"', f'{name}="{translated}"')
        for message in re.findall(r"confirm\('([^']+)'\)", raw):
            translated = translate_text(message, self.missing, self.name)
            new = new.replace(f"confirm('{message}')", f"confirm('{translated}')")
        if new != raw:
            self.edits.append((start, start + len(raw), new))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag in ("script", "style"):
            self.in_script -= 1

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.in_script -= 1

    def handle_data(self, data):
        if self.in_script:
            return
        start = self.abs_pos()
        assert self.source[start:start + len(data)] == data, (self.name, data[:40])
        parts = re.split(r"(\{[{%].*?[}%]\})", data, flags=re.S)
        out = []
        for part in parts:
            if part.startswith(("{{", "{%")):
                out.append(part)
                continue
            core = part.strip()
            if not core:
                out.append(part)
                continue
            lead = part[:len(part) - len(part.lstrip())]
            trail = part[len(part.rstrip()):]
            out.append(lead + translate_text(core, self.missing, self.name) + trail)
        new = "".join(out)
        if new != data:
            self.edits.append((start, start + len(data), new))


def translate_file(path, missing):
    source = path.read_text(encoding="utf-8")
    parser = Translator(source, path.name, missing)
    parser.feed(source)
    parser.close()
    result = source
    for start, end, new in sorted(parser.edits, reverse=True):
        result = result[:start] + new + result[end:]
    for name, english, polish in SCRIPT:
        if name in ("*", path.name) and english in result:
            result = result.replace(english, polish)
    return result


def main():
    TARGET.mkdir(exist_ok=True)
    missing = set()
    for path in sorted(SOURCE.glob("*.html")):
        (TARGET / path.name).write_text(translate_file(path, missing), encoding="utf-8", newline="")
    for name in ("favicon.ico",):
        if (SOURCE / name).exists():
            (TARGET / name).write_bytes((SOURCE / name).read_bytes())
    for key, where in sorted(missing):
        print(f"untranslated ({where}): {key!r}")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
