"""Tkinter front end. All work happens in the runner and steps; this only gathers settings and shows results."""
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import runner
from .context import StepError, check_visualization_name, folder_resolution
from .settings import DEFAULT_FONT_PATTERN, DEFAULT_PIXEL_PROPERTIES, RESOLUTION_PRESETS, Settings
from .steps import discover
from .textio import scale_int


class App(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=8)
        self.master.title("VisuScaler - Automation Studio visualization scaler")
        self.pack(fill="both", expand=True)
        self.q = queue.Queue()
        self.steps = discover()
        self.step_vars = {m.ID: tk.BooleanVar(value=True) for m in self.steps}
        self._build()
        self.after(100, self._drain)

    # layout
    def _build(self):
        top = ttk.Frame(self)
        top.pack(fill="x")
        self.package = tk.StringVar()
        self.source = tk.StringVar()
        self.dest = tk.StringVar()
        self.factor_x = tk.StringVar(value="2")
        self.factor_y = tk.StringVar(value="2")
        self.resolution = tk.StringVar()
        ttk.Label(top, text="Package folder").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.package, width=60).grid(row=0, column=1, sticky="we", padx=4)
        ttk.Button(top, text="Browse...", command=self._browse_package).grid(row=0, column=2)
        ttk.Label(top, text="Source").grid(row=1, column=0, sticky="w")
        self.source_box = ttk.Combobox(top, textvariable=self.source, state="readonly")
        self.source_box.grid(row=1, column=1, sticky="we", padx=4)
        self.source_box.bind("<<ComboboxSelected>>", lambda e: self._source_changed())
        ttk.Label(top, text="Destination").grid(row=2, column=0, sticky="w")
        self.dest_box = ttk.Combobox(top, textvariable=self.dest)
        self.dest_box.grid(row=2, column=1, sticky="we", padx=4)
        self.target_w = tk.StringVar()
        self.target_h = tk.StringVar()
        self.preset = tk.StringVar()
        self._syncing = False
        self._by_target = False   # which pair of fields the user edited last
        ttk.Label(top, text="Target size").grid(row=3, column=0, sticky="w")
        t = ttk.Frame(top)
        t.grid(row=3, column=1, sticky="w", padx=4)
        self.preset_box = ttk.Combobox(t, textvariable=self.preset, state="readonly", width=22,
                                       values=["%s  %dx%d" % p for p in RESOLUTION_PRESETS])
        self.preset_box.pack(side="left")
        self.preset_box.bind("<<ComboboxSelected>>", lambda e: self._preset_chosen())
        ttk.Entry(t, textvariable=self.target_w, width=6).pack(side="left", padx=(8, 2))
        ttk.Label(t, text="x").pack(side="left")
        ttk.Entry(t, textvariable=self.target_h, width=6).pack(side="left", padx=2)
        ttk.Label(t, text="px  (or set a factor below)").pack(side="left", padx=6)
        ttk.Label(top, text="Scale factor").grid(row=4, column=0, sticky="w")
        f = ttk.Frame(top)
        f.grid(row=4, column=1, sticky="w", padx=4)
        ttk.Label(f, text="X").pack(side="left")
        ttk.Entry(f, textvariable=self.factor_x, width=8).pack(side="left", padx=(2, 8))
        ttk.Label(f, text="Y").pack(side="left")
        ttk.Entry(f, textvariable=self.factor_y, width=8).pack(side="left", padx=2)
        ttk.Label(f, textvariable=self.resolution).pack(side="left", padx=10)
        self.warning = ttk.Label(top, foreground="#b00020", wraplength=700)
        self.warning.grid(row=5, column=1, sticky="w", padx=4)
        for v in (self.factor_x, self.factor_y):
            v.trace_add("write", lambda *_: self._edited(False))
        for v in (self.target_w, self.target_h):
            v.trace_add("write", lambda *_: self._edited(True))
        top.columnconfigure(1, weight=1)

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, pady=8)
        self._steps_tab()
        self._exclusions_tab()
        self._options_tab()
        self.log_text = self._text_tab("Log")
        self.check_text = self._text_tab("Checklist")

        bar = ttk.Frame(self)
        bar.pack(fill="x")
        ttk.Button(bar, text="Load settings...", command=self._load).pack(side="left")
        ttk.Button(bar, text="Save settings...", command=self._save).pack(side="left", padx=4)
        self.apply_btn = ttk.Button(bar, text="Apply", command=lambda: self._start(False))
        self.apply_btn.pack(side="right")
        self.dry_btn = ttk.Button(bar, text="Dry run", command=lambda: self._start(True))
        self.dry_btn.pack(side="right", padx=4)

    def _steps_tab(self):
        tab = ttk.Frame(self.nb, padding=8)
        self.nb.add(tab, text="Steps")
        ttk.Label(tab, text="Tick the scripts to run. Each can be run on its own, in any combination.").pack(anchor="w")
        for m in self.steps:
            ttk.Checkbutton(tab, text=m.TITLE, variable=self.step_vars[m.ID]).pack(anchor="w", pady=(8, 0))
            ttk.Label(tab, text=m.DESCRIPTION, wraplength=700, foreground="#555").pack(anchor="w", padx=24)

    def _exclusions_tab(self):
        tab = ttk.Frame(self.nb, padding=8)
        self.nb.add(tab, text="Exclusions")
        ttk.Label(tab, text="Selected items keep their original size (with the bitmaps their touchpads use).") \
            .grid(row=0, column=0, columnspan=3, sticky="w")
        self.lists = {}
        for col, (key, title) in enumerate((("TouchPads", "Touchpads"), ("Pages", "Pages"), ("Layers", "Layers"))):
            ttk.Label(tab, text=title).grid(row=1, column=col, sticky="w")
            lb = tk.Listbox(tab, selectmode="multiple", exportselection=False, height=14)
            lb.grid(row=2, column=col, sticky="nsew", padx=3)
            self.lists[key] = lb
            tab.columnconfigure(col, weight=1)
        tab.rowconfigure(2, weight=1)

    def _options_tab(self):
        tab = ttk.Frame(self.nb, padding=8)
        self.nb.add(tab, text="Options")
        self.create_fonts = tk.BooleanVar()
        self.clean_dest = tk.BooleanVar()
        self.resample = tk.StringVar(value="auto")
        self.pattern = tk.StringVar(value=DEFAULT_FONT_PATTERN)
        ttk.Checkbutton(tab, text="Create a font when no exact scaled size exists (otherwise nearest + report)",
                        variable=self.create_fonts).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(tab, text="Font name pattern").grid(row=1, column=0, sticky="w")
        ttk.Entry(tab, textvariable=self.pattern, width=70).grid(row=1, column=1, sticky="we")
        ttk.Label(tab, text="Bitmap resampling").grid(row=2, column=0, sticky="w")
        ttk.Combobox(tab, textvariable=self.resample, values=("auto", "nearest", "bicubic"),
                     state="readonly", width=10).grid(row=2, column=1, sticky="w")
        self.bitmap_whole = tk.BooleanVar()
        self.bitmap_whole.trace_add("write", lambda *_: self._update_resolution())
        ttk.Checkbutton(tab, text="Scale bitmaps by a whole factor (e.g. layout x2.25 -> bitmaps x2)",
                        variable=self.bitmap_whole).grid(row=3, column=0, columnspan=2, sticky="w")
        ttk.Label(tab, foreground="#b00020", wraplength=700,
                  text="Bitmaps resampled by a fraction (e.g. x2.25) look uneven or blurred. With this option they "
                       "stay crisp, but come out smaller than the controls that show them (x2 vs x2.25), so check "
                       "buttons, icons and backgrounds for gaps or misalignment."
                  ).grid(row=4, column=0, columnspan=2, sticky="w", padx=20)
        ttk.Checkbutton(tab, text="Delete destination files that are not in the source",
                        variable=self.clean_dest).grid(row=5, column=0, columnspan=2, sticky="w")
        self.register = tk.BooleanVar(value=True)
        ttk.Checkbutton(tab, text="Add a new destination to Package.pkg and the data sources (not on a dry run)",
                        variable=self.register).grid(row=6, column=0, columnspan=2, sticky="w")
        ttk.Label(tab, text="Pixel properties to scale (one per line)").grid(row=7, column=0, sticky="nw")
        self.props = tk.Text(tab, height=14, width=40)
        self.props.grid(row=7, column=1, sticky="nsew")
        self.props.insert("1.0", "\n".join(DEFAULT_PIXEL_PROPERTIES))
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(7, weight=1)

    def _text_tab(self, title):
        tab = ttk.Frame(self.nb)
        self.nb.add(tab, text=title)
        t = tk.Text(tab, wrap="word", height=18)
        sb = ttk.Scrollbar(tab, command=t.yview)
        t.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        t.pack(fill="both", expand=True)
        return t

    # folder handling
    def _browse_package(self):
        d = filedialog.askdirectory(title="Folder containing the visualization folders (e.g. Logical/HMIControl)")
        if d:
            self.package.set(d)
            self._scan()

    def _visualizations(self):
        pkg = self.package.get()
        if not os.path.isdir(pkg):
            return []
        return sorted(d for d in os.listdir(pkg) if os.path.isfile(os.path.join(pkg, d, "VCObject.vc")))

    def _scan(self):
        vis = self._visualizations()
        self.source_box["values"] = vis
        self.dest_box["values"] = vis
        if vis and self.source.get() not in vis:
            self.source.set(vis[0])
        if len(vis) > 1 and not self.dest.get():
            self.dest.set(next(v for v in vis if v != self.source.get()))
        self._source_changed()

    def _source_changed(self):
        root = os.path.join(self.package.get(), self.source.get())
        for key, ext in (("TouchPads", ".tpr"), ("Pages", ".page"), ("Layers", ".layer")):
            lb = self.lists[key]
            lb.delete(0, "end")
            d = os.path.join(root, key)
            for fn in sorted(os.listdir(d)) if os.path.isdir(d) else []:
                if fn.endswith(ext):
                    lb.insert("end", os.path.splitext(fn)[0])
        self._update_resolution()

    def _source_res(self):
        return folder_resolution(os.path.join(self.package.get(), self.source.get()))

    def _set(self, var, value):
        self._syncing = True
        try:
            var.set(value)
        finally:
            self._syncing = False

    def _edited(self, by_target):
        if self._syncing:
            return
        self._by_target = by_target
        self._update_resolution()

    def _preset_chosen(self):
        _, w, h = RESOLUTION_PRESETS[self.preset_box.current()]
        self._by_target = True
        self._set(self.target_w, str(w))
        self._set(self.target_h, str(h))
        self._update_resolution()

    def _update_resolution(self):
        """Keep factors and target size consistent; whichever pair was edited last wins."""
        try:
            w, h = self._source_res()
            if self._by_target:
                tw, th = int(self.target_w.get()), int(self.target_h.get())
                if tw <= 0 or th <= 0:
                    raise ValueError("target must be positive")
                fx, fy = tw / w, th / h
                self._set(self.factor_x, "%.6g" % fx)
                self._set(self.factor_y, "%.6g" % fy)
            else:
                fx, fy = float(self.factor_x.get()), float(self.factor_y.get())
                tw, th = scale_int(w, fx), scale_int(h, fy)
                self._set(self.target_w, str(tw))
                self._set(self.target_h, str(th))
            match = [p for p in RESOLUTION_PRESETS if p[1:] == (tw, th)]
            self._set(self.preset, "%s  %dx%d" % match[0] if match else "Custom")
            self.resolution.set("%dx%d  ->  %dx%d" % (w, h, tw, th))
            warn = []
            if not self._by_target and (abs(w * fx - round(w * fx)) > 1e-9 or abs(h * fy - round(h * fy)) > 1e-9):
                warn.append("Result is not a whole number of pixels (%g x %g): it will be rounded to %dx%d."
                            % (round(w * fx, 3), round(h * fy, 3), tw, th))
            if abs(fx - fy) > 1e-6:
                warn.append("X and Y differ: bitmaps will be stretched, round icons become ovals.")
            if abs(fx - round(fx)) > 1e-6 or abs(fy - round(fy)) > 1e-6:
                warn.append("Bitmaps scaled by x%g / y%g look uneven. Options: 'Scale bitmaps by a whole factor' "
                            "keeps them crisp (x%d / y%d)." % (fx, fy, max(1, fx // 1), max(1, fy // 1))
                            if not self.bitmap_whole.get() else
                            "Bitmaps are scaled by the whole part (x%d / y%d), smaller than the layout."
                            % (max(1, fx // 1), max(1, fy // 1)))
            self.warning.configure(text="  ".join(warn))
        except Exception:
            self.resolution.set("")
            self.warning.configure(text="")

    # settings and widgets
    def _selected(self, key):
        lb = self.lists[key]
        return [lb.get(i) for i in lb.curselection()]

    def _gather(self):
        tw = th = 0
        try:
            if self._by_target:
                tw, th = int(self.target_w.get()), int(self.target_h.get())
                fx, fy = float(self.factor_x.get()), float(self.factor_y.get())
            else:
                fx, fy = float(self.factor_x.get()), float(self.factor_y.get())
        except ValueError:
            raise ValueError("Target size and scale factors must be numbers")
        if fx <= 0 or fy <= 0 or tw < 0 or th < 0:
            raise ValueError("Target size and scale factors must be greater than 0")
        return Settings(
            package_dir=self.package.get(), source=self.source.get(), dest=self.dest.get().strip(),
            factor_x=fx, factor_y=fy, target_width=tw, target_height=th, register_dest=self.register.get(),
            steps=[i for i, v in self.step_vars.items() if v.get()],
            exclude_touchpads=self._selected("TouchPads"), exclude_pages=self._selected("Pages"),
            exclude_layers=self._selected("Layers"), clean_dest=self.clean_dest.get(),
            font_create_missing=self.create_fonts.get(), font_pattern=self.pattern.get(),
            bitmap_resample=self.resample.get(), bitmap_integer_scale=self.bitmap_whole.get(),
            pixel_properties=[l.strip() for l in self.props.get("1.0", "end").splitlines() if l.strip()])

    def _apply(self, s):
        self.package.set(s.package_dir)
        self._scan()
        self.source.set(s.source)
        self.dest.set(s.dest)
        self._by_target = s.target_width > 0 and s.target_height > 0
        self._set(self.factor_x, "%g" % s.factor_x)
        self._set(self.factor_y, "%g" % s.factor_y)
        self._set(self.target_w, str(s.target_width) if self._by_target else "")
        self._set(self.target_h, str(s.target_height) if self._by_target else "")
        self.register.set(s.register_dest)
        self._source_changed()
        for var in self.step_vars.values():
            var.set(not s.steps)
        for i in s.steps:
            if i in self.step_vars:
                self.step_vars[i].set(True)
        for key, names in (("TouchPads", s.exclude_touchpads), ("Pages", s.exclude_pages),
                           ("Layers", s.exclude_layers)):
            lb = self.lists[key]
            for i, n in enumerate(lb.get(0, "end")):
                if n in names:
                    lb.selection_set(i)
        self.clean_dest.set(s.clean_dest)
        self.create_fonts.set(s.font_create_missing)
        self.pattern.set(s.font_pattern)
        self.resample.set(s.bitmap_resample)
        self.bitmap_whole.set(s.bitmap_integer_scale)
        self.props.delete("1.0", "end")
        self.props.insert("1.0", "\n".join(s.pixel_properties))

    def _save(self):
        try:
            s = self._gather()
        except ValueError as e:
            return messagebox.showerror("Settings", str(e))
        p = filedialog.asksaveasfilename(defaultextension=".json", initialfile="visuscaler.json")
        if p:
            s.save(p)

    def _load(self):
        p = filedialog.askopenfilename(filetypes=[("Settings", "*.json")])
        if p:
            self._apply(Settings.load(p))

    # running
    def _start(self, dry_run):
        try:
            s = self._gather()
        except ValueError as e:
            return messagebox.showerror("Settings", str(e))
        if not (os.path.isdir(s.package_dir) and s.source and s.dest):
            return messagebox.showerror("Settings", "Choose the package folder, source and destination.")
        if not s.steps:
            return messagebox.showerror("Settings", "Tick at least one step.")
        if not os.path.isdir(os.path.join(s.package_dir, s.dest)):
            try:
                check_visualization_name(s.dest)
            except StepError as e:
                return messagebox.showerror("Settings", str(e))
        if not dry_run and not messagebox.askyesno(
                "Apply", "This writes into '%s' (the source '%s' is never modified).\n\nContinue?"
                % (s.dest, s.source)):
            return
        self.log_text.delete("1.0", "end")
        self.check_text.delete("1.0", "end")
        self.nb.select(self.log_text.master)
        for b in (self.apply_btn, self.dry_btn):
            b.state(["disabled"])
        threading.Thread(target=self._work, args=(s, dry_run), daemon=True).start()

    def _work(self, s, dry_run):
        try:
            ctx = runner.run(s, s.steps, dry_run, log=lambda m: self.q.put(("log", m)))
            self.q.put(("done", ctx))
        except Exception as e:   # shown in the log and the run is aborted
            self.q.put(("error", "%s: %s" % (type(e).__name__, e)))

    def _drain(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self.log_text.insert("end", payload + "\n")
                    self.log_text.see("end")
                elif kind == "error":
                    self.log_text.insert("end", "\nFAILED - " + payload + "\n")
                    self._finish()
                else:
                    self.check_text.insert("1.0", payload.report_markdown or "(checklist step was not selected)")
                    if payload.report_markdown:
                        self.nb.select(self.check_text.master)
                    self._finish()
        except queue.Empty:
            pass
        self.after(100, self._drain)

    def _finish(self):
        for b in (self.apply_btn, self.dry_btn):
            b.state(["!disabled"])


def launch():
    root = tk.Tk()
    root.geometry("860x640")
    App(root)
    root.mainloop()
