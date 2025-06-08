import json
import sys

COLORS = {
    "black": "\033[30m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "white": "\033[37m",
}

BOLD = "\033[1m"
FAINT = "\033[2m"
ITALIC = "\033[3m"
UNDERLINE = "\033[4m"

COLOR_RESET = "\033[0m"


def eval_expr(env, expr):
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
        raise AssertionError("Invalid expr")


def run_expr(env, expr):
    if expr["type"] == "assign":
        val = eval_expr(env, expr["value"])
        print(f"{FAINT}{BOLD}# SET {expr['name']} = {val}{COLOR_RESET}")
        env[expr["name"]] = val
    else:
        raise AssertionError("Invalid run")


def render_tags(tags):
    ret = COLOR_RESET
    last_color = None
    for tag in tags:
        if tag[0] == "color":
            last_color = tag[1]
        elif tag[0] == "bold":
            ret += BOLD
        else:
            raise AssertionError(f"Invalid markup tag: {tag[0]}")
    if last_color is not None:
        ret += COLORS[last_color]
    return ret


def render_text(env, text):
    ret = ""
    current_tags = []
    for frag in text:
        if "text" in frag:
            ret += frag["text"]
        elif "variable" in frag:
            ret += str(env[frag["variable"]])
        elif "tag_open" in frag:
            current_tags.append((frag["tag_open"], frag.get("parameter")))
            ret += render_tags(current_tags)
        elif "tag_close" in frag:
            assert current_tags[-1][0] == frag["tag_close"]
            current_tags = current_tags[:-1]
            ret += render_tags(current_tags)
        else:
            raise AssertionError("Invalid text")
    ret += COLOR_RESET
    return ret


def get_answer(valid_answers):
    while True:
        s = input("Answer: ")
        try:
            i = int(s)
            if i in valid_answers:
                return i
        except ValueError:
            pass


def play(env, node_map, nodes, idx):
    while idx < len(nodes):
        node = nodes[idx]
        if node["type"] == "if":
            cond = eval_expr(env, node["cond"])
            if cond:
                idx = node_map[node["true_dest"]]
            elif "false_dest" in node:
                idx = node_map[node["false_dest"]]
            else:
                idx += 1
        elif node["type"] == "say":
            print(f"{node['speaker_id']}: {render_text(env, node['line']['text'])}")
            idx += 1
        elif node["type"] == "choice":
            opts = []
            for opt in node["options"]:
                cond = True
                if "cond" in opt:
                    cond = eval_expr(env, opt["cond"])
                opts.append((cond, opt["line"]["text"], opt["dest"]))

            valid_answers = []
            for o in range(len(opts)):
                cond, text, dest = opts[o]
                num = o + 1
                num_color = ""
                if cond:
                    valid_answers.append(num)
                else:
                    num = "X"
                    num_color = FAINT
                print(
                    f"{num_color}{num}. {render_text(env, text)} -> @{UNDERLINE}{dest}{COLOR_RESET}"
                )
            if len(valid_answers) == 0:
                raise AssertionError("No valid answers")
            answer = get_answer(valid_answers)
            idx = node_map[opts[answer - 1][2]]
        elif node["type"] == "run":
            run_expr(env, node["code"])
            idx += 1
        elif node["type"] == "goto":
            idx = node_map[node["dest"]]
        else:
            raise AssertionError(f"Unknown node type: {node['type']}")


def main(args):
    env = {}
    if args.env:
        with open(args.env) as f:
            env = json.load(f)

    with open(args.input) as f:
        dlg = json.load(f)

    section = dlg["sections"][0]
    if args.section:
        for s in dlg["sections"]:
            if s["name"] == args.section:
                section = s
                break
        else:
            sys.exit("Section not found")

    node_map = {"end": 1000000}
    for n in range(len(section["nodes"])):
        node_map[section["nodes"][n]["node_id"]] = n

    if args.node:
        start = node_map[args.node]
    else:
        start = 0

    play(env, node_map, section["nodes"], start)

    if args.env:
        with open(args.env, "w") as f:
            json.dump(env, f, indent=2)
