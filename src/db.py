"""The only SQLite connection entry point, shared by loading and checks."""
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / 'data' / 'phones.db'
TABLES = ('raw_file', 'phone', 'phone_snapshot', 'specification', 'wikidata_item',
          'phone_item_link', 'wikipedia_article', 'article_revision', 'quarantine')


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
    # Identifiers are a closed list maintained here, never incoming values.
    existing = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return {table: con.execute('SELECT COUNT(*) FROM "' + table + '"').fetchone()[0]
            if table in existing else 0 for table in TABLES}


def contents_digest(con):
    """Order-independent digest of every complete row, including surrogate keys."""
    import hashlib
    import json
    result = {}
    for table in TABLES:
        rows = (json.dumps(tuple(row), ensure_ascii=False, separators=(',', ':'))
                for row in con.execute('SELECT * FROM "' + table + '"'))
        digest = hashlib.sha256()
        for row in sorted(rows):
            digest.update(row.encode('utf-8') + b'\n')
        result[table] = digest.hexdigest()
    return result
