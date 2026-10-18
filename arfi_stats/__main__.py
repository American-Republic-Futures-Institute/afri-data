"""CLI for synthetic/pre-publication ARFI statistical chart models.

Example:
  python -m arfi_stats --chart histogram --input examples/statkit-synthetic.json \
      --x value --segment region --bins fd --unit percent

Outputs are ALWAYS unsigned previews and require downstream STAT-01 approval.
"""
import argparse
import json
from pathlib import Path
import sys

from . import boxplot, ecdf, frequency, histogram, intervals, scatter, time_series

MAX_BYTES = 16 * 1024 * 1024


def read_json(path, *, expected="list"):
    if path == "-":
        raw = sys.stdin.buffer.read(MAX_BYTES + 1)
    else:
        file = Path(path)
        if file.stat().st_size > MAX_BYTES:
            raise ValueError("Input JSON exceeds the 16 MiB preview limit")
        raw = file.read_bytes()
    if len(raw) > MAX_BYTES:
        raise ValueError("Input JSON exceeds the 16 MiB preview limit")

    def nonfinite(token):
        raise ValueError("Non-finite JSON values are forbidden: " + token)

    def pairs(items):
        obj = {}
        for key, value in items:
            if key in obj:
                raise ValueError("Duplicate JSON key rejected: " + key)
            obj[key] = value
        return obj

    value = json.loads(raw.decode("utf-8"), parse_constant=nonfinite, object_pairs_hook=pairs)
    if not isinstance(value, list if expected == "list" else dict):
        raise ValueError("Invalid normalized JSON " + expected + " input")
    return value


def run(args):
    rows = read_json(args.input)
    where = None
    if args.where:
        where = read_json(args.where, expected="dict")
    common = {"segment": args.segment, "availability": args.availability,
              "where": where}
    if args.chart == "histogram":
        bins = int(args.bins) if args.bins.isdecimal() else args.bins
        return histogram(rows, x=args.x, bins=bins, scale=args.scale,
                         unit=args.unit, **common)
    if args.chart == "ecdf":
        return ecdf(rows, x=args.x, unit=args.unit, **common)
    if args.chart == "boxplot":
        return boxplot(rows, x=args.x, unit=args.unit, **common)
    if args.chart == "frequency":
        return frequency(rows, x=args.x, scale=args.scale, **common)
    if args.chart == "scatter":
        if not args.y:
            raise ValueError("Scatter needs --y")
        return scatter(rows, x=args.x, y=args.y, x_unit=args.x_unit,
                       y_unit=args.unit, **common)
    if args.chart == "time-series":
        if not args.y:
            raise ValueError("Time series needs --y")
        return time_series(rows, x=args.x, y=args.y, unit=args.unit, **common)
    if args.chart == "interval":
        if not (args.y and args.lower and args.upper):
            raise ValueError("Publisher intervals need --y, --lower and --upper")
        return intervals(rows, x=args.x, y=args.y, lower=args.lower, upper=args.upper,
                         unit=args.unit, interval_label=args.interval_label, **common)
    raise ValueError("Unknown source-neutral chart primitive")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chart", required=True, choices=[
        "histogram", "ecdf", "boxplot", "frequency",
        "scatter", "time-series", "interval"])
    parser.add_argument("--input", required=True, help="JSON list filename, or - for stdin")
    parser.add_argument("--x", required=True, help="Numerical value, category or period field")
    parser.add_argument("--y", help="Second measure field")
    parser.add_argument("--segment", help="Optional categorical cohort/segment field")
    parser.add_argument("--where", help="Optional JSON filter object file")
    parser.add_argument("--availability", default="availability")
    parser.add_argument("--unit", default="untyped")
    parser.add_argument("--x-unit", default="untyped")
    parser.add_argument("--bins", default="fd", help="fd/sturges/sqrt/auto or 1..64")
    parser.add_argument("--scale", default="count", choices=["count", "proportion"])
    parser.add_argument("--lower")
    parser.add_argument("--upper")
    parser.add_argument("--interval-label", default="publisher-reported interval")
    parser.add_argument("--output", default="-", help="Output JSON path, or - for stdout")
    args = parser.parse_args(argv)
    chart = run(args)
    text = json.dumps(chart, indent=2, sort_keys=True,
                      ensure_ascii=False, allow_nan=False) + "\n"
    if args.output == "-":
        print(text, end="")
    else:
        Path(args.output).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
