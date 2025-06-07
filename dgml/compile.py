import json
import hashlib
from dataclasses import dataclass

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


def diag_line_to_json(line):
    return {"line_id": line.line_id, "text": [text_to_json(frag) for frag in line.text]}


def make_node(node, type, **kwargs):
    r = {"node_id": node.meta.node_id, "tags": node.meta.tags, "type": type}
    r.update(kwargs)
    return r


def main(args):
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
            nodes = []
            for node in section.nodes:
                if isinstance(node, parser.RandNode):
                    nodes.append(make_node(node, "rand", nodes=node.nodes))
                if isinstance(node, parser.GotoNode):
                    nodes.append(make_node(node, "goto", dest=node.dest))
                if isinstance(node, parser.CallNode):
                    nodes.append(make_node(node, "call", dest=node.dest))
                if isinstance(node, parser.ReturnNode):
                    nodes.append(make_node(node, "return"))
                if isinstance(node, parser.ChoiceNode):
                    opts = []
                    for opt in node.options:
                        opts.append(
                            {"line": diag_line_to_json(opt.line), "dest": opt.dest}
                        )
                        if opt.cond:
                            opts[-1]["cond"] = expr_to_json(opt.cond)
                    nodes.append(make_node(node, "choice", options=opts))
                if isinstance(node, parser.IfNode):
                    n = make_node(
                        node,
                        "if",
                        cond=expr_to_json(node.cond),
                        true_dest=node.true_dest,
                    )
                    if node.false_dest:
                        n["false_dest"] = node.false_dest
                    nodes.append(n)
                if isinstance(node, parser.RunNode):
                    nodes.append(make_node(node, "run", code=expr_to_json(node.code)))
                if isinstance(node, parser.SayNode):
                    speaker_ids.add(node.speaker_id)
                    nodes.append(
                        make_node(
                            node,
                            "say",
                            speaker_id=node.speaker_id,
                            line=diag_line_to_json(node.line),
                        )
                    )

            sections.append(
                {"name": section.name, "source_file": src.path, "nodes": nodes}
            )

    data = {
        "build_id": build_id.hexdigest(),
        "speaker_ids": list(speaker_ids),
        "sources": [{"path": src.path, "hash": src.source_hash} for s in sources],
        "environment": [],
        "sections": sections,
    }

    with open(args.output, "w") as f:
        json.dump(data, f, indent=2)
