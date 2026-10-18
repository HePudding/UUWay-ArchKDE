"""Desktop selection shared by setup, capture and display services."""
import os


def is_kde():
    return 'KDE' in os.environ.get('XDG_CURRENT_DESKTOP', '').upper().split(':')


def supported_session():
    desktops = os.environ.get('XDG_CURRENT_DESKTOP', '').upper().split(':')
    return os.environ.get('XDG_SESSION_TYPE') == 'wayland' and bool({'GNOME', 'KDE'} & set(desktops))


def display_backend():
    if is_kde():
        from native_display_kde import KScreenDisplay
        return KScreenDisplay()
    from native_display_config import MutterDisplay
    return MutterDisplay()
