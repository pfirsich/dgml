from lark import Lark, Transformer, Tree, Token, v_args
from dataclasses import dataclass


@dataclass
class SourceLoc:
    line: int = 0
    column: int = 0


@dataclass
class NodeMeta:
    node_id: str = None
    tags: list = None


# Text


@dataclass
class DialogLine:
    text: list
    line_id: str
    loc: SourceLoc


@dataclass
class TextFragment:
    text: str


@dataclass
class VariableFragment:
    variable_name: str


@dataclass
class TagOpen:
    name: str
    parameter: str = None


@dataclass
class TagClose:
    name: str


# Dialogue Nodes


@dataclass
class RandNode:
    nodes: list
    meta: NodeMeta


@dataclass
class GotoNode:
    dest: object
    meta: NodeMeta


@dataclass
class CallNode:
    dest: object
    meta: NodeMeta


@dataclass
class ReturnNode:
    meta: NodeMeta


@dataclass
class Option:
    cond: object
    line: DialogLine
    dest: object


@dataclass
class ChoiceNode:
    options: list
    meta: NodeMeta


@dataclass
class IfNode:
    cond: object
    true_dest: object
    false_dest: object
    meta: NodeMeta


@dataclass
class RunNode:
    code: object
    meta: NodeMeta


@dataclass
class SayNode:
    speaker_id: str
    line: DialogLine
    dest: object
    meta: NodeMeta


@dataclass
class Section:
    name: str
    nodes: list


# Expressions


@dataclass
class ExprUnary:
    op: str
    rhs: object


@dataclass
class ExprBinary:
    op: str
    lhs: object
    rhs: object


@dataclass
class ExprIdent:
    name: str


@dataclass
class ExprLiteral:
    value: object  # int, float, bool, string


@dataclass
class ExprAssign:
    name: str
    value: object


def get_dgml_parser():
    if not hasattr(get_dgml_parser, "_parser"):
        get_dgml_parser._parser = Lark.open(
            "dgml.lark",
            rel_to=__file__,
            parser="lalr",
            propagate_positions=True,
        )
    return get_dgml_parser._parser


def get_expr_parser():
    if not hasattr(get_expr_parser, "_parser"):
        get_expr_parser._parser = Lark.open(
            "expressions.lark",
            rel_to=__file__,
            parser="lalr",
            propagate_positions=True,
            maybe_placeholders=False,
        )
    return get_expr_parser._parser


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


def process_expr(node):
    if is_tree(node, "assign"):
        return ExprAssign(node.children[0].value, process_expr(node.children[1]))
    elif is_tree(node, "or_op"):
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


def parse_expr(expr):
    parser = get_expr_parser()
    tree = parser.parse(expr)
    return process_expr(tree)


def add_text(fragments, text):
    if len(fragments) == 0 or not isinstance(fragments[-1], TextFragment):
        fragments.append(TextFragment(text))
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


def parse_node_id(node):
    assert is_tree(node, "node_id"), lark_print(node)
    return node.children[0].value


def parse_line_id(node):
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
    return DialogLine(
        parse_text(node.children[0].value[1:-1]),
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


def process_call(meta, node):
    assert is_tree(node, "call_stmt"), lark_print(node)
    return CallNode(parse_node_id(node.children[0]), meta)


def process_return(meta, node):
    assert is_tree(node, "return_stmt"), lark_print(node)
    return ReturnNode(meta)


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
    return RunNode(parse_expr(node.children[0].children[0].value), meta)


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
    elif is_tree(node, "call_stmt"):
        return process_call(meta, node)
    elif is_tree(node, "return_stmt"):
        return process_return(meta, node)
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


def get_meta(node):
    assert is_tree(node, "meta"), lark_print(node)
    meta = NodeMeta(None, [])
    for child in node.children:
        if is_tree(child, "node_id"):
            meta.node_id = parse_node_id(child)
        elif is_tree(child, "tag_list"):
            meta.tags = [c.value for c in child.children]
    return meta


def process_line(node):
    assert is_tree(node, "line"), lark_print(node)
    if is_tree(node.children[0], "meta"):
        return process_statement(get_meta(node.children[0]), node.children[1])
    else:
        return process_statement(NodeMeta(None, []), node.children[0])


def process_section(node):
    assert is_tree(node, "section"), lark_print(node)
    section_name = node.children[0].value
    nodes = []
    for child in node.children[1:]:
        if is_tree(child, "line"):
            node = process_line(child)
            if node is not None:
                nodes.append(node)
    return Section(section_name, nodes)


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


def parse_dgml(source):
    parser = get_dgml_parser()
    tree = parser.parse(source)
    dgml = process_dgml(tree)
    for section in dgml:
        for node in section.nodes:
            if node.meta.node_id is None:
                node.meta.node_id = generate_node_id(node)
    return dgml
