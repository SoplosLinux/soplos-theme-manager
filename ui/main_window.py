import gi
import threading
from pathlib import Path

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf, Pango

from core.i18n_manager import _
from config.settings import Config
from utils.constants import (
    APPLICATION_NAME, APPLICATION_VERSION, APPLICATION_ID,
    WINDOW_DEFAULT_WIDTH, WINDOW_DEFAULT_HEIGHT
)
from utils.logger import logger


class ThemeManagerWindow(Gtk.ApplicationWindow):

    def __init__(self, application, config: Config):
        super().__init__(application=application)
        self.application = application
        self.config = config

        self.set_title(_(APPLICATION_NAME))
        self.set_default_size(WINDOW_DEFAULT_WIDTH, WINDOW_DEFAULT_HEIGHT)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_resizable(True)
        self.get_style_context().add_class('soplos-window')
        self.get_style_context().add_class('soplos-welcome-window')

        self._pulse_timeout = None
        self._setup_ui()
        self._setup_shortcuts()
        self.show_all()
        self.notebook.set_current_page(0)
        GLib.idle_add(self._ensure_first_tab)

    def _setup_ui(self):
        main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(main_vbox)

        self.notebook = Gtk.Notebook()
        self.notebook.set_tab_pos(Gtk.PositionType.TOP)
        main_vbox.pack_start(self.notebook, True, True, 0)

        self._create_progress_bar(main_vbox)
        self._create_footer(main_vbox)
        self._create_tabs()

    def _create_tabs(self):
        tabs = [
            ('themes',        _("Themes"),           'preferences-desktop-theme'),
            ('wallpapers',    _("Wallpapers"),        'preferences-desktop-wallpaper'),
            ('gtk_themes',    _("GTK Themes"),        'preferences-desktop-theme'),
            ('icons_cursors', _("Icons & Cursors"),   'preferences-desktop-icons'),
            ('panel',         _("Panel"),             'preferences-system'),
            ('docklike',      _("Dock"),              'preferences-desktop'),
            ('lightdm',       _("Login Screen"),      'system-lock-screen'),
        ]

        self.tabs = {}
        for tab_id, tab_label, tab_icon in tabs:
            try:
                tab_content = self._load_tab(tab_id)
                if tab_content is None:
                    continue

                label_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                icon = Gtk.Image.new_from_icon_name(tab_icon, Gtk.IconSize.MENU)
                label = Gtk.Label(label=tab_label)
                label_box.pack_start(icon, False, False, 0)
                label_box.pack_start(label, False, False, 0)
                label_box.show_all()

                page_index = self.notebook.append_page(tab_content, label_box)
                self.tabs[tab_id] = (page_index, tab_content)
            except Exception as e:
                logger.error(f"Error loading tab '{tab_id}': {e}", exc_info=True)

    def open_theme_bundle(self, bundle_path: str):
        """Switch to the Themes tab and start installing bundle_path.

        Used when a .sth file is opened from a file manager (see
        core/application.py's do_open) — activation routes here whether the
        app was just started or was already running.
        """
        entry = self.tabs.get('themes')
        if not entry:
            return
        page_index, themes_tab = entry
        self.notebook.set_current_page(page_index)
        self.present()
        themes_tab.install_bundle_path(bundle_path)

    def _load_tab(self, tab_id: str):
        if tab_id == 'themes':
            from ui.tabs.themes_tab import ThemesTab
            return ThemesTab(config=self.config, parent_window=self)
        elif tab_id == 'wallpapers':
            from ui.tabs.wallpapers_tab import WallpapersTab
            return WallpapersTab(config=self.config, parent_window=self)
        elif tab_id == 'gtk_themes':
            from ui.tabs.gtk_themes_tab import GtkThemesTab
            return GtkThemesTab(config=self.config, parent_window=self)
        elif tab_id == 'icons_cursors':
            from ui.tabs.icons_cursors_tab import IconsCursorsTab
            return IconsCursorsTab(config=self.config, parent_window=self)
        elif tab_id == 'panel':
            from ui.tabs.panel_tab import PanelTab
            return PanelTab(config=self.config, parent_window=self)
        elif tab_id == 'docklike':
            from ui.tabs.docklike_tab import DocklikeTab
            return DocklikeTab(config=self.config, parent_window=self)
        elif tab_id == 'lightdm':
            from ui.tabs.lightdm_tab import LightdmTab
            return LightdmTab(config=self.config, parent_window=self)
        return None

    def _create_progress_bar(self, parent):
        self.progress_revealer = Gtk.Revealer()
        self.progress_revealer.set_transition_type(Gtk.RevealerTransitionType.NONE)

        progress_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        progress_box.set_margin_start(20)
        progress_box.set_margin_end(20)
        progress_box.set_margin_bottom(10)

        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_show_text(True)
        progress_box.pack_start(self.progress_bar, False, False, 0)

        self.progress_msg_label = Gtk.Label()
        self.progress_msg_label.get_style_context().add_class('dim-label')
        progress_box.pack_start(self.progress_msg_label, False, False, 0)

        self.progress_revealer.add(progress_box)
        self.progress_revealer.set_reveal_child(False)
        parent.pack_end(self.progress_revealer, False, True, 0)

    def show_progress(self, message: str, fraction=None):
        """Show the footer progress bar. Pass fraction=None for pulse mode."""
        if self._pulse_timeout:
            GLib.source_remove(self._pulse_timeout)
            self._pulse_timeout = None

        self.progress_msg_label.set_text(message)

        if fraction is not None:
            self.progress_bar.set_fraction(fraction)
            self.progress_bar.set_text(f"{int(fraction * 100)}%")
        else:
            self.progress_bar.pulse()
            self.progress_bar.set_text(_("Working…"))
            self._pulse_timeout = GLib.timeout_add(120, self._do_pulse)

        self.progress_revealer.set_reveal_child(True)

    def hide_progress(self):
        """Hide the footer progress bar."""
        if self._pulse_timeout:
            GLib.source_remove(self._pulse_timeout)
            self._pulse_timeout = None
        self.progress_revealer.set_reveal_child(False)
        self.progress_bar.set_fraction(0.0)
        self.progress_bar.set_text("")
        self.progress_msg_label.set_text("")

    def _do_pulse(self):
        self.progress_bar.pulse()
        return True

    def _create_footer(self, parent):
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        footer.set_margin_start(15)
        footer.set_margin_end(15)
        footer.set_margin_top(6)
        footer.set_margin_bottom(6)
        parent.pack_end(footer, False, False, 0)

        self.status_label = Gtk.Label(label=_("Soplos Linux Tyron — XFCE"))
        self.status_label.set_halign(Gtk.Align.START)
        self.status_label.get_style_context().add_class('dim-label')
        footer.pack_start(self.status_label, False, False, 0)

        version_label = Gtk.Label(label=f"v{APPLICATION_VERSION}")
        version_label.get_style_context().add_class('dim-label')
        footer.pack_end(version_label, False, False, 0)

    def _setup_shortcuts(self):
        accel_group = Gtk.AccelGroup()
        self.add_accel_group(accel_group)

        def add_shortcut(accel, callback):
            keyval, mod = Gtk.accelerator_parse(accel)
            accel_group.connect(keyval, mod, Gtk.AccelFlags.VISIBLE,
                                lambda *a: callback())

        add_shortcut('<Control>q', self.application.quit)
        add_shortcut('F1', self._show_about)

        # Ctrl+Tab / Ctrl+Shift+Tab — tab switching via key-press-event because
        # GTK intercepts these inside child widgets before AccelGroup fires.
        self.connect('key-press-event', self._on_key_press)

    def _on_key_press(self, _widget, event):
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK
        if not ctrl:
            return False
        n = self.notebook.get_n_pages()
        cur = self.notebook.get_current_page()
        if event.keyval == Gdk.KEY_Tab:
            self.notebook.set_current_page((cur + 1) % n)
            return True
        if event.keyval == Gdk.KEY_ISO_Left_Tab:
            self.notebook.set_current_page((cur - 1) % n)
            return True
        return False

    def _ensure_first_tab(self):
        self.notebook.set_current_page(0)
        return False

    def set_status(self, text: str):
        GLib.idle_add(self.status_label.set_text, text)

    def _show_about(self):
        dialog = Gtk.AboutDialog()
        dialog.set_transient_for(self)
        dialog.set_modal(True)
        dialog.set_program_name(_(APPLICATION_NAME))
        dialog.set_version(APPLICATION_VERSION)
        dialog.set_comments(_("Desktop theme manager for Soplos Linux Tyron."))
        dialog.set_website("https://soplos.org")
        dialog.set_website_label("soplos.org")
        dialog.set_authors([f"{_('Author')}: Sergi Perich <info@soploslinux.com>"])
        dialog.set_license_type(Gtk.License.GPL_3_0)

        icon_path = Path(__file__).parent.parent / 'assets' / 'icons' / '64x64' / f'{APPLICATION_ID}.png'
        if icon_path.exists():
            try:
                dialog.set_logo(GdkPixbuf.Pixbuf.new_from_file_at_scale(str(icon_path), 48, 48, True))
            except Exception:
                pass

        dialog.run()
        dialog.destroy()
