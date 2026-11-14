"""Restart and execute every ordinary Python notebook cell, without Jupyter.

Equivalent dependency-free execution route; a fresh namespace and working
directory make execution order explicit. Errors abort without saving success.
The notebook also supports the course's normal nbconvert execution command.
"""
import argparse
import contextlib
import io
import json
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def run(database=None):
    path=ROOT/'notebooks/m4_eda.ipynb'
    notebook=json.loads(path.read_text(encoding='utf-8'))
    namespace={'__name__':'__main__'}
    previous=Path.cwd()
    previous_database=os.environ.get('PHONE_M4_DB')
    if database:
        os.environ['PHONE_M4_DB']=str(Path(database).resolve())
    try:
        os.chdir(ROOT)
        count=0
        for cell in notebook['cells']:
            if cell['cell_type']!='code':continue
            count+=1
            output=io.StringIO()
            with contextlib.redirect_stdout(output):
                exec(compile(''.join(cell['source']),str(path)+' cell '+str(count),'exec'),namespace)
            cell['execution_count']=count
            cell['outputs']=[dict(output_type='stream',name='stdout',text=output.getvalue().splitlines(keepends=True))]
            print('Executed cell',count)
        path.write_text(json.dumps(notebook,indent=1)+'\n',encoding='utf-8',newline='\n')
    finally:
        os.chdir(previous)
        if previous_database is None:os.environ.pop('PHONE_M4_DB',None)
        else:os.environ['PHONE_M4_DB']=previous_database
    print('PASS: executed and saved',count,'code cells in notebooks/m4_eda.ipynb')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path)
    run(parser.parse_args().db)
