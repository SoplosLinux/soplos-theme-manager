import gi
import threading
from pathlib import Path
from typing import Optional

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, GdkPixbuf

from core.i18n_manager import _
from services.lightdm_service import LightdmService
from services.gtk_theme_service import GtkThemeService
from services.icon_cursor_service import IconCursorService
from utils.logger import logger

THUMB_W, THUMB_H = 220, 130
AVATAR_SIZE = 48

_ANCHORS = ('start', 'center', 'end')
_DEFAULT_DIM = (50, 'center')

# Sensible offset to snap to when a grid corner/edge is clicked. Anchor alone
# doesn't visibly move the box when the offset stays wherever it was (e.g. at
# 50%, 'start' vs 'end' only nudges it by half the box size either side of
# dead center — nowhere near the edge a corner click implies), so picking a
# grid cell sets both anchor and a matching offset together.
_ANCHOR_DEFAULT_OFFSET = {'start': 5, 'center': 50, 'end': 95}


def _parse_position_dim(s: str):
    """'5%,start' -> (5, 'start'). Falls back to (50, 'center') on garbage."""
    value, _sep, anchor = s.partition(',')
    value = value.strip()
    if value.endswith('%'):
        value = value[:-1]
    try:
        percent = int(value)
    except ValueError:
        percent = 50
    anchor = anchor.strip()
    if anchor not in _ANCHORS:
        anchor = 'center'
    return max(0, min(100, percent)), anchor


def parse_position(value: Optional[str]):
    """LightDM 'position' string -> ((x_percent, x_anchor), (y_percent, y_anchor))."""
    if not value:
        return _DEFAULT_DIM, _DEFAULT_DIM
    x_str, _sep, y_str = value.strip().partition(' ')
    x = _parse_position_dim(x_str)
    y = _parse_position_dim(y_str) if y_str else x
    return x, y


def format_position(x, y) -> str:
    xs = '{}%,{}'.format(*x)
    ys = '{}%,{}'.format(*y)
    return xs if xs == ys else f'{xs} {ys}'


