import gi
import locale
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf, Pango, Gio

from core.i18n_manager import _
from utils.logger import logger

CHANNEL      = 'xfce4-panel'
PLUGINS_DIR  = Path('/usr/share/xfce4/panel/plugins')
ICON_SIZE    = 24

# Derive locale language code for plugin name localisation
_loc = locale.getdefaultlocale()[0] or ''
_LANG      = _loc                        # e.g. 'es_ES'
_LANG_SHORT = _loc.split('_')[0] if _loc else ''  # e.g. 'es'

# p values confirmed from actual Soplos theme XMLs:
#   p=6  → top   (Modern_Black/White, default.xml panel-1)
#   p=8  → bottom (Classic_Black/White, Special, Unity — x is the horizontal CENTER)
#   p=1  → right (Special, Unity — x is near the right edge)
#   p=10 → left  (default.xml panel-2 dock)
_POSITIONS = [
    (6,  'top'),
    (8,  'bottom'),
    (10, 'left'),
    (1,  'right'),
]
_EDGE_FROM_P = {
    0:  'bottom',  # floating
    1:  'right',
    2:  'right',
    3:  'bottom',
    4:  'bottom',
    5:  'left',
    6:  'top',
    7:  'top',
    8:  'bottom',
    9:  'right',
    10: 'left',
    11: 'left',
    12: 'bottom',
}


# ── xfconf helpers ────────────────────────────────────────────────────────────

def _xfq(*args, timeout=5) -> subprocess.CompletedProcess:
    return subprocess.run(
        ['xfconf-query', '-c', CHANNEL] + list(args),
        capture_output=True, text=True, timeout=timeout
    )

def _get(prop: str) -> Optional[str]:
    r = _xfq('-p', prop)
    return r.stdout.strip() if r.returncode == 0 else None

def _get_array(prop: str) -> list:
    r = _xfq('-p', prop)
    ids = []
    for line in r.stdout.splitlines():
        line = line.strip()
        try:
            ids.append(int(line))
        except ValueError:
            pass
    return ids

def _set(prop: str, type_: str, value: str) -> bool:
    r = _xfq('-p', prop, '--create', '-t', type_, '-s', value)
    return r.returncode == 0

def _set_array(prop: str, type_: str, values: list) -> bool:
    if not values:
        return True
    # --force-array (-a) is required so that a single-element list is written as
    # an xfconf array and not a scalar; without it xfce4-panel cannot read /panels.
    args = ['-p', prop, '--create', '--force-array']
    for v in values:
        args += ['-t', type_, '-s', str(v)]
    r = _xfq(*args)
    return r.returncode == 0

def _remove(prop: str):
    _xfq('-p', prop, '-r', '--recursive')

def _panel_restart():
    import os
    try:
        subprocess.run(['xfce4-panel', '--quit'], capture_output=True, timeout=5)
        time.sleep(0.4)
        subprocess.Popen(
            ['xfce4-panel'],
            env={**os.environ, 'HOME': str(Path.home())},
            cwd=str(Path.home()),
            start_new_session=True,
        )
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            r = subprocess.run(['pgrep', '-x', 'xfce4-panel'], capture_output=True)
            if r.returncode == 0:
                time.sleep(0.3)
                break
            time.sleep(0.1)
    except Exception:
        pass

def _panel_ids() -> list:
    r = _xfq('-p', '/panels')
    ids = []
    for line in r.stdout.splitlines():
        try:
            ids.append(int(line.strip()))
        except ValueError:
            pass
    return ids or [1]


# ── Plugin desktop file reader ────────────────────────────────────────────────

def _parse_desktop(path: Path) -> dict:
    keys = {}
    try:
        for line in path.read_text(errors='replace').splitlines():
            if '=' in line and not line.startswith('#'):
                k, _, v = line.partition('=')
                keys[k.strip()] = v.strip()
    except Exception:
        pass
    return keys

def _plugin_name(keys: dict, fallback: str) -> str:
    for k in (f'Name[{_LANG}]', f'Name[{_LANG_SHORT}]', 'Name'):
        if keys.get(k):
            return keys[k]
    return fallback

def _load_icon(icon_name: str, size: int) -> Optional[GdkPixbuf.Pixbuf]:
    if not icon_name:
        return None
    try:
        theme = Gtk.IconTheme.get_default()
        info = theme.lookup_icon(icon_name, size, 0)
        if info:
            return info.load_icon()
    except Exception:
        pass
    try:
        p = Path(icon_name)
        if p.is_file():
            return GdkPixbuf.Pixbuf.new_from_file_at_scale(str(p), size, size, True)
    except Exception:
        pass
    return None

def _scan_available_plugins() -> list:
    """Return list of dicts: {module, name, comment, icon_name} sorted by name."""
    result = []
    if not PLUGINS_DIR.exists():
        return result
    for f in sorted(PLUGINS_DIR.glob('*.desktop')):
        keys = _parse_desktop(f)
        if not keys.get('X-XFCE-Module', ''):
            continue
        module = f.stem  # xfce4-panel stores the .desktop filename stem in xfconf
        result.append({
            'module':   module,
            'name':     _plugin_name(keys, module),
            'comment':  keys.get('Comment', ''),
            'icon':     keys.get('Icon', 'application-x-executable'),
        })
    return sorted(result, key=lambda x: x['name'].lower())


# ── Panel settings reader ─────────────────────────────────────────────────────

