#!/usr/bin/env python3

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GdkPixbuf, GLib, Gdk
import subprocess
import os
import tempfile
import threading
import json

CONFIG_DIR = os.path.expanduser("~/.config/printflow")
PRESETS_FILE = os.path.join(CONFIG_DIR, "presets.json")

MEDIA = [
    (0, "Plain paper"),
    (1, "Epson Inkjet Paper"),
    (2, "Archival Matte"),
    (3, "Epson Photo Glossy"),
    (4, "Epson Premium Glossy"),
    (5, "Epson Premium Semiglossy"),
    (6, "Epson Premium Luster"),
    (7, "Epson Proof Paper"),
    (8, "Transparency"),
    (9, "Hahnemuehle Smooth FineArt"),
    (10, "Hahnemuehle Canvas"),
    (11, "Ilford Omnijet"),
    (12, "Hahnemuehle PhotoRag Baryta"),
]

PAGESIZE = [
    (3,  "A4",             210, 297),
    (4,  "A3",             297, 420),
    (5,  "A3+",            329, 483),
    (6,  "A2",             420, 594),
    (17, "A4 Borderless",  210, 297),
    (18, "A3 Borderless",  297, 420),
    (19, "A3+ Borderless", 329, 483),
    (1,  "US Letter",      216, 279),
    (11, "8x10 inch",      203, 254),
    (12, "11x14 inch",     279, 356),
    (13, "16x20 inch",     406, 508),
]

ALIGNMENTS = [
    ("top-left",   "Top left"),
    ("top-center", "Top center"),
    ("top-right",  "Top right"),
    ("mid-left",   "Center left"),
    ("center",     "Center"),
    ("mid-right",  "Center right"),
    ("bot-left",   "Bottom left"),
    ("bot-center", "Bottom center"),
    ("bot-right",  "Bottom right"),
]

ICC_MAP = {
    0: None, 1: None,
    2: "Archival Matte",
    3: "Epson Photo Glossy",
    4: "Epson Ultra Premium Glossy",
    5: "Epson Premium Semiglossy",
    6: "SC-P800 Series Epson Premium Luster",
    7: None, 8: None,
    9: "Hahnemuehle Smooth FineArt",
    10: None, 11: None,
    12: "Hahnemuehle PhotoRag Baryta",
}

INK_TYPE = {
    0: "Photo Black", 1: "Photo Black", 2: "Matte Black",
    3: "Photo Black", 4: "Photo Black", 5: "Photo Black",
    6: "Photo Black", 7: "Photo Black", 8: "Photo Black",
    9: "Matte Black", 10: "Matte Black", 11: "Photo Black",
    12: "Matte Black",
}

ICC_SEARCH_DIRS = [
    os.path.expanduser("~/.local/share/icc"),
    os.path.expanduser("~/.local/share/color/icc"),
    "/usr/share/color/icc",
]

DEFAULTS = {
    "media": 6, "pagesize": 0, "orientation": 0,
    "quality": 0, "colormode": 0, "colorspace": 0,
    "intent": 0, "light": 0, "blackpoint": True,
    "alignment": "center", "scale": 0,
    "brightness": 0, "saturation": 0, "contrast": 0,
    "color_mode": "simple",
    "warmth": 0, "tint": 0, "hue": 0,
    "cyan": 0, "magenta": 0, "yellow": 0, "black": 0,
}


def ensure_config_dir():
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)


def find_icc(name):
    if not name:
        return None
    for d in ICC_SEARCH_DIRS:
        for f in [name + ".icc", name + ".icm"]:
            path = os.path.join(d, f)
            if os.path.exists(path):
                return path
    return None


def get_image_dpi(path):
    try:
        result = subprocess.run(
            ["identify", "-format", "%x", path],
            capture_output=True, text=True, timeout=10
        )
        val = result.stdout.strip().split()[0]
        dpi = float(val)
        if dpi > 50:
            return dpi
    except Exception:
        pass
    return 300.0


def get_turboprint_printers():
    try:
        result = subprocess.run(["lpstat", "-p"], capture_output=True, text=True)
        printers = []
        for line in result.stdout.splitlines():
            if line.startswith("printer ") and "TurboPrint" in line:
                printers.append(line.split()[1])
        return printers if printers else []
    except Exception:
        return []


