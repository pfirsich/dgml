from pprint import pprint

from .parser import parse_dgml, parse_expr


def main_ast(args):
    if args.file:
        with open(args.input) as f:
            source = f.read()
    else:
        source = args.input

    if args.expr:
        pprint(parse_expr(source))
    else:
        pprint(parse_dgml(source))