def _read_settings(pk: str) -> dict:
    # xfce4-panel xfconf layout: /panels/panel-N/prop (panel-N is a child of panels)
    pos_str = _get(f'/panels/{pk}/position') or ''
    p_val = 8
    coords = {}
    try:
        for part in pos_str.split(';'):
            if '=' in part:
                k, v = part.split('=', 1)
                if k == 'p':
                    p_val = int(v)
                else:
                    coords[k] = int(v)
    except Exception:
        pass

    if p_val == 0:
        # Floating panel: derive edge from x/y position relative to screen
        try:
            scr = Gdk.Screen.get_default()
            sw, sh = scr.get_width(), scr.get_height()
            cx = coords.get('x', sw // 2)
            cy = coords.get('y', sh // 2)
            if cy <= sh // 4:
                edge = 'top'
            elif cy >= 3 * sh // 4:
                edge = 'bottom'
            elif cx <= sw // 4:
                edge = 'left'
            elif cx >= 3 * sw // 4:
                edge = 'right'
            else:
                edge = 'bottom'
        except Exception:
            edge = 'bottom'
    else:
        edge = _EDGE_FROM_P.get(p_val, 'bottom')

    return {
        'edge':          edge,
        'mode':          _get(f'/panels/{pk}/mode'),
        'size':          _get(f'/panels/{pk}/size'),
        'icon_sz':       _get(f'/panels/{pk}/icon-size'),
        'length':        _get(f'/panels/{pk}/length'),
        'length_adjust': _get(f'/panels/{pk}/length-adjust'),
        'nrows':         _get(f'/panels/{pk}/nrows'),
        'autohide':      _get(f'/panels/{pk}/autohide-behavior'),
        'dark':          _get('/panels/dark-mode'),
        'locked':        _get(f'/panels/{pk}/position-locked'),
        'pos_str':       pos_str,
    }

def _build_module_map() -> dict:
    """Return dict mapping .desktop filename stem → desktop keys for all plugins."""
    result = {}
    if not PLUGINS_DIR.exists():
        return result
    for f in PLUGINS_DIR.glob('*.desktop'):
        keys = _parse_desktop(f)
        if keys.get('X-XFCE-Module', ''):
            result[f.stem] = keys  # key by filename stem = what xfconf stores
    return result

def _read_active_plugins(pk: str) -> list:
    """Return ordered list of dicts: {id, module, name, icon}."""
    module_map = _build_module_map()
    ids = _get_array(f'/panels/{pk}/plugin-ids')
    plugins = []
    for pid in ids:
        module = _get(f'/plugins/plugin-{pid}') or ''
        keys   = module_map.get(module, {})
        name   = _plugin_name(keys, module) if keys else module
        icon   = keys.get('Icon', 'application-x-executable')
        plugins.append({'id': pid, 'module': module, 'name': name, 'icon': icon})
    return plugins

_SNAP_P = {'top': 6, 'bottom': 8, 'left': 10, 'right': 1}

def _build_position_string(edge: str, align: int, length: int, size: int = 42) -> str:
    """Return a position string for xfce4-panel.

    Full-width panels (length >= 100) use the snapped p values (p=6/8/10/1) so
    the WM receives _NET_WM_STRUT hints and windows don't maximize under them.

    Partial-width (dock-style) panels use p=0 floating with explicit center
    coordinates, which is the only mode where XFCE4 reliably respects placement
    across different hardware and screen resolutions.
    """
    if length >= 100:
        # Snapped panels tell the WM to reserve screen space (struts).
        p = _SNAP_P.get(edge, 8)
        return f'p={p};x=0;y=0'

    # Partial-width: floating panel, center coordinates.
    try:
        screen = Gdk.Screen.get_default()
        sw = screen.get_width()
        sh = screen.get_height()
    except Exception:
        sw, sh = 1920, 1080

    if edge in ('top', 'bottom'):
        panel_w = max(1, int(sw * length / 100))
        cy      = size // 2 if edge == 'top' else sh - size // 2
        if align == 0:
            cx = panel_w // 2
        elif align == 2:
            cx = sw - panel_w // 2
        else:
            cx = sw // 2
    else:
        panel_h = max(1, int(sh * length / 100))
        cx      = size // 2 if edge == 'left' else sw - size // 2
        if align == 0:
            cy = panel_h // 2
        elif align == 2:
            cy = sh - panel_h // 2
        else:
            cy = sh // 2

    return f'p=0;x={cx};y={cy}'


# ═══════════════════════════════════════════════════════════════════════════════

class PanelTab(Gtk.Box):

    def __init__(self, config, parent_window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.config         = config
        self.parent_window  = parent_window
        self._panel_ids     = []
        self._current_panel = 'panel-1'
        self._old_pos_str   = ''
        self._old_edge      = 'bottom'
        self._available     = []   # list of plugin dicts from system

        self._loaded = False
        self._panel_lock = threading.Lock()
        self._setup_ui()
        self.connect('map', self._on_mapped)

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self):
        # ── Single full-width column: settings on top, plugins below ───────────
        # The whole tab lives inside one outer ScrolledWindow (same pattern as
        # Themes/Wallpapers/Icons&Cursors) so a short app window scrolls the
        # whole page instead of forcing the window itself to grow taller. The
        # plugin lists further down keep their own internal scroll too, so
        # long lists don't force the outer page to grow unreasonably either.
        outer_scroller = Gtk.ScrolledWindow()
        outer_scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.pack_start(outer_scroller, True, True, 0)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        outer_scroller.add(body)

        # ════════════════════════════════════════════
        # TOP AREA — panel selector, preview, grouped settings
        # ════════════════════════════════════════════
        top_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        top_area.set_margin_start(16)
        top_area.set_margin_end(16)
        top_area.set_margin_top(12)
        body.pack_start(top_area, False, False, 0)

        # Panel selector — segmented pills (one per panel) + add/delete
        self._selector_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._selector_row.set_margin_bottom(12)
        top_area.pack_start(self._selector_row, False, False, 0)

        self._panel_pills_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self._panel_pills_box.get_style_context().add_class('linked')
        self._selector_row.pack_start(self._panel_pills_box, False, False, 0)
        self._panel_pill_group = None   # first Gtk.RadioButton, used to group the rest
        self._panel_ids_order  = []     # ids in the same order as the pills

        new_btn = Gtk.Button()
        new_btn.add(Gtk.Image.new_from_icon_name('list-add', Gtk.IconSize.BUTTON))
        new_btn.set_tooltip_text(_("Add new panel"))
        new_btn.connect('clicked', self._on_new_panel)
        self._selector_row.pack_start(new_btn, False, False, 0)

        self._del_panel_btn = Gtk.Button()
        self._del_panel_btn.add(Gtk.Image.new_from_icon_name('list-remove', Gtk.IconSize.BUTTON))
        self._del_panel_btn.set_tooltip_text(_("Delete this panel"))
        self._del_panel_btn.connect('clicked', self._on_delete_panel)
        self._del_panel_btn.set_sensitive(False)
        self._selector_row.pack_start(self._del_panel_btn, False, False, 0)

        # ── Live position preview ───────────────────────────────────────────
        preview_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        preview_box.get_style_context().add_class('theme-card')
        preview_box.set_margin_bottom(12)
        top_area.pack_start(preview_box, False, False, 0)

        self._preview_area = Gtk.DrawingArea()
        self._preview_area.set_size_request(120, 72)
        self._preview_area.set_margin_start(10)
        self._preview_area.set_margin_top(10)
        self._preview_area.set_margin_bottom(10)
        self._preview_area.connect('draw', self._on_preview_draw)
        preview_box.pack_start(self._preview_area, False, False, 0)

        self._preview_label = Gtk.Label()
        self._preview_label.set_line_wrap(True)
        self._preview_label.set_halign(Gtk.Align.START)
        self._preview_label.set_valign(Gtk.Align.CENTER)
        self._preview_label.set_margin_end(10)
        self._preview_label.get_style_context().add_class('dim-label')
        preview_box.pack_start(self._preview_label, True, True, 0)

        # ── Grouped settings sections — laid out two-up so the row uses the
        # full window width instead of stacking every field in one narrow column.
        sections_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        sections_row.set_homogeneous(True)
        top_area.pack_start(sections_row, False, False, 0)

        def make_section(parent_box, title, hint):
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            card.get_style_context().add_class('theme-card')

            lbl = Gtk.Label()
            lbl.set_markup(
                f"<b>{GLib.markup_escape_text(title)}</b>  "
                f"<span alpha='55%' size='small'>{GLib.markup_escape_text(hint)}</span>"
            )
            lbl.set_halign(Gtk.Align.START)
            lbl.set_margin_start(8)
            lbl.set_margin_top(8)
            card.pack_start(lbl, False, False, 0)

            grid = Gtk.Grid()
            grid.set_row_spacing(8)
            grid.set_column_spacing(8)
            grid.set_margin_start(8)
            grid.set_margin_end(8)
            grid.set_margin_bottom(8)
            card.pack_start(grid, False, False, 0)

            parent_box.pack_start(card, True, True, 0)
            return grid

        def row(grid, r, label_text, widget):
            lbl = Gtk.Label(label=label_text)
            lbl.set_halign(Gtk.Align.END)
            lbl.get_style_context().add_class('dim-label')
            grid.attach(lbl, 0, r, 1, 1)
            widget.set_hexpand(True)
            grid.attach(widget, 1, r, 1, 1)

        # -- Posición: dónde vive el panel --------------------------------------
        pos_grid = make_section(sections_row, _("Position"), _("where the panel lives"))

        self._pos_combo = Gtk.ComboBoxText()
        for lbl in [_("Top"), _("Bottom"), _("Left"), _("Right")]:
            self._pos_combo.append_text(lbl)
        self._pos_combo.set_active(1)
        self._pos_combo.connect('changed', self._on_preview_inputs_changed)
        row(pos_grid, 0, _("Position:"), self._pos_combo)

        self._align_combo = Gtk.ComboBoxText()
        for lbl in [_("Left"), _("Center"), _("Right")]:
            self._align_combo.append_text(lbl)
        self._align_combo.set_active(1)
        self._align_combo.connect('changed', self._on_preview_inputs_changed)
        row(pos_grid, 1, _("Alignment:"), self._align_combo)

        self._length_spin = Gtk.SpinButton.new_with_range(1, 100, 1)
        self._length_spin.set_value(100)
        self._length_spin.connect('value-changed', self._on_preview_inputs_changed)
        row(pos_grid, 2, _("Length (%):"), self._length_spin)

        lock_box = Gtk.Box()
        self._lock_switch = Gtk.Switch()
        self._lock_switch.set_halign(Gtk.Align.START)
        lock_box.pack_start(self._lock_switch, False, False, 0)
        row(pos_grid, 3, _("Lock position:"), lock_box)

        # -- Apariencia: tamaño y estilo -----------------------------------------
        look_grid = make_section(sections_row, _("Appearance"), _("size and style"))

        self._mode_combo = Gtk.ComboBoxText()
        for lbl in [_("Horizontal"), _("Vertical"), _("Deskbar")]:
            self._mode_combo.append_text(lbl)
        self._mode_combo.set_active(0)
        row(look_grid, 0, _("Mode:"), self._mode_combo)

        self._size_spin = Gtk.SpinButton.new_with_range(16, 128, 1)
        self._size_spin.set_value(42)
        row(look_grid, 1, _("Height (px):"), self._size_spin)

        self._icon_spin = Gtk.SpinButton.new_with_range(8, 96, 1)
        self._icon_spin.set_value(24)
        row(look_grid, 2, _("Icon size (px):"), self._icon_spin)

        self._rows_spin = Gtk.SpinButton.new_with_range(1, 6, 1)
        self._rows_spin.set_value(1)
        row(look_grid, 3, _("Rows:"), self._rows_spin)

        dark_box = Gtk.Box()
        self._dark_switch = Gtk.Switch()
        self._dark_switch.set_halign(Gtk.Align.START)
        dark_box.pack_start(self._dark_switch, False, False, 0)
        row(look_grid, 4, _("Dark mode:"), dark_box)

        # -- Comportamiento: cuándo se oculta ------------------------------------
        behavior_grid = make_section(sections_row, _("Behavior"), _("when it hides"))

        self._autohide_combo = Gtk.ComboBoxText()
        for opt in [_("Never"), _("Intelligent"), _("Always")]:
            self._autohide_combo.append_text(opt)
        self._autohide_combo.set_active(0)
        row(behavior_grid, 0, _("Auto-hide:"), self._autohide_combo)

        auto_expand_box = Gtk.Box()
        self._auto_expand_switch = Gtk.Switch()
        self._auto_expand_switch.set_halign(Gtk.Align.START)
        auto_expand_box.pack_start(self._auto_expand_switch, False, False, 0)
        row(behavior_grid, 1, _("Auto-expand:"), auto_expand_box)

        # ── Apply bar — right below the sections, above the plugin list ────────
        apply_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        apply_bar.set_halign(Gtk.Align.END)
        apply_bar.set_margin_top(10)
        apply_bar.set_margin_bottom(10)
        top_area.pack_start(apply_bar, False, False, 0)

        self.apply_btn = Gtk.Button()
        apply_inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        apply_inner.pack_start(
            Gtk.Image.new_from_icon_name('object-select-symbolic', Gtk.IconSize.BUTTON),
            False, False, 0
        )
        apply_inner.pack_start(Gtk.Label(label=_("Save & Apply")), False, False, 0)
        self.apply_btn.add(apply_inner)
        self.apply_btn.get_style_context().add_class('suggested-action')
        self.apply_btn.connect('clicked', self._on_apply)
        apply_bar.pack_start(self.apply_btn, False, False, 0)

        body.pack_start(Gtk.Separator(), False, False, 0)

        # ════════════════════════════════════════════
        # BOTTOM AREA — plugin management (expands, full width)
        # ════════════════════════════════════════════
        plugins_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        body.pack_start(plugins_col, True, True, 0)

        # Header
        ph_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        ph_box.set_margin_start(16)
        ph_box.set_margin_top(8)
        ph_box.set_margin_bottom(6)
        ph_box.pack_start(
            Gtk.Image.new_from_icon_name('preferences-desktop', Gtk.IconSize.MENU),
            False, False, 0
        )
        ph_lbl = Gtk.Label(label=_("Panel Plugins"))
        ph_lbl.get_style_context().add_class('theme-card-label')
        ph_lbl.set_halign(Gtk.Align.START)
        ph_box.pack_start(ph_lbl, False, False, 0)
        plugins_col.pack_start(ph_box, False, False, 0)
        plugins_col.pack_start(Gtk.Separator(), False, False, 0)

        # Two-pane plugin split
        plug_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        plugins_col.pack_start(plug_hbox, True, True, 0)

        # ── Active plugins list ───────────────────────────────────────────────
        act_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        act_box.set_size_request(260, -1)
        plug_hbox.pack_start(act_box, False, False, 0)

        act_hdr = Gtk.Box()
        act_hdr.set_margin_start(8)
        act_hdr.set_margin_top(6)
        act_hdr.set_margin_bottom(4)
        act_lbl = Gtk.Label(label=_("Active (drag to reorder)"))
        act_lbl.get_style_context().add_class('dim-label')
        act_lbl.set_halign(Gtk.Align.START)
        act_hdr.pack_start(act_lbl, True, True, 0)
        act_box.pack_start(act_hdr, False, False, 0)
        act_box.pack_start(Gtk.Separator(), False, False, 0)

        sc_act = Gtk.ScrolledWindow()
        sc_act.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sc_act.set_min_content_height(220)
        act_box.pack_start(sc_act, True, True, 0)

        self._active_store = Gtk.ListStore(GdkPixbuf.Pixbuf, str, str, int)
        self._active_view  = Gtk.TreeView(model=self._active_store)
        self._active_view.set_headers_visible(False)
        self._active_view.set_reorderable(True)

        col_ic = Gtk.TreeViewColumn()
        cr_ic  = Gtk.CellRendererPixbuf()
        col_ic.pack_start(cr_ic, False)
        col_ic.add_attribute(cr_ic, 'pixbuf', 0)
        self._active_view.append_column(col_ic)

        col_nm = Gtk.TreeViewColumn()
        cr_nm  = Gtk.CellRendererText()
        cr_nm.set_property('ellipsize', Pango.EllipsizeMode.END)
        col_nm.pack_start(cr_nm, True)
        col_nm.add_attribute(cr_nm, 'text', 1)
        self._active_view.append_column(col_nm)

        sc_act.add(self._active_view)

        act_btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        act_btns.set_halign(Gtk.Align.CENTER)
        act_btns.set_margin_top(6)
        act_btns.set_margin_bottom(8)
        act_box.pack_start(act_btns, False, False, 0)

        for icon_name, tip, cb in [
            ('go-up',              _("Move Up"),       self._on_move_up),
            ('go-down',            _("Move Down"),     self._on_move_down),
            ('list-remove',        _("Remove"),        self._on_remove),
            ('preferences-system', _("Settings"),      self._on_plugin_settings),
        ]:
            btn = Gtk.Button()
            btn.add(Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.BUTTON))
            btn.set_tooltip_text(tip)
            btn.connect('clicked', cb)
            act_btns.pack_start(btn, False, False, 0)

        plug_hbox.pack_start(
            Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 0
        )

        # ── Available plugins list ────────────────────────────────────────────
        avail_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        plug_hbox.pack_start(avail_box, True, True, 0)

        avail_hdr = Gtk.Box()
        avail_hdr.set_margin_start(8)
        avail_hdr.set_margin_top(6)
        avail_hdr.set_margin_bottom(4)
        avail_lbl = Gtk.Label(label=_("Available"))
        avail_lbl.get_style_context().add_class('dim-label')
        avail_lbl.set_halign(Gtk.Align.START)
        avail_hdr.pack_start(avail_lbl, True, True, 0)
        avail_hint = Gtk.Label(label=_("double-click to add"))
        avail_hint.get_style_context().add_class('dim-label')
        avail_hint.set_halign(Gtk.Align.END)
        avail_hdr.pack_start(avail_hint, False, False, 0)
        avail_box.pack_start(avail_hdr, False, False, 0)

        self._search = Gtk.SearchEntry()
        self._search.set_placeholder_text(_("Search plugins…"))
        self._search.set_margin_start(8)
        self._search.set_margin_end(8)
        self._search.set_margin_bottom(4)
        self._search.connect('search-changed', lambda w: self._avail_filter.refilter())
        avail_box.pack_start(self._search, False, False, 0)

        avail_box.pack_start(Gtk.Separator(), False, False, 0)

        sc_avail = Gtk.ScrolledWindow()
        sc_avail.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sc_avail.set_min_content_height(220)
        avail_box.pack_start(sc_avail, True, True, 0)

        # Columns: pixbuf, name (plain, used for filtering), module, comment, markup (display)
        self._avail_store  = Gtk.ListStore(GdkPixbuf.Pixbuf, str, str, str, str)
        self._avail_filter = self._avail_store.filter_new()
        self._avail_filter.set_visible_func(self._filter_func)

        self._avail_view = Gtk.TreeView(model=self._avail_filter)
        self._avail_view.set_headers_visible(False)
        self._avail_view.connect('row-activated', self._on_avail_row_activated)

        col_ai = Gtk.TreeViewColumn()
        cr_ai  = Gtk.CellRendererPixbuf()
        col_ai.pack_start(cr_ai, False)
        col_ai.add_attribute(cr_ai, 'pixbuf', 0)
        self._avail_view.append_column(col_ai)

        col_an = Gtk.TreeViewColumn()
        cr_an  = Gtk.CellRendererText()
        cr_an.set_property('ellipsize', Pango.EllipsizeMode.END)
        cr_an.set_property('ypad', 4)
        col_an.pack_start(cr_an, True)
        col_an.add_attribute(cr_an, 'markup', 4)
        self._avail_view.append_column(col_an)

        sc_avail.add(self._avail_view)

        add_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        add_bar.set_halign(Gtk.Align.CENTER)
        add_bar.set_margin_top(6)
        add_bar.set_margin_bottom(8)
        avail_box.pack_start(add_bar, False, False, 0)

        add_btn = Gtk.Button()
        add_inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        add_inner.pack_start(
            Gtk.Image.new_from_icon_name('list-add', Gtk.IconSize.BUTTON), False, False, 0
        )
        add_inner.pack_start(Gtk.Label(label=_("Add to Panel")), False, False, 0)
        add_btn.add(add_inner)
        add_btn.connect('clicked', self._on_add)
        add_bar.pack_start(add_btn, False, False, 0)

    # ── Loading ───────────────────────────────────────────────────────────────

    def _on_mapped(self, _widget):
        self._loaded = True
        self._load_async()

    def _load_async(self):
        self.parent_window.show_progress(_("Reading panel settings…"))
        threading.Thread(target=self._load_worker, daemon=True).start()

    def _load_worker(self):
        ids        = _panel_ids()
        pk         = f'panel-{ids[0]}'
        settings   = _read_settings(pk)
        active     = _read_active_plugins(pk)
        available  = _scan_available_plugins()
        GLib.idle_add(self._on_load_done, ids, pk, settings, active, available)

    def _on_load_done(self, ids, pk, settings, active, available):
        self._panel_ids     = ids
        self._current_panel = pk
        self._available     = available

        self._rebuild_panel_pills(ids, ids[0])
        self._del_panel_btn.set_sensitive(len(ids) > 1)
        self._fill_settings(settings)
        self._fill_active(active)
        self._fill_available(available)
        self.parent_window.hide_progress()
        return False

    # ── Panel pill selector ──────────────────────────────────────────────────

    def _rebuild_panel_pills(self, ids: list, active_id: int):
        """Rebuild the segmented Panel-1/Panel-2/... selector and select active_id.

        Selecting a pill during construction would otherwise fire 'toggled' and
        kick off a redundant reload — the caller always loads settings itself
        right after rebuilding, so pill toggling is suppressed while building.
        """
        for child in list(self._panel_pills_box.get_children()):
            self._panel_pills_box.remove(child)
        self._panel_ids_order = list(ids)
        self._panel_pill_group = None

        self._suppress_pill_toggle = True
        for pid in ids:
            btn = Gtk.RadioButton.new_from_widget(self._panel_pill_group)
            btn.set_mode(False)   # draw as a button, not a radio dot
            btn.set_label(_("Panel {n}").format(n=pid))
            btn.set_active(pid == active_id)
            btn.connect('toggled', self._on_panel_pill_toggled, pid)
            self._panel_pills_box.pack_start(btn, True, True, 0)
            if self._panel_pill_group is None:
                self._panel_pill_group = btn
        self._suppress_pill_toggle = False
        self._panel_pills_box.show_all()

    def _on_panel_pill_toggled(self, btn, pid):
        if not btn.get_active() or getattr(self, '_suppress_pill_toggle', False):
            return
        self._current_panel = f'panel-{pid}'
        self.parent_window.show_progress(_("Reading panel settings…"))
        threading.Thread(target=self._reload_worker, daemon=True).start()

    # ── Live position preview ────────────────────────────────────────────────

    _PREVIEW_EDGES = ('top', 'bottom', 'left', 'right')

    def _on_preview_inputs_changed(self, *_args):
        self._preview_area.queue_draw()
        edge_idx  = self._pos_combo.get_active()
        edge      = self._PREVIEW_EDGES[edge_idx] if 0 <= edge_idx < 4 else 'bottom'
        align_idx = self._align_combo.get_active()
        align     = {0: _("start"), 1: _("center"), 2: _("end")}.get(align_idx, _("center"))
        length    = int(self._length_spin.get_value())
        edge_name = {
            'top':    _("top"),
            'bottom': _("bottom"),
            'left':   _("left"),
            'right':  _("right"),
        }.get(edge, edge)
        if length >= 100:
            self._preview_label.set_markup(
                _("Full width on the <b>{edge}</b> edge.").format(edge=edge_name)
            )
        else:
            self._preview_label.set_markup(
                _("{length}% wide, {align}-aligned on the <b>{edge}</b> edge.").format(
                    length=length, align=align, edge=edge_name
                )
            )

    def _on_preview_draw(self, area, cr):
        w = area.get_allocated_width()
        h = area.get_allocated_height()

        style = area.get_style_context()
        fg = style.get_color(Gtk.StateFlags.NORMAL)

        # Screen outline
        cr.set_line_width(1.5)
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.35)
        cr.rectangle(1, 1, w - 2, h - 2)
        cr.stroke()

        edge_idx  = self._pos_combo.get_active()
        edge      = self._PREVIEW_EDGES[edge_idx] if 0 <= edge_idx < 4 else 'bottom'
        align_idx = self._align_combo.get_active()
        length    = max(1, min(100, int(self._length_spin.get_value()))) / 100.0

        thickness = 5
        cr.set_source_rgba(1.0, 0.533, 0.0, 0.9)   # @soplos_orange (#ff8800)

        if edge in ('top', 'bottom'):
            bar_w = (w - 4) * length
            if align_idx == 0:
                x = 2
            elif align_idx == 2:
                x = w - 2 - bar_w
            else:
                x = 2 + (w - 4 - bar_w) / 2
            y = 2 if edge == 'top' else h - 2 - thickness
            cr.rectangle(x, y, bar_w, thickness)
        else:
            bar_h = (h - 4) * length
            if align_idx == 0:
                y = 2
            elif align_idx == 2:
                y = h - 2 - bar_h
            else:
                y = 2 + (h - 4 - bar_h) / 2
            x = 2 if edge == 'left' else w - 2 - thickness
            cr.rectangle(x, y, thickness, bar_h)

        cr.fill()
        return False

    def _fill_settings(self, s: dict):
        def si(v, d):
            """Parse int or float string → int, return default on failure.
            Handles both dot and comma as decimal separator (locale-safe)."""
            if v is None:
                return d
            try:
                return int(round(float(str(v).replace(',', '.'))))
            except Exception:
                return d

        edge_idx = {'top': 0, 'bottom': 1, 'left': 2, 'right': 3}
        self._old_edge    = s.get('edge', 'bottom')
        self._old_pos_str = s.get('pos_str', '')
        self._pos_combo.set_active(edge_idx.get(self._old_edge, 1))

        # Derive alignment from p value: 1/4/7/10=start, 2/5/8/11=center, 3/6/9/12=end, 0=center
        p_val = 8
        try:
            for part in self._old_pos_str.split(';'):
                if part.startswith('p='):
                    p_val = int(part[2:])
        except Exception:
            pass
        # Derive alignment from p+x for floating panels; from p for snapped panels.
        # p=8 bottom-center: x=960=sw//2 → center confirmed from Classic_Black theme.
        _align_from_p = {
            0: 1,   # floating → compute below from x
            1: 1,   # right (E)
            2: 2,   # right-end
            3: 2,   # bottom-right
            4: 0,   # bottom-left
            5: 1,   # left
            6: 1,   # top (usually full-width)
            7: 0,   # top-left
            8: 1,   # bottom-center (x=sw//2 confirmed)
            9: 2,   # bottom-right
            10: 1,  # left/dock
            11: 1,  # left-center
            12: 1,  # bottom-center
        }
        try:
            scr = Gdk.Screen.get_default()
            sw, sh = scr.get_width(), scr.get_height()
            pos_coords = {}
            for part in self._old_pos_str.split(';'):
                if '=' in part:
                    k, v = part.split('=', 1)
                    try:
                        pos_coords[k] = int(v)
                    except ValueError:
                        pass
            edge_now = self._old_edge
            if edge_now in ('top', 'bottom'):
                ref = pos_coords.get('x', sw // 2)
                if ref < sw // 3:
                    align_idx = 0
                elif ref > 2 * sw // 3:
                    align_idx = 2
                else:
                    align_idx = 1
            else:
                ref = pos_coords.get('y', sh // 2)
                if ref < sh // 3:
                    align_idx = 0
                elif ref > 2 * sh // 3:
                    align_idx = 2
                else:
                    align_idx = 1
        except Exception:
            align_idx = _align_from_p.get(p_val, 1)
        self._old_align = align_idx
        self._align_combo.set_active(align_idx)

        mode = si(s.get('mode'), 0)
        self._mode_combo.set_active(max(0, min(2, mode)))

        self._size_spin.set_value(si(s.get('size'), 42))
        self._icon_spin.set_value(si(s.get('icon_sz'), 24))

        self._orig_length        = si(s.get('length'), 100)
        self._orig_length_adjust = s.get('length_adjust')
        self._length_spin.set_value(self._orig_length)

        la = s.get('length_adjust')
        self._auto_expand_switch.set_active(la == 'true')

        self._rows_spin.set_value(si(s.get('nrows'), 1))

        ah = si(s.get('autohide'), 0)
        self._autohide_combo.set_active(max(0, min(2, ah)))

        dark   = s.get('dark')
        locked = s.get('locked')
        self._dark_switch.set_active(dark == 'true' if dark else False)
        self._lock_switch.set_active(locked == 'true' if locked else False)

    def _fill_active(self, plugins: list):
        self._active_store.clear()
        for p in plugins:
            pb = _load_icon(p['icon'], ICON_SIZE)
            self._active_store.append([pb, p['name'], p['module'], p['id']])

    def _fill_available(self, plugins: list):
        self._avail_store.clear()
        for p in plugins:
            pb      = _load_icon(p['icon'], ICON_SIZE)
            comment = p.get('comment', '')
            markup  = f"<b>{GLib.markup_escape_text(p['name'])}</b>"
            if comment:
                markup += f"\n<span alpha='65%' size='small'>{GLib.markup_escape_text(comment)}</span>"
            self._avail_store.append([pb, p['name'], p['module'], comment, markup])

    def _filter_func(self, model, it, _data):
        q = self._search.get_text().lower()
        if not q:
            return True
        name = (model.get_value(it, 1) or '').lower()
        return q in name

    # ── Panel reload ──────────────────────────────────────────────────────────

    def _reload_worker(self):
        pk       = self._current_panel
        settings = _read_settings(pk)
        active   = _read_active_plugins(pk)
        GLib.idle_add(self._on_reload_done, settings, active)

    def _on_reload_done(self, settings, active):
        self._fill_settings(settings)
        self._fill_active(active)
        self.parent_window.hide_progress()
        return False

    # ── Active plugin list actions ────────────────────────────────────────────

    def _on_move_up(self, _btn):
        sel = self._active_view.get_selection()
        model, it = sel.get_selected()
        if not it:
            return
        path = model.get_path(it)
        if path[0] > 0:
            model.swap(model.get_iter(Gtk.TreePath(path[0] - 1)), it)
            self._apply_plugin_order()

    def _on_move_down(self, _btn):
        sel = self._active_view.get_selection()
        model, it = sel.get_selected()
        if not it:
            return
        nxt = model.iter_next(it)
        if nxt:
            model.swap(it, nxt)
            self._apply_plugin_order()

    def _apply_plugin_order(self):
        pk = self._current_panel
        new_order = [row[3] for row in self._active_store if row[3] != 0]
        def do_reorder():
            with self._panel_lock:
                _set_array(f'/panels/{pk}/plugin-ids', 'int', new_order)
                _panel_restart()
        threading.Thread(target=do_reorder, daemon=True).start()

    def _on_remove(self, _btn):
        sel = self._active_view.get_selection()
        model, it = sel.get_selected()
        if not it:
            return
        plugin_id = model.get_value(it, 3)
        pk = self._current_panel
        model.remove(it)
        def do_remove():
            with self._panel_lock:
                current_ids = _get_array(f'/panels/{pk}/plugin-ids')
                new_ids = [i for i in current_ids if i != plugin_id]
                _set_array(f'/panels/{pk}/plugin-ids', 'int', new_ids)
                if plugin_id != 0:
                    _remove(f'/plugins/plugin-{plugin_id}')
                _panel_restart()
        threading.Thread(target=do_remove, daemon=True).start()

    def _on_plugin_settings(self, _btn):
        sel = self._active_view.get_selection()
        model, it = sel.get_selected()
        if not it:
            return
        # XFCE 4.20 removed --plugin-event and exposes no public D-Bus API to open
        # a specific plugin's configure dialog from an external process. The Set signal
        # that triggers it is filtered by sender (must come from the panel process itself).
        # Best available option: open the panel preferences where the user can click the
        # plugin's settings button natively.
        try:
            panel_num = int(self._current_panel.split('-')[1])
        except Exception:
            panel_num = 1
        subprocess.Popen(
            ['xfce4-panel', f'--preferences={panel_num}'],
            start_new_session=True,
        )

    # ── Available plugin add ──────────────────────────────────────────────────

    def _on_add(self, _btn):
        sel = self._avail_view.get_selection()
        model, it = sel.get_selected()
        if not it:
            return
        self._add_plugin_from_iter(it)

    def _on_avail_row_activated(self, view, path, _column):
        it = self._avail_filter.get_iter(path)
        if it:
            self._add_plugin_from_iter(it)

    def _add_plugin_from_iter(self, filter_it):
        real_it = self._avail_filter.convert_iter_to_child_iter(filter_it)
        pb      = self._avail_store.get_value(real_it, 0)
        name    = self._avail_store.get_value(real_it, 1)
        module  = self._avail_store.get_value(real_it, 2)

        def do_add():
            try:
                with self._panel_lock:
                    pk = self._current_panel
                    all_ids = []
                    for pid in _panel_ids():
                        all_ids.extend(_get_array(f'/panels/panel-{pid}/plugin-ids'))
                    new_id = (max(all_ids) + 1) if all_ids else 1
                    logger.info(f"[ADD] module={module} panel={pk} new_id={new_id}")
                    _set(f'/plugins/plugin-{new_id}', 'string', module)
                    current_ids = _get_array(f'/panels/{pk}/plugin-ids')
                    _set_array(f'/panels/{pk}/plugin-ids', 'int', current_ids + [new_id])
                    logger.info(f"[ADD] xfconf written — restarting panel")
                    _panel_restart()
                def append_row():
                    self._active_store.append([pb, name, module, new_id])
                    return False
                GLib.idle_add(append_row)
            except Exception as e:
                logger.warning(f"[ADD] EXCEPTION: {e}")

        threading.Thread(target=do_add, daemon=True).start()

    # ── Apply ─────────────────────────────────────────────────────────────────

    def _on_apply(self, _btn):
        pk        = self._current_panel
        edge_idx  = self._pos_combo.get_active()
        edges     = ['top', 'bottom', 'left', 'right']
        edge      = edges[edge_idx] if 0 <= edge_idx < 4 else 'bottom'
        mode      = self._mode_combo.get_active()   # 0=horizontal, 1=vertical, 2=deskbar
        align     = self._align_combo.get_active()   # 0=left/top, 1=center, 2=right/bottom
        length_pct = int(self._length_spin.get_value())
        auto_expand = self._auto_expand_switch.get_active()

        edge_changed   = (edge       != getattr(self, '_old_edge', None))
        align_changed  = (align      != getattr(self, '_old_align', 1))
        length_changed = (length_pct != getattr(self, '_orig_length', length_pct))
        if edge_changed or align_changed or length_changed:
            pos_str = _build_position_string(edge, align, length_pct,
                                             int(self._size_spin.get_value()))
        else:
            pos_str = self._old_pos_str

        size      = int(self._size_spin.get_value())
        icon_sz   = int(self._icon_spin.get_value())
        length    = int(self._length_spin.get_value())
        nrows     = int(self._rows_spin.get_value())
        autohide  = self._autohide_combo.get_active()
        dark      = self._dark_switch.get_active()
        locked    = self._lock_switch.get_active()

        # Collect current active plugin list from the store
        active_plugins = [
            (row[2], row[3])   # (module, old_id)
            for row in self._active_store
        ]

        old_ids = _get_array(f'/panels/{pk}/plugin-ids')

        self.apply_btn.set_sensitive(False)
        self.parent_window.show_progress(_("Applying panel settings…"))

        def worker():
            logger.info(f"worker start: pk={pk} active_plugins={active_plugins} old_ids={old_ids}")
            ok = True
            ok &= _set(f'/panels/{pk}/position',          'string', pos_str)
            ok &= _set(f'/panels/{pk}/mode',               'uint',   str(mode))
            ok &= _set(f'/panels/{pk}/size',               'uint',   str(size))
            ok &= _set(f'/panels/{pk}/icon-size',          'uint',   str(icon_sz))
            ok &= _set(f'/panels/{pk}/length',             'double', str(float(length)))
            ok &= _set(f'/panels/{pk}/length-adjust',      'bool',   'true' if auto_expand else 'false')
            ok &= _set(f'/panels/{pk}/nrows',              'uint',   str(nrows))
            ok &= _set(f'/panels/{pk}/autohide-behavior',  'uint',   str(autohide))
            ok &= _set('/panels/dark-mode',                'bool',   'true' if dark else 'false')
            ok &= _set(f'/panels/{pk}/position-locked',    'bool',   'true' if locked else 'false')
            ok &= _set(f'/panels/{pk}/enable-struts',      'bool',   'true')

            new_ids = []
            for module, old_id in active_plugins:
                if old_id != 0:
                    new_ids.append(old_id)
                # id=0 entries were already written to xfconf in _on_add — skip here

            # Remove plugins that were deleted
            for pid in old_ids:
                if pid not in new_ids:
                    _remove(f'/plugins/plugin-{pid}')

            _set_array(f'/panels/{pk}/plugin-ids', 'int', new_ids)
            _panel_restart()

            la_str = 'true' if auto_expand else 'false'
            GLib.idle_add(self._on_apply_done, ok, pos_str, edge, length, la_str)

        threading.Thread(target=worker, daemon=True).start()

    # ── Add / Delete panel ────────────────────────────────────────────────────

    def _on_new_panel(self, _btn):
        self.apply_btn.set_sensitive(False)
        self.parent_window.show_progress(_("Adding panel…"))

        def worker():
            new_id = (max(self._panel_ids) + 1) if self._panel_ids else 2
            new_ids = sorted(self._panel_ids + [new_id])
            pk = f'panel-{new_id}'
            _set(f'/panels/{pk}/position',          'string', _build_position_string('top', 1, 100, 30))
            _set(f'/panels/{pk}/size',               'uint',   '30')
            _set(f'/panels/{pk}/icon-size',          'uint',   '22')
            _set(f'/panels/{pk}/length',             'double', '100.0')
            _set(f'/panels/{pk}/length-adjust',      'bool',   'true')
            _set(f'/panels/{pk}/nrows',              'uint',   '1')
            _set(f'/panels/{pk}/autohide-behavior',  'uint',   '0')
            _set(f'/panels/{pk}/position-locked',    'bool',   'false')
            _set(f'/panels/{pk}/enable-struts',      'bool',   'true')
            # Write the updated panel list last so xfce4-panel sees a complete config
            _set_array('/panels', 'int', new_ids)
            _panel_restart()
            GLib.idle_add(self._on_new_panel_done, new_id, new_ids)

        threading.Thread(target=worker, daemon=True).start()

    def _on_new_panel_done(self, new_id: int, new_ids: list):
        self._panel_ids = new_ids
        self._rebuild_panel_pills(new_ids, new_id)
        self._current_panel = f'panel-{new_id}'
        self._del_panel_btn.set_sensitive(True)
        pk       = self._current_panel
        settings = _read_settings(pk)
        active   = _read_active_plugins(pk)
        self._fill_settings(settings)
        self._fill_active(active)
        self.apply_btn.set_sensitive(True)
        self.parent_window.hide_progress()
        return False

    def _on_delete_panel(self, _btn):
        if len(self._panel_ids) <= 1:
            return
        pk = self._current_panel
        dialog = Gtk.MessageDialog(
            transient_for=self.parent_window, modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO,
            text=_("Delete {pk}?").format(pk=pk)
        )
        dialog.format_secondary_text(_("This will remove the panel and all its plugins."))
        response = dialog.run()
        dialog.destroy()
        if response != Gtk.ResponseType.YES:
            return

        panel_id = int(pk.split('-')[1])
        self.apply_btn.set_sensitive(False)
        self.parent_window.show_progress(_("Deleting panel…"))

        def worker():
            new_ids           = [i for i in self._panel_ids if i != panel_id]
            orphan_plugin_ids = _get_array(f'/panels/{pk}/plugin-ids')
            surviving_ids: set = set()
            for other_panel_id in new_ids:
                surviving_ids.update(_get_array(f'/panels/panel-{other_panel_id}/plugin-ids'))
            for pid in orphan_plugin_ids:
                if pid not in surviving_ids:
                    _remove(f'/plugins/plugin-{pid}')
            _remove(f'/panels/{pk}')
            _set_array('/panels', 'int', new_ids)
            _panel_restart()
            GLib.idle_add(self._on_delete_panel_done, panel_id, new_ids)

        threading.Thread(target=worker, daemon=True).start()

    def _on_delete_panel_done(self, panel_id: int, new_ids: list):
        self._panel_ids = new_ids
        self._rebuild_panel_pills(new_ids, new_ids[0])
        self._current_panel = f'panel-{new_ids[0]}'
        self._del_panel_btn.set_sensitive(len(new_ids) > 1)
        self.apply_btn.set_sensitive(True)
        self.parent_window.hide_progress()
        threading.Thread(target=self._reload_worker, daemon=True).start()
        return False

    def _on_apply_done(self, ok: bool, new_pos_str: str, new_edge: str, new_length: int, new_la: str):
        self.parent_window.hide_progress()
        self.apply_btn.set_sensitive(True)
        if ok:
            self._old_pos_str        = new_pos_str
            self._old_edge           = new_edge
            self._old_align          = self._align_combo.get_active()
            self._orig_length        = new_length
            self._orig_length_adjust = new_la
            # Reload active plugin list so all id=0 entries get real IDs (Bug 6)
            threading.Thread(target=self._reload_worker, daemon=True).start()
        else:
            dlg = Gtk.MessageDialog(
                transient_for=self.parent_window, modal=True,
                message_type=Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.OK,
                text=_("Some settings could not be applied.")
            )
            dlg.run()
            dlg.destroy()
        return False
