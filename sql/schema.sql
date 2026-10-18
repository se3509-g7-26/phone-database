-- All source dates are canonical UTC TEXT. Opaque specifications stay TEXT.
CREATE TABLE IF NOT EXISTS raw_file (
    file_key INTEGER PRIMARY KEY NOT NULL,
    source_id TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL CHECK(source IN ('gsmarena','wikidata','wikipedia')),
    url TEXT NOT NULL,
    byte_count INTEGER NOT NULL CHECK(byte_count >= 0),
    sha256 TEXT NOT NULL CHECK(length(sha256) = 64),
    retrieved_at TEXT NOT NULL CHECK(length(retrieved_at) = 27 AND substr(retrieved_at,27) = 'Z' AND julianday(retrieved_at) IS NOT NULL)
) STRICT;

CREATE TABLE IF NOT EXISTS phone (
    phone_key INTEGER PRIMARY KEY NOT NULL,
    source_id TEXT NOT NULL UNIQUE CHECK(source_id <> '' AND source_id NOT GLOB '*[^0-9]*'),
    name TEXT NOT NULL CHECK(length(name) > 0),
    source_url TEXT NOT NULL,
    file_key INTEGER NOT NULL REFERENCES raw_file(file_key),
    retrieved_at TEXT NOT NULL CHECK(length(retrieved_at) = 27 AND substr(retrieved_at,27) = 'Z' AND julianday(retrieved_at) IS NOT NULL)
) STRICT;

-- A saved observation of a model, not an announcement or a retail transaction.
CREATE TABLE IF NOT EXISTS phone_snapshot (
    phone_key INTEGER NOT NULL REFERENCES phone(phone_key),
    retrieved_at TEXT NOT NULL CHECK(length(retrieved_at) = 27 AND substr(retrieved_at,27) = 'Z' AND julianday(retrieved_at) IS NOT NULL),
    name TEXT NOT NULL,
    file_key INTEGER NOT NULL REFERENCES raw_file(file_key),
    PRIMARY KEY(phone_key, retrieved_at)
) STRICT;

-- row_number preserves repeated labels and unlabeled continuation rows.
CREATE TABLE IF NOT EXISTS specification (
    phone_key INTEGER NOT NULL,
    retrieved_at TEXT NOT NULL CHECK(length(retrieved_at) = 27 AND substr(retrieved_at,27) = 'Z' AND julianday(retrieved_at) IS NOT NULL),
    row_number INTEGER NOT NULL CHECK(row_number > 0),
    section TEXT NOT NULL,
    label TEXT NOT NULL,
    source_field TEXT,
    value_text TEXT,
    file_key INTEGER NOT NULL REFERENCES raw_file(file_key),
    PRIMARY KEY(phone_key, retrieved_at, row_number),
    FOREIGN KEY(phone_key, retrieved_at) REFERENCES phone_snapshot(phone_key, retrieved_at)
) STRICT;

CREATE TABLE IF NOT EXISTS wikidata_item (
    item_key INTEGER PRIMARY KEY NOT NULL,
    source_id TEXT NOT NULL UNIQUE CHECK(source_id GLOB 'Q[0-9]*' AND substr(source_id,2) NOT GLOB '*[^0-9]*'),
    file_key INTEGER NOT NULL REFERENCES raw_file(file_key),
    retrieved_at TEXT NOT NULL CHECK(length(retrieved_at) = 27 AND substr(retrieved_at,27) = 'Z' AND julianday(retrieved_at) IS NOT NULL)
) STRICT;

CREATE TABLE IF NOT EXISTS phone_item_link (
    phone_key INTEGER NOT NULL REFERENCES phone(phone_key),
    item_key INTEGER NOT NULL REFERENCES wikidata_item(item_key),
    article_url TEXT,
    file_key INTEGER NOT NULL REFERENCES raw_file(file_key),
    retrieved_at TEXT NOT NULL CHECK(length(retrieved_at) = 27 AND substr(retrieved_at,27) = 'Z' AND julianday(retrieved_at) IS NOT NULL),
    PRIMARY KEY(phone_key, item_key)
) STRICT;

CREATE TABLE IF NOT EXISTS wikipedia_article (
    article_key INTEGER PRIMARY KEY NOT NULL,
    source_id TEXT NOT NULL UNIQUE CHECK(source_id <> '' AND source_id NOT GLOB '*[^0-9]*'),
    title TEXT NOT NULL,
    item_key INTEGER REFERENCES wikidata_item(item_key),
    file_key INTEGER NOT NULL REFERENCES raw_file(file_key),
    retrieved_at TEXT NOT NULL CHECK(length(retrieved_at) = 27 AND substr(retrieved_at,27) = 'Z' AND julianday(retrieved_at) IS NOT NULL)
) STRICT;

CREATE TABLE IF NOT EXISTS article_revision (
    article_key INTEGER NOT NULL REFERENCES wikipedia_article(article_key),
    revision_at TEXT NOT NULL CHECK(length(revision_at) = 27 AND substr(revision_at,27) = 'Z' AND julianday(revision_at) IS NOT NULL),
    content TEXT NOT NULL,
    file_key INTEGER NOT NULL REFERENCES raw_file(file_key),
    retrieved_at TEXT NOT NULL CHECK(length(retrieved_at) = 27 AND substr(retrieved_at,27) = 'Z' AND julianday(retrieved_at) IS NOT NULL),
    PRIMARY KEY(article_key, revision_at)
) STRICT;

CREATE TABLE IF NOT EXISTS quarantine (
    file_key INTEGER NOT NULL REFERENCES raw_file(file_key),
    record_key TEXT NOT NULL,
    reason TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
    retrieved_at TEXT NOT NULL CHECK(length(retrieved_at) = 27 AND substr(retrieved_at,27) = 'Z' AND julianday(retrieved_at) IS NOT NULL),
    PRIMARY KEY(file_key, record_key)
) STRICT;

CREATE INDEX IF NOT EXISTS specification_field ON specification(source_field, phone_key, retrieved_at);
CREATE INDEX IF NOT EXISTS phone_item_by_item ON phone_item_link(item_key);
