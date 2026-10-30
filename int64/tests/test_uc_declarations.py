import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from uc_declarations import normalize, strip_constructive


class DeclarationTests(unittest.TestCase):
    def test_forward_struct_preserves_variable_order(self):
        source = 'class C extends Object;\nvar int X;\nvar S Y;\nstruct S { var int Z; };\nvar int W;'
        result, moved = normalize(source)
        self.assertEqual(moved, ['s'])
        self.assertLess(result.index('struct S'), result.index('var S Y'))
        self.assertLess(result.index('var int X'), result.index('var S Y'))
        self.assertLess(result.index('var S Y'), result.index('var int W'))
        self.assertEqual(normalize(result), (result, []))

    def test_dependencies_constants_enum_and_comments(self):
        source = '''class C extends Object;
var A Value;
struct A { var B Member; var int Data[Count]; };
const Count=4;
struct B { var E Kind; };
enum E { First, Second };
function F() { Log("struct Bogus { }; // "); /* enum NotAType {} */ }
'''
        result, names = normalize(source)
        self.assertEqual(names, ['count', 'e', 'b', 'a'])
        self.assertIn('function F() { Log("struct Bogus { }; // "); /* enum NotAType {} */ }', result)

    def test_var_const_is_not_a_declaration(self):
        source = 'class C extends Object; var const int X; function F() { local int Y; }'
        self.assertEqual(normalize(source), (source, []))

    def test_cycle_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize('class C; struct A {var B BValue;}; struct B {var A AValue;};')

    def test_native_struct_and_crlf(self):
        source = 'class C;\r\nvar S V;\r\nstruct native S {var int X;};\r\n'
        result, names = normalize(source)
        self.assertEqual(names, ['s'])
        self.assertNotIn('\n', result.replace('\r\n', ''))

    def test_exec_directive_does_not_hide_enum(self):
        source = 'class C;\n#exec Texture Import File=foo.pcx\nenum E { A };\nstruct S { var E V; };\nvar S Value;'
        result, _ = normalize(source)
        self.assertLess(result.index('enum E'), result.index('struct S'))
        self.assertIn('#exec Texture Import File=foo.pcx', result)

    def test_inline_enum_keeps_property_position(self):
        source = 'class C; var int Before; var(Movement) const enum E {A, B} Mode; struct S {var E V;}; var int After;'
        result, names = normalize(source)
        self.assertIn('e', names)
        self.assertIn('var(Movement) const E Mode;', result)
        self.assertLess(result.index('enum E'), result.index('struct S'))
        self.assertLess(result.index('var int Before'), result.index('const E Mode'))
        self.assertLess(result.index('const E Mode'), result.index('var int After'))
        self.assertEqual(normalize(result), (result, []))

    def test_constructive_is_header_only(self):
        source = 'class C; struct native constructive S {var int X;}; function F(){Log("constructive");}'
        result, names = strip_constructive(source)
        self.assertEqual(names, ['S'])
        self.assertIn('struct native  S {var int X;}', result)
        self.assertIn('Log("constructive")', result)
        self.assertEqual(strip_constructive('class C; struct constructive {var int X;};')[1], [])


if __name__ == '__main__':
    unittest.main()
