import gi
import threading
from pathlib import Path
from typing import Optional, List

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, GdkPixbuf, Pango

from core.i18n_manager import _
from services.docklike_service import DocklikeService
from utils.logger import logger

ICON_SIZE = 32
LIST_ICON_SIZE = 48
PREVIEW_ICON_SIZE = 34


class DocklikeTab(Gtk.Box):

    def __init__(self, config, parent_window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.config = config
        self.parent_window = parent_window
        self.service = DocklikeService()
        self._pinned: List[dict] = []
        self._ui_ready = False

        if not self.service.is_plugin_active():
            self._show_plugin_missing()
        else:
            self._setup_ui()
            self._load_pinned()
        self.connect('map', self._on_mapped)

    def _show_plugin_missing(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)
        self.pack_start(box, True, True, 0)

        icon = Gtk.Image.new_from_icon_name('dialog-information', Gtk.IconSize.DIALOG)
        box.pack_start(icon, False, False, 0)

        label = Gtk.Label(label=_("Docklike plugin is not active in your panel."))
        label.get_style_context().add_class('dim-label')
        box.pack_start(label, False, False, 0)

        sub = Gtk.Label(label=_("Add the Docklike Taskbar plugin to your XFCE panel to use this feature."))
        sub.set_line_wrap(True)
        sub.set_max_width_chars(50)
        sub.get_style_context().add_class('dim-label')
        box.pack_start(sub, False, False, 0)

        refresh_btn = Gtk.Button()
        ref_inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        ref_inner.pack_start(Gtk.Image.new_from_icon_name('view-refresh', Gtk.IconSize.BUTTON), False, False, 0)
        ref_inner.pack_start(Gtk.Label(label=_("Refresh")), False, False, 0)
        refresh_btn.add(ref_inner)
        refresh_btn.connect('clicked', self._on_refresh)
        box.pack_start(refresh_btn, False, False, 0)

    def _setup_ui(self):
        # ── Live horizontal dock preview ────────────────────────────────────
        preview_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        preview_card.get_style_context().add_class('theme-card')
        preview_card.set_margin_start(12)
        preview_card.set_margin_end(12)
        preview_card.set_margin_top(10)
        preview_card.set_margin_bottom(4)
        self.pack_start(preview_card, False, False, 0)

        preview_title = Gtk.Label()
        preview_title.set_markup(
            f"<b>{_('Dock preview')}</b>  "
            f"<span alpha='55%' size='small'>{_('how it will look on screen')}</span>"
        )
        preview_title.set_halign(Gtk.Align.START)
        preview_title.set_margin_start(8)
        preview_title.set_margin_top(8)
        preview_card.pack_start(preview_title, False, False, 0)

        preview_strip_wrap = Gtk.Box()
        preview_strip_wrap.set_halign(Gtk.Align.CENTER)
        preview_strip_wrap.set_margin_start(8)
        preview_strip_wrap.set_margin_end(8)
        preview_strip_wrap.set_margin_bottom(8)
        preview_card.pack_start(preview_strip_wrap, False, False, 0)

        self._dock_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._dock_bar.get_style_context().add_class('docklike-preview-bar')
        self._dock_bar.set_margin_start(10)
        self._dock_bar.set_margin_end(10)
        self._dock_bar.set_margin_top(6)
        self._dock_bar.set_margin_bottom(6)
        preview_strip_wrap.pack_start(self._dock_bar, False, False, 0)

        # Panel izquierdo: lista de apps ancladas
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.pack_start(hbox, True, True, 0)

        # Lista de pinned apps
        left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        left_box.set_size_request(320, -1)
        hbox.pack_start(left_box, False, False, 0)

        left_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        left_header.set_margin_start(12)
        left_header.set_margin_end(12)
        left_header.set_margin_top(10)
        left_header.set_margin_bottom(6)
        title = Gtk.Label(label=_("Pinned Applications"))
        title.get_style_context().add_class('theme-card-label')
        title.set_halign(Gtk.Align.START)
        left_header.pack_start(title, True, True, 0)
        left_box.pack_start(left_header, False, False, 0)

        left_box.pack_start(Gtk.Separator(), False, False, 0)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        left_box.pack_start(scrolled, True, True, 0)

        # ListStore: icon_path (str), name (str), desktop_path (str)
        self.store = Gtk.ListStore(GdkPixbuf.Pixbuf, str, str)
        self.store.connect('row-inserted',   self._on_store_changed)
        self.store.connect('row-deleted',    self._on_store_changed)
        self.store.connect('row-changed',    self._on_store_changed)
        self.store.connect('rows-reordered', self._on_store_changed)
        self.treeview = Gtk.TreeView(model=self.store)
        self.treeview.set_headers_visible(False)
        self.treeview.set_reorderable(True)

        col_icon = Gtk.TreeViewColumn()
        cell_icon = Gtk.CellRendererPixbuf()
        col_icon.pack_start(cell_icon, False)
        col_icon.add_attribute(cell_icon, 'pixbuf', 0)
        self.treeview.append_column(col_icon)

        col_name = Gtk.TreeViewColumn()
        cell_name = Gtk.CellRendererText()
        cell_name.set_property('ellipsize', Pango.EllipsizeMode.END)
        col_name.pack_start(cell_name, True)
        col_name.add_attribute(cell_name, 'text', 1)
        self.treeview.append_column(col_name)

        scrolled.add(self.treeview)

        # Botones de orden/eliminar
        list_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        list_actions.set_halign(Gtk.Align.CENTER)
        list_actions.set_margin_top(8)
        list_actions.set_margin_bottom(8)
        left_box.pack_start(list_actions, False, False, 0)

        for icon_name, tooltip, callback in [
            ('go-up',     _("Move Up"),   self._on_move_up),
            ('go-down',   _("Move Down"), self._on_move_down),
            ('list-remove', _("Remove"),  self._on_remove_selected),
        ]:
            btn = Gtk.Button()
            btn.add(Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.BUTTON))
            btn.set_tooltip_text(tooltip)
            btn.connect('clicked', callback)
            list_actions.pack_start(btn, False, False, 0)

        # Separador vertical
        hbox.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 0)

        # Panel derecho: buscador de apps disponibles
        right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        hbox.pack_start(right_box, True, True, 0)

        right_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        right_header.set_margin_start(12)
        right_header.set_margin_end(12)
        right_header.set_margin_top(10)
        right_header.set_margin_bottom(6)
        title2 = Gtk.Label(label=_("Available Applications"))
        title2.get_style_context().add_class('theme-card-label')
        title2.set_halign(Gtk.Align.START)
        right_header.pack_start(title2, True, True, 0)
        right_box.pack_start(right_header, False, False, 0)

        # Buscador
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text(_("Search applications…"))
        self.search_entry.set_margin_start(12)
        self.search_entry.set_margin_end(12)
        self.search_entry.set_margin_bottom(6)
        self.search_entry.connect('search-changed', self._on_search_changed)
        right_box.pack_start(self.search_entry, False, False, 0)

        right_box.pack_start(Gtk.Separator(), False, False, 0)

        scrolled2 = Gtk.ScrolledWindow()
        scrolled2.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        right_box.pack_start(scrolled2, True, True, 0)

        self.apps_store = Gtk.ListStore(GdkPixbuf.Pixbuf, str, str, str)  # pixbuf, name, desktop_path, icon_path
        self.apps_filter = self.apps_store.filter_new()
        self.apps_filter.set_visible_func(self._apps_filter_func)

        self.apps_view = Gtk.TreeView(model=self.apps_filter)
        self.apps_view.set_headers_visible(False)

        col_i = Gtk.TreeViewColumn()
        cell_i = Gtk.CellRendererPixbuf()
        col_i.pack_start(cell_i, False)
        col_i.add_attribute(cell_i, 'pixbuf', 0)
        self.apps_view.append_column(col_i)

        col_n = Gtk.TreeViewColumn()
        cell_n = Gtk.CellRendererText()
        cell_n.set_property('ellipsize', Pango.EllipsizeMode.END)
        col_n.pack_start(cell_n, True)
        col_n.add_attribute(cell_n, 'text', 1)
        self.apps_view.append_column(col_n)

        scrolled2.add(self.apps_view)

        add_btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        add_btn_box.set_halign(Gtk.Align.CENTER)
        add_btn_box.set_margin_top(8)
        add_btn_box.set_margin_bottom(8)
        right_box.pack_start(add_btn_box, False, False, 0)

        add_btn = Gtk.Button()
        add_inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        add_inner.pack_start(Gtk.Image.new_from_icon_name('list-add', Gtk.IconSize.BUTTON), False, False, 0)
        add_inner.pack_start(Gtk.Label(label=_("Pin to Dock")), False, False, 0)
        add_btn.add(add_inner)
        add_btn.get_style_context().add_class('suggested-action')
        add_btn.connect('clicked', self._on_add_app)
        add_btn_box.pack_start(add_btn, False, False, 0)

        # Barra inferior: Guardar / Aplicar
        bottom_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        bottom_bar.set_halign(Gtk.Align.CENTER)
        bottom_bar.set_margin_top(8)
        bottom_bar.set_margin_bottom(10)
        self.pack_start(bottom_bar, False, False, 0)

        save_btn = Gtk.Button()
        save_inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        save_inner.pack_start(Gtk.Image.new_from_icon_name('document-save', Gtk.IconSize.BUTTON), False, False, 0)
        save_inner.pack_start(Gtk.Label(label=_("Save & Apply")), False, False, 0)
        save_btn.add(save_inner)
        save_btn.get_style_context().add_class('suggested-action')
        save_btn.connect('clicked', self._on_save)
        bottom_bar.pack_start(save_btn, False, False, 0)

        self.status_label = Gtk.Label()
        self.status_label.get_style_context().add_class('dim-label')
        self.status_label.set_margin_bottom(6)
        self.pack_start(self.status_label, False, False, 0)
        self._refresh_dock_preview()
        self._ui_ready = True

    def _on_mapped(self, _widget):
        if self._ui_ready:
            # Reload only pinned list in case docklike moved to a different panel/ID
            self._reload_pinned_only()
        elif self.service.is_plugin_active():
            # Plugin became active after initial load — rebuild the UI
            for child in self.get_children():
                self.remove(child)
            self._setup_ui()
            self._load_pinned()

    def _on_refresh(self, _btn):
        if self.service.is_plugin_active():
            for child in self.get_children():
                self.remove(child)
            self._setup_ui()
            self._load_pinned()

    def _load_pinned(self):
        self.status_label.set_text(_("Loading…"))
        def worker():
            pinned = self.service.read_pinned()
            apps = self.service.get_available_apps()
            GLib.idle_add(self._fill_lists, pinned, apps)
        threading.Thread(target=worker, daemon=True).start()

    def _reload_pinned_only(self):
        def worker():
            pinned = self.service.read_pinned()
            GLib.idle_add(self._fill_pinned, pinned)
        threading.Thread(target=worker, daemon=True).start()

    def _fill_pinned(self, pinned: list):
        self._pinned = pinned
        self.store.clear()
        for app in pinned:
            pixbuf = self._load_icon(app.get('icon_path'), LIST_ICON_SIZE)
            self.store.append([pixbuf, app['name'], app['desktop_path']])
        self.status_label.set_text(_("{n} pinned").format(n=len(pinned)))

    def _fill_lists(self, pinned: list, apps: list):
        self._pinned = pinned
        self.store.clear()
        for app in pinned:
            pixbuf = self._load_icon(app.get('icon_path'), LIST_ICON_SIZE)
            self.store.append([pixbuf, app['name'], app['desktop_path']])

        self.apps_store.clear()
        for app in apps:
            pixbuf = self._load_icon(app.get('icon_path'), ICON_SIZE)
            self.apps_store.append([pixbuf, app['name'], app['desktop_path'], app.get('icon_path', '')])

        self.status_label.set_text(_("{n} pinned").format(n=len(pinned)))

    # ── Live horizontal dock preview ────────────────────────────────────────

    def _on_store_changed(self, *_args):
        self._refresh_dock_preview()

    def _refresh_dock_preview(self):
        for child in list(self._dock_bar.get_children()):
            self._dock_bar.remove(child)

        if len(self.store) == 0:
            empty = Gtk.Label(label=_("Your dock is empty — pin an app below"))
            empty.get_style_context().add_class('dim-label')
            empty.set_margin_start(10)
            empty.set_margin_end(10)
            self._dock_bar.pack_start(empty, False, False, 0)
        else:
            for row in self.store:
                pixbuf = row[0]
                img = Gtk.Image()
                if pixbuf:
                    scaled = pixbuf.scale_simple(
                        PREVIEW_ICON_SIZE, PREVIEW_ICON_SIZE, GdkPixbuf.InterpType.BILINEAR
                    )
                    img.set_from_pixbuf(scaled)
                else:
                    img.set_from_icon_name('application-x-executable', Gtk.IconSize.LARGE_TOOLBAR)
                img.set_tooltip_text(row[1])
                self._dock_bar.pack_start(img, False, False, 0)

        self._dock_bar.show_all()

    def _load_icon(self, icon_path: Optional[str], size: int) -> Optional[GdkPixbuf.Pixbuf]:
        if not icon_path:
            return None
        try:
            return GdkPixbuf.Pixbuf.new_from_file_at_scale(icon_path, size, size, True)
        except Exception:
            return None

    def _on_search_changed(self, entry):
        self.apps_filter.refilter()

    def _apps_filter_func(self, model, it, data):
        query = self.search_entry.get_text().lower()
        if not query:
            return True
        name = model.get_value(it, 1) or ''
        return query in name.lower()

    def _on_move_up(self, btn):
        sel = self.treeview.get_selection()
        model, it = sel.get_selected()
        if not it:
            return
        path = model.get_path(it)
        if path[0] > 0:
            prev = Gtk.TreePath(path[0] - 1)
            model.swap(model.get_iter(prev), it)

    def _on_move_down(self, btn):
        sel = self.treeview.get_selection()
        model, it = sel.get_selected()
        if not it:
            return
        next_it = model.iter_next(it)
        if next_it:
            model.swap(it, next_it)

    def _on_remove_selected(self, btn):
        sel = self.treeview.get_selection()
        model, it = sel.get_selected()
        if it:
            model.remove(it)
            self.status_label.set_text(_("Removed. Click 'Save & Apply' to confirm."))

    def _on_add_app(self, btn):
        sel = self.apps_view.get_selection()
        model, it = sel.get_selected()
        if not it:
            return
        it_real = self.apps_filter.convert_iter_to_child_iter(it)
        name = self.apps_store.get_value(it_real, 1)
        desktop_path = self.apps_store.get_value(it_real, 2)
        icon_path = self.apps_store.get_value(it_real, 3)
        pixbuf = self._load_icon(icon_path, LIST_ICON_SIZE)

        # Evitar duplicados
        for row in self.store:
            if row[2] == desktop_path:
                self.status_label.set_text(_("Already pinned: {name}").format(name=name))
                return

        self.store.append([pixbuf, name, desktop_path])
        self.status_label.set_text(_("Added: {name}. Click 'Save & Apply' to confirm.").format(name=name))

    def _on_save(self, btn):
        desktop_paths = [row[2] for row in self.store]
        ok = self.service.write_pinned(desktop_paths)
        if ok:
            self.service.restart_panel()
            self.status_label.set_text(_("Saved and applied"))
        else:
            self.status_label.set_text(_("Error saving configuration"))
