import sys
import json
import re
from dataclasses import dataclass
from collections.abc import Iterable
from pathlib import Path

import lark
from watchfiles import watch, Change
import yaml

from .parser import *
from .config import load_config


def get_duplicates(
    seq: Iterable[tuple[str, FileLocation]]
) -> list[tuple[str, FileLocation]]:
    s = set()
    duplicates = []
    for val, loc in seq:
        if val in s:
            duplicates.append((val, loc))
        s.add(val)
    return duplicates


def lint_unique_section_names(ctx, config, sources):
    for path, sections in sources.items():
        dup_sec_names = get_duplicates(
            (s.name, FileLocation(path, s.loc)) for s in sections
        )
        for name, loc in dup_sec_names:
            ctx.messages.append(
                Message("error", loc, f"Duplicate section name: {name}")
            )


def get_line_ids(path, node):
    if isinstance(node, SayNode) and node.line.line_id is not None:
        return [(node.line.line_id, FileLocation(path, node.line.loc))]
    elif isinstance(node, ChoiceNode):
        return [
            (o.line.line_id, FileLocation(path, o.line.loc))
            for o in node.options
            if o.line.line_id is not None
        ]
    else:
        return []


def lint_unique_ids(ctx, config, sources):
    line_ids = []
    for path, sections in sources.items():
        for section in sections:
            dup_node_ids = get_duplicates(
                (n.meta.node_id, FileLocation(path, n.meta.loc)) for n in section.nodes
            )
            for node_id, loc in dup_node_ids:
                ctx.messages.append(
                    Message("error", loc, f"Duplicate node id: {node_id}")
                )
            for node in section.nodes:
                line_ids.extend(get_line_ids(path, node))

    for line_id, loc in get_duplicates(line_ids):
        ctx.messages.append(Message("error", loc, f"Duplicate line id: {line_id}"))


def lint_valid_speaker_id(ctx, config, sources):
    if "speaker_ids" not in config:
        return
    valid_speaker_ids = config["speaker_ids"]

    for path, sections in sources.items():
        for section in sections:
            for node in section.nodes:
                if isinstance(node, SayNode):
                    if not node.speaker_id in valid_speaker_ids:
                        ctx.messages.append(
                            Message(
                                "error",
                                FileLocation(path, node.meta.loc),
                                f"Invalid speaker: {node.speaker_id}",
                            )
                        )


def find_node(section: Section, node_id: str) -> int | None:
    for i, n in enumerate(section.nodes):
        if n.meta.node_id == node_id:
            return i
    if node_id == "end":
        return len(section.nodes)
    return None


def get_node_idx(section: Section, node_id: str) -> int:
    idx = find_node(section, node_id)
    if idx == None:
        sys.exit(f"Invalid node id: {node_id}")
    return idx


def check_node_id(ctx, section, loc, node_id):
    if find_node(section, node_id) == None:
        ctx.messages.append(Message("error", loc, f"Invalid node id: {node_id}"))


def lint_valid_node_ids(ctx, config, sources):
    for path, sections in sources.items():
        for section in sections:
            for node in section.nodes:
                node_loc = FileLocation(path, node.meta.loc)

                if node.meta.node_id == "end":
                    ctx.messages.append(
                        Message("error", node_loc, "'end' is a reserved node id")
                    )

                if isinstance(node, RandNode):
                    for n in node.nodes:
                        check_node_id(ctx, section, node_loc, n)
                elif isinstance(node, GotoNode):
                    check_node_id(ctx, section, node_loc, node.dest)
                elif isinstance(node, ChoiceNode):
                    for opt in node.options:
                        check_node_id(
                            ctx, section, FileLocation(path, opt.line.loc), opt.dest
                        )
                elif isinstance(node, IfNode):
                    check_node_id(ctx, section, node_loc, node.true_dest)
                    if node.false_dest:
                        check_node_id(
                            ctx,
                            section,
                            node_loc,
                            node.false_dest,
                        )
                elif isinstance(node, SayNode):
                    if node.next_node:
                        check_node_id(ctx, section, node_loc, node.next_node)


