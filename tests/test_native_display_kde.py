import copy
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from native_display_kde import decode_kscreen, KScreenDisplay
from native_desktop import supported_session, is_kde
from native_display_config import DisplayTransaction


def fixture():
    return {'outputs': [dict(connected=True, enabled=True, name='DP-1', scale=1.7,
                            pos={'x': 0, 'y': 0}, rotation=1, currentModeId='2', hdr=False,
                            modes=[dict(id='1', size={'width': 1920, 'height': 1080}, refreshRate=60),
                                   dict(id='2', size={'width': 3840, 'height': 2160}, refreshRate=160)])]}


class KDETests(unittest.TestCase):
    def test_high_refresh_fractional_scale_and_no_remote_modes(self):
        state = decode_kscreen(fixture())
        self.assertEqual(state['scale'], 1.7)
        self.assertEqual(state['modes'], [dict(id='2', width=3840, height=2160, refresh=160., scales=[1.7])])
        backend = KScreenDisplay()
        with patch.object(backend, 'current', return_value=state):
            plan = DisplayTransaction(backend).prepare(state['serial'], 3840, 2160, 160, 1.7)
            self.assertFalse(DisplayTransaction(backend).apply(plan)['changed'])
            with self.assertRaises(ValueError):
                backend.configure(state, dict(mode='1', scale=1.7), False)

    def test_serial_tracks_local_changes(self):
        value = fixture()
        initial = decode_kscreen(value)['serial']
        self.assertEqual(initial, decode_kscreen(copy.deepcopy(value))['serial'])
        value['outputs'][0]['scale'] = 2
        self.assertNotEqual(initial, decode_kscreen(value)['serial'])

    def test_unsupported_layouts_fail_closed(self):
        for field, value in [('hdr', True), ('rotation', 2), ('pos', {'x': 10, 'y': 0}),
                             ('scale', float('nan')), ('currentModeId', 'missing'), ('enabled', False)]:
            config = fixture()
            config['outputs'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                decode_kscreen(config)
        config = fixture()
        config['outputs'] *= 2
        with self.assertRaises(ValueError):
            decode_kscreen(config)

    def test_refresh_bounds(self):
        for rate in [0, float('nan'), 361]:
            value = fixture()
            value['outputs'][0]['modes'][1]['refreshRate'] = rate
            with self.assertRaises(ValueError):
                decode_kscreen(value)

    def test_desktop_tokens(self):
        for desktop, expected in [('KDE', True), ('ubuntu:GNOME', True), ('fakeKDE', False), ('sway', False)]:
            with patch.dict(os.environ, XDG_CURRENT_DESKTOP=desktop, XDG_SESSION_TYPE='wayland'):
                self.assertEqual(supported_session(), expected)
                self.assertEqual(is_kde(), desktop == 'KDE')


if __name__ == '__main__':
    unittest.main()
