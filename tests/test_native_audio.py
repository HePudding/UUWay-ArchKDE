import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from native_audio import AudioMonitor, owned_stream


class AudioTests(unittest.TestCase):
    def test_only_owned_prefix_streams_are_selected(self):
        prefix = Path(os.environ.get('WINEPREFIX', '/not-a-wine-process'))
        stream = {'properties': {'application.process.id': str(os.getpid())}}
        # The test runner normally has no Wine prefix and must never be routed.
        if 'WINEPREFIX' not in os.environ:
            self.assertFalse(owned_stream(stream, prefix))
        for pid in ('', '../self', '0', '-1', '１２３'):
            self.assertFalse(owned_stream({'properties': {'application.process.id': pid}}, prefix))

    def test_move_only_uu_stream_and_follow_current_playback_device(self):
        monitor = AudioMonitor(Path('/owned-prefix'))
        streams = '[{"index":10,"source":5},{"index":11,"source":5},{"index":12,"source":9}]'
        def query(*args):
            if args == ('get-default-sink',): return 'speaker\n'
            if args == ('--format=json', 'list', 'sources'): return '[{"name":"speaker.monitor","index":9}]'
            if args == ('--format=json', 'list', 'source-outputs'): return streams
            return ''
        with patch.object(monitor, 'query', side_effect=query) as run, \
                patch('native_audio.owned_stream', side_effect=lambda s, _: s['index'] == 10):
            monitor.route()
            moves = [c.args for c in run.call_args_list if c.args[0] == 'move-source-output']
            self.assertEqual(moves, [('move-source-output', '10', 'speaker.monitor')])

    def test_missing_monitor_preserves_microphone_selection(self):
        monitor = AudioMonitor(Path('/owned-prefix'))
        with patch.object(monitor, 'query', side_effect=['speaker', '[]']) as run:
            monitor.route()
            self.assertEqual(run.call_count, 2)
