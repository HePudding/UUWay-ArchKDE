"""Experimental single-output KDE backend using the installed kscreen-doctor.

The initial port only enumerates the current scale. KDE persists display writes;
remote mode changes are therefore disabled until temporary KWin output
transactions have been implemented. Capture/input work at the local mode.
"""
import hashlib
import json
import math
import subprocess
from pathlib import Path


def decode_kscreen(value):
    outputs = value['outputs']
    connected = [o for o in outputs if o.get('connected')]
    if len(connected) != 1 or not connected[0].get('enabled'):
        raise ValueError('KDE bridge requires exactly one connected, enabled output')
    output = connected[0]
    if (output['pos'] != {'x': 0, 'y': 0} or output['rotation'] != 1 or
            output.get('replicationSource', 0) or output.get('hdr') or output.get('wcg')):
        raise ValueError('Unsupported KDE layout, rotation or HDR')
    connector, scale = output['name'], output['scale']
    if (not isinstance(connector, str) or not 0 < len(connector) <= 128 or
            type(scale) not in (int, float) or not math.isfinite(scale) or not 0.5 <= scale <= 4):
        raise ValueError('Invalid KDE output identity or scale')
    entries = output['modes']
    if not 1 <= len(entries) <= 256:
        raise ValueError('Invalid KDE mode count')
    current = output['currentModeId']
    modes = []
    for entry in entries:
        identifier, size, rate = entry['id'], entry['size'], entry['refreshRate']
        width, height = size['width'], size['height']
        if (not isinstance(identifier, str) or not 0 < len(identifier) <= 128 or
                type(width) is not int or type(height) is not int or
                not 2 <= width <= 4096 or not 2 <= height <= 4096 or width % 2 or height % 2 or
                type(rate) not in (int, float) or not math.isfinite(rate) or not 1 <= rate <= 360):
            if identifier == current:
                raise ValueError('Current KDE mode exceeds bridge limits (maximum 360 Hz, 4096 pixels)')
            continue
        modes.append(dict(id=identifier, width=width, height=height, refresh=float(rate), scales=[float(scale)]))
    if len({m['id'] for m in modes}) != len(modes) or not any(m['id'] == current for m in modes):
        raise ValueError('Invalid or missing current KDE mode')
    # Only report the current mode: advertising a mode implies we can apply it.
    modes = [m for m in modes if m['id'] == current]
    state = dict(connector=connector, mode=current, scale=float(scale), modes=modes,
                 layout_mode=1, can_change_layout=False, underscanning=False, supports_underscanning=False)
    encoded = json.dumps(state, sort_keys=True, allow_nan=False).encode()
    state['serial'] = int.from_bytes(hashlib.sha256(encoded).digest()[:4], 'little')
    return state


class KScreenDisplay:
    def identity(self):
        from gi.repository import Gio, GLib
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        def call(method, arguments=None):
            return bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus',
                                 'org.freedesktop.DBus', method, arguments, None,
                                 Gio.DBusCallFlags.NONE, 2000, None).unpack()[0]
        return [Path('/proc/sys/kernel/random/boot_id').read_text().strip(), call('GetId'),
                call('GetNameOwner', GLib.Variant('(s)', ('org.kde.KWin',)))]

    def current(self):
        result = subprocess.run(['kscreen-doctor', '-j'], capture_output=True, text=True,
                                check=True, timeout=3)
        if len(result.stdout) > 1024 * 1024:
            raise ValueError('KScreen output exceeds bound')
        return decode_kscreen(json.loads(result.stdout))

    def configure(self, state, target, verify_only):
        current = self.current()
        if current['serial'] != state['serial']:
            raise RuntimeError('KDE display configuration changed')
        if target['mode'] != current['mode'] or target['scale'] != current['scale']:
            raise ValueError('Remote KDE display changes are not supported yet; use System Settings locally')

    def topology(self):
        state = self.current()
        mode = state['modes'][0]
        return dict(generation=state['serial'], connectors=[state['connector']],
                    layout=[dict(x=0, y=0, scale=state['scale'], transform=0, outputs=1)],
                    modes=[dict(width=mode['width'], height=mode['height'])])
