import gi
import threading
from pathlib import Path
from typing import Optional, Dict, Any

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, GdkPixbuf, Pango

from core.i18n_manager import _
from services.xfce_theme_service import XfceThemeService
from services.screenshot_service import ScreenshotService
from services.theme_export_service import ThemeExportService
from utils.constants import (
    CARD_WIDTH, CARD_HEIGHT, PREVIEW_WIDTH, PREVIEW_HEIGHT,
    THEME_BUNDLE_EXT, APPLICATION_ID
)
from utils.logger import logger


class ThemeCard(Gtk.Button):

    def __init__(self, theme_info: Dict[str, Any]):
        super().__init__()
        self.theme_info = theme_info
        self.set_relief(Gtk.ReliefStyle.NONE)
        self.get_style_context().add_class('theme-card')
        self.set_size_request(CARD_WIDTH, CARD_HEIGHT)
        self.connect('clicked', self._on_clicked)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.add(vbox)

        img_box = Gtk.Box()
        img_box.set_halign(Gtk.Align.CENTER)
        img_box.set_valign(Gtk.Align.CENTER)
        img_box.get_style_context().add_class('theme-preview-box')
        img_box.set_size_request(PREVIEW_WIDTH, PREVIEW_HEIGHT)
        vbox.pack_start(img_box, True, True, 0)

        preview_path = theme_info.get('preview_path') or theme_info.get('thumbnail_path')
        if preview_path and Path(preview_path).exists():
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    preview_path, PREVIEW_WIDTH, PREVIEW_HEIGHT, True
                )
                img_box.add(Gtk.Image.new_from_pixbuf(pixbuf))
            except Exception:
                img_box.add(Gtk.Image.new_from_icon_name('preferences-desktop-theme', Gtk.IconSize.DIALOG))
        else:
            img_box.add(Gtk.Image.new_from_icon_name('preferences-desktop-theme', Gtk.IconSize.DIALOG))

        label = Gtk.Label(label=theme_info['name'])
        label.get_style_context().add_class('theme-card-label')
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_max_width_chars(15)
        label.set_halign(Gtk.Align.CENTER)
        vbox.pack_start(label, False, False, 0)

        self.show_all()

    def _on_clicked(self, btn):
        parent = self.get_parent()
        if isinstance(parent, Gtk.FlowBoxChild):
            flowbox = parent.get_parent()
            flowbox.select_child(parent)
            flowbox.emit('child-activated', parent)

    def set_selected(self, selected: bool):
        ctx = self.get_style_context()
        if selected:
            ctx.add_class('theme-card-selected')
        else:
            ctx.remove_class('theme-card-selected')


