import json
import os
import sys

from .colors import *
import dgml.runtime as rt


def render_fragment(frag: rt.TextFragment) -> str:
    ret = ""
    if "color" in frag.tags:
        assert frag.tags["color"] is not None
        ret += COLORS[frag.tags["color"]]
    if "bold" in frag.tags:
        ret += BOLD
    ret += frag.text
    ret += COLOR_RESET
    return ret


def render_text(text: list[rt.TextFragment]) -> str:
    return "".join(render_fragment(frag) for frag in text)


def get_answer(valid_answers):
    while True:
        s = input("Answer: ")
        try:
            i = int(s)
            if i in valid_answers:
                return i
            else:
                print("Not a valid option")
        except ValueError:
            print("Input must be a number")
            pass


def main(args):
    dgtree = rt.DialogueTree(args.input)
    vm = rt.Vm(dgtree)

    if args.env and os.path.isfile(args.env):
        with open(args.env) as f:
            env = json.load(f)
        for k, v in env.items():
            vm.env[k] = v

    vm.enter(args.section, args.node)
    section = dgtree.data["sections"][args.section]

    state = vm.advance()
    while state.node is not None:
        for var in state.changed_vars:
            print(f"{FAINT}{BOLD}# SET {var} = {vm.env[var]}{COLOR_RESET}")

        if isinstance(state.node, rt.SayNode):
            print(f"{state.node.speaker_id}: {render_text(state.node.text)}")
            state = vm.advance()

        elif isinstance(state.node, rt.ChoiceNode):
            valid_answers = []
            for i, option in enumerate(state.node.options):
                if option.enabled:
                    valid_answers.append(i + 1)
                    num = i + 1
                else:
                    num = f"{FAINT}X"
                dest = section["nodes"][state.node.node_id]["options"][i]["dest"]
                print(
                    f"{num}. {render_text(option.text)} -> {FAINT}{UNDERLINE}@{dest}{COLOR_RESET}"
                )

            if len(valid_answers) == 0:
                sys.exit("No valid answers")
            answer = get_answer(valid_answers)
            print()

            state = vm.advance(answer - 1)

    if args.env:
        with open(args.env, "w") as f:
            json.dump(vm.env, f, indent=2)