def reach_node(reachable: list[bool], path: str, section: Section, idx: int):
    if idx >= len(section.nodes):  # probably @end
        return

    # We've already been here, avoid infinite recursion
    if reachable[idx]:
        return

    reachable[idx] = True
    node = section.nodes[idx]
    if isinstance(node, RandNode):
        for n in node.nodes:
            reach_node(reachable, path, section, get_node_idx(section, n))
    elif isinstance(node, GotoNode):
        reach_node(reachable, path, section, get_node_idx(section, node.dest))
    elif isinstance(node, ChoiceNode):
        for opt in node.options:
            reach_node(reachable, path, section, get_node_idx(section, opt.dest))
    elif isinstance(node, IfNode):
        reach_node(reachable, path, section, get_node_idx(section, node.true_dest))
        if node.false_dest:
            reach_node(reachable, path, section, get_node_idx(section, node.false_dest))
        else:
            reach_node(reachable, path, section, idx + 1)
    elif isinstance(node, RunNode):
        reach_node(reachable, path, section, idx + 1)
    elif isinstance(node, SayNode):
        if node.next_node:
            reach_node(reachable, path, section, get_node_idx(section, node.next_node))
        else:
            reach_node(reachable, path, section, idx + 1)


def lint_unreachable_nodes(ctx, config, sources):
    for path, sections in sources.items():
        for section in sections:
            reachable = [False for n in section.nodes]
            reach_node(reachable, path, section, 0)
            for i, r in enumerate(reachable):
                if not r:
                    ctx.messages.append(
                        Message(
                            "warning",
                            FileLocation(path, section.nodes[i].meta.loc),
                            f"Unreachable node",
                        )
                    )


def find_env_var(env_vars, name):
    for var in env_vars:
        if var["name"] == name:
            return var
    return None


def check_valid_interpolations(ctx, env_vars, path, line):
    for seg in line.text:
        if isinstance(seg, VariableFragment):
            if find_env_var(env_vars, seg.variable_name) == None:
                ctx.messages.append(
                    Message(
                        "warning",
                        FileLocation(path, line.loc),
                        f"Invalid variable interpolation: {seg.variable_name}",
                    )
                )


def lint_valid_interpolations(ctx, config, sources):
    if "environment" not in config:
        return
    if "variables" not in config["environment"]:
        return
    env_vars = config["environment"]["variables"]

    for path, sections in sources.items():
        for section in sections:
            for node in section.nodes:
                if isinstance(node, ChoiceNode):
                    for opt in node.options:
                        check_valid_interpolations(ctx, env_vars, path, opt.line)
                elif isinstance(node, SayNode):
                    check_valid_interpolations(ctx, env_vars, path, node.line)


def check_valid_markup_nesting(ctx, markup, path, line):
    markup_stack = []
    for seg in line.text:
        if isinstance(seg, TagOpen):
            markup_stack.append(seg.name)
        elif isinstance(seg, TagClose):
            if len(markup_stack) == 0 or markup_stack[-1] != seg.name:
                ctx.messages.append(
                    Message(
                        "warning",
                        FileLocation(path, line.loc),
                        f"Invalid nesting of markup tags: {seg.name}",
                    )
                )
                return
            markup_stack.pop()

    if len(markup_stack) > 0:
        ctx.messages.append(
            Message(
                "warning",
                FileLocation(path, line.loc),
                f"Unclosed markup tags: {', '.join(markup_stack)}",
            )
        )


def lint_markup_nesting(ctx, config, sources):
    if "environment" not in config:
        return
    if "markup" not in config["environment"]:
        return
    markup = config["environment"]["markup"]

    for path, sections in sources.items():
        for section in sections:
            for node in section.nodes:
                if isinstance(node, ChoiceNode):
                    for opt in node.options:
                        check_valid_markup_nesting(ctx, markup, path, opt.line)
                elif isinstance(node, SayNode):
                    check_valid_markup_nesting(ctx, markup, path, node.line)


