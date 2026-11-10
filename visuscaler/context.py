"""Shared state handed to every step."""
import math
import os
import re
from collections import Counter
from dataclasses import dataclass, replace

from .settings import X_PROPERTIES, Y_PROPERTIES
from .textio import read_text

KEEP_IN_DEST = ("VCObject.vc", "Vc.dob")   # identity of the destination visualization
NOTE_LEVELS = ("action", "warning", "info")


class StepError(Exception):
    pass


@dataclass
class Note:
    level: str      # action means the user must do or check it, warning means a likely visual issue, info is for information only
    step: str
    text: str


def folder_resolution(root):
    """Width and height from a visualization folder's VCObject.vc."""
    path = os.path.join(root, "VCObject.vc")
    if not os.path.isfile(path):
        raise StepError("no VCObject.vc in %s" % root)
    text = read_text(path)
    w = re.search(r'Name="Width" Value="(\d+)"', text)
    h = re.search(r'Name="Height" Value="(\d+)"', text)
    if not (w and h):
        raise StepError("cannot read resolution from %s" % path)
    return int(w[1]), int(h[1])


def find_project_root(start):
    """Folder containing the .apj, searching upward."""
    cur = os.path.abspath(start)
    while True:
        if any(f.endswith(".apj") for f in os.listdir(cur)):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def check_visualization_name(name):
    """Automation Studio: starts with a letter, at most 6 characters, no special characters."""
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,5}", name or ""):
        raise StepError("Destination name '%s' is not valid: Automation Studio visualization names must start "
                        "with a letter, contain only letters, digits or _, and be at most 6 characters long." % name)


def resolve_target(settings):
    """Settings with the factors derived from target_width/target_height, if those are set."""
    if settings.target_width <= 0 and settings.target_height <= 0:
        return settings
    if settings.target_width <= 0 or settings.target_height <= 0:
        raise StepError("set both target width and target height")
    w, h = folder_resolution(os.path.join(settings.package_dir, settings.source))
    return replace(settings, factor_x=settings.target_width / w, factor_y=settings.target_height / h)


class Context:
    def __init__(self, settings, log=print, dry_run=False):
        self.s = settings
        self.log_fn = log
        self.dry_run = dry_run
        self.src_root = os.path.join(settings.package_dir, settings.source)
        self.dest_root = os.path.join(settings.package_dir, settings.dest)
        self.notes = []
        self.stats = Counter()
        self.report_markdown = ""
        self.report_path = None
        self._excluded_bitmaps = None

    # reporting
    def log(self, msg):
        self.log_fn(msg)

    def note(self, level, step, text):
        assert level in NOTE_LEVELS, level
        self.notes.append(Note(level, step, text))

    # geometry
    @property
    def factor(self):
        """Direction-less factor (fonts, line widths and so on): the smaller axis, so nothing overgrows."""
        return min(float(self.s.factor_x), float(self.s.factor_y))

    def factor_for(self, prop):
        if prop in X_PROPERTIES:
            return float(self.s.factor_x)
        if prop in Y_PROPERTIES:
            return float(self.s.factor_y)
        return self.factor

    @property
    def bitmap_factors(self):
        """(x, y) applied to bitmap images: the layout factors, or their whole part when
        bitmap_integer_scale is on (factors below 1 are left alone)."""
        fx, fy = float(self.s.factor_x), float(self.s.factor_y)
        if self.s.bitmap_integer_scale:
            fx = math.floor(fx + 1e-9) if fx >= 1 else fx
            fy = math.floor(fy + 1e-9) if fy >= 1 else fy
        return fx, fy

    def bitmap_factor_for(self, prop):
        fx, fy = self.bitmap_factors
        if prop in X_PROPERTIES:
            return fx
        if prop in Y_PROPERTIES:
            return fy
        return min(fx, fy)

    @property
    def src_resolution(self):
        return folder_resolution(self.src_root)

    @property
    def dest_resolution(self):
        from .textio import scale_int
        w, h = self.src_resolution
        return scale_int(w, self.s.factor_x), scale_int(h, self.s.factor_y)

    # exclusions
    def is_excluded(self, subdir, name):
        key = {"Pages": self.s.exclude_pages, "Layers": self.s.exclude_layers,
               "TouchPads": self.s.exclude_touchpads}.get(subdir, [])
        return name in key

    def excluded_bitmap_names(self):
        """Bitmaps used (via bitmap groups) by excluded touchpads: they keep their size."""
        if self._excluded_bitmaps is not None:
            return self._excluded_bitmaps
        groups, bitmaps = set(), set()
        for pad in self.s.exclude_touchpads:
            p = os.path.join(self.src_root, "TouchPads", pad + ".tpr")
            if os.path.isfile(p):
                groups |= set(re.findall(r'BitmapGroup\[([^\]]+)\]', read_text(p)))
        for g in groups:
            p = os.path.join(self.src_root, "BitmapGroups", g + ".bmgrp")
            if os.path.isfile(p):
                bitmaps |= set(re.findall(r'Bitmap\[([^\]]+)\]', read_text(p)))
        # a bitmap also used by a non-excluded group would be scaled in one place, not the other
        shared = set()
        bg_dir = os.path.join(self.src_root, "BitmapGroups")
        if os.path.isdir(bg_dir):
            for fn in os.listdir(bg_dir):
                if fn.endswith(".bmgrp") and os.path.splitext(fn)[0] not in groups:
                    shared |= bitmaps & set(re.findall(r'Bitmap\[([^\]]+)\]', read_text(os.path.join(bg_dir, fn))))
        if shared:
            self.note("warning", "bitmaps",
                      "Bitmaps %s are used by an excluded touchpad AND by another bitmap group; "
                      "they stay at the original size, so the other group shows them small."
                      % ", ".join(sorted(shared)))
        self._excluded_bitmaps = bitmaps
        return bitmaps

    # file iteration
    def files(self, root, subdir, ext):
        d = os.path.join(root, subdir)
        if not os.path.isdir(d):
            return []
        return sorted(fn for fn in os.listdir(d) if fn.lower().endswith(ext))

    def require_dest(self):
        if not os.path.isdir(self.dest_root):
            raise StepError("destination %s does not exist: run the copy step first" % self.dest_root)
