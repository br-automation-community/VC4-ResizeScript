import os
import re
import shutil
from collections import Counter

from ..context import Context
from ..textio import patch_by_ordinal, read_text, scale_int, write_text

ID = "geometry"
TITLE = "2. Scale layout geometry"
DESCRIPTION = ("Scales Left/Top/Width/Height and the other pixel properties (padding, spacing, line and "
               "border widths, border splits, grid sizes...) on pages, layers, touchpads and borders.")
ORDER = 20

SUBDIRS = (("Pages", ".page"), ("Layers", ".layer"), ("TouchPads", ".tpr"), ("Borders", ".bdr"))
NUMERIC_PROP = re.compile(r'<Property Name="([A-Za-z0-9_-]+)" Value="-?\d+"')
PIXELISH = re.compile(r"Width|Height|Size|Offset|Spacing|Radius|Length|Left|Top|Right|Bottom|Pad|Gap|Margin|Thick"
                      r"|^(Start|End|Center|Origin)[XY]$", re.I)
NOT_PIXELS = re.compile(r"Color|Index|BitmapOffset")


def run(ctx: Context):
    ctx.require_dest()
    names = "|".join(re.escape(n) for n in sorted(ctx.s.pixel_properties, key=len, reverse=True))
    regex = re.compile(r'(<Property Name=")(%s)(" Value=")(-?\d+)(")' % names)
    seen_unlisted = Counter()
    nonint = 0

    def scale(s, d):
        nonlocal nonint
        v = int(s[4])
        k = ctx.factor_for(s[2])
        out = scale_int(v, k)
        if abs(v * k - out) > 1e-9:
            nonint += 1
        ctx.stats["values scaled"] += 1
        return s[1] + s[2] + s[3] + str(out) + s[5]

    for subdir, ext in SUBDIRS:
        for fn in ctx.files(ctx.src_root, subdir, ext):
            name = os.path.splitext(fn)[0]
            src_p = os.path.join(ctx.src_root, subdir, fn)
            dest_p = os.path.join(ctx.dest_root, subdir, fn)
            src_text = read_text(src_p)
            for n in NUMERIC_PROP.findall(src_text):
                if n not in ctx.s.pixel_properties and PIXELISH.search(n) and not NOT_PIXELS.search(n):
                    seen_unlisted[n] += 1
            if ctx.is_excluded(subdir, name):
                shutil.copyfile(src_p, dest_p)   # restore, in case an earlier run scaled it
                ctx.stats["files excluded"] += 1
                ctx.note("info", "geometry", "%s/%s left at its original size (excluded)." % (subdir, fn))
                continue
            write_text(dest_p, patch_by_ordinal(src_text, read_text(dest_p), regex, scale))
            ctx.stats["files scaled"] += 1

    if nonint:
        ctx.note("action", "geometry",
                 "%d value(s) did not scale to a whole pixel and were rounded (X x%g, Y x%g); neighbouring "
                 "controls can end up 1px off. Check aligned rows/columns."
                 % (nonint, ctx.s.factor_x, ctx.s.factor_y))
    if seen_unlisted:
        ctx.note("action", "geometry",
                 "These numeric properties look pixel-related but are not in the scaled list, so they were "
                 "left alone: %s. Add them under Options if they are sizes."
                 % ", ".join("%s (%d)" % kv for kv in sorted(seen_unlisted.items())))
    ctx.log("geometry: %d values in %d files" % (ctx.stats["values scaled"], ctx.stats["files scaled"]))
