# Arch Linux / KDE Wayland experimental port

This fork supports one connected, enabled SDR output at the origin, without rotation.
It reads the current mode from `kscreen-doctor -j`. Only that mode and the current
scale are advertised to UU. Remote display writes are rejected, so KDE's persistent
output configuration cannot be changed by an untested rollback implementation.
GNOME retains its existing display backend.

## Prepare and install

Run as your desktop user in this checkout:

```bash
python scripts/prepare-arch.py
python scripts/uuway_cli.py setup --installer /path/to/UURemote_Setup.exe
```

Enable Arch's multilib repository first. A working NVIDIA driver with NVENC is
required. The preparation script installs build/runtime dependencies with pacman;
it does not install a graphics driver. It stages unchanged components from the
SHA-256-pinned upstream UUWay 1.3.0 package, installs the SHA-256-pinned WineHQ
11.0 runtime and development files under `/opt/wine-stable`, and builds this fork's
display bridge, input hook, PipeWire consumer and Fcitx5 add-on locally. An existing
Wine directory is preserved and must already contain Wine 11.0 and matching headers.
Build downloads stay under `build/arch-setup`.

Download the Windows UU installer from [NetEase](https://uuyc.163.com/).
Sign in and grant screen sharing when requested. The installed user units refer
to this checkout and to immutable runtime bundles; keep the checkout in place.
The upstream `install.sh`, Debian updates and GDM autologin configuration do not
provide an Arch installation or SDDM autologin path.

If Fcitx5 is already running, load the newly installed add-on by quitting the
existing instance completely before starting it again. A replacement race can
leave the old process running without the add-on. Confirm that the private
`~/.local/state/uurb/ime.sock` socket exists. Do this between text input operations;
restarting Fcitx5 interrupts an unfinished local composition.

Diagnostics and later rebuilds:

```bash
python scripts/uuway_cli.py doctor
python scripts/uuway_cli.py refresh
```

`refresh` interrupts an active UU connection. It packages newly built components
and restarts the bridge, while preserving the independent text/display daemons.
Do not use `uuway update install` on Arch: that upstream updater installs Debian packages.

## Capture and audio

KDE capture negotiates `SPA_META_SyncTimeline` and the two extra syncobj descriptors.
The consumer waits for the producer's acquire point before reading the frame and
signals release after its synchronous GPU read. Superseded and cursor-only buffers
also follow the acquire/release lifecycle. Synchronization failure ends that capture
generation rather than reading a buffer still being rendered. See
[PipeWire's DMA-BUF contract](https://docs.pipewire.org/1.2/page_dma_buf.html).
This path requires modern PipeWire headers and libdrm; GNOME's existing implicit
DMA-BUF fence path remains the default there.

The KDE bridge routes recording streams whose Linux process belongs to the owned
UU Wine prefix to the default playback sink's monitor. It follows reconnects and
playback-device changes without changing the user's default microphone or another
application's recording stream. A missing audio server/monitor leaves routing unchanged.

## Validation

Environment tested: Arch Linux, Plasma 6.8, PipeWire 1.6.9, NVIDIA 615.78.08,
RTX 5070 Ti, one 3840×2160 output at 160Hz with scale 1.7, WineHQ 11.0.
The original DMA-BUF/NVENC path encoded and independently decoded 1,131 live frames;
the explicit sync path also passed live H.264 encode/decode. This is local capture
evidence, not a promise of 160 remote frames per second.

The user confirmed remote video, mouse/keyboard and phone IME text. Dynamic-video
flicker and system-audio routing require controller-side retesting after the
explicit-sync/audio changes. Multi-output, HDR, remote mode changes and AMD on KDE
remain unverified or unsupported.

The targeted regression suite covers CLI setup, desktop selection, high-refresh
native RPC parsing, service lifetime, bundle verification, audio stream isolation,
and the capture broker. One unrelated existing process-mapping test fails on this
host's Btrfs device-number mapping (`stat` versus `/proc/PID/maps`); it is not used
to enable KDE remote display writes, which remain disabled.
