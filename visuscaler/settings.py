"""Run settings, saved as JSON so a run can be repeated."""
import json
from dataclasses import dataclass, field, asdict, fields

DEFAULT_PIXEL_PROPERTIES = [
    "Left", "Top", "Width", "Height", "StartX", "StartY", "EndX", "EndY",   # the last four are for the Line control
    "PaddingVertical", "PaddingHorizontal", "SpacingVertical", "SpacingHorizontal", "Spacing",
    "LineWidth", "BorderWidth", "InnerWidth", "OuterWidth",
    "SplitTop", "SplitLeft", "SplitRight", "SplitBottom",
    "ColumnWidth", "RowHeight", "UnitTextWidth",
    "MinorPitchLinesLength", "MajorPitchLinesLength", "PitchLinesLength",
    "PitchLineSpacing", "PitchLinesSpacing", "MinorPitchLinesWidth", "MajorPitchLinesWidth",
    "LabelSpacing", "ThumbSpacing", "RangeWidth", "RangeSpacing", "MarkerSpacing",
    "ScaleRadius", "NeedleWidth", "NeedleLength", "NeedleBitmapCenterOffset",
    "CenterPointVerticalOffset", "CenterPointHorizontalOffset", "ButtonsWidth",
]
# Which axis a pixel property follows. Anything not listed (line and border widths, radii, pitch
# lengths and so on) has no direction and uses the smaller of the two factors so it never overgrows.
X_PROPERTIES = {"Left", "Width", "StartX", "EndX", "PaddingHorizontal", "SpacingHorizontal", "SplitLeft", "SplitRight",
                "ColumnWidth", "UnitTextWidth", "CenterPointHorizontalOffset", "ButtonsWidth", "FillAreaLeft"}
Y_PROPERTIES = {"Top", "Height", "StartY", "EndY", "PaddingVertical", "SpacingVertical", "SplitTop", "SplitBottom",
                "RowHeight", "CenterPointVerticalOffset", "FillAreaTop"}
# bitmap .bminfo properties, scaled by the bitmaps step together with the image
BITMAP_PIXEL_PROPERTIES = ["FillAreaLeft", "FillAreaTop"]

# Common panel resolutions offered as targets, as name, width, height
RESOLUTION_PRESETS = [
    ("QVGA", 320, 240), ("WQVGA", 480, 272), ("VGA", 640, 480), ("WVGA", 800, 480),
    ("SVGA", 800, 600), ("WSVGA", 1024, 600), ("XGA", 1024, 768), ("WXGA", 1280, 800),
    ("HD", 1366, 768), ("SXGA", 1280, 1024), ("Full HD", 1920, 1080),
]

DEFAULT_FONT_PATTERN = r"^(?P<family>[A-Za-z]+?)(?P<size>\d+)px(?P<style>.*)$"


@dataclass
class Settings:
    package_dir: str = ""          # folder holding the visualization folders, for example Logical/HMIControl
    source: str = "HMI"
    dest: str = "Visu"
    factor_x: float = 2.0
    factor_y: float = 2.0
    target_width: int = 0          # when above 0 (with target_height) this is the size of the new visualization,
    target_height: int = 0         # the factors are then derived from the source resolution
    register_dest: bool = True     # add a new destination to Package.pkg and the data sources like the source
    steps: list = field(default_factory=list)   # empty means every step
    exclude_touchpads: list = field(default_factory=list)
    exclude_pages: list = field(default_factory=list)
    exclude_layers: list = field(default_factory=list)
    clean_dest: bool = False       # delete files in dest that are not in source
    font_create_missing: bool = False
    font_pattern: str = DEFAULT_FONT_PATTERN
    bitmap_resample: str = "auto"  # auto, nearest or bicubic
    bitmap_integer_scale: bool = False   # scale bitmaps by the whole part of a factor above 1 (2.25 -> 2)
    bitmap_overrides: dict = field(default_factory=dict)   # bitmap name mapped to nearest or bicubic
    pixel_properties: list = field(default_factory=lambda: list(DEFAULT_PIXEL_PROPERTIES))
    report_dir: str = ""           # default is the VisuScaler_Reports folder in the project

    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def load(cls, path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        known = {x.name for x in fields(cls)}
        if "factor" in data:   # settings saved before X and Y were separate
            data.setdefault("factor_x", data["factor"])
            data.setdefault("factor_y", data["factor"])
        props = data.get("pixel_properties")
        if props is not None:   # saved before Line end points were scaled
            props.extend(p for p in ("StartX", "StartY", "EndX", "EndY") if p not in props)
        return cls(**{k: v for k, v in data.items() if k in known})
