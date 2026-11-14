"""Verify M4 against an independently rebuilt M2/M3 database."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from explore import database_hash
from verify_m3 import digest
from run_m4_eda import run

NBCONVERT=['-m','jupyter','nbconvert','--to','notebook','--execute','--inplace','notebooks/m4_eda.ipynb']


def run_nbconvert(database):
    """Execute the notebook with the course command, against the given database."""
    env=dict(os.environ,PHONE_M4_DB=str(database))
    subprocess.run([sys.executable,*NBCONVERT],cwd=ROOT,env=env,check=True)


def generated_hashes():
    paths=sorted((ROOT/'figures').glob('*.svg'))+[ROOT/'docs/eda_report.md',ROOT/'docs/m4/results.json']
    return {str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def sql_scan():
    """Reject direct formatting at execution and obvious formatted SQL assignments.

    This is a focused static guard, complemented by review of the fixed SQL
    files and binding calls; it is not a general SQL taint-analysis proof.
    """
    errors=[]
    non_sql=[]
    files=[p for folder in ['src','scripts','tests'] for p in (ROOT/folder).glob('*.py')]
    sources=[(str(p.relative_to(ROOT)),p.read_text(encoding='utf-8-sig')) for p in files]
    for p in (ROOT/'notebooks').glob('*.ipynb'):
        notebook=json.loads(p.read_text(encoding='utf-8'))
        sources.extend((str(p.relative_to(ROOT))+' cell '+str(i),''.join(c['source'])) for i,c in enumerate(notebook['cells']) if c['cell_type']=='code')
    for name,source in sources:
        for node in ast.walk(ast.parse(source)):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr in ['execute','executemany','executescript'] and node.args:
                arg=node.args[0]
                if isinstance(arg,(ast.JoinedStr,ast.BinOp)) or (isinstance(arg,ast.Call) and isinstance(arg.func,ast.Attribute) and arg.func.attr=='format'):
                    errors.append(name+':'+str(node.lineno))
            if isinstance(node,ast.JoinedStr) and node.values and isinstance(node.values[0],ast.Constant):
                prefix=str(node.values[0].value)
                if re.match(r'^\s*SELECT\s+\?',prefix,re.I) and 'wdt:P4723' in prefix:
                    non_sql.append(dict(source=name+':'+str(node.lineno),language='Wikidata SPARQL; HTTP query, not SQLite SQL'))
                elif re.match(r'^\s*(SELECT|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|PRAGMA)\b',prefix,re.I):
                    errors.append(name+':'+str(node.lineno))
    return dict(sources_checked=len(sources),formatting_violations=errors,
                non_sql_queries=non_sql,
                scope='Python modules and notebook code cells; direct execution formatting and formatted SQL literals')


def verify(fresh,baseline,nbconvert=False,fresh_note=None):
    execute=run_nbconvert if nbconvert else run
    raw_base,clean_base=digest(baseline)
    raw_fresh,clean_fresh=digest(fresh)
    assert raw_base==raw_fresh,'Fresh M2 rows differ'
    assert clean_base==clean_fresh,'Fresh M3 rows differ'
    before_fresh=database_hash(fresh)
    execute(fresh)
    after_fresh=database_hash(fresh)
    generated_fresh=generated_hashes()
    before_baseline=database_hash(baseline)
    execute(baseline)
    after_baseline=database_hash(baseline)
    generated_baseline=generated_hashes()
    scan=sql_scan()
    if nbconvert:
        execution='python '+' '.join(NBCONVERT)+' on both databases, after a restart (new kernel)'
    else:
        execution='Every notebook Python cell executed in a fresh namespace (scripts/run_m4_eda.py)'
    evidence=dict(fresh_database=fresh.relative_to(ROOT).as_posix(),
                  baseline_database=baseline.relative_to(ROOT).as_posix(),
                  fresh_build=fresh_note,
                  m2_full_row_hashes=raw_fresh,m3_full_row_hashes=clean_fresh,
                  fresh_matches_m2=raw_base==raw_fresh,fresh_matches_m3=clean_base==clean_fresh,
                  fresh_database_sha256_before=before_fresh,fresh_database_sha256_after=after_fresh,
                  baseline_database_sha256_before=before_baseline,baseline_database_sha256_after=after_baseline,
                  database_bytes_unchanged=(before_fresh==after_fresh and before_baseline==after_baseline),
                  generated_files_match=generated_fresh==generated_baseline,
                  generated_sha256=generated_baseline,sql_formatting_scan=scan,
                  execution=execution)
    (ROOT/'docs/m4/fresh-build-verification.json').write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8',newline='\n')
    assert evidence['database_bytes_unchanged']
    assert evidence['generated_files_match']
    assert not scan['formatting_violations'],scan
    print('PASS: fresh M2/M3 rows match; notebook runs on both databases; report/results/figures match; both databases unchanged; SQL scan clean')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,required=True,help='Already independently rebuilt M2/M3 database')
    parser.add_argument('--baseline',type=Path,default=ROOT/'data/phones.db')
    parser.add_argument('--nbconvert',action='store_true',help='Execute with jupyter nbconvert (the course command) instead of the runner')
    parser.add_argument('--fresh-note',help='How the fresh database was built, recorded in the evidence file')
    args=parser.parse_args()
    verify(args.db.resolve(),args.baseline.resolve(),args.nbconvert,args.fresh_note)
