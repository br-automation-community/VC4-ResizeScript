import datetime
import os
import re

from ..context import find_project_root
from ..textio import read_text

ID = "checklist"
TITLE = "7. Write the pre-flight checklist"
DESCRIPTION = ("Collects everything the earlier steps flagged, adds the standing checks, and writes a "
               "markdown checklist of what to verify in Automation Studio and on the panel before use.")
ORDER = 90

STANDING = [
    "Build the project in Automation Studio and fix any VC compile errors in the output window.",
    "Confirm the target display really is {w}x{h}: the tool cannot see the panel configuration.",
    "Confirm '{dest}' is the visualization assigned to the target (not '{src}'); only one should run.",
    "Open '{dest}' in the visualization editor and flip through every page, including pages that only "
    "appear via popups, alarms or recipes.",
    "Check text fit on the busiest pages: fonts changed size, and long text strings can wrap or clip.",
    "Check hidden/popup layers (NavLayer, password, help) show and stack correctly with the visible ones.",
    "Re-run touch calibration and test the small buttons and touchpads on the real panel.",
    "Test every touchpad (numeric, alpha, navigation): they open over the page and must not cover the "
    "field being edited.",
]


def _dir_bytes(path):
    return sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(path) for f in fs)


def run(ctx):
    w, h = ctx.dest_resolution
    fmt = dict(w=w, h=h, dest=ctx.s.dest, src=ctx.s.source)
    for text in STANDING:
        ctx.note("action", "checklist", text.format(**fmt))

    vcp_s = os.path.join(ctx.src_root, "Package.vcp")
    vcp_d = os.path.join(ctx.dest_root, "Package.vcp")
    if os.path.isfile(vcp_s) and os.path.isfile(vcp_d):
        shared = set(re.findall(r'Source\[global\][^"]+', read_text(vcp_d))) & \
            set(re.findall(r'Source\[global\][^"]+', read_text(vcp_s)))
        if shared:
            ctx.note("action", "checklist", "Source and destination share %d global datapoint(s) "
                     "(page change, current page, language...). Fine if only one visualization is active, "
                     "otherwise they will fight over them." % len(shared))
    if os.path.isdir(ctx.dest_root) and os.path.isdir(ctx.src_root):
        a, b = _dir_bytes(ctx.src_root), _dir_bytes(ctx.dest_root)
        ctx.note("info", "checklist", "Visualization size on disk: %.1f MB -> %.1f MB. Bitmaps grow with the "
                 "square of the factor; check the target's UserROM/memory." % (a / 1e6, b / 1e6))

    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = ["# %s -> %s (x%g by y%g, %dx%d) %s" % (ctx.s.source, ctx.s.dest, ctx.s.factor_x, ctx.s.factor_y, w, h,
                                              "[DRY RUN]" if ctx.dry_run else ""), "", "Generated %s" % stamp, ""]
    titles = {"action": "Check before use", "warning": "Probable problems", "info": "For information"}
    for level in ("action", "warning", "info"):
        items = [n for n in ctx.notes if n.level == level]
        if not items:
            continue
        lines += ["## " + titles[level], ""]
        lines += [("- [ ] " if level != "info" else "- ") + "**%s**: %s" % (n.step, n.text) for n in items]
        lines.append("")
    if ctx.stats:
        lines += ["## Run statistics", ""] + ["- %s: %d" % kv for kv in sorted(ctx.stats.items())] + [""]
    ctx.report_markdown = "\n".join(lines)

    if not ctx.dry_run:
        root = find_project_root(ctx.s.package_dir) or ctx.s.package_dir
        folder = ctx.s.report_dir or os.path.join(root, "VisuScaler_Reports")
        os.makedirs(folder, exist_ok=True)
        ctx.report_path = os.path.join(folder, "%s_%s_%s.md" % (
            ctx.s.dest, ctx.s.source, datetime.datetime.now().strftime("%Y%m%d_%H%M%S")))
        with open(ctx.report_path, "w", encoding="utf-8") as f:
            f.write(ctx.report_markdown)
        ctx.log("checklist written: %s" % ctx.report_path)
