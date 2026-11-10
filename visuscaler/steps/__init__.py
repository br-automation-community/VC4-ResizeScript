"""Each module in this package is one independently selectable script.

A step module defines:
    ID, TITLE, DESCRIPTION, ORDER   metadata (steps run in ORDER)
    run(ctx)                        does the work; records follow-ups with ctx.note(...)
Dropping a new module in this folder makes it appear in the GUI automatically.
"""
import importlib
import pkgutil


def discover():
    steps = []
    for info in pkgutil.iter_modules(__path__):
        mod = importlib.import_module("%s.%s" % (__name__, info.name))
        if all(hasattr(mod, a) for a in ("ID", "TITLE", "DESCRIPTION", "ORDER", "run")):
            steps.append(mod)
    return sorted(steps, key=lambda m: m.ORDER)
