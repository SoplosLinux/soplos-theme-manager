import gi
import grp
import os
import pwd
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf, Gio

from core.i18n_manager import _
from utils.logger import logger

AVATAR_SIZE = 128
ACCOUNTS_SERVICE_DIR = Path("/var/lib/AccountsService/icons")
CROP_DISPLAY_MAX = 420  # max px for the crop dialog canvas
HANDLE_SIZE  = 12       # drawn handle square side (display px)
HANDLE_HIT   = 16       # hit area radius around each corner (display px)
LO_PREFS = Path(GLib.get_user_config_dir()) / 'libreoffice' / '4' / 'user' / 'registrymodifications.xcu'
MIN_CROP     = 40       # minimum crop side in image px


class CropDialog(Gtk.Dialog):
    """Dialog that lets the user move and resize a square crop area over an image."""

    def __init__(self, parent, pixbuf: GdkPixbuf.Pixbuf):
        super().__init__(title=_("Crop Avatar"), transient_for=parent, modal=True)
        self.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK,     Gtk.ResponseType.OK
        )
        self.set_default_response(Gtk.ResponseType.OK)

        self.orig = pixbuf
        iw = pixbuf.get_width()
        ih = pixbuf.get_height()

        # Scale factor to fit image in the dialog canvas
        self._scale = min(CROP_DISPLAY_MAX / iw, CROP_DISPLAY_MAX / ih, 1.0)
        self._dw = int(iw * self._scale)
        self._dh = int(ih * self._scale)
        self._disp = pixbuf.scale_simple(self._dw, self._dh, GdkPixbuf.InterpType.BILINEAR)

        # Initial crop: centered square using the shorter image dimension (in image coords)
        side = min(iw, ih)
        self._cx = (iw - side) // 2  # image-space coords
        self._cy = (ih - side) // 2
        self._cs = side              # crop size (always square)

        self._drag_start    = None   # (mx, my, orig_cx, orig_cy) when moving
        self._resize_corner = None   # 0=TL 1=TR 2=BL 3=BR when resizing
        self._resize_fixed  = None   # fixed corner in image coords (fx, fy)

        da = Gtk.DrawingArea()
        da.set_size_request(self._dw, self._dh)
        da.connect('draw',                 self._on_draw)
        da.connect('button-press-event',   self._on_press)
        da.connect('button-release-event', self._on_release)
        da.connect('motion-notify-event',  self._on_motion)
        da.connect('scroll-event',         self._on_scroll)
        da.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK   |
            Gdk.EventMask.BUTTON_RELEASE_MASK |
            Gdk.EventMask.POINTER_MOTION_MASK |
            Gdk.EventMask.SCROLL_MASK
        )
        da.get_style_context().add_class('avatar-crop-canvas')

        hint = Gtk.Label(label=_("Drag inside to move · Drag corners to resize · Scroll to resize"))
        hint.get_style_context().add_class('dim-label')
        hint.set_margin_bottom(6)

        box = self.get_content_area()
        box.set_spacing(8)
        box.pack_start(da, False, False, 0)
        box.pack_start(hint, False, False, 0)
        self.show_all()

    # ── Drawing ───────────────────────────────────────────────────────────────

    def _on_draw(self, _widget, cr):
        Gdk.cairo_set_source_pixbuf(cr, self._disp, 0, 0)
        cr.paint()

        # Crop rect in display coords
        sx = self._cx * self._scale
        sy = self._cy * self._scale
        ss = self._cs * self._scale

        # Dimmed overlay outside the selection
        cr.set_source_rgba(0, 0, 0, 0.55)
        cr.rectangle(0,       0,       self._dw,           sy)
        cr.rectangle(0,       sy + ss, self._dw,           self._dh)
        cr.rectangle(0,       sy,      sx,                  ss)
        cr.rectangle(sx + ss, sy,      self._dw - sx - ss, ss)
        cr.fill()

        # Border
        cr.set_source_rgba(1, 1, 1, 0.95)
        cr.set_line_width(2)
        cr.rectangle(sx, sy, ss, ss)
        cr.stroke()

        # Corner handles
        h = HANDLE_SIZE
        for hx, hy in [
            (sx,          sy),
            (sx + ss - h, sy),
            (sx,          sy + ss - h),
            (sx + ss - h, sy + ss - h),
        ]:
            cr.rectangle(hx, hy, h, h)
            cr.fill()

    # ── Hit detection ─────────────────────────────────────────────────────────

    def _hit_corner(self, x, y):
        """Return corner index (0=TL 1=TR 2=BL 3=BR) if (x,y) is near a handle, else None."""
        sx = self._cx * self._scale
        sy = self._cy * self._scale
        ss = self._cs * self._scale
        corners = [
            (sx,      sy),
            (sx + ss, sy),
            (sx,      sy + ss),
            (sx + ss, sy + ss),
        ]
        for i, (cx, cy) in enumerate(corners):
            if abs(x - cx) <= HANDLE_HIT and abs(y - cy) <= HANDLE_HIT:
                return i
        return None

    # ── Mouse interaction ─────────────────────────────────────────────────────

    def _on_press(self, widget, event):
        corner = self._hit_corner(event.x, event.y)
        if corner is not None:
            # Resize mode: fix the opposite corner in image coords
            cx2 = self._cx + self._cs
            cy2 = self._cy + self._cs
            fixed_map = {
                0: (cx2, cy2),   # dragging TL → fix BR
                1: (self._cx, cy2),   # dragging TR → fix BL
                2: (cx2, self._cy),   # dragging BL → fix TR
                3: (self._cx, self._cy),  # dragging BR → fix TL
            }
            self._resize_corner = corner
            self._resize_fixed  = fixed_map[corner]
            self._drag_start    = None
        else:
            # Move mode: only if click is inside the crop square
            sx = self._cx * self._scale
            sy = self._cy * self._scale
            ss = self._cs * self._scale
            if sx <= event.x <= sx + ss and sy <= event.y <= sy + ss:
                self._drag_start = (event.x, event.y, self._cx, self._cy)
            self._resize_corner = None
            self._resize_fixed  = None

    def _on_release(self, _widget, _event):
        self._drag_start    = None
        self._resize_corner = None
        self._resize_fixed  = None

    def _on_motion(self, _widget, event):
        if self._resize_corner is not None:
            self._do_resize(event.x, event.y)
        elif self._drag_start:
            ox, oy, ocx, ocy = self._drag_start
            dx = int((event.x - ox) / self._scale)
            dy = int((event.y - oy) / self._scale)
            iw = self.orig.get_width()
            ih = self.orig.get_height()
            self._cx = max(0, min(ocx + dx, iw - self._cs))
            self._cy = max(0, min(ocy + dy, ih - self._cs))
        else:
            return
        event.window.invalidate_rect(None, False)

    def _do_resize(self, mx_disp, my_disp):
        """Resize crop square keeping the fixed corner stationary."""
        iw = self.orig.get_width()
        ih = self.orig.get_height()
        fx, fy = self._resize_fixed

        # Mouse position in image coords
        img_mx = mx_disp / self._scale
        img_my = my_disp / self._scale

        # New side = min of x and y distance from fixed corner (keeps it square)
        new_side = max(MIN_CROP, int(min(abs(img_mx - fx), abs(img_my - fy))))

        # New top-left: fixed corner determines which direction the square grows
        corner = self._resize_corner
        if corner == 0:    # TL moves, BR fixed → TL = (fx-side, fy-side)
            new_cx = fx - new_side
            new_cy = fy - new_side
        elif corner == 1:  # TR moves, BL fixed → TL = (fx, fy-side)
            new_cx = fx
            new_cy = fy - new_side
        elif corner == 2:  # BL moves, TR fixed → TL = (fx-side, fy)
            new_cx = fx - new_side
            new_cy = fy
        else:              # BR moves, TL fixed → TL = (fx, fy)
            new_cx = fx
            new_cy = fy

        # Clamp to image bounds
        new_cx = max(0, new_cx)
        new_cy = max(0, new_cy)
        if new_cx + new_side > iw:
            new_side = iw - new_cx
        if new_cy + new_side > ih:
            new_side = ih - new_cy

        self._cx = new_cx
        self._cy = new_cy
        self._cs = max(MIN_CROP, new_side)

    def _on_scroll(self, widget, event):
        """Resize crop square with the scroll wheel, keeping it centered."""
        if event.direction == Gdk.ScrollDirection.UP:
            delta = 20
        elif event.direction == Gdk.ScrollDirection.DOWN:
            delta = -20
        elif event.direction == Gdk.ScrollDirection.SMOOTH:
            delta = int(-event.delta_y * 12)
        else:
            return

        iw = self.orig.get_width()
        ih = self.orig.get_height()
        cx_center = self._cx + self._cs // 2
        cy_center = self._cy + self._cs // 2
        new_side = max(MIN_CROP, min(self._cs + delta, min(iw, ih)))
        self._cx = max(0, min(cx_center - new_side // 2, iw - new_side))
        self._cy = max(0, min(cy_center - new_side // 2, ih - new_side))
        self._cs = new_side
        widget.queue_draw()

    # ── Result ────────────────────────────────────────────────────────────────

    def get_cropped_pixbuf(self) -> GdkPixbuf.Pixbuf:
        return self.orig.new_subpixbuf(self._cx, self._cy, self._cs, self._cs)


class PasswordDialog(Gtk.Dialog):
    """Password prompt for privileged operations (sudo chfn for phone numbers)."""

    def __init__(self, parent):
        super().__init__(title=_("Authentication Required"), transient_for=parent, modal=True)
        self.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK,     Gtk.ResponseType.OK
        )
        self.set_default_response(Gtk.ResponseType.OK)

        box = self.get_content_area()
        box.set_spacing(12)
        box.set_margin_top(12)
        box.set_margin_bottom(6)
        box.set_margin_start(18)
        box.set_margin_end(18)

        icon = Gtk.Image.new_from_icon_name('dialog-password', Gtk.IconSize.DIALOG)
        icon.set_halign(Gtk.Align.CENTER)
        box.pack_start(icon, False, False, 0)

        msg = Gtk.Label(label=_("Enter your password to update phone numbers."))
        msg.set_line_wrap(True)
        msg.set_halign(Gtk.Align.CENTER)
        box.pack_start(msg, False, False, 0)

        self._entry = Gtk.Entry()
        self._entry.set_visibility(False)
        self._entry.set_activates_default(True)
        box.pack_start(self._entry, False, False, 0)

        self.show_all()

    def get_password(self) -> str:
        return self._entry.get_text()


class AvatarTab(Gtk.Box):

    def __init__(self, config, parent_window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.config = config
        self.parent_window = parent_window
        self._username = os.environ.get('USER') or os.environ.get('LOGNAME') or ''
        self._pending_pixbuf    = None
        self._orig_home_phone   = ''
        self._orig_office_phone = ''
        self._orig_fax          = ''
        self._groups_checks     = {}
        self._primary_group     = ''

        self._setup_ui()
        self._load_current_avatar()
        self._load_user_data()
        self._load_groups_async()

    def _setup_ui(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        outer.set_margin_top(30)
        outer.set_margin_bottom(20)
        outer.set_margin_start(40)
        outer.set_margin_end(40)
        self.pack_start(outer, True, True, 0)

        content_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=40)
        content_row.set_halign(Gtk.Align.CENTER)
        content_row.set_valign(Gtk.Align.CENTER)
        outer.pack_start(content_row, True, True, 0)

        # ── Left column: avatar ──────────────────────────────────────────────
        left_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        left_col.set_valign(Gtk.Align.CENTER)
        content_row.pack_start(left_col, False, False, 0)

        avatar_frame = Gtk.Box()
        avatar_frame.set_halign(Gtk.Align.CENTER)
        avatar_frame.get_style_context().add_class('avatar-frame')
        left_col.pack_start(avatar_frame, False, False, 0)

        self.avatar_image = Gtk.Image()
        self.avatar_image.set_size_request(AVATAR_SIZE, AVATAR_SIZE)
        avatar_frame.add(self.avatar_image)

        choose_btn = Gtk.Button()
        choose_inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        choose_inner.set_halign(Gtk.Align.CENTER)
        choose_inner.pack_start(
            Gtk.Image.new_from_icon_name('document-open', Gtk.IconSize.BUTTON),
            False, False, 0
        )
        choose_inner.pack_start(Gtk.Label(label=_("Choose Image…")), False, False, 0)
        choose_btn.add(choose_inner)
        choose_btn.connect('clicked', self._on_choose)
        left_col.pack_start(choose_btn, False, False, 0)

        # ── Center column: user data form ────────────────────────────────────
        right_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        right_col.set_valign(Gtk.Align.CENTER)
        content_row.pack_start(right_col, False, False, 0)

        grid = Gtk.Grid()
        grid.set_row_spacing(10)
        grid.set_column_spacing(14)
        right_col.pack_start(grid, False, False, 0)

        # Mugshot field order: First Name, Last Name, Initials, Username, Home Phone,
        #                      Email, Office Phone, Fax
        fields = [
            ('first_name',   _("First Name"),   True),
            ('last_name',    _("Last Name"),    True),
            ('initials',     _("Initials"),     True),
            ('username',     _("Username"),     False),
            ('home_phone',   _("Home Phone"),   True),
            ('email',        _("Email"),        True),
            ('office_phone', _("Office Phone"), True),
            ('fax',          _("Fax"),          True),
        ]

        self._entries = {}
        for row, (key, label_text, editable) in enumerate(fields):
            lbl = Gtk.Label(label=label_text + ":")
            lbl.set_halign(Gtk.Align.END)
            lbl.get_style_context().add_class('dim-label')
            grid.attach(lbl, 0, row, 1, 1)

            entry = Gtk.Entry()
            entry.set_width_chars(28)
            entry.set_editable(editable)
            if not editable:
                entry.get_style_context().add_class('dim-label')
            grid.attach(entry, 1, row, 1, 1)
            self._entries[key] = entry

        # Auto-suggest initials when first or last name changes
        for key in ('first_name', 'last_name'):
            self._entries[key].connect('changed', self._on_name_changed)

        # Apply button below the form
        apply_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        apply_box.set_halign(Gtk.Align.CENTER)
        apply_box.set_margin_top(16)
        right_col.pack_start(apply_box, False, False, 0)

        self.apply_btn = Gtk.Button()
        apply_inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        apply_inner.pack_start(
            Gtk.Image.new_from_icon_name('object-select-symbolic', Gtk.IconSize.BUTTON),
            False, False, 0
        )
        apply_inner.pack_start(Gtk.Label(label=_("Apply")), False, False, 0)
        self.apply_btn.add(apply_inner)
        self.apply_btn.get_style_context().add_class('suggested-action')
        self.apply_btn.connect('clicked', self._on_apply)
        apply_box.pack_start(self.apply_btn, False, False, 0)

        # ── Vertical separator ────────────────────────────────────────────────
        content_row.pack_start(
            Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 0
        )

        # ── Right column: groups ──────────────────────────────────────────────
        groups_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        groups_col.set_size_request(200, -1)
        groups_col.set_valign(Gtk.Align.FILL)
        content_row.pack_start(groups_col, False, False, 0)

        groups_title = Gtk.Label(label=_("Groups"))
        groups_title.get_style_context().add_class('theme-card-label')
        groups_title.set_halign(Gtk.Align.START)
        groups_title.set_margin_bottom(6)
        groups_col.pack_start(groups_title, False, False, 0)

        groups_col.pack_start(Gtk.Separator(), False, False, 0)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        groups_col.pack_start(scrolled, True, True, 0)

        self._groups_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._groups_box.set_margin_top(6)
        self._groups_box.set_margin_bottom(6)
        self._groups_box.set_margin_start(8)
        scrolled.add(self._groups_box)

        groups_btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        groups_btn_box.set_halign(Gtk.Align.CENTER)
        groups_btn_box.set_margin_top(8)
        groups_col.pack_start(groups_btn_box, False, False, 0)

        self._groups_apply_btn = Gtk.Button()
        g_inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        g_inner.pack_start(
            Gtk.Image.new_from_icon_name('object-select-symbolic', Gtk.IconSize.BUTTON),
            False, False, 0
        )
        g_inner.pack_start(Gtk.Label(label=_("Apply Groups")), False, False, 0)
        self._groups_apply_btn.add(g_inner)
        self._groups_apply_btn.get_style_context().add_class('suggested-action')
        self._groups_apply_btn.connect('clicked', self._on_apply_groups)
        groups_btn_box.pack_start(self._groups_apply_btn, False, False, 0)

        self._groups_status = Gtk.Label()
        self._groups_status.get_style_context().add_class('dim-label')
        self._groups_status.set_halign(Gtk.Align.CENTER)
        self._groups_status.set_margin_top(4)
        self._groups_status.set_line_wrap(True)
        self._groups_status.set_max_width_chars(24)
        groups_col.pack_start(self._groups_status, False, False, 0)

    # ── Groups loading ────────────────────────────────────────────────────────

    def _load_groups_async(self):
        threading.Thread(target=self._load_groups_worker, daemon=True).start()

    def _load_groups_worker(self):
        try:
            pw = pwd.getpwnam(self._username)
            primary_grp = grp.getgrgid(pw.pw_gid).gr_name
        except Exception:
            primary_grp = ''

        # id -Gn reads all NSS sources and gives the authoritative group list
        try:
            result = subprocess.run(
                ['id', '-Gn', self._username],
                capture_output=True, text=True, timeout=5
            )
            user_groups = set(result.stdout.strip().split())
        except Exception:
            user_groups = {primary_grp} if primary_grp else set()

        # Show groups the user is already in + non-system groups (gid >= 100)
        try:
            all_groups = sorted(
                {g.gr_name for g in grp.getgrall()
                 if g.gr_gid >= 100 or g.gr_name in user_groups},
                key=str.lower
            )
        except Exception:
            all_groups = sorted(user_groups)

        GLib.idle_add(self._fill_groups, primary_grp, user_groups, all_groups)

    def _fill_groups(self, primary_grp: str, user_groups: set, all_groups: list):
        self._primary_group = primary_grp
        self._groups_checks = {}

        for child in self._groups_box.get_children():
            self._groups_box.remove(child)

        for name in all_groups:
            cb = Gtk.CheckButton(label=name)
            cb.set_active(name in user_groups)
            if name == primary_grp:
                cb.set_sensitive(False)
                cb.set_tooltip_text(_("Primary group — cannot be removed"))
            self._groups_checks[name] = cb
            self._groups_box.pack_start(cb, False, False, 0)

        self._groups_box.show_all()
        return False

    # ── Groups apply ──────────────────────────────────────────────────────────

    def _on_apply_groups(self, _btn):
        selected = [name for name, cb in self._groups_checks.items() if cb.get_active()]
        self._groups_apply_btn.set_sensitive(False)
        self._groups_status.set_text(_("Applying…"))

        def worker():
            ok, msg = self._apply_groups(selected)
            GLib.idle_add(self._on_groups_done, ok, msg)

        threading.Thread(target=worker, daemon=True).start()

    def _apply_groups(self, groups: list):
        try:
            groups_str = ','.join(groups)
            result = subprocess.run(
                ['pkexec', 'usermod', '-G', groups_str, self._username],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                return True, _("Applied. Re-login to take effect.")
            if result.returncode == 126:
                return False, _("Cancelled.")
            return False, result.stderr.strip() or _("Error updating groups")
        except Exception as e:
            logger.error(f"Error applying groups: {e}")
            return False, str(e)

    def _on_groups_done(self, ok: bool, msg: str):
        self._groups_apply_btn.set_sensitive(True)
        self._groups_status.set_text(msg)
        return False

    # ── Data loading ─────────────────────────────────────────────────────────

    def _find_current_avatar(self) -> str:
        face = Path.home() / ".face"
        if face.exists():
            return str(face)

        accounts_icon = ACCOUNTS_SERVICE_DIR / self._username
        if accounts_icon.exists():
            return str(accounts_icon)

        user_file = Path(f"/var/lib/AccountsService/users/{self._username}")
        if user_file.exists():
            try:
                for line in user_file.read_text().splitlines():
                    if line.startswith("Icon="):
                        icon_path = line.split("=", 1)[1].strip()
                        if icon_path and Path(icon_path).exists():
                            return icon_path
            except Exception:
                pass

        return ""

    def _load_current_avatar(self):
        path = self._find_current_avatar()
        if path:
            self._set_avatar_image(path)
        else:
            self.avatar_image.set_from_icon_name('avatar-default', Gtk.IconSize.DIALOG)

    def _on_name_changed(self, _entry):
        first = self._entries['first_name'].get_text().strip()
        last  = self._entries['last_name'].get_text().strip()
        initials = ''.join(p[0].upper() for p in (first + ' ' + last).split() if p)
        self._entries['initials'].set_text(initials)

    def _read_libreoffice(self) -> dict:
        data = {'first_name': '', 'last_name': '', 'initials': '', 'email': '',
                'home_phone': '', 'office_phone': '', 'fax': ''}
        if not LO_PREFS.is_file():
            return data
        try:
            for line in LO_PREFS.read_text().splitlines():
                if 'org.openoffice.UserProfile/Data' not in line:
                    continue
                try:
                    value = line.split('<value>')[1].split('</value>')[0].strip()
                except IndexError:
                    continue
                if   'name="givenname"' in line:              data['first_name']   = value
                elif 'name="sn"' in line:                     data['last_name']    = value
                elif 'name="initials"' in line:               data['initials']     = value
                elif 'name="mail"' in line:                   data['email']        = value
                elif 'name="homephone"' in line:              data['home_phone']   = value
                elif 'name="telephonenumber"' in line:        data['office_phone'] = value
                elif 'name="facsimiletelephonenumber"' in line: data['fax']        = value
        except Exception as e:
            logger.warning(f"LibreOffice read failed: {e}")
        return data

    def _update_libreoffice(self, first_name: str, last_name: str, initials: str,
                            email: str, home_phone: str, office_phone: str, fax: str):
        if not LO_PREFS.is_file():
            return
        try:
            field_map = {
                'givenname':                first_name,
                'sn':                       last_name,
                'initials':                 initials,
                'mail':                     email,
                'homephone':                home_phone,
                'telephonenumber':          office_phone,
                'facsimiletelephonenumber': fax,
            }
            content = LO_PREFS.read_text()

            # Remove any existing UserProfile/Data entries for our fields
            for attr in field_map:
                content = re.sub(
                    r'<item oor:path="/org\.openoffice\.UserProfile/Data">'
                    r'<prop oor:name="' + re.escape(attr) + r'"[^<]*'
                    r'<value>[^<]*</value></prop></item>\n?',
                    '', content
                )

            # Build new entries and insert before </oor:items>
            new_entries = ''.join(
                f'<item oor:path="/org.openoffice.UserProfile/Data">'
                f'<prop oor:name="{attr}" oor:op="fuse">'
                f'<value>{val}</value></prop></item>\n'
                for attr, val in field_map.items()
            )
            content = content.replace('</oor:items>', new_entries + '</oor:items>', 1)
            LO_PREFS.write_text(content)
            logger.info("LibreOffice user data updated")
        except Exception as e:
            logger.warning(f"LibreOffice update failed: {e}")

    def _load_user_data(self):
        self._entries['username'].set_text(self._username)

        # LibreOffice — fast, no blocking
        lo = self._read_libreoffice()
        first_name   = lo['first_name']
        last_name    = lo['last_name']
        initials     = lo['initials']
        email        = lo['email']
        home_phone   = lo['home_phone']
        office_phone = lo['office_phone']
        fax          = lo['fax']

        # GECOS — fast, fallback for name and phones
        # Format: full_name,room,work_phone,home_phone,other
        try:
            pw = pwd.getpwnam(self._username)
            gecos = pw.pw_gecos.split(',')
            if not first_name and gecos[0]:
                parts = gecos[0].split(None, 1)
                first_name = parts[0]
                last_name  = parts[1] if len(parts) > 1 else ''
            if not office_phone and len(gecos) > 2 and gecos[2] not in ('', 'none'):
                office_phone = gecos[2]
            if not home_phone and len(gecos) > 3 and gecos[3] not in ('', 'none'):
                home_phone = gecos[3]
        except Exception as e:
            logger.warning(f"Could not read GECOS data: {e}")

        if not initials and (first_name or last_name):
            initials = ''.join(p[0].upper() for p in (first_name + ' ' + last_name).split() if p)

        self._orig_home_phone   = home_phone
        self._orig_office_phone = office_phone
        self._orig_fax          = fax

        self._entries['first_name'].set_text(first_name)
        self._entries['last_name'].set_text(last_name)
        self._entries['initials'].set_text(initials)
        self._entries['email'].set_text(email)
        self._entries['home_phone'].set_text(home_phone)
        self._entries['office_phone'].set_text(office_phone)
        self._entries['fax'].set_text(fax)

        # D-Bus AccountsService — preferred for name/email; fetch async to avoid blocking the main loop
        threading.Thread(target=self._load_user_data_dbus, daemon=True).start()

    def _load_user_data_dbus(self):
        proxy = self._get_accounts_proxy(self._username)
        if not proxy:
            return
        rn = proxy.get_cached_property('RealName')
        em = proxy.get_cached_property('Email')

        first_name = None
        last_name  = None
        email      = None

        if rn:
            parts = rn.unpack().split(None, 1)
            if parts:
                first_name = parts[0]
                last_name  = parts[1] if len(parts) > 1 else ''
        if em:
            val = em.unpack()
            if val:
                email = val

        GLib.idle_add(self._apply_dbus_user_data, first_name, last_name, email)

    def _apply_dbus_user_data(self, first_name, last_name, email):
        if first_name is not None:
            self._entries['first_name'].set_text(first_name)
            if last_name is not None:
                self._entries['last_name'].set_text(last_name)
        if email is not None:
            self._entries['email'].set_text(email)
        return False

    # ── Avatar helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _crop_to_square(pixbuf: GdkPixbuf.Pixbuf) -> GdkPixbuf.Pixbuf:
        """Center-crop pixbuf to a square using the shorter dimension."""
        w = pixbuf.get_width()
        h = pixbuf.get_height()
        if w == h:
            return pixbuf
        side = min(w, h)
        x = (w - side) // 2
        y = (h - side) // 2
        return pixbuf.new_subpixbuf(x, y, side, side)

    def _set_avatar_image(self, path: str):
        try:
            raw = GdkPixbuf.Pixbuf.new_from_file(path)
            square = self._crop_to_square(raw)
            scaled = square.scale_simple(AVATAR_SIZE, AVATAR_SIZE, GdkPixbuf.InterpType.BILINEAR)
            self.avatar_image.set_from_pixbuf(scaled)
        except Exception:
            self.avatar_image.set_from_icon_name('avatar-default', Gtk.IconSize.DIALOG)

    def _on_choose(self, btn):
        dialog = Gtk.FileChooserDialog(
            title=_("Choose Avatar Image"),
            parent=self.parent_window,
            action=Gtk.FileChooserAction.OPEN
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN,   Gtk.ResponseType.OK
        )
        filt = Gtk.FileFilter()
        filt.set_name(_("Images"))
        for pattern in ('*.png', '*.jpg', '*.jpeg', '*.bmp', '*.webp'):
            filt.add_pattern(pattern)
        dialog.add_filter(filt)

        preview = Gtk.Image()
        dialog.set_preview_widget(preview)
        dialog.connect('update-preview', self._update_preview, preview)

        if dialog.run() == Gtk.ResponseType.OK:
            path = dialog.get_filename()
            dialog.destroy()
            self._open_crop_dialog(path)
        else:
            dialog.destroy()

    def _open_crop_dialog(self, path: str):
        try:
            raw = GdkPixbuf.Pixbuf.new_from_file(path)
        except Exception:
            return

        crop_dlg = CropDialog(self.parent_window, raw)
        response = crop_dlg.run()
        if response == Gtk.ResponseType.OK:
            self._pending_pixbuf = crop_dlg.get_cropped_pixbuf()
            scaled = self._pending_pixbuf.scale_simple(AVATAR_SIZE, AVATAR_SIZE, GdkPixbuf.InterpType.BILINEAR)
            self.avatar_image.set_from_pixbuf(scaled)
        crop_dlg.destroy()

    def _update_preview(self, dialog, preview):
        path = dialog.get_preview_filename()
        if path:
            try:
                raw = GdkPixbuf.Pixbuf.new_from_file(path)
                square = self._crop_to_square(raw)
                scaled = square.scale_simple(150, 150, GdkPixbuf.InterpType.BILINEAR)
                preview.set_from_pixbuf(scaled)
                dialog.set_preview_widget_active(True)
            except Exception:
                dialog.set_preview_widget_active(False)

    # ── Apply ─────────────────────────────────────────────────────────────────

    def _on_apply(self, _btn):
        self.apply_btn.set_sensitive(False)
        self.parent_window.show_progress(_("Applying user data…"))

        pending_pixbuf = self._pending_pixbuf
        username     = self._username
        first_name   = self._entries['first_name'].get_text().strip()
        last_name    = self._entries['last_name'].get_text().strip()
        initials     = self._entries['initials'].get_text().strip()
        email        = self._entries['email'].get_text().strip()
        home_phone   = self._entries['home_phone'].get_text().strip()
        office_phone = self._entries['office_phone'].get_text().strip()
        fax          = self._entries['fax'].get_text().strip()

        # If phones changed, ask for password (sudo chfn requires it, like Mugshot)
        password = None
        phones_changed = (home_phone != self._orig_home_phone or
                          office_phone != self._orig_office_phone)
        if phones_changed:
            dlg = PasswordDialog(self.parent_window)
            response = dlg.run()
            password = dlg.get_password() if response == Gtk.ResponseType.OK else None
            dlg.destroy()
            if response != Gtk.ResponseType.OK:
                self.apply_btn.set_sensitive(True)
                self.parent_window.hide_progress()
                return

        def worker():
            # Proxy creation is blocking — run in the worker thread, not the main loop
            proxy = self._get_accounts_proxy(username)

            messages = []
            ok = True

            if pending_pixbuf:
                avatar_ok, avatar_msg = self._set_avatar(pending_pixbuf, proxy)
                if not avatar_ok:
                    ok = False
                messages.append(avatar_msg)

            data_ok, data_msg = self._save_user_data(proxy, first_name, last_name, initials, email, home_phone, office_phone, fax, password)
            if not data_ok:
                ok = False
            messages.append(data_msg)

            final_msg = " | ".join(m for m in messages if m)
            GLib.idle_add(self._on_apply_done, ok, final_msg, home_phone, office_phone, fax)

        threading.Thread(target=worker, daemon=True).start()

    def _get_accounts_proxy(self, username: str):
        """Return a D-Bus proxy for the AccountsService User object, or None."""
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
            manager = Gio.DBusProxy.new_sync(
                bus, Gio.DBusProxyFlags.NONE, None,
                'org.freedesktop.Accounts',
                '/org/freedesktop/Accounts',
                'org.freedesktop.Accounts',
                None
            )
            result = manager.call_sync(
                'FindUserByName',
                GLib.Variant('(s)', (username,)),
                Gio.DBusCallFlags.NONE, -1, None
            )
            user_path = result.unpack()[0]
            return Gio.DBusProxy.new_sync(
                bus, Gio.DBusProxyFlags.NONE, None,
                'org.freedesktop.Accounts',
                user_path,
                'org.freedesktop.Accounts.User',
                None
            )
        except Exception as e:
            logger.warning(f"AccountsService D-Bus unavailable: {e}")
            return None

    def _dbus_set(self, proxy, method: str, value: str) -> bool:
        """Call a single-string setter on an AccountsService D-Bus proxy."""
        try:
            proxy.call_sync(
                method,
                GLib.Variant('(s)', (value,)),
                Gio.DBusCallFlags.NONE, -1, None
            )
            logger.info(f"D-Bus {method} OK: {value!r}")
            return True
        except Exception as e:
            logger.warning(f"D-Bus {method} failed: {e}")
            return False

    def _set_avatar(self, square_pixbuf: GdkPixbuf.Pixbuf, proxy=None):
        face_path = Path.home() / ".face"

        try:
            # Save cropped square pixbuf scaled to 512px (sufficient for any DM)
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tf:
                tmp_path = tf.name
            save_size = min(512, square_pixbuf.get_width())
            save_pixbuf = square_pixbuf.scale_simple(save_size, save_size, GdkPixbuf.InterpType.BILINEAR)
            save_pixbuf.savev(tmp_path, 'png', [], [])

            # ~/.face — primary location for LightDM and XFCE, no privileges needed
            shutil.copy2(tmp_path, str(face_path))
            os.chmod(str(face_path), 0o644)

            # ~/.face.icon — symlink used by some display manager greeters
            face_icon = Path.home() / ".face.icon"
            if face_icon.exists() or face_icon.is_symlink():
                face_icon.unlink()
            face_icon.symlink_to(face_path)

            # Notify AccountsService via D-Bus so Mugshot and the greeter pick it up
            if proxy:
                self._dbus_set(proxy, 'SetIconFile', str(face_path))

            Path(tmp_path).unlink(missing_ok=True)
            return True, _("Avatar updated")

        except Exception as e:
            logger.error(f"Error setting avatar: {e}")
            return False, str(e)

    def _save_user_data(self, proxy, first_name: str, last_name: str, initials: str,
                        email: str, home_phone: str, office_phone: str, fax: str,
                        password: str = None):
        try:
            full_name = f"{first_name} {last_name}".strip()

            if proxy:
                # D-Bus: no password needed for name/email via accounts-daemon polkit
                if full_name:
                    self._dbus_set(proxy, 'SetRealName', full_name)
                if email is not None:
                    self._dbus_set(proxy, 'SetEmail', email)
            else:
                logger.warning("AccountsService proxy unavailable — user data not saved")

            # Phones require sudo — password collected via PasswordDialog (like Mugshot)
            if password:
                for flag, value in [('-w', office_phone), ('-h', home_phone)]:
                    if value is not None:
                        try:
                            proc = subprocess.run(
                                ['/usr/bin/sudo', '-S', '/usr/bin/chfn', flag, value, self._username],
                                input=(password + '\n').encode(),
                                capture_output=True,
                                timeout=10
                            )
                            if proc.returncode != 0:
                                logger.warning(f"chfn {flag} failed: {proc.stderr.decode().strip()}")
                        except Exception as e:
                            logger.warning(f"chfn {flag} error: {e}")

            # LibreOffice update — user-writable, no password needed
            self._update_libreoffice(first_name, last_name, initials, email, home_phone, office_phone, fax)

            return True, _("User data saved")

        except Exception as e:
            logger.error(f"Error saving user data: {e}")
            return False, str(e)

    def _on_apply_done(self, ok: bool, message: str,
                       home_phone: str = '', office_phone: str = '', fax: str = ''):
        self.parent_window.hide_progress()
        if ok:
            self._pending_pixbuf = None
            # Update orig values so phone-change detection works next time
            self._orig_home_phone   = home_phone
            self._orig_office_phone = office_phone
            self._orig_fax          = fax
        self.apply_btn.set_sensitive(True)
