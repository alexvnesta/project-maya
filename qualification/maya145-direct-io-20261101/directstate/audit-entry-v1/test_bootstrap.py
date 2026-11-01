"""CPU-only isolated-import regression. Synthetic modules cannot launch a model."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import bootstrap as b

class Entry(unittest.TestCase):
    def fixture(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        root=Path(temp.name).resolve();entry=root/'audit-entry-v1';entry.mkdir()
        (entry/'bootstrap.py').write_bytes(Path(b.__file__).read_bytes())
        (root/'direct_io.py').write_text('VALUE=17\n')
        for n in ('current_runtime.py','current_config.py','current_controls.py'):(root/n).write_text('# synthetic only\n')
        (root/'current_audit.py').write_text("import sys,direct_io\ndef run(pin,arm,binding):\n return {'passed':direct_io.VALUE==17 and binding=={'native_pid':71} and sys.modules[__name__].run is run,'arm':arm}\n")
        q={'mode':'directstate','files':{str(root/n):b.sha(root/n) for n in ('current_audit.py','direct_io.py','current_runtime.py','current_config.py','current_controls.py')}}
        f=root/'directstate-qualification.json';f.write_text(json.dumps(q));return root,b.sha(f)
    def test_real_isolated_subprocess_resolves_qualified_local_import(self):
        root,pin=self.fixture()
        v=subprocess.run([sys.executable,'-I','-B',str(root/'audit-entry-v1/bootstrap.py'),'--qualification-sha256',pin,'--binding-json','{"native_pid":71}'],capture_output=True,text=True,timeout=5)
        self.assertEqual(v.returncode,0,v.stderr);self.assertEqual(json.loads(v.stdout),{'passed':True,'arm':'ITP2','original_failed_entry_preserved':True})
    def test_changed_dependency_rejected_before_import(self):
        root,pin=self.fixture();(root/'current_audit.py').write_text('raise AssertionError("must not import")\n')
        with self.assertRaisesRegex(ValueError,'dependency'):b.execute(root,pin,'ITP2',{})
    def test_wrong_pin_or_arm_rejected_before_import(self):
        root,pin=self.fixture()
        for p,a in [('0'*64,'ITP2'),(pin,'ITP1')]:
            with self.assertRaises(ValueError):b.execute(root,p,a,{})
    def test_wrong_mode_rejected_before_import(self):
        root,pin=self.fixture();f=root/'directstate-qualification.json';q=json.loads(f.read_text());q['mode']='other';f.write_text(json.dumps(q))
        with self.assertRaisesRegex(ValueError,'mode'):b.execute(root,b.sha(f),'ITP2',{})
