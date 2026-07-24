"""Tests for AST compatibility helpers used by test configuration."""

import ast

import conftest


class LegacyStringNode(object):
    """Python 3.6-style string node double."""

    def __init__(self, value):
        self.s = value


class LegacyAst(object):
    """AST module double exposing only the legacy string node."""

    Str = LegacyStringNode


class ConstantNode(object):
    """Python 3.8+-style constant node double."""

    def __init__(self, value):
        self.value = value


class ModernAst(object):
    """AST module double exposing only the modern constant node."""

    Constant = ConstantNode


def test_ast_string_value_handles_python_36_str_node():
    node = LegacyStringNode("legacy")
    assert conftest._ast_string_value(node, LegacyAst) == "legacy"


def test_ast_string_value_handles_modern_constant_node_without_str():
    node = ConstantNode("modern")
    assert conftest._ast_string_value(node, ModernAst) == "modern"


def test_ast_string_value_rejects_non_string_constant():
    node = ConstantNode(123)
    assert conftest._ast_string_value(node, ModernAst) is None


def test_ast_string_value_handles_current_interpreter_ast():
    node = ast.parse('"current"').body[0].value
    assert conftest._ast_string_value(node) == "current"
