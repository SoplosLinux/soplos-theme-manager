import gi
import threading
from pathlib import Path
from typing import List, Optional

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, GdkPixbuf, Pango

from core.i18n_manager import _
from services.xfce_theme_service import XfceThemeService
from services.theme_export_service import ThemeExportService
from utils.logger import logger

WALLPAPER_DIRS = [
    Path("/usr/share/wallpapers"),
    Path("/usr/share/backgrounds"),
    Path("/usr/share/xfce4/backdrops"),
    Path.home() / "Pictures",
    Path.home() / "Imágenes",
]
WALLPAPER_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.svg'}
THUMB_WIDTH = 200
THUMB_HEIGHT = 120


class WallpaperCard(Gtk.Button):

    def __init__(self, image_path: str, pixbuf: GdkPixbuf.Pixbuf = None):
        super().__init__()
        self.image_path = image_path
        self.set_relief(Gtk.ReliefStyle.NONE)
        self.get_style_context().add_class('theme-card')
        self.set_size_request(THUMB_WIDTH + 8, THUMB_HEIGHT + 32)
        self.connect('clicked', self._on_clicked)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.add(vbox)

        img_box = Gtk.Box()
        img_box.set_halign(Gtk.Align.CENTER)
        img_box.get_style_context().add_class('theme-preview-box')
        img_box.set_size_request(THUMB_WIDTH, THUMB_HEIGHT)
        vbox.pack_start(img_box, True, True, 0)

        if pixbuf:
            img_box.add(Gtk.Image.new_from_pixbuf(pixbuf))
        else:
            img_box.add(Gtk.Image.new_from_icon_name('image-x-generic', Gtk.IconSize.DIALOG))

        name = Path(image_path).stem
        label = Gtk.Label(label=name)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_max_width_chars(18)
        label.get_style_context().add_class('theme-card-label')
        vbox.pack_start(label, False, False, 0)

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


