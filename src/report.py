"""Print the checked-in evidence coverage query against the derived database."""
import argparse
from pathlib import Path

from db import ROOT, DEFAULT_DB, connect


def report(database=DEFAULT_DB):
    con = connect(database, read_only=True)
    try:
        cursor = con.execute((ROOT / 'sql' / 'queries' / 'price_coverage.sql').read_text(encoding='utf-8'))
        print(' | '.join(column[0] for column in cursor.description))
        for row in cursor:
            print(' | '.join(str(value) for value in row))
    finally:
        con.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=DEFAULT_DB)
    report(parser.parse_args().db)
