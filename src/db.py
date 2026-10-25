"""The only SQLite connection entry point, shared by loading and checks."""
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / 'data' / 'phones.db'
TABLES = ('raw_file', 'phone', 'phone_snapshot', 'specification', 'wikidata_item',
          'phone_item_link', 'wikipedia_article', 'article_revision', 'quarantine')

# One fixed statement per table, so no SQL text is ever assembled at run time.
COUNT_SQL = {
    'raw_file': 'SELECT COUNT(*) FROM raw_file',
    'phone': 'SELECT COUNT(*) FROM phone',
    'phone_snapshot': 'SELECT COUNT(*) FROM phone_snapshot',
    'specification': 'SELECT COUNT(*) FROM specification',
    'wikidata_item': 'SELECT COUNT(*) FROM wikidata_item',
    'phone_item_link': 'SELECT COUNT(*) FROM phone_item_link',
    'wikipedia_article': 'SELECT COUNT(*) FROM wikipedia_article',
    'article_revision': 'SELECT COUNT(*) FROM article_revision',
    'quarantine': 'SELECT COUNT(*) FROM quarantine',
}
ROWS_SQL = {
    'raw_file': 'SELECT * FROM raw_file',
    'phone': 'SELECT * FROM phone',
    'phone_snapshot': 'SELECT * FROM phone_snapshot',
    'specification': 'SELECT * FROM specification',
    'wikidata_item': 'SELECT * FROM wikidata_item',
    'phone_item_link': 'SELECT * FROM phone_item_link',
    'wikipedia_article': 'SELECT * FROM wikipedia_article',
    'article_revision': 'SELECT * FROM article_revision',
    'quarantine': 'SELECT * FROM quarantine',
}


def connect(path=DEFAULT_DB, *, read_only=False):
    """Connect to the SQLite database and enforce PRAGMA foreign_keys = ON immediately.

    Requires SQLite 3.37 or later to ensure STRICT table support.
    """
    if sqlite3.sqlite_version_info < (3, 37):
        raise RuntimeError('SQLite 3.37 or later is required for STRICT tables')
    path = Path(path)
    if not read_only:
        path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) if read_only else sqlite3.connect(path)
    con.execute('PRAGMA foreign_keys = ON')
    con.row_factory = sqlite3.Row
    return con


def create_schema(con):
    # executescript() commits implicitly. Executing each DDL statement separately
    # keeps schema creation inside the same explicit transaction as the load.
    sql = (ROOT / 'sql' / 'schema.sql').read_text(encoding='utf-8')
    for statement in sql.split(';'):
        if statement.strip():
            con.execute(statement)


def counts(con):
    existing = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return {table: con.execute(COUNT_SQL[table]).fetchone()[0]
            if table in existing else 0 for table in TABLES}


def contents_digest(con):
    """Order-independent digest of every complete row, including surrogate keys."""
    import hashlib
    import json
    result = {}
    for table in TABLES:
        rows = (json.dumps(tuple(row), ensure_ascii=False, separators=(',', ':'))
                for row in con.execute(ROWS_SQL[table]))
        digest = hashlib.sha256()
        for row in sorted(rows):
            digest.update(row.encode('utf-8') + b'\n')
        result[table] = digest.hexdigest()
    return result
