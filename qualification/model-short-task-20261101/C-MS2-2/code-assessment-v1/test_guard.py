"""Only exact helper/constant-format AST guards; generated code stays unexecuted."""
import ast
import hashlib
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
reviewer = ast.parse((HERE / 'review_code.py').read_text())
nodes = [n for n in reviewer.body if
         (isinstance(n, ast.FunctionDef) and n.name in ('reviewed_helper', 'reviewed_error_format', 'reviewed_import_from'))
         or (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'ERROR_FORMATS' for t in n.targets))]
namespace = {'ast': ast}
exec(compile(ast.Module(body=nodes, type_ignores=[]), 'exact-guards-only', 'exec'), namespace)
allowed_helper = namespace['reviewed_helper']
allowed_format = namespace['reviewed_error_format']
actual_source = (HERE / 'generated_code.py').read_text()
actual = ast.parse(actual_source)
helper_source = ast.get_source_segment(actual_source, actual.body[3])

def helper(text):
    return ast.parse(text).body[0]

def call(text):
    return ast.parse(text, mode='eval').body

class Guard(unittest.TestCase):
    def test_actual_exact_helper(self):
        self.assertTrue(allowed_helper(helper(helper_source)))

    def test_helper_rename_refused(self):
        self.assertFalse(allowed_helper(helper(helper_source.replace('_is_integer_endpoint', 'other'))))

    def test_helper_float_accepting_refused(self):
        self.assertFalse(allowed_helper(helper(helper_source.replace('value, int', 'value, (int, float)'))))

    def test_helper_bool_accepting_refused(self):
        self.assertFalse(allowed_helper(helper(helper_source.replace(' and not isinstance(value, bool)', ''))))

    def test_actual_main_has_no_formats(self):
        calls = [n for n in ast.walk(actual.body[4]) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute) and n.func.attr == 'format']
        self.assertEqual(calls, [])

    def test_changed_message_refused(self):
        self.assertFalse(allowed_format(call('"bad {}".format(index)')))

    def test_field_attribute_refused(self):
        self.assertFalse(allowed_format(call('"{0.__class__}".format(index)')))

    def test_keyword_format_refused(self):
        self.assertFalse(allowed_format(call('"range at index {} must be a pair".format(index=index)')))

    def test_extra_format_argument_refused(self):
        self.assertFalse(allowed_format(call('"range at index {} must be a pair".format(index, index)')))

    def test_dynamic_receiver_refused(self):
        self.assertFalse(allowed_format(call('message.format(index)')))

    def test_actual_module_all21_supplied_tests_still_unexecuted(self):
        self.assertEqual([n.name for n in actual.body if isinstance(n, ast.FunctionDef)],
                         ['_is_integer_endpoint', 'coalesce_ranges'])
        self.assertEqual(sum(isinstance(n, ast.FunctionDef) and n.name.startswith('test_')
                             for c in actual.body if isinstance(c, ast.ClassDef) for n in c.body), 21)

    def test_actual_sequence_import_is_exact(self):
        self.assertTrue(namespace['reviewed_import_from'](actual.body[1]))
        self.assertEqual(ast.dump(actual.body[1]), ast.dump(ast.parse('from collections.abc import Sequence').body[0]))

    def test_other_collection_import_refused(self):
        self.assertFalse(namespace['reviewed_import_from'](ast.parse('from collections.abc import Callable').body[0]))

    def test_reference_and_all_four_negatives_unchanged(self):
        expected = json.loads((HERE / 'ROOT_FULL_GENERATED_SOURCE_REVIEW.json').read_text())[
            'unchanged_reference_and_negative_AST_sha256']
        observed = {n.name: hashlib.sha256(ast.dump(n).encode()).hexdigest()
                    for n in reviewer.body if isinstance(n, ast.FunctionDef) and n.name in expected}
        self.assertEqual(observed, expected)

if __name__ == '__main__':
    unittest.main()
