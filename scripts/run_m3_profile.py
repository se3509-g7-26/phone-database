"""Execute the plain-Python notebook cells in order and save their outputs.

No Jupyter dependency is needed. The notebook also runs normally in Jupyter.
"""
import contextlib
import io
import json
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[1]


def run():
    path = ROOT/'notebooks'/'m3_profile.ipynb'
    notebook = json.loads(path.read_text(encoding='utf-8'))
    namespace = {'__name__':'__main__'}
    old = Path.cwd()
    try:
        os.chdir(ROOT)
        count = 0
        for cell in notebook['cells']:
            if cell['cell_type'] != 'code':
                continue
            count += 1
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exec(compile(''.join(cell['source']),str(path)+' cell '+str(count),'exec'),namespace)
            cell['execution_count'] = count
            cell['outputs'] = [{'output_type':'stream','name':'stdout','text':output.getvalue().splitlines(keepends=True)}]
        path.write_text(json.dumps(notebook,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    finally:
        os.chdir(old)
    print('Executed and saved '+str(count)+' cells: notebooks/m3_profile.ipynb')


if __name__ == '__main__':
    run()
