"""Actual helper guard only; generated code is parsed but never executed."""
import ast
from pathlib import Path
import unittest
HERE=Path(__file__).resolve().parent
source=(HERE/'review_code.py').read_text();node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='reviewed_helper')
namespace={'ast':ast};exec(compile(ast.Module(body=[node],type_ignores=[]),'reviewed-helper-guard','exec'),namespace);allowed=namespace['reviewed_helper']
ACTUAL=(HERE/'generated_code.py').read_text()
HELPER=ast.get_source_segment(ACTUAL,ast.parse(ACTUAL).body[2])

def helper(text):return ast.parse(text).body[0]

class Guard(unittest.TestCase):
    def test_actual_exact_helper(self):self.assertTrue(allowed(helper(HELPER)))
    def test_actual_main_and_all16_supplied_tests_are_still_unexecuted(self):
        tree=ast.parse(ACTUAL);self.assertEqual([n.name for n in tree.body if isinstance(n,ast.FunctionDef)],['_require_integer_endpoint','coalesce_ranges']);self.assertEqual(sum(isinstance(n,ast.FunctionDef) and n.name.startswith('test_') for c in tree.body if isinstance(c,ast.ClassDef) for n in c.body),16)
    def test_different_helper_name_refused(self):bad=HELPER.replace('_require_integer_endpoint','other');self.assertFalse(allowed(helper(bad)))
    def test_bool_accepting_helper_refused(self):bad=HELPER.replace('isinstance(value, bool) or ','');self.assertFalse(allowed(helper(bad)))
    def test_float_accepting_helper_refused(self):bad=HELPER.replace('isinstance(value, int)','isinstance(value, (int, float))');self.assertFalse(allowed(helper(bad)))
    def test_changed_operator_refused(self):bad=HELPER.replace(' or ',' and ');self.assertFalse(allowed(helper(bad)))
    def test_coercion_or_extra_return_refused(self):bad=HELPER+'\n    return int(value)\n';self.assertFalse(allowed(helper(bad)))
    def test_extra_side_effect_refused(self):bad=HELPER+'\n    open("anything")\n';self.assertFalse(allowed(helper(bad)))
    def test_import_refused(self):bad=HELPER+'\n    import os\n';self.assertFalse(allowed(helper(bad)))
    def test_decorator_refused(self):bad='@unsafe\n'+HELPER;self.assertFalse(allowed(helper(bad)))
    def test_changed_error_type_refused(self):bad=HELPER.replace('TypeError','ValueError');self.assertFalse(allowed(helper(bad)))
    def test_default_argument_refused(self):bad=HELPER.replace('(value):','(value=0):');self.assertFalse(allowed(helper(bad)))

if __name__=='__main__':unittest.main()
