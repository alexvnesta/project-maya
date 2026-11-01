"""Exact new import/sort-key guards; generated code is parsed, never run."""
import ast
import hashlib
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
reviewer = ast.parse((HERE / 'review_code.py').read_text())
nodes = [n for n in reviewer.body if isinstance(n, ast.FunctionDef)
         and n.name in ('reviewed_import_from', 'reviewed_sort_key')]
namespace = {'ast': ast}
exec(compile(ast.Module(body=nodes, type_ignores=[]), 'exact-guard-only', 'exec'), namespace)
allowed_import = namespace['reviewed_import_from']
allowed_key = namespace['reviewed_sort_key']
actual = ast.parse((HERE / 'generated_code.py').read_text())

def imported(text):
    return ast.parse(text).body[0]

def key(text):
    return ast.parse(text, mode='eval').body

class Guard(unittest.TestCase):
    def test_actual_exact_deepcopy_import(self):
        self.assertTrue(allowed_import(actual.body[1]))

    def test_copy_alias_refused(self):
        self.assertFalse(allowed_import(imported('from copy import deepcopy as alias')))

    def test_other_copy_function_refused(self):
        self.assertFalse(allowed_import(imported('from copy import copy')))

    def test_copy_wildcard_refused(self):
        self.assertFalse(allowed_import(imported('from copy import *')))

    def test_process_import_refused(self):
        self.assertFalse(allowed_import(imported('from os import system')))

    def test_actual_exact_start_key(self):
        keys = [n for n in ast.walk(actual) if isinstance(n, ast.Lambda)]
        self.assertEqual(len(keys), 1)
        self.assertTrue(allowed_key(keys[0]))

    def test_changed_index_refused(self):
        self.assertFalse(allowed_key(key('lambda interval: interval[1]')))

    def test_changed_parameter_refused(self):
        self.assertFalse(allowed_key(key('lambda other: other[0]')))

    def test_side_effect_key_refused(self):
        self.assertFalse(allowed_key(key('lambda interval: open("anything")')))

    def test_different_tuple_key_refused(self):
        self.assertFalse(allowed_key(key('lambda interval: (interval[0], interval[1])')))

    def test_actual_module_and_all18_tests_still_unexecuted(self):
        self.assertEqual([n.name for n in actual.body if isinstance(n, ast.FunctionDef)],
                         ['coalesce_ranges'])
        self.assertEqual(sum(isinstance(n, ast.FunctionDef) and n.name.startswith('test_')
                             for c in actual.body if isinstance(c, ast.ClassDef)
                             for n in c.body), 18)

    def test_reference_and_all_four_negatives_unchanged(self):
        expected = json.loads((HERE / 'ROOT_FULL_GENERATED_SOURCE_REVIEW.json').read_text())[
            'unchanged_reference_and_negative_AST_sha256']
        observed = {n.name: hashlib.sha256(ast.dump(n).encode()).hexdigest()
                    for n in reviewer.body if isinstance(n, ast.FunctionDef) and n.name in expected}
        self.assertEqual(observed, expected)

if __name__ == '__main__':
    unittest.main()
