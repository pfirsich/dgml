import json
import hashlib
import sys
from dataclasses import dataclass

import yaml

from . import parser


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


def text_to_json(frag):
    if isinstance(frag, parser.TextFragment):
        return {"text": frag.text}
    elif isinstance(frag, parser.VariableFragment):
        return {"variable": frag.variable_name}
    elif isinstance(frag, parser.TagOpen):
        if frag.parameter is not None:
            return {"tag_open": frag.name, "parameter": frag.parameter}
        else:
            return {"tag_open": frag.name}
    elif isinstance(frag, parser.TagClose):
        return {"tag_close": frag.name}
    else:
        raise AssertionError("Invalid text fragment")


def diag_line_to_json(section_meta, line):
    jline = {
        "line_id": line.line_id,
        "text": [text_to_json(frag) for frag in line.text],
    }
    if line.line_id in section_meta:
        jline["meta"] = section_meta.pop(line.line_id)
    return jline


def make_node(node, type, **kwargs):
    r = {"node_id": node.meta.node_id, "tags": node.meta.tags, "type": type}
    for k, v in kwargs.items():
        if v is not None:
            r[k] = v
    return r


def main(args):
    config = {}
    if args.config:
        with open(args.config) as f:
            config = yaml.load(f, Loader=yaml.SafeLoader)

    meta = {}
    if args.meta:
        with open(args.meta) as f:
            meta = json.load(f)

    sources = []
    for path in args.input:
        with open(path) as f:
            src = f.read()
            src_hash = hashlib.md5(src.encode("utf-8")).hexdigest()
            sections = parser.parse_dgml(src)
            sources.append(Source(path, f.read(), src_hash, sections))

    build_id = hashlib.md5()
    for src in sources:
        build_id.update(src.source_hash.encode("utf-8"))

    speaker_ids = set()
    sections = []

    for src in sources:
        for section in src.sections:
            section_meta = meta.get(section.name, {})
            nodes = []
            for node in section.nodes:
                if isinstance(node, parser.RandNode):
                    nodes.append(make_node(node, "rand", nodes=node.nodes))
                elif isinstance(node, parser.GotoNode):
                    nodes.append(make_node(node, "goto", dest=node.dest))
                elif isinstance(node, parser.CallNode):
                    nodes.append(make_node(node, "call", dest=node.dest))
                elif isinstance(node, parser.ReturnNode):
                    nodes.append(make_node(node, "return"))
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
                    nodes.append(make_node(node, "choice", options=opts))
                elif isinstance(node, parser.IfNode):
                    nodes.append(
                        make_node(
                            node,
                            "if",
                            cond=expr_to_json(node.cond),
                            true_dest=node.true_dest,
                            false_dest=node.false_dest,
                        )
                    )
                elif isinstance(node, parser.RunNode):
                    nodes.append(make_node(node, "run", code=expr_to_json(node.code)))
                elif isinstance(node, parser.SayNode):
                    speaker_ids.add(node.speaker_id)
                    nodes.append(
                        make_node(
                            node,
                            "say",
                            speaker_id=node.speaker_id,
                            line=diag_line_to_json(section_meta, node.line),
                            dest=node.dest,
                        )
                    )
                else:
                    sys.exit(f"Unknown node type: {type(node).__name__}")

            sections.append(
                {"name": section.name, "source_file": src.path, "nodes": nodes}
            )

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
                sys.exit(f"Invalid speaker id: {speaker}")
            speaker_ids = config["speaker_ids"]

    data = {
        "build_id": build_id.hexdigest(),
        "speaker_ids": list(speaker_ids),
        "sources": [{"path": src.path, "hash": src.source_hash} for s in sources],
        "environment": config.get("environment", {}),
        "sections": sections,
    }

    with open(args.output, "w") as f:
        json.dump(data, f, indent=2)
