import gi
import struct
import threading
from pathlib import Path
from typing import Optional

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, GdkPixbuf

from core.i18n_manager import _
from services.icon_cursor_service import IconCursorService, ARCHIVE_SUFFIXES
from utils.logger import logger

PREVIEW_SIZE = 28

# Xcursor files to try, in order, when rendering a cursor theme's preview —
# these are the two conventional names for the plain arrow pointer.
_CURSOR_PREVIEW_NAMES = ('left_ptr', 'default')


class IconsCursorsTab(Gtk.Box):

    def __init__(self, config, parent_window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.config = config
        self.parent_window = parent_window
        self.service = IconCursorService()
        self._cols = {}   # kind -> {'listbox':.., 'status':.., 'active':..}

        self._loaded = False
        self._setup_ui()
        self.connect('map', self._on_mapped)

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self):
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        body.set_margin_start(16)
        body.set_margin_end(16)
        body.set_margin_top(12)
        body.set_margin_bottom(16)
        self.pack_start(body, True, True, 0)

        # Both cards fill the tab like every other tab does — only their
        # minimum height is fixed, so a maximized window lets them grow
        # instead of leaving a dead gap, and a short window still just
        # shrinks each list down to its own internal scrollbar.
        body.pack_start(
            self._build_card('icon', _("Icon Themes"), 'preferences-desktop-theme'),
            True, True, 0
        )
        body.pack_start(
            self._build_card('cursor', _("Cursor Themes"), 'input-mouse'),
            True, True, 0
        )

    def _build_card(self, kind: str, title: str, header_icon: str) -> Gtk.Box:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.get_style_context().add_class('theme-card')

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        header.set_margin_start(8)
        header.set_margin_top(8)
        header.pack_start(Gtk.Image.new_from_icon_name(header_icon, Gtk.IconSize.MENU), False, False, 0)
        title_lbl = Gtk.Label(label=title)
        title_lbl.get_style_context().add_class('theme-card-label')
        title_lbl.set_halign(Gtk.Align.START)
        header.pack_start(title_lbl, False, False, 0)
        status = Gtk.Label()
        status.get_style_context().add_class('dim-label')
        status.set_halign(Gtk.Align.END)
        header.pack_start(status, True, True, 0)
        card.pack_start(header, False, False, 0)

        # Horizontal row: scrollable list on the left, actions stacked on
        # the right — a wide card instead of a column that stretches down
        # the whole tab.
        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        content.set_margin_start(8)
        content.set_margin_end(8)
        content.set_margin_bottom(8)
        card.pack_start(content, True, True, 0)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_min_content_height(140)
        scrolled.get_style_context().add_class('docklike-preview-bar')
        content.pack_start(scrolled, True, True, 0)

        listbox = Gtk.ListBox()
        listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        scrolled.add(listbox)

        actions = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        actions.set_valign(Gtk.Align.START)
        content.pack_start(actions, False, False, 0)

        activate_btn = Gtk.Button()
        activate_inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        activate_inner.pack_start(Gtk.Image.new_from_icon_name('object-select-symbolic', Gtk.IconSize.BUTTON), False, False, 0)
        activate_inner.pack_start(Gtk.Label(label=_("Activate")), False, False, 0)
        activate_btn.add(activate_inner)
        activate_btn.get_style_context().add_class('suggested-action')
        activate_btn.connect('clicked', lambda b, k=kind: self._on_activate(k))
        actions.pack_start(activate_btn, False, False, 0)

        install_btn = Gtk.Button()
        install_inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        install_inner.pack_start(Gtk.Image.new_from_icon_name('list-add', Gtk.IconSize.BUTTON), False, False, 0)
        install_inner.pack_start(Gtk.Label(label=_("Install package…")), False, False, 0)
        install_btn.add(install_inner)
        install_btn.connect('clicked', lambda b, k=kind: self._on_install_package(k))
        actions.pack_start(install_btn, False, False, 0)

        self._cols[kind] = {'listbox': listbox, 'status': status, 'active': None}
        return card

    # ── Loading ───────────────────────────────────────────────────────────────

    def _on_mapped(self, _widget):
        if not self._loaded:
            self._loaded = True
            self._load_async()

    def _load_async(self):
        self.parent_window.show_progress(_("Reading installed themes…"))
        threading.Thread(target=self._load_worker, daemon=True).start()

    def _load_worker(self):
        icon_themes   = self.service.list_icon_themes()
        cursor_themes = self.service.list_cursor_themes()
        active_icon   = self.service.get_active_icon_theme()
        active_cursor = self.service.get_active_cursor_theme()

        for t in icon_themes:
            t['pixbuf'] = self._load_icon_theme_preview(t['name'])
        for t in cursor_themes:
            t['pixbuf'] = self._load_cursor_theme_preview(t['path'])

        GLib.idle_add(
            self._on_load_done, icon_themes, cursor_themes, active_icon, active_cursor
        )

    def _load_icon_theme_preview(self, theme_name: str) -> Optional[GdkPixbuf.Pixbuf]:
        try:
            it = Gtk.IconTheme.new()
            it.set_custom_theme(theme_name)
            info = it.lookup_icon('folder', PREVIEW_SIZE, 0)
            if info:
                return info.load_icon()
        except Exception:
            pass
        return None

    def _load_cursor_theme_preview(self, theme_path: str) -> Optional[GdkPixbuf.Pixbuf]:
        """Render the actual pointer bitmap from the theme's own Xcursor file.

        GTK has no API to read an arbitrary (non-active) cursor theme, so the
        Xcursor binary format is parsed directly: a small header + a table of
        images at different sizes, each stored as raw premultiplied ARGB32.
        """
        cursors_dir = Path(theme_path) / 'cursors'
        for name in _CURSOR_PREVIEW_NAMES:
            candidate = cursors_dir / name
            if candidate.is_file():
                pixbuf = self._parse_xcursor(candidate, PREVIEW_SIZE)
                if pixbuf:
                    if pixbuf.get_width() != PREVIEW_SIZE:
                        pixbuf = pixbuf.scale_simple(
                            PREVIEW_SIZE, PREVIEW_SIZE, GdkPixbuf.InterpType.BILINEAR
                        )
                    return pixbuf
        return None

    @staticmethod
    def _parse_xcursor(path: Path, target_size: int) -> Optional[GdkPixbuf.Pixbuf]:
        try:
            data = path.read_bytes()
            magic, header_size, _version, ntoc = struct.unpack_from('<4sIII', data, 0)
            if magic != b'Xcur':
                return None

            # Table of contents: pick the image entry whose nominal size is
            # closest to what we want to display.
            offset = header_size
            best = None
            for _ in range(ntoc):
                entry_type, subtype, position = struct.unpack_from('<III', data, offset)
                offset += 12
                if entry_type == 0xfffd0002:   # image chunk
                    if best is None or abs(subtype - target_size) < abs(best[0] - target_size):
                        best = (subtype, position)
            if best is None:
                return None

            _, pos = best
            (hsize, _typ, _subtype, _ver, width, height,
             _xhot, _yhot, _delay) = struct.unpack_from('<IIIIIIIII', data, pos)
            if not (0 < width <= 256 and 0 < height <= 256):
                return None

            pixels_off = pos + hsize
            raw = data[pixels_off:pixels_off + width * height * 4]
            if len(raw) < width * height * 4:
                return None

            # Xcursor pixels are premultiplied ARGB32 (native endian, so on
            # disk as little-endian bytes: B, G, R, A) — GdkPixbuf wants
            # straight (non-premultiplied) RGBA.
            out = bytearray(width * height * 4)
            for i in range(width * height):
                b, g, r, a = raw[i * 4], raw[i * 4 + 1], raw[i * 4 + 2], raw[i * 4 + 3]
                if a:
                    r = min(255, r * 255 // a)
                    g = min(255, g * 255 // a)
                    b = min(255, b * 255 // a)
                out[i * 4], out[i * 4 + 1], out[i * 4 + 2], out[i * 4 + 3] = r, g, b, a

            gbytes = GLib.Bytes.new(bytes(out))
            return GdkPixbuf.Pixbuf.new_from_bytes(
                gbytes, GdkPixbuf.Colorspace.RGB, True, 8, width, height, width * 4
            )
        except Exception:
            return None

    def _on_load_done(self, icon_themes, cursor_themes, active_icon, active_cursor):
        self._cols['icon']['active']   = active_icon
        self._cols['cursor']['active'] = active_cursor
        self._fill_column('icon', icon_themes, active_icon)
        self._fill_column('cursor', cursor_themes, active_cursor)
        self.parent_window.hide_progress()
        return False

    def _fill_column(self, kind: str, themes: list, active_name: Optional[str]):
        col = self._cols[kind]
        listbox = col['listbox']
        for row in list(listbox.get_children()):
            listbox.remove(row)

        for t in themes:
            is_active = (t['name'] == active_name)
            row = self._make_row(
                t['display_name'], is_active,
                pixbuf=t.get('pixbuf'),
                fallback_icon='input-mouse' if kind == 'cursor' else 'image-x-generic',
            )
            row.theme_name = t['name']
            listbox.add(row)
            if is_active:
                listbox.select_row(row)
        listbox.show_all()

        col['status'].set_text(
            _("{n} installed — active: {active}").format(
                n=len(themes), active=active_name or _("none")
            )
        )

    def _make_row(self, display_name: str, is_active: bool,
                  pixbuf=None, fallback_icon: str = 'image-x-generic') -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_margin_start(8)
        box.set_margin_end(8)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        row.add(box)

        img = Gtk.Image()
        if pixbuf:
            img.set_from_pixbuf(pixbuf)
        else:
            img.set_from_icon_name(fallback_icon, Gtk.IconSize.LARGE_TOOLBAR)
        box.pack_start(img, False, False, 0)

        lbl = Gtk.Label()
        lbl.set_halign(Gtk.Align.START)
        if is_active:
            lbl.set_markup(f"<b>{GLib.markup_escape_text(display_name)}</b>")
        else:
            lbl.set_text(display_name)
        box.pack_start(lbl, True, True, 0)

        if is_active:
            chk = Gtk.Image.new_from_icon_name('object-select-symbolic', Gtk.IconSize.MENU)
            chk.set_tooltip_text(_("Currently active"))
            box.pack_start(chk, False, False, 0)

        return row

    # ── Activate ─────────────────────────────────────────────────────────────

    def _on_activate(self, kind: str):
        listbox = self._cols[kind]['listbox']
        row = listbox.get_selected_row()
        if not row:
            return
        name = row.theme_name
        self.parent_window.show_progress(_("Activating…"))

        def worker():
            if kind == 'icon':
                ok = self.service.set_active_icon_theme(name)
            else:
                ok = self.service.set_active_cursor_theme(name)
            GLib.idle_add(self._on_activate_done, ok)

        threading.Thread(target=worker, daemon=True).start()

    def _on_activate_done(self, ok: bool):
        if not ok:
            self.parent_window.hide_progress()
            self._show_info(_("Error activating theme."))
            return
        self._load_async()
        return False

    # ── Install package ─────────────────────────────────────────────────────

    def _on_install_package(self, kind: str):
        dialog = Gtk.FileChooserDialog(
            title=_("Select a package to install"),
            parent=self.parent_window,
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN,   Gtk.ResponseType.OK,
        )

        pkg_filter = Gtk.FileFilter()
        pkg_filter.set_name(_("Icon/cursor packages (.tar.gz, .tar.xz, .zip…)"))
        for ext in ARCHIVE_SUFFIXES:
            pkg_filter.add_pattern(f'*{ext}')
        dialog.add_filter(pkg_filter)

        response = dialog.run()
        path = dialog.get_filename() if response == Gtk.ResponseType.OK else None
        dialog.destroy()
        if not path:
            return

        self.parent_window.show_progress(_("Reading package…"))

        def worker():
            tmp_dir, candidates = self.service.extract_package(path)
            GLib.idle_add(self._on_extract_done, tmp_dir, candidates)

        threading.Thread(target=worker, daemon=True).start()

    def _on_extract_done(self, tmp_dir: Optional[Path], candidates: list):
        self.parent_window.hide_progress()

        if not candidates:
            self.service.cleanup(tmp_dir)
            self._show_info(_(
                "No installable icon or cursor theme was found in this package.\n\n"
                "Some packages only ship source files and need their own install "
                "script to be built, which Theme Manager does not run for safety "
                "reasons — install those manually."
            ))
            return

        chosen = self._ask_candidates(candidates)
        if not chosen:
            self.service.cleanup(tmp_dir)
            return

        scope = self._ask_install_scope()
        if scope is None:
            self.service.cleanup(tmp_dir)
            return

        self.parent_window.show_progress(_("Installing…"))

        def worker():
            ok, skipped = self.service.install_candidates(chosen, system=(scope == 'global'))
            self.service.cleanup(tmp_dir)
            GLib.idle_add(self._on_install_done, ok, skipped)

        threading.Thread(target=worker, daemon=True).start()

    def _ask_candidates(self, candidates: list) -> Optional[list]:
        dialog = Gtk.Dialog(
            title=_("Themes found in this package"),
            parent=self.parent_window,
            modal=True,
            destroy_with_parent=True,
        )
        dialog.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        install_btn = dialog.add_button(_("Install selected"), Gtk.ResponseType.OK)
        install_btn.get_style_context().add_class('suggested-action')
        dialog.set_default_size(420, -1)

        area = dialog.get_content_area()
        area.set_spacing(8)
        area.set_margin_start(16)
        area.set_margin_end(16)
        area.set_margin_top(16)
        area.set_margin_bottom(8)

        hint = Gtk.Label(label=_("This package contains {n} theme(s). Choose which to install:").format(n=len(candidates)))
        hint.set_line_wrap(True)
        hint.set_halign(Gtk.Align.START)
        area.pack_start(hint, False, False, 0)

        checks = []
        for c in candidates:
            kind_label = _("Icon theme") if c['kind'] == 'icon' else _("Cursor theme")
            check = Gtk.CheckButton(label=f"{c['display_name']}  —  {kind_label}")
            check.set_active(True)
            area.pack_start(check, False, False, 0)
            checks.append((check, c))

        dialog.show_all()
        response = dialog.run()
        selected = [c for check, c in checks if check.get_active()] if response == Gtk.ResponseType.OK else []
        dialog.destroy()
        return selected or None

    def _ask_install_scope(self) -> Optional[str]:
        dialog = Gtk.Dialog(
            title=_("Installation scope"),
            parent=self.parent_window,
            modal=True,
            destroy_with_parent=True,
        )
        dialog.add_button(_("Cancel"),           Gtk.ResponseType.CANCEL)
        dialog.add_button(_("Current user"),     Gtk.ResponseType.ACCEPT)
        btn_global = dialog.add_button(_("Global (recommended)"), Gtk.ResponseType.OK)
        btn_global.get_style_context().add_class('suggested-action')
        dialog.set_default_size(380, -1)

        area = dialog.get_content_area()
        area.set_spacing(8)
        area.set_margin_start(16)
        area.set_margin_end(16)
        area.set_margin_top(16)
        area.set_margin_bottom(8)
        area.pack_start(
            Gtk.Label(label=_("Where should the theme(s) be installed?")),
            False, False, 0
        )
        dialog.show_all()
        response = dialog.run()
        dialog.destroy()

        if response == Gtk.ResponseType.OK:
            return 'global'
        if response == Gtk.ResponseType.ACCEPT:
            return 'user'
        return None

    def _on_install_done(self, ok: bool, skipped: list):
        self.parent_window.hide_progress()
        if ok:
            if skipped:
                self._show_info(_(
                    "Installed. These were already present and left untouched: {names}"
                ).format(names=", ".join(skipped)))
            self._loaded = True
            self._load_async()
        else:
            self._show_info(_("Error installing the package."))

    def _show_info(self, message: str):
        dialog = Gtk.MessageDialog(
            parent=self.parent_window,
            modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=message,
        )
        dialog.run()
        dialog.destroy()
