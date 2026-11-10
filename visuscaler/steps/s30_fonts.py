import os
import re

from ..context import Context
from ..textio import patch_by_ordinal, read_text, register_source, scale_int, write_text

ID = "fonts"
TITLE = "3. Map fonts to the scaled size"
DESCRIPTION = ("Points every font reference at the existing font closest to the scaled size (same family, "
               "bold, italic). Optionally creates a font when no exact size exists. Never adds languages.")
ORDER = 30

FONT_REF = re.compile(r'(Font\[)([^\]]+)(\])')
REF_SUBDIRS = (("Pages", ".page"), ("Layers", ".layer"), ("TouchPads", ".tpr"),
               ("Borders", ".bdr"), ("StyleSheets", ".vcs"))


class Font:
    def __init__(self, path):
        self.path = path
        self.text = read_text(path)
        self.name = re.search(r'<LogicalFont[^>]* Name="([^"]+)"', self.text)[1]
        self.index = int(re.search(r'Name="Index" Value="(\d+)"', self.text)[1])
        blocks = dict(re.findall(r'<FontMapping LanguageId="([^"]+)">(.*?)</FontMapping>', self.text, re.S))
        block = blocks.get("en-US") or next(iter(blocks.values()))
        prop = lambda n: re.search(r'Name="%s" Value="([^"]*)"' % n, block)[1]
        self.family = prop("Family").lower()
        self.bold = prop("Bold") == "True"
        self.italic = prop("Italic") == "True"
        self.size = int(prop("Size"))

    @property
    def key(self):
        return (self.family, self.bold, self.italic)


def _closest(candidates, target):
    # nearest size, and on a tie prefer the larger font
    return min(candidates, key=lambda f: (abs(f.size - target), -f.size))


def _new_name(font, target, pattern, taken):
    m = pattern.match(font.name)
    base = ("%s%dpx%s" % (m["family"], target, m["style"])) if m else "%s%dpx" % (font.name, target)
    name, n = base, 2
    while name in taken:
        name, n = "%s_%d" % (base, n), n + 1
    return name


def _create(font, name, index, factor):
    text = font.text.replace('Name="%s">' % font.name, 'Name="%s">' % name, 1)
    text = re.sub(r'(Name="Index" Value=")\d+(")', lambda m: m[1] + str(index) + m[2], text, 1)
    return re.sub(r'(Name="Size" Value=")(\d+)(")',
                  lambda m: m[1] + str(scale_int(int(m[2]), factor)) + m[3], text)


def run(ctx: Context):
    ctx.require_dest()
    fonts_dir = os.path.join(ctx.src_root, "Fonts")
    fonts = [Font(os.path.join(fonts_dir, fn)) for fn in ctx.files(ctx.src_root, "Fonts", ".fninfo")]
    if not fonts:
        ctx.log("fonts: source has no fonts")
        return
    by_name = {f.name: f for f in fonts}
    pattern = re.compile(ctx.s.font_pattern)
    taken = set(by_name)
    next_index = max(f.index for f in fonts) + 1
    dest_vcp = os.path.join(ctx.dest_root, "Package.vcp")

    # which fonts are actually used by the files that get scaled
    used = set()
    ref_files = []
    for subdir, ext in REF_SUBDIRS:
        for fn in ctx.files(ctx.src_root, subdir, ext):
            if ctx.is_excluded(subdir, os.path.splitext(fn)[0]):
                continue
            ref_files.append((subdir, fn))
            used |= {m[1] for m in FONT_REF.findall(read_text(os.path.join(ctx.src_root, subdir, fn)))}

    mapping, gaps, created = {}, [], []
    for name in sorted(used):
        font = by_name.get(name)
        if font is None:
            ctx.note("warning", "fonts", "Font '%s' is referenced but has no .fninfo; left as is." % name)
            mapping[name] = name
            continue
        target = scale_int(font.size, ctx.factor)
        same = [f for f in fonts if f.key == font.key]
        exact = [f for f in same if f.size == target]
        if exact:
            mapping[name] = exact[0].name
        elif ctx.s.font_create_missing:
            new = _new_name(font, target, pattern, taken)
            taken.add(new)
            write_text(os.path.join(ctx.dest_root, "Fonts", new + ".fninfo"),
                       _create(font, new, next_index, ctx.factor))
            write_text(dest_vcp, register_source(read_text(dest_vcp), "Fonts\\%s.fninfo" % new))
            next_index += 1
            mapping[name] = new
            created.append("%s (%dpx)" % (new, target))
        else:
            sub = _closest(same, target)
            mapping[name] = sub.name
            gaps.append("%s (%dpx) needs %dpx, using %s (%dpx)" % (name, font.size, target, sub.name, sub.size))

    def swap(s, d):
        ctx.stats["font references remapped"] += 1
        return s[1] + mapping.get(s[2], s[2]) + s[3]

    for subdir, fn in ref_files:
        src_text = read_text(os.path.join(ctx.src_root, subdir, fn))
        dest_p = os.path.join(ctx.dest_root, subdir, fn)
        write_text(dest_p, patch_by_ordinal(src_text, read_text(dest_p), FONT_REF, swap))

    if created:
        ctx.note("info", "fonts", "Created %d font(s): %s." % (len(created), ", ".join(created)))
    if gaps:
        ctx.note("action", "fonts",
                 "No font of the exact scaled size exists for %d font(s); the nearest was used. Text may be "
                 "smaller or larger than intended. Add the font in Automation Studio or re-run with "
                 "'create missing fonts': %s" % (len(gaps), "; ".join(gaps)))
    ctx.log("fonts: %d refs remapped, %d created, %d gaps"
            % (ctx.stats["font references remapped"], len(created), len(gaps)))
