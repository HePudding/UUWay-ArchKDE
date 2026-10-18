"""Route only this UU Wine prefix's recording streams to system playback.

Wine exposes PulseAudio microphone devices as capture endpoints. UU's Windows
loopback selection can select one of those on Linux. Keep the user's default
microphone intact and move only authenticated owned-prefix streams.
"""
import json
import os
from pathlib import Path
import subprocess
import threading


def owned_stream(stream, prefix):
    properties = stream.get('properties', {})
    pid = properties.get('application.process.id', '')
    if not isinstance(pid, str) or not pid.isascii() or not pid.isdecimal() or int(pid) <= 1:
        return False
    root = Path('/proc') / pid
    try:
        if root.stat().st_uid != os.getuid():
            return False
        with (root / 'environ').open('rb') as source:
            environment = source.read(2 * 1024 * 1024 + 1)
        return (len(environment) <= 2 * 1024 * 1024 and
                os.fsencode('WINEPREFIX=' + str(prefix)) in environment.split(b'\0'))
    except OSError:
        return False


class AudioMonitor:
    def __init__(self, prefix):
        self.prefix = prefix
        self.done = threading.Event()
        self.thread = None

    @staticmethod
    def query(*args):
        return subprocess.run(['pactl', *args], capture_output=True, text=True, check=True, timeout=2).stdout

    def route(self):
        sink = self.query('get-default-sink').strip()
        sources = json.loads(self.query('--format=json', 'list', 'sources'))
        monitor = next((s for s in sources if s.get('name') == sink + '.monitor'), None)
        if monitor is None:
            return
        for stream in json.loads(self.query('--format=json', 'list', 'source-outputs')):
            if (stream.get('source') != monitor['index'] and type(stream.get('index')) is int
                    and owned_stream(stream, self.prefix)):
                self.query('move-source-output', str(stream['index']), monitor['name'])

    def start(self):
        def work():
            while not self.done.is_set():
                try:
                    self.route()
                except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
                    pass  # Audio server/stream may disappear during reconnection.
                self.done.wait(2)
        self.thread = threading.Thread(target=work, name='uu-system-audio', daemon=True)
        self.thread.start()

    def stop(self):
        self.done.set()
        if self.thread is not None:
            self.thread.join(timeout=10)
