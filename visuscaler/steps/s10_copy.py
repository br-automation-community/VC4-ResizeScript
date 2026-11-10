import os
import re
import shutil

from ..context import KEEP_IN_DEST
from ..textio import read_text, write_text

ID = "copy"
TITLE = "1. Copy source to destination"
DESCRIPTION = ("Copies every file of the source visualization into the destination. "
               "VCObject.vc and Vc.dob already in the destination are kept.")
ORDER = 10


def run(ctx):
    src, dest = ctx.src_root, ctx.dest_root
    had_identity = os.path.exists(os.path.join(dest, "VCObject.vc"))
    os.makedirs(dest, exist_ok=True)
    src_files = set()
    for dirpath, _, files in os.walk(src):
        rel_dir = os.path.relpath(dirpath, src)
        os.makedirs(os.path.join(dest, rel_dir), exist_ok=True)
        for fn in files:
            rel = os.path.normpath(os.path.join(rel_dir, fn))
            src_files.add(rel)
            target = os.path.join(dest, rel)
            if rel in KEEP_IN_DEST and os.path.exists(target):
                continue
            shutil.copyfile(os.path.join(dirpath, fn), target)
            ctx.stats["files copied"] += 1

    extras = []
    for dirpath, _, files in os.walk(dest):
        for fn in files:
            rel = os.path.normpath(os.path.join(os.path.relpath(dirpath, dest), fn))
            if rel not in src_files and rel not in KEEP_IN_DEST:
                extras.append(rel)
    if extras and ctx.s.clean_dest:
        for rel in extras:
            os.remove(os.path.join(dest, rel))
        ctx.note("info", "copy", "Removed %d destination file(s) not present in the source: %s"
                 % (len(extras), ", ".join(sorted(extras)[:10])))
    elif extras:
        ctx.note("action", "copy",
                 "Destination has %d file(s) that are not in the source (%s). They are not registered "
                 "in Package.vcp and may be left over from a skeleton page or earlier run; delete them "
                 "if unused." % (len(extras), ", ".join(sorted(extras)[:10])))
    if not had_identity:
        vc = os.path.join(dest, "VCObject.vc")
        text = read_text(vc)
        write_text(vc, re.sub(r'(<Visualization Name=")[^"]*(")', lambda m: m[1] + ctx.s.dest + m[2], text, 1))
        ctx.note("info", "copy", "Created visualization '%s' from the source's VCObject.vc and Vc.dob." % ctx.s.dest)
    ctx.log("copy: %d files" % ctx.stats["files copied"])