def get_quality_list(printer=None, medium=None):
    try:
        cmd = ["tpconfig"]
        if printer:
            cmd += ["--printer=" + printer]
        if medium is not None:
            cmd += ["--medium=" + str(medium)]
        cmd += ["--listquality"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        best = {}
        for line in result.stdout.strip().splitlines():
            parts = line.split(":")
            if len(parts) >= 4:
                try:
                    num = int(parts[0].strip())
                    dpi_raw = parts[3].strip().replace("dpi", "").strip()
                    if "x" in dpi_raw:
                        w, h = dpi_raw.split("x")
                        label = w.strip() + " x " + h.strip() + " dpi"
                    else:
                        val = dpi_raw.strip()
                        label = val + " x " + val + " dpi"
                    if label not in best or num > best[label][0]:
                        best[label] = (num, label)
                except Exception:
                    pass
        qualities = sorted(best.values(), key=lambda x: x[0], reverse=True)
        return qualities if qualities else _default_quality()
    except Exception:
        return _default_quality()


def _default_quality():
    return [
        (4, "1440 x 1440 dpi"),
        (2, "720 x 720 dpi"),
        (1, "360 x 360 dpi"),
    ]


def load_presets():
    try:
        if os.path.exists(PRESETS_FILE):
            with open(PRESETS_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_presets(presets):
    ensure_config_dir()
    with open(PRESETS_FILE, "w") as f:
        json.dump(presets, f, indent=2)


def simple_to_advanced(warmth, tint, hue):
    cyan    = -int(warmth * 0.6)
    magenta = -int(tint * 0.8)
    yellow  = int(warmth * 0.4) - int(hue * 0.5)
    black   = 0
    return cyan, magenta, yellow, black


def make_info_button(tooltip_title, tooltip_text, parent):
    btn = Gtk.Button(label="\u2139")
    btn.set_relief(Gtk.ReliefStyle.NORMAL)
    btn.set_size_request(26, 26)
    def on_click(b):
        dialog = Gtk.MessageDialog(
            parent=parent, flags=0,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=tooltip_title
        )
        dialog.format_secondary_text(tooltip_text)
        dialog.run()
        dialog.destroy()
    btn.connect("clicked", on_click)
    return btn


class PaperPreview(Gtk.DrawingArea):
    def __init__(self):
        super().__init__()
        self.set_size_request(290, 260)
        self.paper_w_mm = 210
        self.paper_h_mm = 297
        self.landscape = False
        self.alignment = "center"
        self.pixbuf = None
        self.scale_mode = "fit"
        self.image_dpi = 300.0
        self.info_text = ""
        self.connect("draw", self.on_draw)

    def set_paper(self, w_mm, h_mm, landscape):
        self.paper_w_mm = w_mm
        self.paper_h_mm = h_mm
        self.landscape = landscape
        self._update_info()
        self.queue_draw()

    def set_image(self, pixbuf, dpi=300.0):
        self.pixbuf = pixbuf
        self.image_dpi = dpi
        self._update_info()
        self.queue_draw()

    def set_alignment(self, alignment):
        self.alignment = alignment
        self.queue_draw()

    def set_scale_mode(self, mode):
        self.scale_mode = mode
        self._update_info()
        self.queue_draw()

    def _update_info(self):
        if self.pixbuf and self.scale_mode == "actual":
            mm_per_inch = 25.4
            iw = self.pixbuf.get_width()
            ih = self.pixbuf.get_height()
            pw = self.paper_w_mm if not self.landscape else self.paper_h_mm
            ph = self.paper_h_mm if not self.landscape else self.paper_w_mm
            img_w_mm = iw / self.image_dpi * mm_per_inch
            img_h_mm = ih / self.image_dpi * mm_per_inch
            w_cm = img_w_mm / 10
            h_cm = img_h_mm / 10
            if img_w_mm > pw or img_h_mm > ph:
                self.info_text = "Actual: %.1fcm x %.1fcm (larger than paper)" % (w_cm, h_cm)
            else:
                self.info_text = "Actual: %.1fcm x %.1fcm" % (w_cm, h_cm)
        else:
            self.info_text = ""

    def on_draw(self, widget, cr):
        alloc = self.get_allocation()
        aw = alloc.width
        ah = alloc.height
        pw = self.paper_w_mm
        ph = self.paper_h_mm
        if self.landscape:
            pw, ph = ph, pw
        margin = 16
        info_h = 18 if self.info_text else 0
        scale = min((aw - margin * 2) / pw, (ah - margin * 2 - info_h) / ph)
        rw = pw * scale
        rh = ph * scale
        rx = (aw - rw) / 2
        ry = (ah - rh - info_h) / 2

        cr.set_source_rgba(0, 0, 0, 0.15)
        cr.rectangle(rx + 3, ry + 3, rw, rh)
        cr.fill()
        cr.set_source_rgb(1, 1, 1)
        cr.rectangle(rx, ry, rw, rh)
        cr.fill()
        cr.set_source_rgb(0.7, 0.7, 0.7)
        cr.set_line_width(0.5)
        cr.rectangle(rx, ry, rw, rh)
        cr.stroke()

        if self.pixbuf:
            iw = self.pixbuf.get_width()
            ih = self.pixbuf.get_height()
            mm_per_inch = 25.4
            if self.scale_mode == "fit":
                s = min(rw * 0.92 / iw, rh * 0.92 / ih)
                diw, dih = iw * s, ih * s
            elif self.scale_mode == "actual":
                diw = iw / self.image_dpi * mm_per_inch * scale
                dih = ih / self.image_dpi * mm_per_inch * scale
            elif self.scale_mode == "fill":
                s = max(rw / iw, rh / ih)
                diw, dih = iw * s, ih * s
            else:
                s = min(rw * 0.92 / iw, rh * 0.92 / ih)
                diw, dih = iw * s, ih * s

            a = self.alignment
            ix = rx + (rw - diw) / 2
            iy = ry + (rh - dih) / 2
            if "left" in a:
                ix = rx + rw * 0.04
            elif "right" in a:
                ix = rx + rw - diw - rw * 0.04
            if "top" in a:
                iy = ry + rh * 0.02
            elif "bot" in a:
                iy = ry + rh - dih - rh * 0.02

            cr.save()
            cr.rectangle(rx, ry, rw, rh)
            cr.clip()
            scaled = self.pixbuf.scale_simple(
                max(1, int(diw)), max(1, int(dih)),
                GdkPixbuf.InterpType.BILINEAR
            )
            Gdk.cairo_set_source_pixbuf(cr, scaled, ix, iy)
            cr.paint()
            cr.restore()
        else:
            cr.set_source_rgb(0.88, 0.88, 0.88)
            cr.rectangle(rx + rw * 0.1, ry + rh * 0.1, rw * 0.8, rh * 0.8)
            cr.fill()
            cr.set_source_rgb(0.6, 0.6, 0.6)
            cr.set_font_size(11)
            cr.move_to(rx + rw * 0.15, ry + rh * 0.52)
            cr.show_text("No image selected")

        if self.info_text:
            cr.set_source_rgb(0.4, 0.4, 0.4)
            cr.set_font_size(10)
            cr.move_to(rx, ry + rh + 13)
            cr.show_text(self.info_text)


class PrintFlow(Gtk.Window):
    def __init__(self):
        super().__init__(title="PrintFlow")
        self.set_wmclass("mutter-x11-frames", "mutter-x11-frames")
        self.set_default_size(920, 740)
        self.set_border_width(14)
        self.image_path = None
        self.image_dpi = 300.0
        self.presets = load_presets()
        self.color_mode = "simple"
        self.current_align = "center"
        self.current_scale = "fit"

        printers = get_turboprint_printers()
        self.current_printer = printers[0] if printers else None
        self.quality_list = get_quality_list(self.current_printer, medium=6)

        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add(main)

        printer_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        main.pack_start(printer_row, False, False, 0)
        printer_row.pack_start(Gtk.Label(label="Printer"), False, False, 0)

        self.printer_combo = Gtk.ComboBoxText()
        if printers:
            for p in printers:
                self.printer_combo.append_text(p)
            self.printer_combo.set_active(0)
            status_txt = "Status: Ready  TurboPrint 2.58"
        else:
            self.printer_combo.append_text("No TurboPrint printer found")
            self.printer_combo.set_active(0)
            status_txt = "Status: TurboPrint printer not found"
        self.printer_combo.connect("changed", self.on_printer_changed)
        printer_row.pack_start(self.printer_combo, True, True, 0)

        self.status_label = Gtk.Label(label=status_txt)
        self.status_label.set_xalign(0)
        self.status_label.get_style_context().add_class("dim-label")
        printer_row.pack_start(self.status_label, False, False, 8)

        main.pack_start(Gtk.Separator(), False, False, 0)

        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        main.pack_start(content, True, True, 0)

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        left.set_size_request(300, -1)
        content.pack_start(left, False, False, 0)

        self.paper_preview = PaperPreview()
        left.pack_start(self.paper_preview, False, False, 0)

        self.filename_label = Gtk.Label(label="No file selected")
        self.filename_label.get_style_context().add_class("dim-label")
        left.pack_start(self.filename_label, False, False, 0)

        choose_btn = Gtk.Button(label="Choose image...")
        choose_btn.connect("clicked", self.on_choose_image)
        left.pack_start(choose_btn, False, False, 0)

        left.pack_start(Gtk.Label(label="PAPER", xalign=0), False, False, 4)
        left.pack_start(Gtk.Label(label="Type", xalign=0), False, False, 0)

        self.media_combo = Gtk.ComboBoxText()
        for num, name in MEDIA:
            self.media_combo.append_text(name)
        self.media_combo.set_active(6)
        self.media_combo.connect("changed", self.on_media_changed)
        left.pack_start(self.media_combo, False, False, 0)

        size_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        left.pack_start(size_row, False, False, 0)

        size_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        size_col.pack_start(Gtk.Label(label="Size", xalign=0), False, False, 0)
        self.pagesize_combo = Gtk.ComboBoxText()
        for _, name, _, _ in PAGESIZE:
            self.pagesize_combo.append_text(name)
        self.pagesize_combo.set_active(0)
        self.pagesize_combo.connect("changed", self.on_pagesize_changed)
        size_col.pack_start(self.pagesize_combo, False, False, 0)
        size_row.pack_start(size_col, True, True, 0)

        orient_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        orient_col.pack_start(Gtk.Label(label="Orientation", xalign=0), False, False, 0)
        self.orient_combo = Gtk.ComboBoxText()
        for name in ["Portrait", "Landscape"]:
            self.orient_combo.append_text(name)
        self.orient_combo.set_active(0)
        self.orient_combo.connect("changed", self.on_orient_changed)
        orient_col.pack_start(self.orient_combo, False, False, 0)
        size_row.pack_start(orient_col, True, True, 0)

        self.icc_info = Gtk.Label(xalign=0)
        self.icc_info.get_style_context().add_class("dim-label")
        left.pack_start(self.icc_info, False, False, 0)
        self.update_icc_info()

        left.pack_start(Gtk.Label(label="PLACEMENT", xalign=0), False, False, 4)
        align_grid = Gtk.Grid(column_spacing=4, row_spacing=4)
        left.pack_start(align_grid, False, False, 0)
        self.align_buttons = {}
        positions = [
            ("top-left",   0, 0), ("top-center",  1, 0), ("top-right",   2, 0),
            ("mid-left",   0, 1), ("center",       1, 1), ("mid-right",   2, 1),
            ("bot-left",   0, 2), ("bot-center",   1, 2), ("bot-right",   2, 2),
        ]
        for key, col, row in positions:
            label = next(l for k, l in ALIGNMENTS if k == key)
            btn = Gtk.ToggleButton(label=label)
            btn.set_size_request(88, 28)
            btn.connect("toggled", self.on_align_toggled, key)
            align_grid.attach(btn, col, row, 1, 1)
            self.align_buttons[key] = btn
        self.align_buttons["center"].set_active(True)

        left.pack_start(Gtk.Label(label="Scaling", xalign=0), False, False, 4)
        self.scale_combo = Gtk.ComboBoxText()
        for s in ["Fit to page", "Actual size", "Fill paper"]:
            self.scale_combo.append_text(s)
        self.scale_combo.set_active(0)
        self.scale_combo.connect("changed", self.on_scale_changed)
        left.pack_start(self.scale_combo, False, False, 0)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        content.pack_start(right, True, True, 0)

        quality_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        right.pack_start(quality_header, False, False, 4)
        quality_header.pack_start(Gtk.Label(label="QUALITY"), False, False, 0)
        quality_info = make_info_button(
            "Quality",
            "Shows print resolutions available for the selected paper type "
            "in the TurboPrint driver.\n\nThe list updates automatically when you change paper type.",
            self
        )
        quality_header.pack_start(quality_info, False, False, 0)

        self.quality_combo = Gtk.ComboBoxText()
        for num, label in self.quality_list:
            self.quality_combo.append_text(label)
        self.quality_combo.set_active(0)
        right.pack_start(self.quality_combo, False, False, 0)

        right.pack_start(Gtk.Label(label="COLOR MANAGEMENT", xalign=0), False, False, 4)
        fg_grid = Gtk.Grid(column_spacing=8, row_spacing=4)
        right.pack_start(fg_grid, False, False, 0)

        fg_grid.attach(Gtk.Label(label="Color mode", xalign=0), 0, 0, 1, 1)
        fg_grid.attach(Gtk.Label(label="RGB color space", xalign=0), 1, 0, 1, 1)

        self.colormode_combo = Gtk.ComboBoxText()
        for m in ["RGB", "CMYK"]:
            self.colormode_combo.append_text(m)
        self.colormode_combo.set_active(0)
        fg_grid.attach(self.colormode_combo, 0, 1, 1, 1)

        self.colorspace_combo = Gtk.ComboBoxText()
        for s in ["Adobe RGB", "sRGB", "ProPhoto RGB"]:
            self.colorspace_combo.append_text(s)
        self.colorspace_combo.set_active(0)
        fg_grid.attach(self.colorspace_combo, 1, 1, 1, 1)

        fg_grid.attach(Gtk.Label(label="Rendering intent", xalign=0), 0, 2, 1, 1)

        ref_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        ref_box.pack_start(Gtk.Label(label="Reference light", xalign=0), False, False, 0)
        ref_info = make_info_button(
            "Reference light",
            "D50 (5000K) \u2014 industry standard for print and gallery. Recommended.\n\n"
            "D65 (6500K) \u2014 daylight/screen standard. Common among photographers.\n\n"
            "D80 (8000K) \u2014 warm light.",
            self
        )
        ref_box.pack_start(ref_info, False, False, 0)
        fg_grid.attach(ref_box, 1, 2, 1, 1)

        self.intent_combo = Gtk.ComboBoxText()
        for i in ["Rel. colorimetric", "Perceptual", "Absolute"]:
            self.intent_combo.append_text(i)
        self.intent_combo.set_active(0)
        fg_grid.attach(self.intent_combo, 0, 3, 1, 1)

        self.light_combo = Gtk.ComboBoxText()
        self.light_combo.append_text("D50 \u2014 gallery/print (standard)")
        self.light_combo.append_text("D65 \u2014 daylight/screen")
        self.light_combo.append_text("D80 \u2014 warm light")
        self.light_combo.set_active(0)
        fg_grid.attach(self.light_combo, 1, 3, 1, 1)

        bp_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.blackpoint_check = Gtk.CheckButton(label="Black point compensation")
        self.blackpoint_check.set_active(True)
        bp_info = make_info_button(
            "Black point compensation",
            "Maps the darkest black in your image to the darkest black "
            "the printer can reproduce, preserving shadow detail.\n\n"
            "Recommended: On.",
            self
        )
        bp_box.pack_start(self.blackpoint_check, False, False, 0)
        bp_box.pack_start(bp_info, False, False, 0)
        fg_grid.attach(bp_box, 0, 4, 2, 1)

        img_adj_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        right.pack_start(img_adj_header, False, False, 4)
        img_adj_header.pack_start(Gtk.Label(label="IMAGE ADJUSTMENTS"), False, False, 0)
        note1 = Gtk.Label(label="(applied to print only)")
        note1.get_style_context().add_class("dim-label")
        img_adj_header.pack_start(note1, False, False, 0)

        self.bright_scale, bright_row = self.make_slider("Brightness", -50, 50, 0, "Dark", "Bright")
        self.sat_scale,   sat_row   = self.make_slider("Saturation", -50, 50, 0, "Less", "More")
        self.con_scale,   con_row   = self.make_slider("Contrast",   -50, 50, 0, "Less", "More")
        right.pack_start(bright_row, False, False, 0)
        right.pack_start(sat_row,    False, False, 0)
        right.pack_start(con_row,    False, False, 0)

        color_adj_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        right.pack_start(color_adj_header, False, False, 4)
        color_adj_header.pack_start(Gtk.Label(label="COLOR ADJUSTMENT"), False, False, 0)
        note2 = Gtk.Label(label="(applied to print only)")
        note2.get_style_context().add_class("dim-label")
        color_adj_header.pack_start(note2, False, False, 0)

        self.adv_color_btn = Gtk.ToggleButton(label="Advanced")
        self.adv_color_btn.connect("toggled", self.on_advanced_color_toggled)
        color_adj_header.pack_end(self.adv_color_btn, False, False, 0)

        self.simple_btn = Gtk.ToggleButton(label="Simple")
        self.simple_btn.set_active(True)
        self.simple_btn.connect("toggled", self.on_simple_toggled)
        color_adj_header.pack_end(self.simple_btn, False, False, 0)

        self.simple_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        right.pack_start(self.simple_box, False, False, 0)
        self.warmth_scale, warmth_row = self.make_slider("Warmth", -50, 50, 0, "Cool", "Warm")
        self.tint_scale,   tint_row   = self.make_slider("Tint",   -50, 50, 0, "Green", "Magenta")
        self.hue_scale,    hue_row    = self.make_slider("Hue",    -50, 50, 0, "Yellow", "Blue")
        self.simple_box.pack_start(warmth_row, False, False, 0)
        self.simple_box.pack_start(tint_row,   False, False, 0)
        self.simple_box.pack_start(hue_row,    False, False, 0)

        self.advanced_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        right.pack_start(self.advanced_box, False, False, 0)
        self.cyan_scale, cyan_row = self.make_slider("Cyan",    -50, 50, 0, "Less", "More")
        self.mag_scale,  mag_row  = self.make_slider("Magenta", -50, 50, 0, "Less", "More")
        self.yel_scale,  yel_row  = self.make_slider("Yellow",  -50, 50, 0, "Less", "More")
        self.blk_scale,  blk_row  = self.make_slider("Black",   -50, 50, 0, "Less", "More")
        self.advanced_box.pack_start(cyan_row, False, False, 0)
        self.advanced_box.pack_start(mag_row,  False, False, 0)
        self.advanced_box.pack_start(yel_row,  False, False, 0)
        self.advanced_box.pack_start(blk_row,  False, False, 0)

        ink_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        right.pack_start(ink_header, False, False, 4)
        ink_header.pack_start(Gtk.Label(label="PRINTER"), False, False, 0)

        adv_btn = Gtk.Button(label="Open TurboPrint Control Center")
        adv_btn.connect("clicked", self.on_advanced)
        ink_header.pack_end(adv_btn, False, False, 0)

        self.ink_label = Gtk.Label(
            label="Ink levels and nozzle check: use TurboPrint Control Center"
        )
        self.ink_label.get_style_context().add_class("dim-label")
        self.ink_label.set_xalign(0)
        self.ink_label.set_line_wrap(True)
        right.pack_start(self.ink_label, False, False, 0)

        main.pack_start(Gtk.Separator(), False, False, 0)

        preset_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        main.pack_start(preset_row, False, False, 0)

        preset_info_btn = make_info_button(
            "Presets",
            "Save your current settings as a preset to quickly restore them later.\n\n"
            "Presets are saved to:\n" + PRESETS_FILE,
            self
        )
        preset_row.pack_start(preset_info_btn, False, False, 0)

        save_btn = Gtk.Button(label="Save adjustments as preset")
        save_btn.connect("clicked", self.on_save_preset)
        preset_row.pack_start(save_btn, False, False, 0)

        self.preset_combo = Gtk.ComboBoxText()
        self.preset_combo.append_text("Select preset")
        for name in self.presets:
            self.preset_combo.append_text(name)
        self.preset_combo.set_active(0)
        self.preset_combo.connect("changed", self.on_preset_selected)
        preset_row.pack_start(self.preset_combo, True, True, 0)

        del_btn = Gtk.Button(label="Delete preset")
        del_btn.connect("clicked", self.on_delete_preset)
        preset_row.pack_start(del_btn, False, False, 0)

        reset_btn = Gtk.Button(label="Reset to defaults")
        reset_btn.connect("clicked", self.on_reset)
        preset_row.pack_start(reset_btn, False, False, 0)

        config_lbl = Gtk.Label(label="Saved to: " + PRESETS_FILE)
        config_lbl.get_style_context().add_class("dim-label")
        preset_row.pack_start(config_lbl, False, False, 4)

        self.print_btn = Gtk.Button(label="Print")
        self.print_btn.set_sensitive(False)
        self.print_btn.connect("clicked", self.on_print)
        preset_row.pack_end(self.print_btn, False, False, 0)

        self.show_all()
        self.advanced_box.hide()
        self.update_preview_paper()

    def make_slider(self, label, min_val, max_val, default, left_label="", right_label=""):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lbl = Gtk.Label(label=label, xalign=0)
        lbl.set_size_request(76, -1)
        top_row.pack_start(lbl, False, False, 0)
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, min_val, max_val, 1)
        scale.set_value(default)
        scale.set_draw_value(True)
        scale.set_hexpand(True)
        top_row.pack_start(scale, True, True, 0)
        box.pack_start(top_row, False, False, 0)
        if left_label or right_label:
            hint_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            spacer = Gtk.Label()
            spacer.set_size_request(76, -1)
            hint_row.pack_start(spacer, False, False, 0)
            left_lbl = Gtk.Label(label=left_label, xalign=0)
            left_lbl.get_style_context().add_class("dim-label")
            left_lbl.set_size_request(60, -1)
            hint_row.pack_start(left_lbl, False, False, 0)
            right_lbl = Gtk.Label(label=right_label, xalign=1)
            right_lbl.get_style_context().add_class("dim-label")
            right_lbl.set_hexpand(True)
            hint_row.pack_start(right_lbl, True, True, 0)
            box.pack_start(hint_row, False, False, 0)
        return scale, box

    def update_preview_paper(self):
        idx = self.pagesize_combo.get_active()
        _, _, w, h = PAGESIZE[idx]
        landscape = self.orient_combo.get_active() == 1
        self.paper_preview.set_paper(w, h, landscape)

    def update_quality_list(self):
        medium_idx = self.media_combo.get_active()
        medium_num = MEDIA[medium_idx][0]
        active = self.quality_combo.get_active()
        self.quality_list = get_quality_list(self.current_printer, medium=medium_num)
        self.quality_combo.remove_all()
        for num, label in self.quality_list:
            self.quality_combo.append_text(label)
        self.quality_combo.set_active(min(active, len(self.quality_list) - 1))

    def on_printer_changed(self, combo):
        self.current_printer = combo.get_active_text()
        self.update_quality_list()

    def on_media_changed(self, combo):
        self.update_icc_info()
        self.update_quality_list()

    def update_icc_info(self):
        idx = self.media_combo.get_active()
        media_num = MEDIA[idx][0]
        icc_name = ICC_MAP.get(media_num)
        ink = INK_TYPE.get(media_num, "Photo Black")
        icc_path = find_icc(icc_name) if icc_name else None
        if icc_path:
            self.icc_info.set_text("ICC: " + icc_name + "  |  " + ink)
        elif icc_name:
            self.icc_info.set_text("ICC: not found  |  " + ink)
        else:
            self.icc_info.set_text("ICC: none  |  " + ink)

    def on_pagesize_changed(self, combo):
        self.update_preview_paper()

    def on_orient_changed(self, combo):
        self.update_preview_paper()

    def on_scale_changed(self, combo):
        modes = ["fit", "actual", "fill"]
        self.current_scale = modes[combo.get_active()]
        self.paper_preview.set_scale_mode(self.current_scale)

    def on_align_toggled(self, btn, key):
        if btn.get_active():
            for k, b in self.align_buttons.items():
                if k != key:
                    b.set_active(False)
            self.current_align = key
            self.paper_preview.set_alignment(key)

    def on_simple_toggled(self, btn):
        if btn.get_active():
            self.adv_color_btn.set_active(False)
            self.color_mode = "simple"
            self.simple_box.show_all()
            self.advanced_box.hide()

    def on_advanced_color_toggled(self, btn):
        if btn.get_active():
            self.simple_btn.set_active(False)
            self.color_mode = "advanced"
            self.advanced_box.show_all()
            self.simple_box.hide()

    def on_advanced(self, btn):
        try:
            subprocess.Popen(["turboprint"])
        except Exception:
            self.status_label.set_text("Could not open TurboPrint Control Center")

    def get_current_settings(self):
        return {
            "media": self.media_combo.get_active(),
            "pagesize": self.pagesize_combo.get_active(),
            "orientation": self.orient_combo.get_active(),
            "quality": self.quality_combo.get_active(),
            "colormode": self.colormode_combo.get_active(),
            "colorspace": self.colorspace_combo.get_active(),
            "intent": self.intent_combo.get_active(),
            "light": self.light_combo.get_active(),
            "blackpoint": self.blackpoint_check.get_active(),
            "alignment": self.current_align,
            "scale": self.scale_combo.get_active(),
            "brightness": self.bright_scale.get_value(),
            "saturation": self.sat_scale.get_value(),
            "contrast": self.con_scale.get_value(),
            "color_mode": self.color_mode,
            "warmth": self.warmth_scale.get_value(),
            "tint": self.tint_scale.get_value(),
            "hue": self.hue_scale.get_value(),
            "cyan": self.cyan_scale.get_value(),
            "magenta": self.mag_scale.get_value(),
            "yellow": self.yel_scale.get_value(),
            "black": self.blk_scale.get_value(),
        }

    def apply_settings(self, s):
        self.media_combo.set_active(s.get("media", 6))
        self.pagesize_combo.set_active(s.get("pagesize", 0))
        self.orient_combo.set_active(s.get("orientation", 0))
        self.quality_combo.set_active(s.get("quality", 0))
        self.colormode_combo.set_active(s.get("colormode", 0))
        self.colorspace_combo.set_active(s.get("colorspace", 0))
        self.intent_combo.set_active(s.get("intent", 0))
        self.light_combo.set_active(s.get("light", 0))
        self.blackpoint_check.set_active(s.get("blackpoint", True))
        self.scale_combo.set_active(s.get("scale", 0))
        self.bright_scale.set_value(s.get("brightness", 0))
        self.sat_scale.set_value(s.get("saturation", 0))
        self.con_scale.set_value(s.get("contrast", 0))
        self.warmth_scale.set_value(s.get("warmth", 0))
        self.tint_scale.set_value(s.get("tint", 0))
        self.hue_scale.set_value(s.get("hue", 0))
        self.cyan_scale.set_value(s.get("cyan", 0))
        self.mag_scale.set_value(s.get("magenta", 0))
        self.yel_scale.set_value(s.get("yellow", 0))
        self.blk_scale.set_value(s.get("black", 0))
        align = s.get("alignment", "center")
        if align in self.align_buttons:
            self.align_buttons[align].set_active(True)
        if s.get("color_mode", "simple") == "advanced":
            self.adv_color_btn.set_active(True)
        else:
            self.simple_btn.set_active(True)

    def on_reset(self, btn):
        self.apply_settings(DEFAULTS)
        self.status_label.set_text("Status: Reset to defaults")

    def on_preset_selected(self, combo):
        name = combo.get_active_text()
        if name and name in self.presets:
            self.apply_settings(self.presets[name])

    def on_save_preset(self, btn):
        dialog = Gtk.Dialog(title="Save preset", parent=self, flags=0)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                           Gtk.STOCK_OK, Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_spacing(8)
        box.set_border_width(12)
        box.pack_start(Gtk.Label(label="Preset name:"), False, False, 0)
        entry = Gtk.Entry()
        box.pack_start(entry, False, False, 0)
        dialog.show_all()
        if dialog.run() == Gtk.ResponseType.OK:
            name = entry.get_text().strip()
            if name:
                self.presets[name] = self.get_current_settings()
                save_presets(self.presets)
                found = any(
                    self.preset_combo.get_model()[i][0] == name
                    for i in range(len(self.preset_combo.get_model()))
                )
                if not found:
                    self.preset_combo.append_text(name)
                self.status_label.set_text("Preset saved: " + name)
        dialog.destroy()

    def on_delete_preset(self, btn):
        name = self.preset_combo.get_active_text()
        if name and name in self.presets:
            del self.presets[name]
            save_presets(self.presets)
            self.preset_combo.remove(self.preset_combo.get_active())
            self.preset_combo.set_active(0)
            self.status_label.set_text("Preset deleted: " + name)

    def on_choose_image(self, btn):
        dialog = Gtk.FileChooserDialog(
            title="Choose image", parent=self,
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                           Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        filt = Gtk.FileFilter()
        filt.set_name("Image files")
        for pat in ["*.tif", "*.tiff", "*.jpg", "*.jpeg", "*.png"]:
            filt.add_pattern(pat)
        dialog.add_filter(filt)
        if dialog.run() == Gtk.ResponseType.OK:
            self.image_path = dialog.get_filename()
            self.filename_label.set_text(os.path.basename(self.image_path))
            self.image_dpi = get_image_dpi(self.image_path)
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(self.image_path)
                self.paper_preview.set_image(pixbuf, self.image_dpi)
            except Exception:
                self.paper_preview.set_image(None)
            self.print_btn.set_sensitive(True)
        dialog.destroy()

    def on_print(self, btn):
        if not self.image_path:
            return
        self.print_btn.set_sensitive(False)
        self.status_label.set_text("Status: Converting image...")
        thread = threading.Thread(target=self.do_print)
        thread.daemon = True
        thread.start()

    def do_print(self):
        try:
            media_idx    = self.media_combo.get_active()
            media_num    = MEDIA[media_idx][0]
            quality_num  = self.quality_list[self.quality_combo.get_active()][0]
            pagesize_num = PAGESIZE[self.pagesize_combo.get_active()][0]
            pagesize_data = PAGESIZE[self.pagesize_combo.get_active()]
            landscape    = self.orient_combo.get_active() == 1
            brightness   = int(self.bright_scale.get_value())
            saturation   = int(self.sat_scale.get_value())
            contrast     = int(self.con_scale.get_value())

            if self.color_mode == "simple":
                cyan, magenta, yellow, black = simple_to_advanced(
                    self.warmth_scale.get_value(),
                    self.tint_scale.get_value(),
                    self.hue_scale.get_value()
                )
            else:
                cyan    = int(self.cyan_scale.get_value())
                magenta = int(self.mag_scale.get_value())
                yellow  = int(self.yel_scale.get_value())
                black   = int(self.blk_scale.get_value())

            with tempfile.NamedTemporaryFile(suffix=".pnm", delete=False) as tmp:
                tmp_path = tmp.name

            # Convert image to 8-bit PNM — no ICC, tpprint handles color
            convert_cmd = ["convert", self.image_path, "-depth", "8"]
            if landscape:
                convert_cmd += ["-rotate", "90"]
            convert_cmd += [tmp_path]
            subprocess.run(convert_cmd, check=True)

            GLib.idle_add(self.set_status, "Status: Sending to printer...")

            bt_str = ("t1b" + str(brightness) +
                      "o" + str(contrast) +
                      "s" + str(saturation) +
                      "i0g180y" + str(yellow) +
                      "m" + str(magenta) +
                      "c" + str(cyan) +
                      "k" + str(black))

            with tempfile.NamedTemporaryFile(suffix=".prn", delete=False) as out:
                out_path = out.name

            tpprint_cmd = [
                "tpprint",
                "-dEpson_SureColorP800",
                "-q" + str(quality_num),
                "-m" + str(media_num),
                "-f" + str(pagesize_num),
                "-i0", "-o0", "-u0", "-c0", "-g2", "-t0", "-y1",
                "-a1",
                "-b" + bt_str,
                tmp_path,
                out_path,
            ]

            subprocess.run(tpprint_cmd, check=True)
            os.unlink(tmp_path)

            lp_cmd = ["lp", "-d", self.current_printer, "-o", "raw", out_path]
            subprocess.run(lp_cmd, check=True)
            os.unlink(out_path)

            GLib.idle_add(self.print_done, True, None)
        except Exception as e:
            GLib.idle_add(self.print_done, False, str(e))

    def set_status(self, text):
        self.status_label.set_text(text)

    def print_done(self, success, error):
        if success:
            self.status_label.set_text("Status: Print sent successfully")
        else:
            self.status_label.set_text("Status: Error - " + str(error))
        self.print_btn.set_sensitive(True)


def main():
    ensure_config_dir()
    win = PrintFlow()
    win.connect("destroy", Gtk.main_quit)
    Gtk.main()


if __name__ == "__main__":
    main()

