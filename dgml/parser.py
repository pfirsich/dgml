from __future__ import annotations

import sys
from dataclasses import dataclass

from lark import Lark, Transformer, Tree, Token, v_args, exceptions

from .colors import *


@dataclass
class SourceLoc:
    line: int = 0
    column: int = 0


def loc_from_meta(node):
    return SourceLoc(node.meta.line, node.meta.column)


@dataclass
class NodeMeta:
    node_id: str | None
    tags: list
    loc: SourceLoc


# Text


@dataclass
class LiteralFragment:
    text: str


@dataclass
class VariableFragment:
    variable_name: str


@dataclass
class TagOpen:
    name: str
    parameter: str | None = None


@dataclass
class TagClose:
    name: str


LineFragment = LiteralFragment | VariableFragment | TagOpen | TagClose


@dataclass
class DialogLine:
    text: list[LineFragment]
    raw_text: str
    line_id: str | None
    loc: SourceLoc


# Expressions


@dataclass
class ExprUnary:
    op: str  # not
    rhs: "ExprNode"


@dataclass
class ExprBinary:
    op: str  # or, and, add, sub, mul, div, lt, le, eq, ne, gt, ge
    lhs: "ExprNode"
    rhs: "ExprNode"


@dataclass
class ExprIdent:
    name: str


@dataclass
class ExprLiteral:
    value: bool | int | float | str


@dataclass
class ExprAssign:
    name: str
    value: "ExprNode"


# Assign is missing intentionally
ExprNode = ExprUnary | ExprBinary | ExprIdent | ExprLiteral


@dataclass
class Expression:
    ast: ExprNode
    raw: str


@dataclass
class Assignment:
    ast: ExprAssign
    raw: str


# Dialogue Nodes


@dataclass
class RandNode:
    nodes: list[str]
    meta: NodeMeta


@dataclass
class GotoNode:
    dest: str
    meta: NodeMeta


@dataclass
class Option:
    cond: Expression | None
    line: DialogLine
    dest: str


@dataclass
class ChoiceNode:
    options: list[Option]
    meta: NodeMeta


@dataclass
class IfNode:
    cond: Expression
    true_dest: str
    false_dest: str | None
    meta: NodeMeta


@dataclass
class RunNode:
    code: Assignment
    meta: NodeMeta


@dataclass
class SayNode:
    speaker_id: str
    line: DialogLine
    next_node: str | None
    meta: NodeMeta


Node = RandNode | GotoNode | ChoiceNode | IfNode | RunNode | SayNode


@dataclass
class Section:
    name: str
    nodes: list[Node]
    loc: SourceLoc


def get_dgml_parser():
    if not hasattr(get_dgml_parser, "_parser"):
        parser = Lark.open(
            "dgml.lark",
            rel_to=__file__,
            parser="lalr",
            propagate_positions=True,
        )
        setattr(get_dgml_parser, "_parser", parser)
    return getattr(get_dgml_parser, "_parser")


def get_expr_parser():
    if not hasattr(get_expr_parser, "_parser"):
        parser = Lark.open(
            "expressions.lark",
            rel_to=__file__,
            parser="lalr",
            propagate_positions=True,
            maybe_placeholders=False,
        )
        setattr(get_expr_parser, "_parser", parser)
    return getattr(get_expr_parser, "_parser")


def is_tree(node, tree_data):
    return isinstance(node, Tree) and node.data == tree_data


def is_token(node, token_type):
    return isinstance(node, Token) and node.type == token_type


def lark_print(node, depth=0):
    if isinstance(node, Token):
        print(depth * "  " + f"{node.type}: {node.value}")
    elif isinstance(node, Tree):
        print(depth * "  " + f"{node.data}")
        for child in node.children:
            lark_print(child, depth + 1)


compare_map = {
    "<": "lt",
    "<=": "le",
    "==": "eq",
    "!=": "ne",
    ">": "gt",
    ">=": "ge",
}