class LightdmTab(Gtk.Box):

    def __init__(self, config, parent_window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.config = config
        self.parent_window = parent_window
        self.service = LightdmService()
        self.gtk_service = GtkThemeService()
        self.icon_service = IconCursorService()

        self._background_path: Optional[str] = None
        self._avatar_path: Optional[str] = None
        self._current_anchor = ('center', 'center')
        self._suppress_anchor_offset_reset = False

        self._loaded = False
        self._setup_ui()
        self.connect('map', self._on_mapped)

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self):
        # Wrapped in an outer ScrolledWindow so a short window scrolls this
        # form instead of forcing the app window to grow taller. body fills
        # the full viewport height and both cards below expand into it (with
        # their actual fields kept centered inside via each content row's own
        # valign), so a maximized window doesn't leave a large dead gap.
        outer_scroller = Gtk.ScrolledWindow()
        outer_scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.pack_start(outer_scroller, True, True, 0)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        body.set_margin_start(16)
        body.set_margin_end(16)
        body.set_margin_top(12)
        body.set_margin_bottom(16)
        outer_scroller.add(body)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.get_style_context().add_class('theme-card')
        body.pack_start(card, True, True, 0)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        header.set_margin_start(8)
        header.set_margin_top(8)
        header.pack_start(
            Gtk.Image.new_from_icon_name('system-lock-screen', Gtk.IconSize.MENU), False, False, 0
        )
        title_lbl = Gtk.Label(label=_("Login Screen (LightDM)"))
        title_lbl.get_style_context().add_class('theme-card-label')
        title_lbl.set_halign(Gtk.Align.START)
        header.pack_start(title_lbl, False, False, 0)
        card.pack_start(header, False, False, 0)

        hint = Gtk.Label(
            label=_("These settings only affect the login screen, not your desktop session.")
        )
        hint.set_halign(Gtk.Align.START)
        hint.set_margin_start(8)
        hint.get_style_context().add_class('dim-label')
        card.pack_start(hint, False, False, 0)

        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        content.set_margin_start(8)
        content.set_margin_end(8)
        content.set_margin_top(8)
        content.set_margin_bottom(8)
        content.set_valign(Gtk.Align.CENTER)
        card.pack_start(content, True, True, 0)

        # ── Left: background + avatar previews ──────────────────────────
        left_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        content.pack_start(left_col, False, False, 0)

        bg_frame = Gtk.Box()
        bg_frame.get_style_context().add_class('theme-preview-box')
        bg_frame.set_size_request(THUMB_W, THUMB_H)
        bg_frame.set_halign(Gtk.Align.CENTER)
        self._bg_image = Gtk.Image()
        bg_frame.add(self._bg_image)
        left_col.pack_start(bg_frame, False, False, 0)

        bg_btn = Gtk.Button(label=_("Change background…"))
        bg_btn.connect('clicked', self._on_pick_background)
        left_col.pack_start(bg_btn, False, False, 0)

        avatar_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        avatar_row.set_margin_top(6)
        left_col.pack_start(avatar_row, False, False, 0)

        avatar_frame = Gtk.Box()
        avatar_frame.get_style_context().add_class('theme-preview-box')
        avatar_frame.set_size_request(AVATAR_SIZE, AVATAR_SIZE)
        self._avatar_image = Gtk.Image()
        avatar_frame.add(self._avatar_image)
        avatar_row.pack_start(avatar_frame, False, False, 0)

        avatar_btn = Gtk.Button(label=_("Change user image…"))
        avatar_btn.connect('clicked', self._on_pick_avatar)
        avatar_row.pack_start(avatar_btn, True, True, 0)

        # ── Right: theme / icon / cursor / font form ────────────────────
        grid = Gtk.Grid()
        grid.set_row_spacing(10)
        grid.set_column_spacing(12)
        grid.set_valign(Gtk.Align.START)
        content.pack_start(grid, True, True, 0)

        def row(r, label_text, widget):
            lbl = Gtk.Label(label=label_text)
            lbl.set_halign(Gtk.Align.END)
            lbl.get_style_context().add_class('dim-label')
            grid.attach(lbl, 0, r, 1, 1)
            widget.set_hexpand(True)
            grid.attach(widget, 1, r, 1, 1)

        self._theme_combo = Gtk.ComboBoxText()
        row(0, _("GTK theme:"), self._theme_combo)

        self._icon_combo = Gtk.ComboBoxText()
        row(1, _("Icon theme:"), self._icon_combo)

        self._cursor_combo = Gtk.ComboBoxText()
        row(2, _("Cursor theme:"), self._cursor_combo)

        self._font_btn = Gtk.FontButton()
        row(3, _("Font:"), self._font_btn)

        # ════════════════════════════════════════════
        # SECOND CARD — login box position + misc toggles
        # ════════════════════════════════════════════
        pos_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        pos_card.get_style_context().add_class('theme-card')
        body.pack_start(pos_card, True, True, 0)

        pos_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        pos_header.set_margin_start(8)
        pos_header.set_margin_top(8)
        pos_header.pack_start(
            Gtk.Image.new_from_icon_name('view-grid-symbolic', Gtk.IconSize.MENU), False, False, 0
        )
        pos_title = Gtk.Label(label=_("Login Box Position"))
        pos_title.get_style_context().add_class('theme-card-label')
        pos_title.set_halign(Gtk.Align.START)
        pos_header.pack_start(pos_title, False, False, 0)
        pos_card.pack_start(pos_header, False, False, 0)

        pos_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        pos_content.set_margin_start(8)
        pos_content.set_margin_end(8)
        pos_content.set_margin_top(6)
        pos_content.set_margin_bottom(8)
        pos_content.set_valign(Gtk.Align.CENTER)
        pos_card.pack_start(pos_content, True, True, 0)

        # Live preview of where the box will sit on screen. Fixed valign/
        # halign so it keeps its 150x96 landscape shape instead of
        # stretching tall to match the misc-toggles column next to it,
        # which is naturally taller (5 form rows vs. this one shape).
        self._pos_preview = Gtk.DrawingArea()
        self._pos_preview.set_size_request(150, 96)
        self._pos_preview.set_halign(Gtk.Align.START)
        self._pos_preview.set_valign(Gtk.Align.START)
        self._pos_preview.connect('draw', self._on_pos_preview_draw)
        pos_content.pack_start(self._pos_preview, False, False, 0)

        # 3x3 anchor grid — pick which edge/corner the box hugs. Sized and
        # aligned to match the preview's own 150x96 box exactly (same
        # spacing math: 3 cells + 2 gaps = the preview's width/height) so
        # the two sit flush together instead of one looking centered
        # against the other's top-aligned block.
        GRID_SPACING = 3
        cell_w = (150 - 2 * GRID_SPACING) // 3
        cell_h = (96 - 2 * GRID_SPACING) // 3

        anchor_grid = Gtk.Grid()
        anchor_grid.set_row_spacing(GRID_SPACING)
        anchor_grid.set_column_spacing(GRID_SPACING)
        anchor_grid.set_halign(Gtk.Align.START)
        anchor_grid.set_valign(Gtk.Align.START)
        pos_content.pack_start(anchor_grid, False, False, 0)

        self._anchor_buttons = {}
        anchor_group = None
        for row_i, y_anchor in enumerate(_ANCHORS):
            for col_i, x_anchor in enumerate(_ANCHORS):
                btn = Gtk.RadioButton.new_from_widget(anchor_group)
                btn.set_mode(False)
                btn.set_size_request(cell_w, cell_h)
                btn.connect('toggled', self._on_anchor_toggled, x_anchor, y_anchor)
                anchor_grid.attach(btn, col_i, row_i, 1, 1)
                self._anchor_buttons[(x_anchor, y_anchor)] = btn
                if anchor_group is None:
                    anchor_group = btn

        # Fine offset (% from the chosen anchor) + misc toggles
        misc_grid = Gtk.Grid()
        misc_grid.set_row_spacing(8)
        misc_grid.set_column_spacing(12)
        misc_grid.set_valign(Gtk.Align.CENTER)
        pos_content.pack_start(misc_grid, True, True, 0)

        def misc_row(r, label_text, widget):
            lbl = Gtk.Label(label=label_text)
            lbl.set_halign(Gtk.Align.END)
            lbl.get_style_context().add_class('dim-label')
            misc_grid.attach(lbl, 0, r, 1, 1)
            widget.set_hexpand(True)
            widget.set_halign(Gtk.Align.START)
            misc_grid.attach(widget, 1, r, 1, 1)

        self._x_offset_spin = Gtk.SpinButton.new_with_range(0, 100, 1)
        self._x_offset_spin.connect('value-changed', lambda w: self._pos_preview.queue_draw())
        misc_row(0, _("Horizontal offset (%):"), self._x_offset_spin)

        self._y_offset_spin = Gtk.SpinButton.new_with_range(0, 100, 1)
        self._y_offset_spin.connect('value-changed', lambda w: self._pos_preview.queue_draw())
        misc_row(1, _("Vertical offset (%):"), self._y_offset_spin)

        self._avatar_switch = Gtk.Switch()
        misc_row(2, _("Show user avatar:"), self._avatar_switch)

        self._user_bg_switch = Gtk.Switch()
        misc_row(3, _("Use each user's own wallpaper:"), self._user_bg_switch)

        self._clock_entry = Gtk.Entry()
        self._clock_entry.set_placeholder_text('%a, %H:%M')
        misc_row(4, _("Clock format:"), self._clock_entry)

        # ── Apply bar ────────────────────────────────────────────────────
        apply_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        apply_bar.set_halign(Gtk.Align.END)
        apply_bar.set_margin_top(4)
        body.pack_start(apply_bar, False, False, 0)

        self.status_label = Gtk.Label()
        self.status_label.get_style_context().add_class('dim-label')
        apply_bar.pack_start(self.status_label, False, False, 0)

        self.apply_btn = Gtk.Button()
        apply_inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        apply_inner.pack_start(
            Gtk.Image.new_from_icon_name('object-select-symbolic', Gtk.IconSize.BUTTON), False, False, 0
        )
        apply_inner.pack_start(Gtk.Label(label=_("Save & Apply")), False, False, 0)
        self.apply_btn.add(apply_inner)
        self.apply_btn.get_style_context().add_class('suggested-action')
        self.apply_btn.connect('clicked', self._on_apply)
        apply_bar.pack_start(self.apply_btn, False, False, 0)

    # ── Loading ───────────────────────────────────────────────────────────────

    def _on_mapped(self, _widget):
        if not self._loaded:
            self._loaded = True
            self._load_async()

    def _load_async(self):
        self.parent_window.show_progress(_("Reading login screen settings…"))
        threading.Thread(target=self._load_worker, daemon=True).start()

    def _load_worker(self):
        values        = self.service.read_config()
        gtk_themes    = [t['name'] for t in self.gtk_service.list_gtk_themes()]
        icon_themes   = [t['name'] for t in self.icon_service.list_icon_themes()]
        cursor_themes = [t['name'] for t in self.icon_service.list_cursor_themes()]
        GLib.idle_add(self._on_load_done, values, gtk_themes, icon_themes, cursor_themes)

    def _on_load_done(self, values: dict, gtk_themes: list, icon_themes: list, cursor_themes: list):
        self._background_path = values.get('background') or None
        self._avatar_path     = values.get('default-user-image') or None
        self._set_thumb(self._bg_image, self._background_path, THUMB_W, THUMB_H)
        self._set_thumb(self._avatar_image, self._avatar_path, AVATAR_SIZE, AVATAR_SIZE)

        self._fill_combo(self._theme_combo, gtk_themes, values.get('theme-name'))
        self._fill_combo(self._icon_combo, icon_themes, values.get('icon-theme-name'))
        self._fill_combo(self._cursor_combo, cursor_themes, values.get('cursor-theme-name'))

        try:
            self._font_btn.set_font(values.get('font-name') or 'Sans 10')
        except Exception:
            pass

        x, y = parse_position(values.get('position'))
        self._current_anchor = (x[1], y[1])
        # Selecting the button would otherwise snap the offset spinbuttons to
        # the generic per-anchor default (see _ANCHOR_DEFAULT_OFFSET),
        # clobbering the real offset just read from the config file.
        self._suppress_anchor_offset_reset = True
        btn = self._anchor_buttons.get(self._current_anchor)
        if btn:
            btn.set_active(True)
        self._suppress_anchor_offset_reset = False
        self._x_offset_spin.set_value(x[0])
        self._y_offset_spin.set_value(y[0])
        self._pos_preview.queue_draw()

        # hide-user-image is inverted from the "show avatar" switch we show
        self._avatar_switch.set_active((values.get('hide-user-image') or 'false') != 'true')
        self._user_bg_switch.set_active((values.get('user-background') or 'false') == 'true')
        self._clock_entry.set_text(values.get('clock-format') or '')

        self.parent_window.hide_progress()
        return False

    def _fill_combo(self, combo: Gtk.ComboBoxText, items: list, active_value: Optional[str]):
        combo.remove_all()
        for name in items:
            combo.append_text(name)
        if active_value and active_value in items:
            combo.set_active(items.index(active_value))
        elif active_value:
            # Configured theme isn't currently installed — show it anyway
            # rather than silently switching the greeter to something else.
            combo.append_text(active_value)
            combo.set_active(len(items))

    def _set_thumb(self, image_widget: Gtk.Image, path: Optional[str], w: int, h: int):
        if path and Path(path).is_file():
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, w, h, True)
                image_widget.set_from_pixbuf(pixbuf)
                return
            except Exception:
                pass
        image_widget.set_from_icon_name('image-missing', Gtk.IconSize.DIALOG)

    # ── Login box position ───────────────────────────────────────────────────

    def _on_anchor_toggled(self, btn: Gtk.RadioButton, x_anchor: str, y_anchor: str):
        # 'toggled' fires for both the newly active button and the one it
        # replaced — a plain toggle-mode radio button doesn't show enough
        # visual contrast on its own, so make the selected cell obvious
        # with the same highlight style used for selected cards elsewhere.
        ctx = btn.get_style_context()
        if btn.get_active():
            ctx.add_class('theme-card-selected')
            self._current_anchor = (x_anchor, y_anchor)
            if not self._suppress_anchor_offset_reset:
                self._x_offset_spin.set_value(_ANCHOR_DEFAULT_OFFSET[x_anchor])
                self._y_offset_spin.set_value(_ANCHOR_DEFAULT_OFFSET[y_anchor])
            self._pos_preview.queue_draw()
        else:
            ctx.remove_class('theme-card-selected')

    def _on_pos_preview_draw(self, area, cr):
        w = area.get_allocated_width()
        h = area.get_allocated_height()

        style = area.get_style_context()
        fg = style.get_color(Gtk.StateFlags.NORMAL)

        cr.set_line_width(1.5)
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.35)
        cr.rectangle(1, 1, w - 2, h - 2)
        cr.stroke()

        x_anchor, y_anchor = self._current_anchor
        x_pct = self._x_offset_spin.get_value() / 100.0
        y_pct = self._y_offset_spin.get_value() / 100.0

        box_w, box_h = 46, 28
        px = 2 + (w - 4) * x_pct
        py = 2 + (h - 4) * y_pct

        if x_anchor == 'center':
            bx = px - box_w / 2
        elif x_anchor == 'end':
            bx = px - box_w
        else:
            bx = px
        if y_anchor == 'center':
            by = py - box_h / 2
        elif y_anchor == 'end':
            by = py - box_h
        else:
            by = py

        bx = max(2, min(w - 2 - box_w, bx))
        by = max(2, min(h - 2 - box_h, by))

        cr.set_source_rgba(1.0, 0.533, 0.0, 0.9)   # @soplos_orange (#ff8800)
        cr.rectangle(bx, by, box_w, box_h)
        cr.fill()
        return False

    # ── Pick background / avatar ────────────────────────────────────────────

    def _on_pick_background(self, _btn):
        path = self._pick_image(_("Select background image"))
        if path:
            self._background_path = path
            self._set_thumb(self._bg_image, path, THUMB_W, THUMB_H)

    def _on_pick_avatar(self, _btn):
        path = self._pick_image(_("Select user image"))
        if path:
            self._avatar_path = path
            self._set_thumb(self._avatar_image, path, AVATAR_SIZE, AVATAR_SIZE)

    def _pick_image(self, title: str) -> Optional[str]:
        dialog = Gtk.FileChooserDialog(
            title=title, parent=self.parent_window, action=Gtk.FileChooserAction.OPEN
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN,   Gtk.ResponseType.OK,
        )
        img_filter = Gtk.FileFilter()
        img_filter.set_name(_("Images"))
        for pattern in ('*.jpg', '*.jpeg', '*.png', '*.webp', '*.bmp', '*.svg'):
            img_filter.add_pattern(pattern)
        dialog.add_filter(img_filter)

        response = dialog.run()
        path = dialog.get_filename() if response == Gtk.ResponseType.OK else None
        dialog.destroy()
        return path

    # ── Apply ─────────────────────────────────────────────────────────────────

    def _on_apply(self, _btn):
        x_anchor, y_anchor = self._current_anchor
        position = format_position(
            (int(self._x_offset_spin.get_value()), x_anchor),
            (int(self._y_offset_spin.get_value()), y_anchor),
        )
        updates = {
            'background':         self._background_path or '',
            'default-user-image': self._avatar_path or '',
            'theme-name':         self._theme_combo.get_active_text() or '',
            'icon-theme-name':    self._icon_combo.get_active_text() or '',
            'cursor-theme-name':  self._cursor_combo.get_active_text() or '',
            'font-name':          self._font_btn.get_font() or '',
            'position':           position,
            'hide-user-image':    'false' if self._avatar_switch.get_active() else 'true',
            'user-background':    'true' if self._user_bg_switch.get_active() else 'false',
            'clock-format':       self._clock_entry.get_text().strip(),
        }
        self.apply_btn.set_sensitive(False)
        self.status_label.set_text('')
        self.parent_window.show_progress(_("Applying login screen settings…"))

        def worker():
            ok = self.service.write_config(updates)
            GLib.idle_add(self._on_apply_done, ok)

        threading.Thread(target=worker, daemon=True).start()

    def _on_apply_done(self, ok: bool):
        self.parent_window.hide_progress()
        self.apply_btn.set_sensitive(True)
        self.status_label.set_text(_("Saved") if ok else _("Error saving login screen settings"))
        return False
