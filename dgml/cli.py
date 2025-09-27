# /usr/bin/env python3
import argparse
import sys

from .compile import main as main_compile
from .play import main as main_play
from .util import main_ast as main_util_ast
from .meta import main_set as main_meta_set, main_get as main_meta_get
from .lint import main as main_lint


def add_compile_parser(subparsers):
    parser_compile = subparsers.add_parser("compile")
    parser_compile.set_defaults(func=main_compile)
    parser_compile.add_argument("--config", "-c", help="An optional config file")
    parser_compile.add_argument(
        "--meta", "-m", help="Meta file to include in compiled output"
    )
    parser_compile.add_argument("--output", "-o", help="Compiled JSON")
    parser_compile.add_argument(
        "--binary", "-b", help="Output binary dgmlb file instead", action="store_true"
    )
    parser_compile.add_argument("input", nargs="+", help="DGML files")


def add_lint_parser(subparsers):
    parser_lint = subparsers.add_parser("lint")
    parser_lint.set_defaults(func=main_lint)
    parser_lint.add_argument(
        "--fix", "-f", choices=["add-line-ids"], action="append", default=[]
    )
    parser_lint.add_argument("--config", "-c")
    parser_lint.add_argument(
        "--watch",
        "-w",
        action="store_true",
        help="Keep running and continously lint files that changed",
    )
    parser_lint.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Don't output anything if there are no errors or warnings",
    )
    parser_lint.add_argument("input", nargs="+", help="DGML files")


def add_meta_parser(subparsers):
    parser_meta = subparsers.add_parser("meta")
    parser_meta.add_argument("metafile", help="JSON file with meta data")
    meta_subparsers = parser_meta.add_subparsers(required=True)

    parser_get = meta_subparsers.add_parser("get")
    parser_get.set_defaults(func=main_meta_get)
    parser_get.add_argument(
        "--section",
        "-s",
        action="append",
        help="Specify section names to filter by",
    )
    parser_get.add_argument(
        "--line-id", "-l", action="append", help="Specify line ids to filter by"
    )
    parser_get.add_argument(
        "--no-header", "-H", action="store_true", help="Don't include a header line"
    )
    parser_get.add_argument("--csv", action="store_true")  # TODO: use csv module
    parser_get.add_argument("--json", action="store_true")  # TODO: format?
    parser_get.add_argument("field", nargs="+", help="Fields to include in the output")

    parser_set = meta_subparsers.add_parser("set")
    parser_set.set_defaults(func=main_meta_set)
    parser_set.add_argument("section")
    parser_set.add_argument("lineid")
    parser_set.add_argument("field")
    parser_set.add_argument("value")
    # dgml meta meta.json get --no-header --field status | sort | uniq -c # status statistics


def add_localize_parser(subparsers):
    # dgml localize extract file.dgml loc/de-de.json
    # dgml localize export loc/de-de.json game_de-de.csv
    # node_id;speaker;text;localization comment;translated;status
    # status is DRAFT, TRANSLATED, EDITED, REWORK, FINAL
    # dgml localize import loc/de-de.json game_de-de.csv
    parser_localize = subparsers.add_parser("localize")
    parser_localize.set_defaults(
        func=lambda args: sys.exit("This subcommand is not implemented yet")
    )
    localize_subparsers = parser_localize.add_subparsers(required=True)

    parser_extract = localize_subparsers.add_parser(
        "extract", help="Extract line ids from dgml file to localization JSON file"
    )
    parser_extract.add_argument("input", nargs="+")
    parser_extract.add_argument("--output", "-o", help="Localization JSON")

    parser_export = localize_subparsers.add_parser(
        "export", help="Export CSV for translation from localization JSON file"
    )
    parser_export.add_argument("locjson")
    parser_export.add_argument("csvfile")

    parser_import = localize_subparsers.add_parser(
        "import", help="Import CSV to localization JSON file"
    )
    parser_import.add_argument("locjson")
    parser_import.add_argument("csvfile")


def add_play_parser(subparsers):
    parser_play = subparsers.add_parser("play")
    parser_play.set_defaults(func=main_play)
    parser_play.add_argument("input")
    parser_play.add_argument("section")
    parser_play.add_argument(
        "--env",
        "-e",
        help="A variable environment to use (JSON file). Will be written back to at exit.",
    )
    parser_play.add_argument("--node", "-n")


def add_dot_parser(subparsers):
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
    add_util_parser(subparsers)

    args = parser.parse_args()

    args.func(args)


if __name__ == "__main__":
    main()