class ThemesTab(Gtk.Box):

    def __init__(self, config, parent_window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.config = config
        self.parent_window = parent_window
        self.selected_card: Optional[ThemeCard] = None
        self.theme_service = XfceThemeService()
        self.screenshot_service = ScreenshotService()
        self.export_service = ThemeExportService()

        self._setup_ui()
        self._load_themes_async()

    def _setup_ui(self):
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.get_style_context().add_class('soplos-content')
        self.pack_start(scrolled, True, True, 0)

        self.flowbox = Gtk.FlowBox()
        self.flowbox.set_valign(Gtk.Align.START)
        self.flowbox.set_max_children_per_line(20)
        self.flowbox.set_min_children_per_line(1)
        self.flowbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.flowbox.set_homogeneous(True)
        self.flowbox.set_row_spacing(20)
        self.flowbox.set_column_spacing(20)
        self.flowbox.set_margin_top(20)
        self.flowbox.set_margin_bottom(20)
        self.flowbox.set_margin_start(20)
        self.flowbox.set_margin_end(20)
        self.flowbox.connect('child-activated', self._on_card_activated)
        scrolled.add(self.flowbox)

        # Barra de acciones
        actions_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        actions_box.set_halign(Gtk.Align.CENTER)
        actions_box.set_margin_top(12)
        actions_box.set_margin_bottom(10)
        self.pack_start(actions_box, False, False, 0)

        def btn(label, icon, cb, css_class='soplos-button-secondary'):
            b = Gtk.Button()
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            box.set_margin_start(4)
            box.set_margin_end(4)
            box.pack_start(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.BUTTON), False, False, 0)
            box.pack_start(Gtk.Label(label=label), False, False, 0)
            b.add(box)
            b.get_style_context().add_class(css_class)
            b.connect('clicked', cb)
            return b

        actions_box.pack_start(btn(_("Apply"),   'preferences-desktop-theme', self._on_apply,   'suggested-action'), False, False, 0)
        actions_box.pack_start(btn(_("New"),      'document-new',              self._on_new), False, False, 0)
        actions_box.pack_start(btn(_("Remove"),   'edit-delete',               self._on_remove,  'destructive-action'), False, False, 0)

        sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep.set_margin_start(5)
        sep.set_margin_end(5)
        actions_box.pack_start(sep, False, False, 0)

        actions_box.pack_start(btn(_("Export ↑"), 'document-save-as',          self._on_export), False, False, 0)
        actions_box.pack_start(btn(_("Install ↓"),'document-open',             self._on_install), False, False, 0)
        actions_box.pack_start(btn(_("Refresh"),  'view-refresh',              lambda w: self._load_themes_async()), False, False, 0)


    def _load_themes_async(self):
        self.parent_window.show_progress(_("Loading themes…"))
        def worker():
            themes = self.theme_service.get_available_themes()
            GLib.idle_add(self._fill_gallery, themes)
        threading.Thread(target=worker, daemon=True).start()

    def _fill_gallery(self, themes):
        for child in self.flowbox.get_children():
            self.flowbox.remove(child)
        self.selected_card = None
        for theme in themes:
            self.flowbox.add(ThemeCard(theme))
        self.flowbox.show_all()
        self.parent_window.hide_progress()
        if hasattr(self.parent_window, 'set_status'):
            self.parent_window.set_status(_("{n} themes available").format(n=len(themes)))

    def _on_card_activated(self, flowbox, child):
        flowbox.select_child(child)
        if self.selected_card:
            self.selected_card.set_selected(False)
        self.selected_card = child.get_child()
        self.selected_card.set_selected(True)

    def _on_apply(self, btn):
        if not self.selected_card:
            self._show_info(_("Select a theme first"))
            return
        name = self.selected_card.theme_info['name']

        self.parent_window.show_progress(_("Applying {name}…").format(name=name))
        def progress_cb(f):
            GLib.idle_add(self.parent_window.progress_bar.set_fraction, f)
        def worker():
            ok = self.theme_service.apply_theme(name, progress_callback=progress_cb)
            GLib.idle_add(self._on_apply_done, ok, name)
        threading.Thread(target=worker, daemon=True).start()

    def _on_apply_done(self, ok, name):
        if ok:
            self.parent_window.hide_progress()
            if hasattr(self.parent_window, 'set_status'):
                self.parent_window.set_status(_("Applied: {name}").format(name=name))
        else:
            self.parent_window.show_progress(_("Error applying theme"), fraction=0.0)

    def _on_new(self, btn):
        dialog = Gtk.Dialog(
            title=_("Save Current Theme"),
            parent=self.parent_window,
            modal=True,
            destroy_with_parent=True
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_SAVE,   Gtk.ResponseType.OK
        )
        dialog.set_default_size(340, -1)

        content = dialog.get_content_area()
        content.set_spacing(12)
        content.set_margin_start(16)
        content.set_margin_end(16)
        content.set_margin_top(16)
        content.set_margin_bottom(8)

        content.pack_start(Gtk.Label(label=_("Theme name:")), False, False, 0)
        entry = Gtk.Entry()
        entry.set_placeholder_text(_("My Theme"))
        content.pack_start(entry, False, False, 0)

        screenshot_check = Gtk.CheckButton(label=_("Take screenshot for preview"))
        screenshot_check.set_active(True)
        content.pack_start(screenshot_check, False, False, 0)

        dialog.show_all()
        response = dialog.run()
        theme_name = entry.get_text().strip()
        take_screenshot = screenshot_check.get_active()
        dialog.destroy()

        if response != Gtk.ResponseType.OK or not theme_name:
            return

        self.parent_window.show_progress(_("Saving theme…"))

        def worker():
            from utils.constants import USER_THEMES_DIR
            ok = self.theme_service.save_current_as_theme(theme_name)
            if ok and take_screenshot:
                theme_dir = USER_THEMES_DIR / theme_name
                GLib.idle_add(self._take_screenshots_then_refresh, theme_dir)
            else:
                GLib.idle_add(self._on_save_done, ok, theme_name)

        threading.Thread(target=worker, daemon=True).start()

    def _take_screenshots_then_refresh(self, theme_dir):
        self.parent_window.show_progress(_("Taking screenshot…"))
        self.parent_window.iconify()
        def worker():
            def progress_cb(f):
                GLib.idle_add(self.parent_window.progress_bar.set_fraction, f)
            ok = self.screenshot_service.take_theme_screenshots(theme_dir, delay=3, progress_callback=progress_cb)
            GLib.idle_add(self.parent_window.deiconify)
            GLib.idle_add(self._on_save_done, ok, theme_dir.name)
        threading.Thread(target=worker, daemon=True).start()

    def _on_save_done(self, ok, name):
        if ok:
            self._load_themes_async()
        else:
            self.parent_window.show_progress(_("Error saving theme"), fraction=0.0)

    def _on_remove(self, btn):
        if not self.selected_card:
            self._show_info(_("Select a theme first"))
            return
        name = self.selected_card.theme_info['name']

        dialog = Gtk.MessageDialog(
            parent=self.parent_window,
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO,
            text=_("Remove theme?")
        )
        dialog.format_secondary_text(
            _("'{name}' will be permanently deleted.").format(name=name)
        )
        response = dialog.run()
        dialog.destroy()

        if response != Gtk.ResponseType.YES:
            return

        ok = self.theme_service.remove_theme(name)
        if ok:
            self._load_themes_async()
        else:
            self.parent_window.show_progress(_("Error removing theme"), fraction=0.0)

    def _on_export(self, btn):
        if not self.selected_card:
            self._show_info(_("Select a theme first"))
            return
        name = self.selected_card.theme_info['name']

        dialog = Gtk.FileChooserDialog(
            title=_("Export Theme"),
            parent=self.parent_window,
            action=Gtk.FileChooserAction.SAVE
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_SAVE,   Gtk.ResponseType.OK
        )
        dialog.set_current_name(f"{name}{THEME_BUNDLE_EXT}")
        dialog.set_current_folder(str(Path.home()))

        filt = Gtk.FileFilter()
        filt.set_name(_("Soplos Theme Bundle (*.sth)"))
        filt.add_pattern("*.sth")
        dialog.add_filter(filt)

        if dialog.run() == Gtk.ResponseType.OK:
            dest_path = dialog.get_filename()
            dialog.destroy()
            self.parent_window.show_progress(_("Exporting {name}…").format(name=name))
            def progress_cb(f):
                GLib.idle_add(self.parent_window.progress_bar.set_fraction, f)
            def worker():
                ok, msg = self.export_service.export_theme(name, dest_path, progress_callback=progress_cb)
                if ok:
                    GLib.idle_add(self.parent_window.hide_progress)
                else:
                    GLib.idle_add(self.parent_window.show_progress,
                                  _("Export error: {e}").format(e=msg), 0.0)
            threading.Thread(target=worker, daemon=True).start()
        else:
            dialog.destroy()

    def _on_install(self, btn):
        dialog = Gtk.FileChooserDialog(
            title=_("Install Theme"),
            parent=self.parent_window,
            action=Gtk.FileChooserAction.OPEN
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN,   Gtk.ResponseType.OK
        )
        filt = Gtk.FileFilter()
        filt.set_name(_("Soplos Theme Bundle (*.sth)"))
        filt.add_pattern("*.sth")
        dialog.add_filter(filt)

        if dialog.run() != Gtk.ResponseType.OK:
            dialog.destroy()
            return

        bundle_path = dialog.get_filename()
        dialog.destroy()

        scope = self._ask_install_scope()
        if scope is None:
            return

        self.parent_window.show_progress(_("Installing theme…"))
        def progress_cb(f):
            GLib.idle_add(self.parent_window.progress_bar.set_fraction, f)
        def worker():
            ok, result = self.export_service.import_theme(bundle_path, scope=scope, progress_callback=progress_cb)
            GLib.idle_add(self._on_install_done, ok, result)
        threading.Thread(target=worker, daemon=True).start()

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
        btn_global.get_style_context().add_class("suggested-action")
        dialog.set_default_size(380, -1)

        area = dialog.get_content_area()
        area.set_spacing(8)
        area.set_margin_start(16)
        area.set_margin_end(16)
        area.set_margin_top(16)
        area.set_margin_bottom(8)
        area.pack_start(
            Gtk.Label(label=_("Where should the theme assets be installed?")),
            False, False, 0
        )
        dialog.show_all()
        response = dialog.run()
        dialog.destroy()

        if response == Gtk.ResponseType.OK:
            return "global"
        if response == Gtk.ResponseType.ACCEPT:
            return "user"
        return None

    def _on_install_done(self, ok, result):
        if ok:
            self._load_themes_async()
        else:
            self.parent_window.show_progress(_("Install error: {e}").format(e=result), fraction=0.0)

    def _show_info(self, message: str):
        dialog = Gtk.MessageDialog(
            parent=self.parent_window,
            modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=message
        )
        dialog.run()
        dialog.destroy()
