import json
from dataclasses import dataclass


@dataclass
class TextFragment:
    tags: dict[str, str | None]
    text: str


@dataclass
class SayNode:
    node_id: str
    tags: list[str]
    speaker_id: str
    text: list[TextFragment]


@dataclass
class ChoiceOption:
    text: list[TextFragment]
    enabled: bool


@dataclass
class ChoiceNode:
    node_id: str
    tags: list[str]
    options: list[ChoiceOption]


@dataclass
class AdvanceResult:
    node: SayNode | ChoiceNode | None
    changed_vars: list[str]


class DialogueTree:
    def __init__(self, path: str):
        with open(path) as f:
            self.data = json.load(f)


def eval_expr(env, expr):
    # dgml lint/compile checked the types of these expressions, so
    # we don't need to check again.
    if expr["type"] == "binary_add":
        return eval_expr(env, expr["lhs"]) + eval_expr(env, expr["rhs"])
    elif expr["type"] == "binary_sub":
        return eval_expr(env, expr["lhs"]) - eval_expr(env, expr["rhs"])
    elif expr["type"] == "binary_mul":
        return eval_expr(env, expr["lhs"]) * eval_expr(env, expr["rhs"])
    elif expr["type"] == "binary_div":
        return eval_expr(env, expr["lhs"]) / eval_expr(env, expr["rhs"])
    elif expr["type"] == "binary_or":
        return eval_expr(env, expr["lhs"]) or eval_expr(env, expr["rhs"])
    elif expr["type"] == "binary_and":
        return eval_expr(env, expr["lhs"]) and eval_expr(env, expr["rhs"])
    elif expr["type"] == "binary_lt":
        return eval_expr(env, expr["lhs"]) < eval_expr(env, expr["rhs"])
    elif expr["type"] == "binary_le":
        return eval_expr(env, expr["lhs"]) <= eval_expr(env, expr["rhs"])
    elif expr["type"] == "binary_eq":
        return eval_expr(env, expr["lhs"]) == eval_expr(env, expr["rhs"])
    elif expr["type"] == "binary_ne":
        return eval_expr(env, expr["lhs"]) != eval_expr(env, expr["rhs"])
    elif expr["type"] == "binary_gt":
        return eval_expr(env, expr["lhs"]) > eval_expr(env, expr["rhs"])
    elif expr["type"] == "binary_ge":
        return eval_expr(env, expr["lhs"]) >= eval_expr(env, expr["rhs"])
    elif expr["type"] == "unary_not":
        return not eval_expr(env, expr["rhs"])
    elif expr["type"] == "variable":
        if expr["name"] not in env:
            raise KeyError(f"Invalid variable: '{expr['name']}'")
        return env[expr["name"]]
    elif expr["type"] == "literal_bool":
        return expr["value"]
    elif expr["type"] == "literal_int":
        return expr["value"]
    elif expr["type"] == "literal_float":
        return expr["value"]
    elif expr["type"] == "literal_string":
        return expr["value"]
    else:
        raise ValueError("Invalid expr")


def interpolate_text(env, text) -> list[TextFragment]:
    ret = []
    for frag in text:
        if "variable" in frag:
            if frag["variable"] not in env:
                raise KeyError(f"Invalid variable: '{frag['variable']}'")
            ret.append(TextFragment(frag["tags"], env[frag["variable"]]))
        elif "text" in frag:
            ret.append(TextFragment(frag["tags"], frag["text"]))
    return ret


class Vm:
    def __init__(self, dgtree: DialogueTree):
        self.dgtree = dgtree
        self.env = {}

        variables = self.dgtree.data.get("environment", {}).get("variables", [])
        for var in variables:
            if "default" in var:
                self.env[var["name"]] = var["default"]

        self.trace = []
        self._current_node = None
        self._nodes = None

    def enter(self, section_name: str, node_id=None):
        self.trace = []

        section = self.dgtree.data["sections"][section_name]

        self._current_node = node_id if node_id is not None else section["start_node"]
        if self._current_node not in section["nodes"]:
            raise KeyError(f"Invalid node_id '{node_id}' for section '{section_name}'")

        self._nodes = section["nodes"]

    def advance(self, option_index: int = None) -> AdvanceResult:
        changed_vars = []

        if option_index is not None:
            node = self._nodes[self._current_node]
            if node["type"] != "choice":
                raise ValueError("option_index given for non-choice node")
            self._current_node = node["options"][option_index]["dest"]

        num_its = 0
        while self._current_node != "end":
            self.trace.append(self._current_node)
            node = self._nodes[self._current_node]
            node_type = node["type"]

            # Interactive nodes
            if node_type == "say":
                self._current_node = node["next"]

                return AdvanceResult(
                    SayNode(
                        self._current_node,
                        node["tags"],
                        node["speaker_id"],
                        interpolate_text(self.env, node["line"]["text"]),
                    ),
                    changed_vars,
                )
            elif node_type == "choice":
                options = []
                for option in node["options"]:
                    enabled = True
                    if "cond" in option:
                        enabled = eval_expr(self.env, option["cond"])
                    options.append(
                        ChoiceOption(
                            interpolate_text(self.env, option["line"]["text"]), enabled
                        )
                    )

                return AdvanceResult(
                    ChoiceNode(self._current_node, node["tags"], options), changed_vars
                )

            # Internal nodes
            elif node_type == "if":
                cond = eval_expr(self.env, node["cond"])
                if cond:
                    self._current_node = node["true_dest"]
                else:
                    self._current_node = node["false_dest"]
            elif node_type == "run":
                expr = node["code"]
                if expr["type"] == "assign":
                    self.env[expr["name"]] = eval_expr(self.env, expr["value"])
                else:
                    raise ValueError("Invalid run")

                if expr["name"] not in changed_vars:
                    changed_vars.append(expr["name"])

                self._current_node = node["next"]
            elif node_type == "goto":
                self._current_node = node["dest"]
            else:
                raise ValueError(f"Unknown node type: {node['type']}")

            num_its += 1
            if num_its > 100:
                raise StopIteration("Too many iterations")

        return AdvanceResult(None, changed_vars)
