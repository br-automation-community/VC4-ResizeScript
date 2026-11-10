import glob
import os
import re

from ..context import find_project_root
from ..textio import newline_of, read_text, write_text

ID = "project"
TITLE = "5. Set destination resolution and check registration"
DESCRIPTION = ("Writes the new resolution into the destination's VCObject.vc and checks that the destination "
               "is registered in Package.pkg and mapped to the same data sources as the source.")
ORDER = 50


def run(ctx):
    ctx.require_dest()
    sw_, sh_ = ctx.src_resolution
    w, h = ctx.dest_resolution
    for label, src, k in (("width", sw_, ctx.s.factor_x), ("height", sh_, ctx.s.factor_y)):
        if abs(src * k - round(src * k)) > 1e-9:
            ctx.note("action", "project", "Screen %s %d x %g = %g is not a whole number; it was rounded to %d. "
                     "Choose a factor that divides evenly, or accept that the layout is off by a fraction."
                     % (label, src, k, src * k, round(src * k)))
    p = os.path.join(ctx.dest_root, "VCObject.vc")
    text = read_text(p)
    text = re.sub(r'(Name="Width" Value=")\d+(")', lambda m: m[1] + str(w) + m[2], text, 1)
    text = re.sub(r'(Name="Height" Value=")\d+(")', lambda m: m[1] + str(h) + m[2], text, 1)
    write_text(p, text)
    ctx.log("project: resolution %dx%d" % (w, h))

    _register(ctx, w, h)


def _register(ctx, w, h):
    """Add the destination to Package.pkg and the data sources, as the source is.

    Missing entries are added (with the new resolution as description) unless register_dest is off
    or this is a dry run, in which case they are only reported.
    """
    s = ctx.s
    write = s.register_dest and not ctx.dry_run

    pkg = os.path.join(s.package_dir, "Package.pkg")
    if os.path.isfile(pkg) and (">%s<" % s.dest) not in read_text(pkg):
        text = read_text(pkg)
        nl = newline_of(text)
        line = re.search(r'[ 	]*<Object [^>]*Language="Vc"[^>]*>%s</Object>' % re.escape(s.source), text)
        entry = '<Object Type="DataObject" Language="Vc" Description="%dx%d">%s</Object>' % (w, h, s.dest)
        if write and line:
            indent = re.match(r"[ 	]*", line[0])[0]
            text = text[:line.end()] + nl + indent + entry + text[line.end():]
            write_text(pkg, text)
            ctx.note("info", "project", "Added '%s' to %s." % (s.dest, pkg))
        else:
            ctx.note("action", "project", "'%s' is not listed in %s. Add it as a Visualization object in "
                     "Automation Studio." % (s.dest, pkg))

    root = find_project_root(s.package_dir)
    if not root:
        return
    _map_data_sources(ctx, root, write)
    _report_physical(ctx, root)


def _report_physical(ctx, root):
    """Cpu.sw and Hardware.hw are never edited: every configuration maps exactly one visualization to
    its display, so which configuration runs the new one is the user's call."""
    s = ctx.s
    mapped = []
    for hw in glob.glob(os.path.join(root, "Physical", "*", "Hardware.hw")):
        m = re.search(r'<Parameter ID="(Vnc)?VcObjectName" Value="%s"' % re.escape(s.source), read_text(hw))
        if m:
            mapped.append(os.path.relpath(hw, root))
    where = ("The source '%s' is mapped in: %s. " % (s.source, ", ".join(mapped))) if mapped else ""
    ctx.note("action", "project",
             "'%s' is not added to any Cpu.sw or Hardware.hw. %sTo run it on a configuration, add it to that "
             "Cpu.sw (VcDataObjects) and set VncVcObjectName / VcObjectName in its Hardware.hw to '%s'. "
             "A visualization in a Cpu.sw that no display maps fails the build with 'Mapping for the Visual "
             "Components object is missing'." % (s.dest, where, s.dest))



def _map_data_sources(ctx, root, write):
    """Let the destination use every data point the source may use (ConnectingVisus in the .dso files).

    Without this Automation Studio reports the message that the mapping for the Visual Components object is missing.
    """
    s = ctx.s
    logical = os.path.join(root, "Logical")
    rel = os.path.relpath(s.package_dir, logical).replace("/", "\\")
    src_ref, dest_ref = rel + "\\" + s.source, rel + "\\" + s.dest
    pattern = re.compile(r'(Name="ConnectingVisus" Value=")([^"]*)(")')

    def add(m):
        refs = m[2].split(",")
        if src_ref not in refs or dest_ref in refs:
            return m[0]
        ctx.stats["data points mapped"] += 1
        return m[1] + m[2] + "," + dest_ref + m[3]

    pending = []
    for dirpath, _, files in os.walk(os.path.join(logical, "VCShared")):
        for fn in files:
            if not fn.lower().endswith(".dso"):
                continue
            path = os.path.join(dirpath, fn)
            text = read_text(path)
            new = pattern.sub(add, text)
            if new != text:
                pending.append(os.path.relpath(path, root))
                if write:
                    write_text(path, new)
    if pending and write:
        ctx.note("info", "project", "Mapped '%s' to the same data points as '%s' in: %s."
                 % (s.dest, s.source, ", ".join(pending)))
    elif pending:
        ctx.note("action", "project", "'%s' is not mapped to the data points of '%s' (ConnectingVisus) in: %s. "
                 "Open the data source in Automation Studio and connect it, or the build fails with "
                 "'Mapping for the Visual Components object is missing'." % (s.dest, s.source, ", ".join(pending)))
