import json
import os


def get_field(section_name, line_id, line_meta, field_name):
    if field_name == "section":
        return section_name
    elif field_name == "line_id":
        return line_id
    else:
        return line_meta.get(field_name, "")


def main_get(args):
    with open(args.metafile) as f:
        meta = json.load(f)

    rows = []
    col_sizes = [len(f) for f in args.field]

    for section_name, section in meta.items():
        if args.section is not None and section not in args.section:
            continue
        for line_id, line_meta in section.items():
            if args.line_id is not None and line_id not in args.line_id:
                continue
            rows.append(
                tuple(
                    get_field(section_name, line_id, line_meta, f) for f in args.field
                )
            )
            for i in range(len(args.field)):
                col_sizes[i] = max(col_sizes[i], len(rows[-1][i]))

    row_fmt = "\t".join(f"{{:<{s}}}" for s in col_sizes)

    if not args.no_header:
        print(row_fmt.format(*args.field))

    for row in rows:
        print(row_fmt.format(*row))


def main_set(args):
    if os.path.exists(args.metafile):
        with open(args.metafile) as f:
            meta = json.load(f)
    else:
        meta = {}

    if args.section not in meta:
        meta[args.section] = {}

    if args.lineid not in meta[args.section]:
        meta[args.section][args.lineid] = {}

    meta[args.section][args.lineid][args.field] = args.value

    with open(args.metafile, "w") as f:
        json.dump(meta, f, indent=2)
