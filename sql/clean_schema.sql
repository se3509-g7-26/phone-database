CREATE TABLE IF NOT EXISTS phone_clean (
    phone_key INTEGER PRIMARY KEY NOT NULL REFERENCES phone(phone_key),
    name_raw TEXT NOT NULL,
    name TEXT,
    name_flag TEXT NOT NULL CHECK(name_flag IN ('ok','text_normalized','missing_token','missing_not_reported'))
) STRICT;

CREATE TABLE IF NOT EXISTS specification_clean (
    phone_key INTEGER NOT NULL REFERENCES phone(phone_key),
    retrieved_at TEXT NOT NULL,
    row_number INTEGER NOT NULL,
    value_raw TEXT,
    value TEXT,
    value_flag TEXT NOT NULL CHECK(value_flag IN ('ok','text_normalized','missing_token','missing_not_reported')),
    number_raw TEXT,
    number REAL,
    ram_gb REAL,
    unit TEXT,
    number_flag TEXT NOT NULL CHECK(number_flag IN ('ok','missing_not_reported','missing_token','not_applicable','unparsed','ambiguous','invalid_nonpositive','invalid_year','unit_converted','unusual_low','unusual_high')),
    category_raw TEXT,
    category TEXT,
    category_flag TEXT NOT NULL CHECK(category_flag IN ('mapped','unmapped','not_applicable','missing_not_reported')),
    source_field TEXT,
    file_key INTEGER NOT NULL REFERENCES raw_file(file_key),
    PRIMARY KEY(phone_key,retrieved_at,row_number),
    FOREIGN KEY(phone_key,retrieved_at,row_number) REFERENCES specification(phone_key,retrieved_at,row_number)
) STRICT;

CREATE TABLE IF NOT EXISTS field_rule_map (
    source_field TEXT PRIMARY KEY NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('price','year','memory','weight','display','battery')),
    unit TEXT NOT NULL,
    decided_by TEXT NOT NULL,
    decided_at TEXT NOT NULL,
    note TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS os_category_map (
    alias TEXT PRIMARY KEY NOT NULL,
    category TEXT NOT NULL,
    decided_by TEXT NOT NULL,
    decided_at TEXT NOT NULL,
    note TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS currency_map (
    alias TEXT PRIMARY KEY NOT NULL,
    currency TEXT NOT NULL,
    decided_by TEXT NOT NULL,
    decided_at TEXT NOT NULL,
    note TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS phone_identity_map (
    phone_key INTEGER PRIMARY KEY NOT NULL REFERENCES phone(phone_key),
    canonical_phone_key INTEGER NOT NULL REFERENCES phone(phone_key),
    decided_by TEXT NOT NULL,
    decided_at TEXT NOT NULL,
    note TEXT NOT NULL,
    CHECK(phone_key <> canonical_phone_key)
) STRICT;

CREATE VIEW IF NOT EXISTS phone_resolved AS
SELECT p.*, c.name AS clean_name, COALESCE(m.canonical_phone_key,p.phone_key) AS resolved_phone_key
FROM phone p JOIN phone_clean c USING(phone_key)
LEFT JOIN phone_identity_map m USING(phone_key);

CREATE VIEW IF NOT EXISTS specification_resolved AS
SELECT s.*, p.name AS phone_name, p.source_id, COALESCE(m.canonical_phone_key,s.phone_key) AS resolved_phone_key
FROM specification_clean s JOIN phone p USING(phone_key)
LEFT JOIN phone_identity_map m USING(phone_key);

CREATE VIEW IF NOT EXISTS specification_current AS
SELECT s.* FROM specification_resolved s
JOIN phone p ON p.phone_key=s.phone_key AND p.retrieved_at=s.retrieved_at;