class WallpapersTab(Gtk.Box):

    def __init__(self, config, parent_window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.config = config
        self.parent_window = parent_window
        self.selected_card: Optional[WallpaperCard] = None
        self.theme_service = XfceThemeService()
        self.export_service = ThemeExportService()

        self._loaded = False
        self._setup_ui()
        self.connect('map', self._on_mapped)

    def _setup_ui(self):
        # Barra superior con selector de carpeta
        top_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        top_bar.set_margin_start(15)
        top_bar.set_margin_end(15)
        top_bar.set_margin_top(10)
        top_bar.set_margin_bottom(5)
        self.pack_start(top_bar, False, False, 0)

        top_bar.pack_start(Gtk.Label(label=_("Folder:")), False, False, 0)

        self.folder_btn = Gtk.FileChooserButton(
            title=_("Select wallpaper folder"),
            action=Gtk.FileChooserAction.SELECT_FOLDER
        )
        default_dir = next((str(d) for d in WALLPAPER_DIRS if d.exists()), None)
        if default_dir:
            self.folder_btn.set_filename(default_dir)
        self.folder_btn.connect('file-set', self._on_folder_changed)
        top_bar.pack_start(self.folder_btn, True, True, 0)

        sep = Gtk.Separator()
        self.pack_start(sep, False, False, 0)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.pack_start(scrolled, True, True, 0)

        self.flowbox = Gtk.FlowBox()
        self.flowbox.set_valign(Gtk.Align.START)
        self.flowbox.set_max_children_per_line(20)
        self.flowbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.flowbox.set_homogeneous(True)
        self.flowbox.set_row_spacing(15)
        self.flowbox.set_column_spacing(15)
        self.flowbox.set_margin_top(15)
        self.flowbox.set_margin_bottom(15)
        self.flowbox.set_margin_start(15)
        self.flowbox.set_margin_end(15)
        self.flowbox.connect('child-activated', self._on_card_activated)
        scrolled.add(self.flowbox)

        # Actions
        actions_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        actions_box.set_halign(Gtk.Align.CENTER)
        actions_box.set_margin_top(10)
        actions_box.set_margin_bottom(10)
        self.pack_start(actions_box, False, False, 0)

        apply_btn = Gtk.Button()
        apply_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        apply_box.pack_start(Gtk.Image.new_from_icon_name('preferences-desktop-wallpaper', Gtk.IconSize.BUTTON), False, False, 0)
        apply_box.pack_start(Gtk.Label(label=_("Set Wallpaper")), False, False, 0)
        apply_btn.add(apply_box)
        apply_btn.get_style_context().add_class('suggested-action')
        apply_btn.connect('clicked', self._on_apply)
        actions_box.pack_start(apply_btn, False, False, 0)

        install_btn = Gtk.Button()
        install_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        install_box.pack_start(Gtk.Image.new_from_icon_name('list-add', Gtk.IconSize.BUTTON), False, False, 0)
        install_box.pack_start(Gtk.Label(label=_("Install Wallpaper")), False, False, 0)
        install_btn.add(install_box)
        install_btn.connect('clicked', self._on_install)
        actions_box.pack_start(install_btn, False, False, 0)

        # Status label
        self.status_label = Gtk.Label()
        self.status_label.get_style_context().add_class('dim-label')
        self.status_label.set_margin_bottom(6)
        self.pack_start(self.status_label, False, False, 0)

    def _on_mapped(self, widget):
        if not self._loaded:
            self._loaded = True
            self._load_wallpapers_async()

    def _on_folder_changed(self, btn):
        self._loaded = True
        self._load_wallpapers_async()

    def _load_wallpapers_async(self):
        self.parent_window.show_progress(_("Scanning wallpapers…"))
        def worker():
            folder = self.folder_btn.get_filename()
            paths = self._scan_folder(folder) if folder else self._scan_all_dirs()
            items = []
            for path in paths:
                try:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                        path, THUMB_WIDTH, THUMB_HEIGHT, True
                    )
                except Exception:
                    pixbuf = None
                items.append((path, pixbuf))
            GLib.idle_add(self._fill_gallery, items)
        threading.Thread(target=worker, daemon=True).start()

    def _scan_folder(self, folder: str) -> List[str]:
        seen = set()
        result = []
        try:
            for f in sorted(Path(folder).rglob("*")):
                if f.is_file() and f.suffix.lower() in WALLPAPER_EXTENSIONS:
                    real = f.resolve()
                    if real not in seen:
                        seen.add(real)
                        result.append(str(f))
        except Exception as e:
            logger.warning(f"Error scanning wallpaper folder: {e}")
        return result

    def _scan_all_dirs(self) -> List[str]:
        seen = set()
        result = []
        for d in WALLPAPER_DIRS:
            if d.exists():
                for path in self._scan_folder(str(d)):
                    real = Path(path).resolve()
                    if real not in seen:
                        seen.add(real)
                        result.append(path)
        return result

    def _fill_gallery(self, items: list):
        for child in self.flowbox.get_children():
            self.flowbox.remove(child)
        self.selected_card = None
        for path, pixbuf in items:
            self.flowbox.add(WallpaperCard(path, pixbuf))
        self.flowbox.show_all()
        msg = _("{n} wallpapers found").format(n=len(items))
        self.status_label.set_text(msg)
        self.parent_window.hide_progress()
        return False

    def _on_card_activated(self, flowbox, child):
        flowbox.select_child(child)
        if self.selected_card:
            self.selected_card.set_selected(False)
        self.selected_card = child.get_child()
        self.selected_card.set_selected(True)

    def _on_apply(self, btn):
        if not self.selected_card:
            self._show_info(_("Select a wallpaper first"))
            return
        path = self.selected_card.image_path
        self.parent_window.show_progress(_("Applying wallpaper…"))
        def worker():
            ok = self.theme_service.set_wallpaper(path)
            GLib.idle_add(self._on_apply_done, ok)
        threading.Thread(target=worker, daemon=True).start()

    def _on_apply_done(self, ok: bool):
        self.parent_window.hide_progress()
        msg = _("Wallpaper applied") if ok else _("Error applying wallpaper")
        self.status_label.set_text(msg)
        return False

    def _on_install(self, btn):
        dialog = Gtk.FileChooserDialog(
            title=_("Select wallpapers to install"),
            parent=self.parent_window,
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN, Gtk.ResponseType.OK,
        )
        dialog.set_select_multiple(True)

        img_filter = Gtk.FileFilter()
        img_filter.set_name(_("Images"))
        for pattern in ('*.jpg', '*.jpeg', '*.png', '*.webp', '*.bmp', '*.svg'):
            img_filter.add_pattern(pattern)
        dialog.add_filter(img_filter)

        response = dialog.run()
        paths = dialog.get_filenames() if response == Gtk.ResponseType.OK else []
        dialog.destroy()
        if not paths:
            return

        self.parent_window.show_progress(_("Installing wallpapers…"))

        def worker():
            ok, msg = self.export_service.install_wallpapers_system(paths)
            GLib.idle_add(self._on_install_done, ok, msg)

        threading.Thread(target=worker, daemon=True).start()

    def _on_install_done(self, ok: bool, msg: str):
        self.parent_window.hide_progress()
        if ok:
            self.status_label.set_text(_("Wallpapers installed"))
            self._loaded = True
            self._load_wallpapers_async()
        else:
            self.status_label.set_text(_("Error installing wallpapers: {e}").format(e=msg))
        return False

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
