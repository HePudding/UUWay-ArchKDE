#!/usr/bin/python3
"""Prepare the experimental Arch NVIDIA build, without starting remote access.

Uses reviewed upstream 1.3.0 binaries for unchanged components, then rebuilds
the display/input bridge, PipeWire consumer and Fcitx add-on from this checkout.
Downloads are fixed by SHA-256. Wine stays in /opt/wine-stable, outside pacman.
"""
import hashlib
import os
from pathlib import Path
import platform
import shutil
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'build/arch-setup'
WINE_BASE = 'https://dl.winehq.org/wine-builds/ubuntu/pool/main/w/wine/'
WINE = {
    'wine-stable_11.0.0.0~noble-1_amd64.deb': '04e7b4b995262c734019099d93277d8f219f7d180ebb65b5ccb3df7f97be1078',
    'wine-stable-amd64_11.0.0.0~noble-1_amd64.deb': '6cb835e2171b5572b17f1c06729735c2c7e40178239d7fa6c29ef14bd9b40d16',
    'wine-stable-i386_11.0.0.0~noble-1_i386.deb': 'b322b50f9e8bd59687840d9a7bad10d70b12ef9bdb873298e858ff93a6205e56',
    'wine-stable-dev_11.0.0.0~noble-1_amd64.deb': 'f7063898def11864b76be91f4e69f1e628b2113a2eb76e48f55ffcd0a49dc689',
}
CUDA_BASE = 'https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/'
CUDA = {
    'cuda-cudart-dev-12-1_12.1.105-1_amd64.deb': '531c1cc54bc76e383a4a43f04a60f5bb1b6e34e79fc3a4156422057e87031240',
    'cuda-driver-dev-12-1_12.1.105-1_amd64.deb': '49a0807b1f37da920a9417b3fa16d5e281c306595412e40ba4af04195d1655f4',
}


def run(*args, **kwargs):
    print('$', ' '.join(map(str, args)), flush=True)
    return subprocess.run(list(map(str, args)), check=True, cwd=ROOT, **kwargs)


def download(url, digest):
    path = WORK / url.rsplit('/', 1)[-1]
    if not path.exists():
        partial = path.with_suffix(path.suffix + '.partial')
        with urllib.request.urlopen(url, timeout=60) as response, partial.open('wb') as output:
            shutil.copyfileobj(response, output)
        partial.rename(path)
    with path.open('rb') as source:
        actual = hashlib.file_digest(source, 'sha256').hexdigest()
    if actual != digest:
        raise RuntimeError(f'Hash mismatch; remove {path} before retrying')
    return path


def extract(archive, target):
    target.mkdir(parents=True, exist_ok=True)
    member = next(s for s in subprocess.check_output(['ar', 't', str(archive)], text=True).splitlines()
                  if s.startswith('data.tar.'))
    compression = {'xz': '-J', 'zst': '--zstd', 'gz': '-z'}[member.rsplit('.', 1)[1]]
    with subprocess.Popen(['ar', 'p', str(archive), member], stdout=subprocess.PIPE) as source:
        run('tar', '-x', compression, '-C', target, stdin=source.stdout)
        source.stdout.close()
        if source.wait():
            raise RuntimeError('Debian archive extraction failed')


def main():
    if os.geteuid() == 0 or platform.machine() != 'x86_64' or not shutil.which('pacman'):
        raise SystemExit('Run as a normal user on x86_64 Arch Linux.')
    run('nvidia-smi', '-L')
    run('sudo', 'pacman', '-S', '--needed', 'base-devel', 'python-gobject', 'python-dbus',
        'gtk3', 'at-spi2-core', 'kscreen', 'libdrm', 'libei', 'json-c', 'libxfixes',
        'pipewire', 'libpulse', 'xorg-server-xvfb', 'xorg-xauth', 'xclip',
        'mingw-w64-gcc', 'vulkan-headers', 'glslang', 'fcitx5', 'curl', 'git', 'ripgrep',
        'lib32-libpulse', 'lib32-alsa-lib', 'lib32-gnutls', 'lib32-libx11',
        'lib32-libxext', 'lib32-freetype2', 'lib32-fontconfig', 'lib32-libxrender', 'lib32-libxrandr')
    WORK.mkdir(parents=True, exist_ok=True)
    if not Path('/opt/wine-stable').exists():
        for name, digest in WINE.items():
            extract(download(WINE_BASE + name, digest), WORK / 'wine')
        run('sudo', 'cp', '-a', WORK / 'wine/opt/wine-stable', '/opt/')
    if subprocess.check_output(['/opt/wine-stable/bin/wine', '--version'], text=True).strip() != 'wine-11.0':
        raise SystemExit('Existing /opt/wine-stable is not Wine 11.0; it has been preserved.')
    if not Path('/opt/wine-stable/include/wine/windows').is_dir():
        raise SystemExit('Existing Wine 11.0 needs its matching development headers.')
    for name, digest in CUDA.items():
        extract(download(CUDA_BASE + name, digest), WORK / 'cuda')
    release = download('https://github.com/GaryOAO/UUWay/releases/download/v1.3.0/uuway_1.3.0_amd64.deb',
                       'ce797f1e8f839c994fde71e8c73fb49c130295cb84a9bd5fd443d03b2955372a')
    extract(release, WORK / 'release')
    base = WORK / 'release/usr/lib/uuway'
    # Do not silently overwrite another build in this checkout.
    for name in ('backends', 'helpers', 'native-presenter', 'dxvk-capture'):
        target = ROOT / 'build' / name
        if not target.exists():
            shutil.copytree(base / 'build' / name, target)
    codec = ROOT / 'build/gpu-relay/nv-codec-headers'
    if not codec.exists():
        run('git', 'clone', '--depth', '1', '--branch', 'n13.0.19.0',
            'https://github.com/FFmpeg/nv-codec-headers.git', codec)
    if subprocess.check_output(['git', '-C', str(codec), 'rev-parse', 'HEAD'], text=True).strip() != 'e844e5b26f46bb77479f063029595293aa8f812d':
        raise SystemExit('Unexpected nv-codec-headers revision.')
    env = dict(os.environ, UURB_WINE_HEADERS='/opt/wine-stable/include',
               UURB_PIPEWIRE_HEADERS='/usr/include', UURB_GLSLANG=shutil.which('glslangValidator') or '/usr/bin/glslang',
               UURB_CUDA_HEADERS=str(WORK / 'cuda/usr/local/cuda-12.1/include'))
    for script in ('build-uu-native-input.sh', 'build-uu-native-display.sh',
                   'build-pipewire-native-probe.sh', 'build-native-ime.sh'):
        run('bash', ROOT / 'scripts' / script, env=env)
    for name in ('uu-native-input-bridge.dll', 'uurb-native-display.dll.so', 'uu-pipewire-native-probe'):
        shutil.copy2(ROOT / 'build/native-presenter' / name,
                     ROOT / 'build/backends/nvidia/native-presenter' / name)
    (ROOT / 'fcitx5').mkdir(exist_ok=True)
    shutil.copy2(ROOT / 'build/native-ime/libuurb-native-ime.so', ROOT / 'fcitx5/libuurb-native-ime.so')
    print('Prepared. Next run: python scripts/uuway_cli.py setup --installer /path/to/UURemote_Setup.exe')


if __name__ == '__main__':
    main()