def process_expr(node) -> ExprNode:
    if is_tree(node, "or_op"):
        return ExprBinary(
            "or",
            process_expr(node.children[0]),
            process_expr(node.children[1]),
        )
    elif is_tree(node, "and_op"):
        return ExprBinary(
            "and",
            process_expr(node.children[0]),
            process_expr(node.children[1]),
        )
    elif is_tree(node, "not_op"):
        return ExprUnary(
            "not",
            process_expr(node.children[0]),
        )
    elif is_tree(node, "compare"):
        return ExprBinary(
            compare_map[node.children[1].value],
            process_expr(node.children[0]),
            process_expr(node.children[2]),
        )
    elif is_tree(node, "add"):
        return ExprBinary(
            "add",
            process_expr(node.children[0]),
            process_expr(node.children[1]),
        )
    elif is_tree(node, "sub"):
        return ExprBinary(
            "sub",
            process_expr(node.children[0]),
            process_expr(node.children[1]),
        )
    elif is_tree(node, "mul"):
        return ExprBinary(
            "mul",
            process_expr(node.children[0]),
            process_expr(node.children[1]),
        )
    elif is_tree(node, "div"):
        return ExprBinary(
            "div",
            process_expr(node.children[0]),
            process_expr(node.children[1]),
        )
    elif is_tree(node, "int_literal"):
        return ExprLiteral(int(node.children[0].value))
    elif is_tree(node, "float_literal"):
        return ExprLiteral(float(node.children[0].value))
    elif is_tree(node, "string_literal"):
        return ExprLiteral(node.children[0].value[1:-1])
    elif is_tree(node, "bool_literal"):
        return ExprLiteral(bool(node.children[0].value))
    elif is_tree(node, "paren"):
        return process_expr(node.children[0])
    elif is_tree(node, "ident"):
        return ExprIdent(node.children[0].value)
    else:
        raise AssertionError(f"Invalid expr: {node}")


def parse_expr(expr) -> Expression:
    parser = get_expr_parser()
    tree = parser.parse(expr)
    return Expression(process_expr(tree), expr)


def process_assignment(node) -> ExprAssign:
    if not is_tree(node, "assign"):
        raise ValueError("Expression must be assignment")
    return ExprAssign(node.children[0].value, process_expr(node.children[1]))


def parse_assignment(assign_str) -> Assignment:
    parser = get_expr_parser()
    tree = parser.parse(assign_str)
    return Assignment(process_assignment(tree), assign_str)


def add_text(fragments, text):
    if len(fragments) == 0 or not isinstance(fragments[-1], LiteralFragment):
        fragments.append(LiteralFragment(text))
    else:
        fragments[-1].text += text


def parse_text(text):
    fragments = []
    i = 0
    while i < len(text):
        if text[i] == "[":
            if i == len(text) - 1:
                raise ValueError("Unmatched [")
            if text[i + 1] == "[":
                add_text(fragments, "[")
                i += 2
            else:
                is_closing = text[i + 1] == "/"
                closing_bracket = text.find("]", i + 1)
                if closing_bracket == -1:
                    raise ValueError("Unmatched [")
                inner = text[i + 1 : closing_bracket]
                if is_closing:
                    fragments.append(TagClose(inner[1:]))
                else:
                    param_split = inner.split(":", 1)
                    if len(param_split) == 1:
                        fragments.append(TagOpen(inner))
                    else:
                        name, param = param_split
                        fragments.append(TagOpen(name, param))
                i = closing_bracket + 1
        elif text[i] == "{":
            if i == len(text) - 1:
                raise ValueError("Unmatched [")
            if text[i + 1] == "{":
                add_text(fragments, "{")
                i += 2
            else:
                closing_brace = text.find("}", i + 1)
                if closing_brace == -1:
                    raise ValueError("Unmatched {")
                fragments.append(VariableFragment(text[i + 1 : closing_brace]))
                i = closing_brace + 1
        else:  # TextFragment
            first_bracket = text.find("[", i)
            if first_bracket == -1:
                first_bracket = len(text)
            first_brace = text.find("{", i)
            if first_brace == -1:
                first_brace = len(text)
            end = min(first_brace, first_bracket)
            add_text(fragments, text[i:end])
            i = end

    return fragments


def parse_node_id(node) -> str:
    assert is_tree(node, "node_id"), lark_print(node)
    return node.children[0].value


def parse_line_id(node) -> str:
    assert is_tree(node, "line_id"), lark_print(node)
    return node.children[0].value


def parse_code_block(node):
    assert is_tree(node, "code_block"), lark_print(node)
    return node.children[0].value


def parse_dialog_line(node):
    assert is_tree(node, "dialog_line"), lark_print(node)
    line_id = None
    if len(node.children) > 1:
        line_id = parse_line_id(node.children[1])
    raw_text = node.children[0].value[1:-1]
    return DialogLine(
        parse_text(raw_text),
        raw_text,
        line_id,
        SourceLoc(node.meta.line, node.meta.end_column),
    )


def process_rand(meta, node):
    assert is_tree(node, "rand_stmt"), lark_print(node)
    rand = RandNode([], meta)
    for child in node.children:
        if is_tree(child, "node_id"):
            rand.nodes.append(parse_node_id(child))
    return rand


def process_goto(meta, node):
    assert is_tree(node, "goto_stmt"), lark_print(node)
    return GotoNode(parse_node_id(node.children[0]), meta)


