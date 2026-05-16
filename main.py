#!/usr/bin/env python3
import os
import sys

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

from core import run_application
from utils.constants import APPLICATION_ID
from utils.logger import logger
from core.i18n_manager import _


def main():
    os.environ['GTK_CSD'] = '0'
    os.environ['NO_AT_BRIDGE'] = '1'

    GLib.set_prgname(APPLICATION_ID)
    GLib.set_application_name("Soplos Theme Manager")

    try:
        return run_application()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 0
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        try:
            dialog = Gtk.MessageDialog(
                modal=True,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK,
                text=_("Failed to start:\n{error}").format(error=e)
            )
            dialog.run()
            dialog.destroy()
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
