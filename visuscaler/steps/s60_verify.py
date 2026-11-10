import os
import re
import xml.etree.ElementTree as ET

from ..textio import read_text, scale_int

ID = "verify"
TITLE = "6. Verify result"
DESCRIPTION = ("Re-reads source and destination and checks that every scaled value is exactly the source times "
               "the factor, that controls did not newly overflow their layer, and that registered files exist.")
ORDER = 60

GEOM = re.compile(r'<Property Name="(Left|Top|Width|Height|StartX|StartY|EndX|EndY)" Value="(-?\d+)"')
SUBDIRS = (("Pages", ".page"), ("Layers", ".layer"), ("TouchPads", ".tpr"))


def _overflowing(path):
    """Names of controls extending past their enclosing page/layer/touchpad."""
    out = set()
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return out

    def props(el):
        return {p.get("Name"): p.get("Value") for p in el if p.tag.endswith("Property")}

    def walk(el, size, trail):
        for child in el:
            tag = child.tag.rsplit("}", 1)[-1]
            p = props(child) if len(child) else {}
            nsize = size
            if tag in ("Layer", "Page", "TouchPad") and "Width" in p and "Height" in p:
                nsize = (int(p["Width"]), int(p["Height"]))
            if tag == "Control" and size and all(k in p for k in GEOM_KEYS):
                if (int(p["Left"]) + int(p["Width"]) > size[0] or int(p["Top"]) + int(p["Height"]) > size[1]):
                    out.add(child.get("Name") or "?")
            walk(child, nsize, trail)

    top = props(root)
    walk(root, (int(top["Width"]), int(top["Height"])) if "Width" in top and "Height" in top else None, "")
    return out


GEOM_KEYS = ("Left", "Top", "Width", "Height")


def run(ctx):
    ctx.require_dest()
    bad, checked, newly_over = [], 0, []
    for subdir, ext in SUBDIRS:
        for fn in ctx.files(ctx.src_root, subdir, ext):
            name = os.path.splitext(fn)[0]
            s, d = (os.path.join(r, subdir, fn) for r in (ctx.src_root, ctx.dest_root))
            if not os.path.isfile(d):
                bad.append("%s/%s missing in destination" % (subdir, fn))
                continue
            a, b = GEOM.findall(read_text(s)), GEOM.findall(read_text(d))
            excluded = ctx.is_excluded(subdir, name)
            if len(a) != len(b):
                bad.append("%s/%s: structure differs" % (subdir, fn))
                continue
            for (n1, v1), (n2, v2) in zip(a, b):
                checked += 1
                k = 1.0 if excluded else ctx.factor_for(n1)
                if n1 != n2 or scale_int(int(v1), k) != int(v2):
                    bad.append("%s/%s: %s %s -> %s (expected %s)" % (subdir, fn, n1, v1, v2, scale_int(int(v1), k)))
            new = _overflowing(d) - _overflowing(s)
            if new:
                newly_over.append("%s/%s: %s" % (subdir, fn, ", ".join(sorted(new)[:5])))

    vcp = os.path.join(ctx.dest_root, "Package.vcp")
    if os.path.isfile(vcp):
        gone = [f for f in re.findall(r'<Source File="([^"]+)"', read_text(vcp))
                if not os.path.exists(os.path.join(ctx.dest_root, f.replace("\\", os.sep)))]
        if gone:
            ctx.note("warning", "verify", "Package.vcp lists %d file(s) that do not exist: %s"
                     % (len(gone), ", ".join(gone[:8])))
    ctx.stats["geometry values verified"] = checked
    if bad:
        ctx.note("warning", "verify", "%d geometry value(s) differ from source x factor, e.g. %s"
                 % (len(bad), "; ".join(bad[:5])))
    if newly_over:
        ctx.note("warning", "verify", "Controls that now extend past their layer/page (they did not before): "
                 + " | ".join(newly_over[:10]))
    ctx.log("verify: %d values checked, %d mismatches" % (checked, len(bad)))
