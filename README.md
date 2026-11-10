# VisuScaler

VisuScaler takes an existing B&R Automation Studio VC4 visualization and builds a rescaled copy of it
for a different screen resolution. For example, it can turn a 320x240 `HMI` into a 640x480 `Visu`.

It scales positions, sizes, padding, line widths, fonts and bitmaps. Your source visualization is never modified

> Tested with: B&R Automation Studio 4.12** (Visual Components VC4), Python 3.11.9, Pillow 13.0.0,
> on Windows 11. Other versions may work but have not been tested. Projects from other Automation Studio
> versions may use different file formats, so always check the result (and the generated checklist) before relying on it.
> This tool is provided as is, without warranty. Back up your project first.

---

## Before you start

- **Windows** with Python 3.9 or newer. Check with `python --version`.
- An Automation Studio project that contains the visualization you want to scale.
- **Commit or back up your project first.** VisuScaler only writes to the destination (and, for a new destination,
  `Package.pkg` and the data source files), but a backup is always nice to have.
- Close the project in Automation Studio while you run VisuScaler, so it doesn't overwrite or lock the files.

## 1. Install

Open a terminal in this folder and run:

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

You only do this once.

## 2. Start the GUI

```
.venv\Scripts\python -m visuscaler
```

## 3. Scale a visualization

1. **Package folder**: click *Browse...* and pick the folder that holds your visualization folders. In a typical
   project this is `Logical\HMIControl` (or whatever your visualization package is called). Each folder in there is one
   visualization.
2. **Source**: the visualization to scale from, for example `HMI`.
3. **Destination**: the name of the result, for example `Visu`. It doesn't need to exist. VisuScaler creates it.
4. **Target size**: choose a preset (QVGA ... Full HD) or type a width and height. VisuScaler works out the scale
   factors from the source's resolution. Alternatively, enter an **X** and **Y** scale factor directly.
   A red warning appears if the result looks wrong, such as a different aspect ratio or a non-whole result.
5. Click **Dry run**. This runs everything on a temporary copy and shows you the checklist without touching your
   project. Read it: it lists what was scaled, rounded, or needs a manual look.
6. Happy with it? Click **Apply**.
7. Open the project in Automation Studio and work through the checklist (see below).

Use **Save settings...** to keep your choices in a JSON file, and **Load settings...** to bring them back later.

### The other tabs (all optional)

| Tab | Use it to |
|---|---|
| **Steps** | Run only some steps. Everything is ticked by default, which is what you want the first time. |
| **Exclusions** | Pick touchpads, pages or layers that should **keep their original size**. |
| **Options** | Create missing fonts, change the font name pattern or bitmap resampling, delete stale files in the destination, turn off registration in `Package.pkg`, and edit the list of scaled properties. |

## 4. After applying: what to do in Automation Studio

VisuScaler deliberately never edits `Cpu.sw` or `Hardware.hw`. A configuration maps exactly one visualization to its
display, so you choose where the new one goes:

1. Open the project and check that the new visualization appears in the Logical View.
2. In the configuration for the target panel, point it at the new visualization by setting `VncVcObjectName` /
   `VcObjectName` to the destination name. The checklist tells you exactly where.
3. Open the new visualization in the editor and check pages visually, especially text that may now overflow.
4. Build the project.

