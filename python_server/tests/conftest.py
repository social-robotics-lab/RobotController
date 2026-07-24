"""Test configuration and Python AST compatibility helpers."""

import ast
import os
import sys


def _ast_string_value(node, ast_module=ast):
    """Return a string literal value across supported Python AST layouts.

    Python 3.6 parses string literals as ``Str`` nodes. Python 3.8 and later
    parse them as ``Constant`` nodes, and Python 3.14 removes ``ast.Str``.
    Looking up both node classes dynamically keeps this inspection compatible
    without accessing a removed attribute.
    """
    constant_type = getattr(ast_module, "Constant", None)
    if constant_type is not None and isinstance(node, constant_type):
        value = getattr(node, "value", None)
        if isinstance(value, str):
            return value

    string_type = getattr(ast_module, "Str", None)
    if string_type is not None and isinstance(node, string_type):
        value = getattr(node, "s", None)
        if isinstance(value, str):
            return value

    return None


SOURCE_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, "src")
)
sys.path.insert(0, SOURCE_ROOT)
