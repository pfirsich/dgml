# /usr/bin/env python3
import argparse

from .compile import main as main_compile
from .util import main_ast as main_util_ast


def add_compile_parser(subparsers):
    parser_compile = subparsers.add_parser("compile")
    parser_compile.add_argument("input", nargs="+")
    parser_compile.add_argument("--output", "-o", default="compiled.json")
    parser_compile.set_defaults(func=main_compile)


def add_lint_parser(subparsers):
    # --watch https://pypi.org/project/watchdog/#description
    # --lint
    # --fix add-line-ids
    # exit with non-zero status on warning or error
    # lint:
    # * unreachable nodes
    # * warn about GOTO after SAY
    # * check valid speaker id
    # * check every interpolated var exists in env
    # * check markup tags are properly nested
    # * lint that node ids are unique
    pass


def add_meta_parser(subparsers):
    # dgml meta set
    # dgml meta get --section SECTION --node-id NODE_ID --column COL --tsv --csv --json
    # dgml meta get --column status | sort | uniq -c # status statistics
    pass


def add_localize_parser(subparsers):
    # dgml localize export de-de game_de-de.csv
    # node_id;speaker;text;localization comment;translated;status
    # status is DRAFT, TRANSLATED, EDITED, REWORK, FINAL
    # dgml localize import de-de game_de-de.csv
    pass


def add_play_parser(subparsers):
    pass


def add_dot_parser(subparsers):
    # dgml play [--print-code] --debug (print all node ids) or --trace
    # # if |cond| target_true target_false # cond green or red, chosen target bold
    # # |cond| always red or blue
    pass


def add_md_parser(subparsers):
    # dgml md -> linearizes and prints markdown scripts (for non-developers to read, VO casting, etc.)
    pass


def add_util_parser(subparsers):
    # dgml util rename-node old_id new_id

    parser_util = subparsers.add_parser("util")
    util_subparsers = parser_util.add_subparsers(required=True)

    parser_ast = util_subparsers.add_parser("ast")
    parser_ast.set_defaults(func=main_util_ast)
    parser_ast.add_argument("--expr", "-e", action="store_true")
    parser_ast.add_argument("--file", "-f", action="store_true")
    parser_ast.add_argument("input")


def main():
    parser = argparse.ArgumentParser()

    subparsers = parser.add_subparsers(required=True)

    add_compile_parser(subparsers)
    add_lint_parser(subparsers)
    add_meta_parser(subparsers)
    add_localize_parser(subparsers)
    add_play_parser(subparsers)
    add_dot_parser(subparsers)
    add_md_parser(subparsers)
    add_util_parser(subparsers)

    args = parser.parse_args()

    args.func(args)

    # compile into a single json file?
    # list meta of all files
    # generate localization tsv for all files (merged!)
    # also no duplicate sections in different files
    # => some sort of project? is it too weird to impose a folder structure?

    # dgml compile foo.dgml foo.json
    # dgml lint --add-node-ids --watch foo.dgml # unreachable nodes, invalid label identifiers
    # dgml meta update FILES.. # insert lines for new line ids
    # dgml meta get FILES.. [--node-id] [--columns] [--csv] [--tsv]
    # output localization CSV: dgml meta get FILES.. --csv --columns node_id,speaker,text,
    # dgml meta set node-id key value
    # dgml localize export foo-de.dgml-loc foo-de.tsv # likely multiple files
    # dgml localize import foo-de.tsv foo-de.dgml-loc
    # dgml localize status foo.dgml foo-de.dgml-loc # how many lines translated?
    # dgml play --log log.txt --node-id NODEID SECTION
    # dgml dot

    # meta: comments (developer, localization, voice)
    # character ids: use "pilot" and show "sir lieutenant Cavendish" in game, fixed list of chars (linting!)
    # status: placeholder, draft, polished, edited, rework, final


if __name__ == "__main__":
    main()
