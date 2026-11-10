import os
import re
import shutil
import struct

from ..context import Context
from ..textio import patch_by_ordinal, read_text, scale_int, write_text
from ..settings import BITMAP_PIXEL_PROPERTIES

ID = "bitmaps"
TITLE = "4. Resample bitmaps"
DESCRIPTION = ("Resizes every bitmap image by the factor, or its whole part with the whole-factor option "
               "(including hidden-layer gradients), and scales the "
               "fill-area offsets in the .bminfo files. Flat/palette art uses nearest-neighbour, "
               "smooth art bicubic.")
ORDER = 40


def _bmp_bits(path):
    if not path.lower().endswith(".bmp"):
        return None
    with open(path, "rb") as f:
        head = f.read(30)
    return struct.unpack("<H", head[28:30])[0] if len(head) == 30 else None


def _pick(ctx, name, im, transparent):
    choice = ctx.s.bitmap_overrides.get(name) or ctx.s.bitmap_resample
    if choice in ("nearest", "bicubic"):
        return choice
    flat = im.mode in ("P", "1", "L") or transparent or im.convert("RGBA").getcolors(maxcolors=256) is not None
    return "nearest" if flat else "bicubic"


def run(ctx: Context):
    ctx.require_dest()
    try:
        from PIL import Image
    except ImportError:
        ctx.note("action", "bitmaps", "Pillow is not installed, so bitmaps were NOT resized "
                 "(pip install pillow).")
        raise
    names = "|".join(BITMAP_PIXEL_PROPERTIES)
    fill_re = re.compile(r'(<Property Name=")(%s)(" Value=")(-?\d+)(")' % names)
    excluded = ctx.excluded_bitmap_names()
    bicubic, changed_depth, oversized = [], [], []
    ref_w, ref_h = ctx.dest_resolution
    bx, by = ctx.bitmap_factors
    if bx != by:
        ctx.note("action", "bitmaps", "X and Y bitmap factors differ (%g / %g), so every bitmap is stretched by that "
                 "ratio: round icons become ovals. Replace those bitmaps with redrawn art if needed." % (bx, by))
    layout_whole = float(ctx.s.factor_x).is_integer() and float(ctx.s.factor_y).is_integer()
    if ctx.s.bitmap_integer_scale and (bx, by) != (float(ctx.s.factor_x), float(ctx.s.factor_y)):
        ctx.note("warning", "bitmaps", "Bitmaps are scaled by x%g / y%g (whole part) while the layout is scaled by "
                 "x%g / y%g, so they come out smaller than the controls that show them. Check buttons, icons and "
                 "backgrounds for gaps or wrong alignment." % (bx, by, ctx.s.factor_x, ctx.s.factor_y))
    elif not ctx.s.bitmap_integer_scale and not layout_whole:
        ctx.note("warning", "bitmaps", "The factor (x%g / y%g) is not a whole number, so bitmaps are resampled by a "
                 "fraction and flat art (icons, text, thin lines) comes out uneven or blurred. The option 'Scale "
                 "bitmaps by a whole factor' keeps them crisp at the whole part of the factor."
                 % (ctx.s.factor_x, ctx.s.factor_y))

    for fn in ctx.files(ctx.src_root, "Bitmaps", ".bminfo"):
        name = os.path.splitext(fn)[0]
        info_src = read_text(os.path.join(ctx.src_root, "Bitmaps", fn))
        img = re.search(r'Name="File" Value="([^"]+)"', info_src)
        if not img:
            continue
        img_name = img[1]
        src_img = os.path.join(ctx.src_root, "Bitmaps", img_name)
        dest_img = os.path.join(ctx.dest_root, "Bitmaps", img_name)
        dest_info = os.path.join(ctx.dest_root, "Bitmaps", fn)
        if name in excluded:
            shutil.copyfile(src_img, dest_img)
            shutil.copyfile(os.path.join(ctx.src_root, "Bitmaps", fn), dest_info)
            ctx.stats["bitmaps excluded"] += 1
            continue
        if not os.path.isfile(src_img):
            ctx.note("warning", "bitmaps", "%s references missing image file %s." % (fn, img_name))
            continue
        im = Image.open(src_img)
        im.load()
        method = _pick(ctx, name, im, 'Name="Transparent" Value="True"' in info_src)
        w, h = im.size
        size = (max(1, scale_int(w, bx)), max(1, scale_int(h, by)))
        out = im.resize(size, Image.NEAREST if method == "nearest" else Image.BICUBIC)
        if im.mode == "P":
            out.putpalette(im.getpalette())
            if "transparency" in im.info:
                out.info["transparency"] = im.info["transparency"]
        fmt = {".bmp": "BMP", ".png": "PNG", ".gif": "GIF"}.get(os.path.splitext(img_name)[1].lower())
        if fmt is None:
            ctx.note("warning", "bitmaps", "%s: unsupported image type, copied unscaled." % img_name)
            shutil.copyfile(src_img, dest_img)
            continue
        out.save(dest_img, fmt)
        write_text(dest_info, patch_by_ordinal(
            info_src, read_text(dest_info), fill_re,
            lambda s, d: s[1] + s[2] + s[3] + str(scale_int(int(s[4]), ctx.bitmap_factor_for(s[2]))) + s[5]))
        ctx.stats["bitmaps resized"] += 1
        if method == "bicubic":
            bicubic.append(name)
        if _bmp_bits(src_img) != _bmp_bits(dest_img):
            changed_depth.append("%s (%s -> %s bit)" % (img_name, _bmp_bits(src_img), _bmp_bits(dest_img)))
        if size[0] > 4 * ref_w or size[1] > 4 * ref_h:
            oversized.append("%s %dx%d" % (img_name, *size))

    if bicubic:
        ctx.note("action", "bitmaps", "%d bitmap(s) were smoothed with bicubic resampling (gradients/photos). "
                 "Check them visually for blur or colour shifts: %s" % (len(bicubic), ", ".join(bicubic)))
    if changed_depth:
        ctx.note("warning", "bitmaps", "Bit depth changed on save (check TargetFormat in the .bminfo): %s"
                 % ", ".join(changed_depth))
    if oversized:
        ctx.note("info", "bitmaps", "Very wide/tall images (over 4x the screen): %s" % ", ".join(oversized))
    ctx.log("bitmaps: %d resized, %d excluded" % (ctx.stats["bitmaps resized"], ctx.stats["bitmaps excluded"]))