def find_markup_tag(markup, tag_name):
    for tag in markup:
        if tag["name"] == tag_name:
            return tag
    return None


def check_valid_markup(ctx, markup, path, line):
    line_loc = FileLocation(path, line.loc)
    for seg in line.text:
        if isinstance(seg, TagOpen):
            tag = find_markup_tag(markup, seg.name)
            if tag is None:
                ctx.messages.append(
                    Message("warning", line_loc, f"Invalid markup tag: {seg.name}")
                )
                continue

            if seg.parameter is not None:
                if "parameter" not in tag:
                    ctx.messages.append(
                        Message(
                            "warning",
                            line_loc,
                            f"Parameter not allowed for markup tag: {seg.name}",
                        )
                    )
                else:
                    if not re.fullmatch(tag["parameter"], seg.parameter):
                        ctx.messages.append(
                            Message(
                                "warning",
                                line_loc,
                                f"Invalid parameter for markup tag '{seg.name}': {seg.parameter}",
                            )
                        )
        elif isinstance(seg, TagClose):
            tag = find_markup_tag(markup, seg.name)
            if tag is None:
                ctx.messages.append(
                    Message("error", line_loc, f"Invalid markup tag: {seg.name}")
                )


def lint_known_markup(ctx, config, sources):
    if "environment" not in config:
        return
    if "markup" not in config["environment"]:
        return
    markup = config["environment"]["markup"]

    for path, sections in sources.items():
        for section in sections:
            for node in section.nodes:
                if isinstance(node, ChoiceNode):
                    for opt in node.options:
                        check_valid_markup(ctx, markup, path, opt.line)
                elif isinstance(node, SayNode):
                    check_valid_markup(ctx, markup, path, node.line)


def is_num_type(type):
    return type == "int" or type == "float"


def get_expr_type(env_vars, expr):
    if isinstance(expr, ExprUnary):
        if expr.op == "not":
            if get_expr_type(env_vars, expr.rhs) != "bool":
                raise TypeError("Operand for 'not' must be of type bool")
            return "bool"
        else:
            raise TypeError(f"Invalid unary operand: {expr.op}")
    elif isinstance(expr, ExprBinary):
        if expr.op in ("or", "and"):
            if get_expr_type(env_vars, expr.lhs) != "bool":
                raise TypeError(f"Lhs of {expr.op} operator must be bool")
            if get_expr_type(env_vars, expr.rhs) != "bool":
                raise TypeError(f"Rhs of {expr.op} operator must be bool")
            return "bool"
        elif expr.op in ("lt", "le", "gt", "ge", "add", "sub", "mul", "div"):
            lhs_type = get_expr_type(env_vars, expr.lhs)
            if not is_num_type(lhs_type):
                raise TypeError(f"Lhs of {expr.op} operator must be number")
            rhs_type = get_expr_type(env_vars, expr.rhs)
            if not is_num_type(rhs_type):
                raise TypeError(f"Rhs of {expr.op} operator must be number")
            if expr.op in ("lt", "le", "gt", "ge"):
                return "bool"
            elif lhs_type == "int" and rhs_type == "int":
                return "int"
            else:
                return "float"
        elif expr.op in ("eq", "ne"):
            lhs_type = get_expr_type(env_vars, expr.lhs)
            rhs_type = get_expr_type(env_vars, expr.rhs)
            valid = lhs_type == rhs_type or (
                is_num_type(lhs_type) and is_num_type(rhs_type)
            )
            if not valid:
                raise TypeError(
                    f"Lhs ({lhs_type}) and Rhs ({rhs_type}) of operator {expr.op} must be of convertible types"
                )
            return "bool"
        else:
            raise TypeError(f"Invalid binary operand: {expr.op}")
    elif isinstance(expr, ExprIdent):
        var = find_env_var(env_vars, expr.name)
        assert var is not None, f"Variable missing in config: {expr.name}"
        return var["type"]
    elif isinstance(expr, ExprLiteral):
        # No isinstance, because bool is a subclass of int
        if type(expr.value) == int:
            return "int"
        elif type(expr.value) == float:
            return "float"
        elif type(expr.value) == bool:
            return "bool"
        elif type(expr.value) == str:
            return "string"
        else:
            raise TypeError("Invalid literal type")
    elif isinstance(expr, ExprAssign):
        var = find_env_var(env_vars, expr.name)
        assert var is not None
        rhs_type = get_expr_type(env_vars, expr.value)
        if rhs_type != var["type"]:
            raise TypeError(
                f"Lhs ({var['type']}) and Rhs ({rhs_type}) of assignment must be of the same type"
            )
        return "assign"