The checklist is saved as Markdown in `<project>\VisuScaler_Reports\`.

## What gets done (the steps)

| Step | What it does |
|---|---|
| copy | Copies the source files into the destination. Creates the destination if it's missing. |
| geometry | Scales Left/Top/Width/Height, padding, spacing, line and border widths, border splits, grids. |
| fonts | Points font references at the existing font of the scaled size. Can create missing ones (Options tab). |
| bitmaps | Resamples images and scales their fill areas. |
| project | Writes the new resolution, registers the destination in `Package.pkg` and connects it to the same data sources as the source. |
| verify | Checks every scaled value equals source x factor and flags controls that now overflow. |
| checklist | Writes the checklist described above. |

Every step reads from the **source**, never from its own earlier output, so you can safely re-run any step without
scaling twice.

## Good to know

- **Rounding:** pixel values must be whole numbers, so results are rounded and reported.
- **Direction-less values** (font sizes, line widths) use the smaller of the X and Y factors so they never grow too
  large.
- **Bitmaps:** flat or palette art is resampled with nearest-neighbour to stay crisp. Gradients use bicubic.
- **Non-whole factors and bitmaps:** at a factor like 2.25, bitmaps are resampled by a fraction and flat art (icons,
  text, thin lines) comes out uneven. The Options tab has **Scale bitmaps by a whole factor** (`bitmap_integer_scale` in
  the settings file), which scales bitmaps by the whole part instead (2.25 becomes 2) on each axis. They stay crisp but
  come out smaller than the controls that show them, so check buttons, icons and backgrounds. Factors below 1 are not
  affected.
- **Different aspect ratio** (e.g. 4:3 to 16:9): X and Y factors differ, so expect to tidy up the layout by hand.
- **Re-running:** running Apply again with the same destination overwrites it with fresh output. Any manual edits you
  made in the destination are lost, so finish scaling before you start hand-tuning.
- **Dry run** never changes your project, so use it as often as you like.

## Command line

For scripted or repeatable runs, save your settings from the GUI, then:

```
.venv\Scripts\python -m visuscaler steps                       # list the steps
.venv\Scripts\python -m visuscaler run settings.json           # run everything
.venv\Scripts\python -m visuscaler run settings.json --dry-run
.venv\Scripts\python -m visuscaler run settings.json --steps copy,geometry
```

### Settings file reference

| Key | Meaning | Default |
|---|---|---|
| `package_dir` | Folder holding the visualization folders | |
| `source` / `dest` | Source and destination visualization names | `HMI` / `Visu` |
| `target_width` / `target_height` | Target size. If both > 0, the factors are derived from it | `0` |
| `factor_x` / `factor_y` | Scale factors, used when no target size is set | `2.0` |
| `steps` | List of step ids to run. Empty means all | `[]` |
| `exclude_touchpads` / `exclude_pages` / `exclude_layers` | Names that keep their original size | `[]` |
| `register_dest` | Register a new destination in `Package.pkg` and the data sources | `true` |
| `clean_dest` | Delete destination files that aren't in the source | `false` |
| `font_create_missing` | Create a font when no exact scaled size exists | `false` |
| `font_pattern` | Regex that splits a font name into family, size, style | built in |
| `bitmap_resample` | `auto`, `nearest` or `bicubic` | `auto` |
| `bitmap_overrides` | Per-bitmap override, e.g. `{"Logo": "bicubic"}` | `{}` |
| `pixel_properties` | Properties that get scaled | built in |
| `report_dir` | Where reports go | `<project>/VisuScaler_Reports` |

## Troubleshooting

- **`python` is not recognized**: install Python from python.org and tick "Add python.exe to PATH".
- **`No module named PIL`**: the install step was skipped. Run the `pip install -r requirements.txt` command again.
- **A font looks wrong or is the nearest size**: enable *Create a font when no exact scaled size exists* on the
  Options tab, or create the font in Automation Studio and re-run.
- **Something is off in the result**: check the checklist first. It explains most issues.

## For developers

Each step is one module in `visuscaler/steps`. To add one, drop in a module that defines
`ID, TITLE, DESCRIPTION, ORDER, run(ctx)`.

Run the tests:

```
.venv\Scripts\python -m unittest discover -s tests -t .
```

Build a standalone GUI exe (output: `dist\VisuScaler.exe`):

```
.venv\Scripts\pip install pyinstaller
.venv\Scripts\python -m PyInstaller --noconfirm --clean --onefile --windowed --name VisuScaler --collect-submodules visuscaler.steps run_visuscaler.py
```
