"""Exact helper and endpoint casts; no generated implementation execution."""
import ast
import hashlib
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
reviewer = ast.parse((HERE / 'review_code.py').read_text())
nodes = [n for n in reviewer.body if isinstance(n, ast.FunctionDef)
         and n.name in ('reviewed_helper', 'reviewed_int_normalizer')]
namespace = {'ast': ast}
exec(compile(ast.Module(body=nodes, type_ignores=[]), 'exact-guards-only', 'exec'), namespace)
allowed_helper = namespace['reviewed_helper']
allowed_int = namespace['reviewed_int_normalizer']
actual_source = (HERE / 'generated_code.py').read_text()
actual = ast.parse(actual_source)
helper_source = ast.get_source_segment(actual_source, actual.body[1])

def helper(text):
    return ast.parse(text).body[0]

def call(text):
    return ast.parse(text, mode='eval').body

class Guard(unittest.TestCase):
    def test_actual_exact_helper(self):
        self.assertTrue(allowed_helper(helper(helper_source)))

    def test_helper_rename_refused(self):
        self.assertFalse(allowed_helper(helper(helper_source.replace('_is_integer', 'other'))))

    def test_bool_accepting_helper_refused(self):
        self.assertFalse(allowed_helper(helper(helper_source.replace(' and not isinstance(value, bool)', ''))))

    def test_float_accepting_helper_refused(self):
        self.assertFalse(allowed_helper(helper(helper_source.replace('value, int', 'value, (int, float)'))))

    def test_helper_decorator_refused(self):
        self.assertFalse(allowed_helper(helper('@unsafe\n' + helper_source)))

    def test_helper_side_effect_refused(self):
        self.assertFalse(allowed_helper(helper(helper_source + '\n    open("anything")\n')))

    def test_actual_exact_two_endpoint_casts(self):
        casts = [n for n in ast.walk(actual.body[2]) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name) and n.func.id == 'int']
        self.assertEqual(len(casts), 2)
        self.assertEqual({ast.dump(n) for n in casts}, {ast.dump(call('int(start)')), ast.dump(call('int(end)'))})
        self.assertTrue(all(allowed_int(n) for n in casts))

    def test_cast_literal_refused(self):
        self.assertFalse(allowed_int(call('int(0)')))

    def test_cast_other_name_refused(self):
        self.assertFalse(allowed_int(call('int(value)')))

    def test_cast_extra_argument_refused(self):
        self.assertFalse(allowed_int(call('int(start, base=10)')))

    def test_actual_module_all14_supplied_tests_still_unexecuted(self):
        self.assertEqual([n.name for n in actual.body if isinstance(n, ast.FunctionDef)],
                         ['_is_integer', 'coalesce_ranges'])
        self.assertEqual(sum(isinstance(n, ast.FunctionDef) and n.name.startswith('test_')
                             for c in actual.body if isinstance(c, ast.ClassDef) for n in c.body), 14)

    def test_reference_and_all_four_negatives_unchanged(self):
        expected = json.loads((HERE / 'ROOT_FULL_GENERATED_SOURCE_REVIEW.json').read_text())[
            'unchanged_reference_and_negative_AST_sha256']
        observed = {n.name: hashlib.sha256(ast.dump(n).encode()).hexdigest()
                    for n in reviewer.body if isinstance(n, ast.FunctionDef) and n.name in expected}
        self.assertEqual(observed, expected)

if __name__ == '__main__':
    unittest.main()
