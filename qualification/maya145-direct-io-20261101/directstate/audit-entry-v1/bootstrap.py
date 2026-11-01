"""Isolated CPU entry for the unchanged qualified saved-data auditor.

The first direct script invocation failed at import, before run() entered.
This entry supplies the same explicit local import path as the qualified CPU
driver. It changes no auditor checks, receipts, model result or source pins.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def execute(root,pin,arm,binding):
    root=Path(root)
    path=root/'directstate-qualification.json'
    if arm!='ITP2' or sha(path)!=pin:raise ValueError('Exact single admitted diagnostic qualification')
    q=json.loads(path.read_text())
    if q.get('mode')!='directstate':raise ValueError('Exact diagnostic mode')
    # Check local imports before loading code, then use the original auditor's
    # full immutable/source/CPU/raw-result/restoration checks without alteration.
    for name in ('current_audit.py','direct_io.py','current_runtime.py','current_config.py','current_controls.py'):
        file=root/name
        if file.is_symlink() or q['files'].get(str(file))!=sha(file):raise ValueError('Qualified local dependency changed')
    sys.path.insert(0,str(root))
    spec=importlib.util.spec_from_file_location('directstate_saved_auditor',root/'current_audit.py')
    if spec.name in sys.modules:raise ValueError('Foreign cached auditor')
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module
    spec.loader.exec_module(module)
    return module.run(pin,arm,binding)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qualification-sha256',required=True)
    parser.add_argument('--binding-json',required=True)
    a=parser.parse_args()
    value=execute(Path(__file__).resolve().parents[1],a.qualification_sha256,'ITP2',json.loads(a.binding_json))
    print(json.dumps({'passed':value['passed'],'arm':value['arm'],'original_failed_entry_preserved':True}))

if __name__=='__main__':main()
