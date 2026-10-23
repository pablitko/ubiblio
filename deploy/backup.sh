#!/bin/sh
# Daily backup of uBiblio on the host: consistent SQLite copy + CSV export, keep the last 14.
# Installed as /etc/cron.d/ubiblio-backup (see deploy/ubiblio-backup.cron).
# Copying the backups off the server (rclone/scp to another machine) is configured separately.
set -eu
DATA=/root/MCPAPPS/ubiblio
DEST=/backup/DB
STAMP=$(date +%F-%H%M%S)
mkdir -p "$DEST" && chmod 700 "$DEST"

# sqlite3 backup API inside the container (no sqlite3 needed on the host)
docker exec ubiblio python3 -c "
import sqlite3
src = sqlite3.connect('/app/config/sql_app.db')
dst = sqlite3.connect('/app/export/nightly.db')
src.backup(dst)
dst.close(); src.close()
"
gzip -c "$DATA/export/nightly.db" > "$DEST/ubiblio-$STAMP.sqlite.gz"
rm -f "$DATA/export/nightly.db"

# CSV of all books, readable without the application
docker exec ubiblio python3 -c "
import sys
sys.path.insert(0, '/app')
from ubiblio import csv_books
with open('/app/export/nightly.csv', 'w', encoding='utf-8', newline='') as f:
    csv_books.export_csv(f, '/app/config/sql_app.db')
"
gzip -c "$DATA/export/nightly.csv" > "$DEST/ubiblio-$STAMP.csv.gz"
rm -f "$DATA/export/nightly.csv"

test -s "$DEST/ubiblio-$STAMP.sqlite.gz"
ls -1t "$DEST"/ubiblio-*.sqlite.gz | tail -n +15 | xargs -r rm --
ls -1t "$DEST"/ubiblio-*.csv.gz | tail -n +15 | xargs -r rm --
