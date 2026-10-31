"""New CPU-parent custody and idle deferral controls. No native or service execution."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
import ae_cpu as m


class CPU(unittest.TestCase):
    def test_busy_parent_prevents_source_hashes_metadata_and_child(self):
        with patch.object(m,'physical_idle',side_effect=ValueError('busy')),patch.object(m,'checked') as checked,patch.object(m.subprocess,'Popen') as child:
            with self.assertRaisesRegex(ValueError,'busy'):m.main('a'*64,'owner')
        checked.assert_not_called();child.assert_not_called()
    def test_busy_child_prevents_test_discovery(self):
        with patch.object(m,'physical_idle',side_effect=ValueError('busy')),patch.object(m,'checked') as checked,patch.object(m.unittest.defaultTestLoader,'loadTestsFromName') as load:
            with self.assertRaisesRegex(ValueError,'busy'):m.child('a'*64,Path('/unused'),'owner')
        checked.assert_not_called();load.assert_not_called()
    def test_mac_guard_never_imports_or_connects(self):
        with patch.object(m.sys,'platform','darwin'),patch.object(m,'sha') as hashed:
            self.assertIsNone(m.physical_idle())
        hashed.assert_not_called()
    def test_foreign_cached_linux_bootstrap_refused(self):
        from types import SimpleNamespace as NS
        with patch.object(m.sys,'platform','linux'),patch.object(m,'sha',return_value='8858c1d2f70cd7e97d416fa1535cb1af18f1a2647731c2d88e7c36d66b0e5bad'),patch.dict(m.sys.modules,{'ms_audit_dispatch':NS(__file__='/foreign.py')}):
            with self.assertRaisesRegex(ValueError,'Foreign'):m.physical_idle()
    def test_relative_input_traversal_and_symlink_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();(root/'real').write_text('x');(root/'alias').symlink_to(root/'real')
            with patch.object(m,'E',root):
                for name in ('../real','/real','alias','.'):
                    with self.subTest(name=name),self.assertRaises(ValueError):m.canonical_input(name)
                self.assertEqual(m.canonical_input('real'),root/'real')
    def test_child_limits_are_child_only_and_fixed(self):
        with patch.object(m.os,'nice') as nice,patch.object(m.resource,'setrlimit') as limits,patch.object(m.sys,'platform','linux'):
            m.limits()
        nice.assert_called_once_with(15)
        self.assertEqual(limits.call_args_list[0].args,(m.resource.RLIMIT_CPU,(30,30)))
        self.assertEqual(limits.call_args_list[1].args,(m.resource.RLIMIT_AS,(512*1024**2,512*1024**2)))
    def parent(self,write_receipt):
        from types import SimpleNamespace as NS
        stack=[];self.addCleanup(lambda:[p.stop() for p in reversed(stack)])
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);root=Path(temp.name).resolve()
        before=({'ae.py':'a'*64},{'input.json':'b'*64},['test_new.Case.test_control'])
        def apply(obj,key,value):
            p=patch.object(obj,key,value);stack.append(p);p.start()
        apply(m,'HERE',root);apply(m.sys,'platform','darwin');apply(m,'physical_idle',Mock());apply(m,'checked',Mock(return_value=before));apply(m,'cleanup',Mock(return_value=[]))
        def launch(command,**kw):
            self.assertEqual(command,[m.sys.executable,'-B',str(root/'ae_cpu.py'),'--review-sha','a'*64,'--child',str(root/'owner-CPU-AE1-FIRST-darwin'),'--group','owner'])
            self.assertTrue(kw['start_new_session']);self.assertIs(kw['preexec_fn'],m.limits);self.assertEqual(kw['env']['CUDA_VISIBLE_DEVICES'],'')
            if write_receipt:
                r={'pid':123,'group':'owner','passed':True,'controls':1,'test_ids':before[2],
                    'source_sha256':before[0],'input_sha256':before[1],'CPU_seconds':[30,30],
                    'Linux_AS_bytes':None,'nice':15,'environment':m.ENV}
                (root/'owner-CPU-AE1-FIRST-darwin/receipt.json').write_text(json.dumps(r))
            return NS(pid=123,wait=Mock(return_value=0))
        apply(m.subprocess,'Popen',Mock(side_effect=launch));return root
    def test_parent_command_and_actual_receipt_custody(self):
        root=self.parent(True);self.assertEqual(m.main('a'*64,'owner'),0)
        record=json.loads((root/'owner-CPU-AE1-FIRST-darwin/child.json').read_text())
        self.assertEqual(record['pid'],123);self.assertEqual(record['returncode'],0);self.assertEqual(record['cleanup_errors'],[])
    def test_child0_missing_receipt_is_not_CPU_success(self):
        root=self.parent(False);self.assertEqual(m.main('a'*64,'owner'),1)
        record=json.loads((root/'owner-CPU-AE1-FIRST-darwin/child.json').read_text());self.assertTrue(record['cleanup_errors'])
    def test_AST_discovery_names_all_new_modules_and_driver_tests(self):
        for group in m.GROUPS:
            ids=m.ids(group);self.assertTrue(ids);self.assertEqual(ids,sorted(set(ids)))
        self.assertIn('test_ae_cpu.py',m.SOURCES)


if __name__=='__main__':unittest.main()
