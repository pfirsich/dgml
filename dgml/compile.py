import json
import hashlib
import sys
from dataclasses import dataclass

import yaml

from . import parser
from .config import load_config
from .lint import lint


@dataclass
class Source:
    path: str
    source: str
    source_hash: str
    sections: list


def expr_to_json(expr):
    if isinstance(expr, parser.ExprUnary):
        return {"type": f"unary_{expr.op}", "rhs": expr_to_json(expr.rhs)}
    elif isinstance(expr, parser.ExprBinary):
        return {
            "type": f"binary_{expr.op}",
            "lhs": expr_to_json(expr.lhs),
            "rhs": expr_to_json(expr.rhs),
        }
    elif isinstance(expr, parser.ExprIdent):
        return {"type": f"variable", "name": expr.name}
    elif isinstance(expr, parser.ExprLiteral):
        return {"type": f"literal_{type(expr.value).__name__}", "value": expr.value}
    elif isinstance(expr, parser.ExprAssign):
        return {"type": "assign", "name": expr.name, "value": expr_to_json(expr.value)}
    else:
        raise AssertionError("Invalid expr node")


def text_to_json(text: list) -> list:
    ret = []
    tag_stack = []
    current_tags = {}

    for frag in text:
        if isinstance(frag, parser.TextFragment):
            ret.append({"tags": current_tags, "text": frag.text})
        elif isinstance(frag, parser.VariableFragment):
            ret.append({"tags": current_tags, "variable": frag.variable_name})
        elif isinstance(frag, parser.TagOpen):
            tag_stack.append((frag.name, frag.parameter))
            current_tags = {name: value for (name, value) in tag_stack}
        elif isinstance(frag, parser.TagClose):
            # should have been checked by lint
            assert tag_stack[-1][0] == frag.name
            tag_stack.pop()
            current_tags = {name: value for (name, value) in tag_stack}
        else:
            raise AssertionError("Invalid text fragment")
    return ret


def diag_line_to_json(section_meta, line):
    jline = {
        "line_id": line.line_id,
        "text": text_to_json(line.text),
    }
    if line.line_id in section_meta:
        jline["meta"] = section_meta.pop(line.line_id)
    return jline


def make_node(node, type, **kwargs):
    r = {"tags": node.meta.tags, "type": type}
    for k, v in kwargs.items():
        if v is not None:
            r[k] = v
    return r


def main(args):
    config = {}
    if args.config:
        config = load_config(args.config)

    meta = {}
    if args.meta:
        with open(args.meta) as f:
            meta = json.load(f)

    ctx = parser.ErrorContext([])

    sources = []
    for path in args.input:
        with open(path) as f:
            src = f.read()
            src_hash = hashlib.md5(src.encode("utf-8")).hexdigest()
            sections = parser.parse_dgml(ctx, path, src)
            if sections is not None:
                sources.append(Source(path, f.read(), src_hash, sections))

    lint(ctx, config, {s.path: s.sections for s in sources}, [])

    parser.print_errors(ctx)

    build_id = hashlib.md5()
    for src in sources:
        build_id.update(src.source_hash.encode("utf-8"))

    speaker_ids = set()
    sections = {}

    for src in sources:
        for section in src.sections:
            # lint should have caught this
            assert section.name not in sections

            section_meta = meta.get(section.name, {})
            nodes = {}
            for i, node in enumerate(section.nodes):
                if i == len(section.nodes) - 1:
                    next_node = "end"
                else:
                    next_node = section.nodes[i + 1].meta.node_id

                # lint should have caught this
                assert node.meta.node_id not in nodes

                if isinstance(node, parser.RandNode):
                    nodes[node.meta.node_id] = make_node(node, "rand", nodes=node.nodes)
                elif isinstance(node, parser.GotoNode):
                    nodes[node.meta.node_id] = make_node(node, "goto", dest=node.dest)
                elif isinstance(node, parser.ChoiceNode):
                    opts = []
                    for opt in node.options:
                        opts.append(
                            {
                                "line": diag_line_to_json(section_meta, opt.line),
                                "dest": opt.dest,
                            }
                        )
                        if opt.cond:
                            opts[-1]["cond"] = expr_to_json(opt.cond)
                    nodes[node.meta.node_id] = make_node(node, "choice", options=opts)
                elif isinstance(node, parser.IfNode):
                    false_dest = (
                        node.false_dest if node.false_dest is not None else next_node
                    )
                    nodes[node.meta.node_id] = make_node(
                        node,
                        "if",
                        cond=expr_to_json(node.cond),
                        true_dest=node.true_dest,
                        false_dest=false_dest,
                    )

                elif isinstance(node, parser.RunNode):
                    nodes[node.meta.node_id] = make_node(
                        node, "run", code=expr_to_json(node.code), next=next_node
                    )

                elif isinstance(node, parser.SayNode):
                    speaker_ids.add(node.speaker_id)
                    say_next_node = (
                        node.next_node if node.next_node is not None else next_node
                    )
                    nodes[node.meta.node_id] = make_node(
                        node,
                        "say",
                        speaker_id=node.speaker_id,
                        line=diag_line_to_json(section_meta, node.line),
                        next=say_next_node,
                    )

                else:
                    sys.exit(f"Unknown node type: {type(node).__name__}")

            sections[section.name] = {
                "source_file": src.path,
                "nodes": nodes,
                "start_node": section.nodes[0].meta.node_id,
            }

    invalid_meta = []
    for section_name, section_meta in meta.items():
        invalid_meta.extend(list(section_meta.keys()))

    if len(invalid_meta) > 0:
        sys.exit(
            f"Some metadata items don't belong to a line: {', '.join(invalid_meta)}"
        )

    if "speaker_ids" in config:
        for speaker_id in speaker_ids:
            if speaker_id not in config["speaker_ids"]:
                sys.exit(f"Invalid speaker id: {speaker_id}")
            speaker_ids = config["speaker_ids"]

    data = {
        "build_id": build_id.hexdigest(),
        "speaker_ids": list(speaker_ids),
        "sources": [{"path": s.path, "hash": s.source_hash} for s in sources],
        "environment": config.get("environment", {}),
        "sections": sections,
    }

    with open(args.output, "w") as f:
        json.dump(data, f, indent=2)
