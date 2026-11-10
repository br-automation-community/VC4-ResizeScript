"""Text helpers that keep file encoding and line endings byte-for-byte."""
import math
import re


def read_text(path):
    with open(path, "r", encoding="utf-8", errors="surrogateescape", newline="") as f:
        return f.read()


def write_text(path, text):
    with open(path, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
        f.write(text)


def scale_int(value, factor):
    """Round half away from zero."""
    x = value * factor
    return int(math.floor(x + 0.5)) if x >= 0 else -int(math.floor(-x + 0.5))


def patch_by_ordinal(src_text, dest_text, regex, fn):
    """Rewrite each regex match in dest_text from the match at the same position in src_text.

    Because the replacement is always computed from the source, a step can be
    re-run any number of times without scaling twice, and steps that own
    different properties do not interfere with each other.
    """
    smatches = list(regex.finditer(src_text))
    dmatches = list(regex.finditer(dest_text))
    if len(smatches) != len(dmatches):
        raise ValueError("source and destination differ in structure (%d vs %d matches); "
                         "run the copy step first" % (len(smatches), len(dmatches)))
    out, pos = [], 0
    for s, d in zip(smatches, dmatches):
        out.append(dest_text[pos:d.start()])
        out.append(fn(s, d))
        pos = d.end()
    out.append(dest_text[pos:])
    return "".join(out)


def newline_of(text):
    return "\r\n" if "\r\n" in text else "\n"


def register_source(vcp_text, rel_path):
    """Add a Source File entry for rel_path to a Package.vcp text if missing."""
    entry = '<Source File="%s"/>' % rel_path
    if entry in vcp_text:
        return vcp_text
    nl = newline_of(vcp_text)
    return vcp_text.replace("</SourceFiles>", "  " + entry + nl + "  </SourceFiles>", 1)
