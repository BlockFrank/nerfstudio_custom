from __future__ import annotations


def handle_gui() -> int:
    from ns_installer.gui.app import launch_gui
    launch_gui()
    return 0