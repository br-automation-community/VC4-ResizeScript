"""python -m visuscaler                      open the GUI
python -m visuscaler steps                 list the available steps
python -m visuscaler run SETTINGS.json [--steps copy,geometry] [--dry-run]
"""
import argparse
import sys

from . import runner
from .settings import Settings
from .steps import discover


def main(argv=None):
    ap = argparse.ArgumentParser(prog="visuscaler")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("steps")
    r = sub.add_parser("run")
    r.add_argument("settings")
    r.add_argument("--steps", default="")
    r.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "steps":
        for m in discover():
            print("%-10s %s\n%12s%s" % (m.ID, m.TITLE, "", m.DESCRIPTION))
    elif args.cmd == "run":
        ctx = runner.run(Settings.load(args.settings), [s for s in args.steps.split(",") if s], args.dry_run)
        print("\n" + ctx.report_markdown)
    else:
        from .gui import launch
        launch()


if __name__ == "__main__":
    sys.exit(main())
