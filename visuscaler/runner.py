"""Runs the selected steps, either for real or as a dry run on a temporary copy."""
import os
import shutil
import tempfile

from .context import Context, StepError, check_visualization_name, resolve_target
from .steps import discover


def run(settings, step_ids=None, dry_run=False, log=print):
    """Return the Context (notes, stats, report_markdown) after running the chosen steps in order."""
    ids = step_ids or settings.steps
    chosen = [m for m in discover() if not ids or m.ID in ids]
    if not chosen:
        raise StepError("no steps selected")
    if not os.path.isdir(os.path.join(settings.package_dir, settings.source)):
        raise StepError("source visualization not found: %s" % os.path.join(settings.package_dir, settings.source))
    if not os.path.isdir(os.path.join(settings.package_dir, settings.dest)):
        check_visualization_name(settings.dest)   # only a new destination is created, so only then it matters
    settings = resolve_target(settings)
    ctx = Context(settings, log, dry_run)
    if settings.factor_x <= 0 or settings.factor_y <= 0:
        raise StepError("scale factors must be positive")
    if os.path.abspath(ctx.src_root) == os.path.abspath(ctx.dest_root):
        raise StepError("source and destination must differ")

    tmp = None
    try:
        if dry_run:
            tmp = tempfile.mkdtemp(prefix="visuscaler_")
            ctx.dest_root = os.path.join(tmp, settings.dest)
            real_dest = os.path.join(settings.package_dir, settings.dest)
            if os.path.isdir(real_dest):
                shutil.copytree(real_dest, ctx.dest_root)
            log("DRY RUN: working on a temporary copy, nothing in the project is changed")
        for mod in chosen:
            log("== %s" % mod.TITLE)
            mod.run(ctx)
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
    return ctx
