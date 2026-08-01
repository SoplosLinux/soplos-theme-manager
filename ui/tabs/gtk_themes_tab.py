import gi
import threading
from pathlib import Path
from typing import Optional

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

from core.i18n_manager import _
from services.gtk_theme_service import GtkThemeService, ARCHIVE_SUFFIXES
from utils.logger import logger


class GtkThemesTab(Gtk.Box):

    def __init__(self, config, parent_window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.config = config
        self.parent_window = parent_window
        self.service = GtkThemeService()
        self._listbox: Optional[Gtk.ListBox] = None
        self._status: Optional[Gtk.Label] = None

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

        # The card fills the tab like every other tab does (Panel's plugin
        # list, Dock's app lists) instead of sitting at a fixed height —
        # only its minimum is fixed, so it still degrades to an internal
        # scrollbar on a short window rather than forcing the window to grow.
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.get_style_context().add_class('theme-card')
        body.pack_start(card, True, True, 0)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        header.set_margin_start(8)
        header.set_margin_top(8)
        header.pack_start(Gtk.Image.new_from_icon_name('preferences-desktop-theme', Gtk.IconSize.MENU), False, False, 0)
        title_lbl = Gtk.Label(label=_("GTK Themes"))
        title_lbl.get_style_context().add_class('theme-card-label')
        title_lbl.set_halign(Gtk.Align.START)
        header.pack_start(title_lbl, False, False, 0)
        self._status = Gtk.Label()
        self._status.get_style_context().add_class('dim-label')
        self._status.set_halign(Gtk.Align.END)
        header.pack_start(self._status, True, True, 0)
        card.pack_start(header, False, False, 0)

        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        content.set_margin_start(8)
        content.set_margin_end(8)
        content.set_margin_bottom(8)
        card.pack_start(content, True, True, 0)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_min_content_height(180)
        scrolled.get_style_context().add_class('docklike-preview-bar')
        content.pack_start(scrolled, True, True, 0)

        self._listbox = Gtk.ListBox()
        self._listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        scrolled.add(self._listbox)

        actions = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        actions.set_valign(Gtk.Align.START)
        content.pack_start(actions, False, False, 0)

        activate_btn = Gtk.Button()
        activate_inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        activate_inner.pack_start(Gtk.Image.new_from_icon_name('object-select-symbolic', Gtk.IconSize.BUTTON), False, False, 0)
        activate_inner.pack_start(Gtk.Label(label=_("Activate")), False, False, 0)
        activate_btn.add(activate_inner)
        activate_btn.get_style_context().add_class('suggested-action')
        activate_btn.connect('clicked', self._on_activate)
        actions.pack_start(activate_btn, False, False, 0)

        install_btn = Gtk.Button()
        install_inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        install_inner.pack_start(Gtk.Image.new_from_icon_name('list-add', Gtk.IconSize.BUTTON), False, False, 0)
        install_inner.pack_start(Gtk.Label(label=_("Install package…")), False, False, 0)
        install_btn.add(install_inner)
        install_btn.connect('clicked', self._on_install_package)
        actions.pack_start(install_btn, False, False, 0)

        hint = Gtk.Label(label=_("Some themes also ship matching window-border colors — those are applied automatically together."))
        hint.set_line_wrap(True)
        hint.set_max_width_chars(28)
        hint.get_style_context().add_class('dim-label')
        actions.pack_start(hint, False, False, 0)

    # ── Loading ───────────────────────────────────────────────────────────────

    def _on_mapped(self, _widget):
        if not self._loaded:
            self._loaded = True
            self._load_async()

    def _load_async(self):
        self.parent_window.show_progress(_("Reading installed GTK themes…"))
        threading.Thread(target=self._load_worker, daemon=True).start()

    def _load_worker(self):
        themes = self.service.list_gtk_themes()
        active = self.service.get_active_gtk_theme()
        GLib.idle_add(self._on_load_done, themes, active)

    def _on_load_done(self, themes: list, active: Optional[str]):
        for row in list(self._listbox.get_children()):
            self._listbox.remove(row)

        for t in themes:
            is_active = (t['name'] == active)
            row = self._make_row(t['display_name'], is_active)
            row.theme_name = t['name']
            self._listbox.add(row)
            if is_active:
                self._listbox.select_row(row)
        self._listbox.show_all()

        self._status.set_text(
            _("{n} installed — active: {active}").format(n=len(themes), active=active or _("none"))
        )
        self.parent_window.hide_progress()
        return False

    def _make_row(self, display_name: str, is_active: bool) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_margin_start(8)
        box.set_margin_end(8)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        row.add(box)

        img = Gtk.Image.new_from_icon_name('preferences-desktop-theme', Gtk.IconSize.LARGE_TOOLBAR)
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

    def _on_activate(self, _btn):
        row = self._listbox.get_selected_row()
        if not row:
            return
        name = row.theme_name
        self.parent_window.show_progress(_("Activating…"))

        def worker():
            ok = self.service.set_active_gtk_theme(name)
            GLib.idle_add(self._on_activate_done, ok)

        threading.Thread(target=worker, daemon=True).start()

    def _on_activate_done(self, ok: bool):
        if not ok:
            self.parent_window.hide_progress()
            self._show_info(_("Error activating theme."))
            return
        # Update this app's own dark/light look immediately instead of only
        # on next launch, since we're the ones who just changed the active
        # GTK theme.
        app = getattr(self.parent_window, 'application', None)
        if app is not None and hasattr(app, 'reapply_css'):
            app.reapply_css()
        self._load_async()
        return False

    # ── Install package ─────────────────────────────────────────────────────

    def _on_install_package(self, _btn):
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
        pkg_filter.set_name(_("GTK theme packages (.tar.gz, .tar.xz, .zip…)"))
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
                "No installable GTK theme was found in this package.\n\n"
                "Some packages only ship source files and need their own "
                "install script to be built, which Theme Manager does not "
                "run for safety reasons — install those manually."
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
            suffix = _(" (includes window border)") if c.get('has_xfwm4') else ""
            check = Gtk.CheckButton(label=f"{c['display_name']}{suffix}")
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