# TODO: Error locations are very bad here. Improve this somehow
def lint_expr_types(ctx, config, sources):
    if "environment" not in config:
        return
    if "variables" not in config["environment"]:
        return
    env_vars = config["environment"]["variables"]

    for path, sections in sources.items():
        for section in sections:
            for node in section.nodes:
                node_loc = FileLocation(path, node.meta.loc)
                try:
                    if isinstance(node, ChoiceNode):
                        for opt in node.options:
                            if opt.cond:
                                if get_expr_type(env_vars, opt.cond) != "bool":
                                    ctx.messages.append(
                                        Message(
                                            "error",
                                            node_loc,
                                            f"Expression must be bool",
                                        )
                                    )
                    elif isinstance(node, IfNode):
                        if get_expr_type(env_vars, node.cond) != "bool":
                            ctx.messages.append(
                                Message("error", node_loc, f"Expression must be bool")
                            )
                    elif isinstance(node, RunNode):
                        if get_expr_type(env_vars, node.code) != "assign":
                            ctx.messages.append(
                                Message(
                                    "error", node_loc, f"Expression must be assignment"
                                )
                            )
                except TypeError as exc:
                    ctx.messages.append(Message("error", node_loc, str(exc)))


def fix_add_line_ids(sources):
    pass


def lint(ctx, config, sources, fixes=[]):
    lint_unique_section_names(ctx, config, sources)
    lint_unique_ids(ctx, config, sources)
    lint_valid_node_ids(ctx, config, sources)
    lint_valid_speaker_id(ctx, config, sources)
    lint_unreachable_nodes(ctx, config, sources)
    # lint_goto_after_say(ctx, config, sources) # warn
    lint_valid_interpolations(ctx, config, sources)
    lint_markup_nesting(ctx, config, sources)
    lint_known_markup(ctx, config, sources)
    lint_expr_types(ctx, config, sources)

    if "add-line-ids" in fixes:
        fix_add_line_ids(sources)


def lint_files(args, config, files):
    config = {}
    if args.config:
        config = load_config(args.config)

    ctx = ErrorContext([])

    sources = {}
    for source_path in files:
        with open(source_path) as f:
            source = f.read()
        sources[source_path] = parse_dgml(ctx, source_path, source)

    lint(ctx, config, sources, args.fix)

    print_errors(ctx)

    if len(ctx.messages) > 0:
        if not args.watch:
            sys.exit(1)
    elif not args.quiet:
        print("No warnings or errors", file=sys.stderr)


def rectify_path(path: str, rectified: list[str]):
    for r in rectified:
        if Path(path).samefile(r):
            return r
    raise ValueError(f"Cannot match path: {path}")


def main(args):
    config = {}
    if args.config:
        config = load_config(args.config)

    lint_files(args, config, args.input)

    if args.watch:
        files = []
        files.extend(args.input)
        if args.config:
            files.append(args.config)

        watch_filter = lambda change, str: change == Change.modified
        for changes in watch(*files, watch_filter=watch_filter):
            changed_files = [rectify_path(path, files) for change, path in changes]
            if args.config in changed_files:
                config = load_config(args.config)
                lint_files(args, config, args.input)
            else:
                lint_files(args, config, changed_files)