def process_choice(meta, node):
    assert is_tree(node, "choice_block"), lark_print(node)
    options = []
    for option in node.children:
        assert is_tree(option, "choice_option"), lark_print(option)
        if is_tree(option.children[0], "code_block"):
            cond = parse_expr(option.children[0].children[0].value)
            text = parse_dialog_line(option.children[1])
            dest = parse_node_id(option.children[2])
        else:
            cond = None
            text = parse_dialog_line(option.children[0])
            dest = parse_node_id(option.children[1])
        options.append(Option(cond, text, dest))
    return ChoiceNode(options, meta)


def process_if(meta, node):
    assert is_tree(node, "if_stmt"), lark_print(node)
    false_dest = None
    if len(node.children) > 2:
        false_dest = parse_node_id(node.children[2])
    return IfNode(
        parse_expr(node.children[0].children[0].value),
        parse_node_id(node.children[1]),
        false_dest,
        meta,
    )


def process_run(meta, node):
    assert is_tree(node, "run_stmt"), lark_print(node)
    return RunNode(parse_assignment(node.children[0].children[0].value), meta)


def process_say(meta, node):
    assert is_tree(node, "say_stmt"), lark_print(node)
    next_link = None
    if len(node.children) > 2:
        next_link = parse_node_id(node.children[2].children[1])
    return SayNode(
        node.children[0].value,
        parse_dialog_line(node.children[1]),
        next_link,
        meta,
    )


def process_statement(meta, node):
    if is_tree(node, "rand_stmt"):
        return process_rand(meta, node)
    elif is_tree(node, "goto_stmt"):
        return process_goto(meta, node)
    elif is_tree(node, "choice_block"):
        return process_choice(meta, node)
    elif is_tree(node, "if_stmt"):
        return process_if(meta, node)
    elif is_tree(node, "run_stmt"):
        return process_run(meta, node)
    elif is_tree(node, "say_stmt"):
        return process_say(meta, node)
    else:
        raise AssertionError(f"Invalid statement: {node}")


def get_meta(meta_node, statement_node):
    assert is_tree(meta_node, "meta"), lark_print(meta_node)
    meta = NodeMeta(None, [], loc_from_meta(statement_node))
    for child in meta_node.children:
        if is_tree(child, "node_id"):
            meta.node_id = parse_node_id(child)
        elif is_tree(child, "tag_list"):
            meta.tags = [c.value for c in child.children]
    return meta


def process_line(node):
    assert is_tree(node, "line"), lark_print(node)
    if len(node.children) == 0:
        return None
    if is_tree(node.children[0], "meta"):
        return process_statement(
            get_meta(node.children[0], node.children[1]), node.children[1]
        )
    else:
        return process_statement(
            NodeMeta(None, [], loc_from_meta(node.children[0])), node.children[0]
        )


def process_section(node):
    assert is_tree(node, "section"), lark_print(node)
    section_name = node.children[0].value
    nodes = []
    for child in node.children[1:]:
        if is_tree(child, "line"):
            line_node = process_line(child)
            if line_node is not None:
                nodes.append(line_node)
    return Section(section_name, nodes, loc_from_meta(node))


def process_dgml(node):
    assert is_tree(node, "start"), lark_print(node)
    sections = []
    for child in node.children:
        sections.append(process_section(child))
    return sections


def random_string(n):
    import random
    import string

    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def generate_node_id(node):
    return random_string(8)


@dataclass
class FileLocation:
    file: str
    src_loc: SourceLoc


@dataclass
class Message:
    type: str  # "error" or "warning"
    loc: FileLocation
    message: str


@dataclass
class ErrorContext:
    messages: list


def parse_dgml(ctx: ErrorContext, source_path: str, source: str):
    parser = get_dgml_parser()
    try:
        tree = parser.parse(source)
    except exceptions.UnexpectedInput as exc:
        ctx.messages.append(
            Message(
                "error",
                FileLocation(source_path, SourceLoc(exc.line, exc.column)),
                str(exc),
            )
        )
        return None
    dgml = process_dgml(tree)
    for section in dgml:
        for node in section.nodes:
            if node.meta.node_id is None:
                node.meta.node_id = generate_node_id(node)
    return dgml


def print_errors(ctx):
    for msg in ctx.messages:
        if msg.type == "warning":
            color = COLORS["yellow"]
        elif msg.type == "error":
            color = COLORS["red"]
        else:
            color = ""
        print(
            f"{color}{msg.type}{COLOR_RESET}{FAINT} {msg.loc.file}:{msg.loc.src_loc.line}:{msg.loc.src_loc.column}:{COLOR_RESET} {msg.message}",
            file=sys.stderr,
        )
