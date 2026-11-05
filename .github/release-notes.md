# MK87 Studio · AJAZZ MK87 Cross-platform Configuration Tool

> Unofficial reverse-engineering project · **Windows + Linux** · fully offline & local
> 中文说明 / Chinese documentation: [README.zh-CN.md](https://github.com/w32394045-dotcom/ajazz-mk87/blob/main/README.zh-CN.md)

**MK87 Studio** is a cross-platform configuration tool for the AJAZZ MK87 mechanical keyboard
(USB `0C45:8047` / 2.4G `0C45:FEFE`), built from a complete reverse engineering of its protocol.
It runs fully locally: **no network access, no telemetry, no vendor driver required**.

Screenshots and the full feature list live in the repository README:
**[README.md (English)](https://github.com/w32394045-dotcom/ajazz-mk87/blob/main/README.md)** ·
**[README.zh-CN.md (简体中文)](https://github.com/w32394045-dotcom/ajazz-mk87/blob/main/README.zh-CN.md)**

## What's new in v0.1.8.2

> **This fixes the Linux startup crash reported on Ubuntu (v0.1.7/v0.1.8).** Root cause found: the app died
> because the packaged **PyQt6 could not be imported** — PyInstaller bundled system libraries
> (`libglib` etc.) copied from the build machine, and **GitHub switched its `ubuntu-latest` runner from
> 24.04 to 26.04 (glibc 2.43) between the v0.1.6 and v0.1.7 builds**. On a user's Ubuntu 24.04
> (glibc 2.39) those bundled libs fail to load: `GLIBC_2.43 not found` → Qt bindings disappear →
> silent startup crash (v0.1.6 worked because it was built on Ubuntu 24.04).

- **Fixed: Linux packages are now built on Ubuntu 22.04 (glibc 2.35)** — pinning the packaging runner
  (`ubuntu-22.04` instead of `ubuntu-latest`) means every bundled system library is compatible with
  Ubuntu 22.04 and newer, so a runner upgrade can no longer break users' machines.
- **Fixed: extra Qt 6.12 runtime libraries are bundled** — the PyInstaller spec also collects
  `libpcre2-16.so.0`, `libdouble-conversion.so.3`, `libb2.so.1`, `libmd4c.so.0` plus the missing
  `libxcb`/`libwayland` pieces, so the package is self-contained and starts even after a `dpkg -i`
  force-install that skips dependencies.
- **Fixed: deb/rpm dependency lists are complete** — `Depends` now includes the Qt 6.12 runtime
  libraries and the X11/Wayland/GTK runtime pieces (`libglib2.0-0`, `libgtk-3-0`, `libcairo2`,
  `libpango-1.0-0`, `libxcb-icccm4`, `libwayland-*`, …) with `t64 | plain` alternatives so both
  Ubuntu 22.04 and 24.04 resolve them. RPM `Requires` lists the Fedora equivalents (`pcre2`,
  `double-conversion`, `libb2`, `md4c`, `gtk3`, `xcb-util*`, `wayland-libs-*`, …). `sudo apt install
  ./mk87_*.deb` / `sudo dnf install ./mk87*.rpm` now installs everything in one go.
- **New CI gate: clean-container startup check** — every release now installs the freshly built `.deb`
  in a **clean `ubuntu:24.04` container** (and the `.rpm` in a clean `fedora` container), starts the
  packaged app under Xvfb and fails the release if it dies. This exact class of bug can no longer slip
  through.
- **Startup preflight + diagnostics** — before creating the window the app now imports PyQt6 itself and
  writes the **full traceback** to `~/.mk87-boot.log` and `<log dir>/qt-error.txt` if it fails (instead
  of pywebview's opaque "No Qt bindings could be found"); a desktop error dialog points at the report.
  `QT_API` is forced to `pyqt6` so an unrelated environment variable cannot make qtpy pick a missing
  binding. The `--no-tray` safety mode and boot-stage log from v0.1.8.1 remain available.
- **Tests**: 284 unit tests green; release now blocked by the clean-container startup checks.

### v0.1.8.1

> v0.1.8.1 is a diagnostic/hotfix release for a Linux startup crash reported on v0.1.8.

- **New: boot-stage log `~/.mk87-boot.log`** — the packaged app now writes timestamped stage markers
  (main start → logging ready → server started → window created → tray import/QApplication/queued
  install/shown/no-host) with immediate `fsync`. If the app crashes before or during tray setup, this
  file shows exactly how far it got even when the normal log directory looks empty.
- **New: `--no-tray` / `MK87_NO_TRAY=1` safety mode** — skips system-tray creation entirely, so the app
  can still be used when the crash is tray-related (closing the window then quits the app instead of
  hiding it). Useful for testing and as an emergency workaround.
- **Hardened Qt tray** — exceptions raised inside Qt slots no longer escape. PyQt6 turns an unhandled
  exception in a slot into `qFatal()` (an instant abort that looks exactly like a crash); tray and
  menu callbacks now catch everything, log it and degrade to "no tray". Every tray-creation stage is
  recorded in the boot log.
- **GNOME guard** — if GNOME is detected and the AppIndicator extension is not installed/enabled, Qt
  tray creation is skipped entirely (GNOME cannot display tray icons without it anyway), avoiding the
  riskiest startup path. Settings → System tray still offers the one-click installer.
- **CI speed-up (user request)** — `main` pushes now only run the offline unit tests on two runners
  (~2 min instead of ~10); `.deb` and `.rpm` are built on two **parallel** runners; packages are only
  built for `v*` tags or manual runs. New manual `linux-smoke` workflow builds the packaged app and
  runs it under Xvfb on a fresh Ubuntu runner, uploading `~/.mk87-boot.log`, stderr and session logs.
- **If v0.1.8 crashes on startup for you**: run `mk87` in a terminal (that prints the traceback), and
  send `~/.mk87-boot.log`. With v0.1.8.1 you can also start `mk87 --no-tray` to keep using the app
  while we fix the tray path.

### v0.1.8

> v0.1.8 fixes the two Linux desktop-integration bugs (terminal window on launch, tray icon with no
> right-click menu) and adds a "System tray" diagnostics card with one-click GNOME extension install.

- **Fixed: a terminal window no longer opens on Linux** — the packaged `.desktop` file had
  `Terminal=true`, so launching MK87 Studio from the app menu spawned a terminal that hosted the app.
  It is now `Terminal=false` (the autostart entry already was correct).
- **Fixed: right-clicking the Linux tray icon did nothing** — the tray used `pystray`, which in our
  bundle has neither the AppIndicator nor the GTK backend available, so it always fell back to its X11
  backend. That backend sets `HAS_MENU = False` and only handles left-click activate, so an icon
  appeared but a context menu was impossible to implement. Linux now uses **Qt `QSystemTrayIcon` +
  `QMenu`** (PyQt6 is already bundled by `pywebview[qt]`, no new runtime dependency): left-click shows
  the window, right-click opens the native menu (Show window / Launch at start-up / Quit) on KDE,
  XFCE, Cinnamon, MATE and Ubuntu GNOME. Windows keeps pystray unchanged.
- **New: "System tray" settings card + one-click GNOME extension install** — `GET /api/tray/status`
  reports the real tray backend and host availability, desktop environment, session type
  (Wayland/X11), GNOME Shell version, and whether the AppIndicator extension is installed/enabled. On
  plain GNOME the card offers **one-click install** (distro package via one `pkexec` password prompt;
  `dnf` / `apt` / `zypper` / `pacman` / `rpm-ostree` auto-detected), an "enable extension" action when
  it is installed but disabled, and a "copy commands" fallback. Windows/non-GNOME desktops report
  "no extension needed". After installing on Wayland, log out and back in (or `Alt+F2` → `r` on X11).
- **No zombie windows** — if the desktop really has no tray host, closing the window now quits the
  program instead of hiding it into nowhere; a banner in the main window explains this.
- **Tests**: **277 unit tests green** (32 new tray environment tests); the settings card was
  smoke-tested in both languages with a linkedom DOM harness (16 assertions). Linux tray/extension
  behaviour still needs verification on a real desktop.

### v0.1.7

> v0.1.7 fixes music rhythm on Linux and makes every device operation much faster.

- **Fixed: music rhythm could not start on Linux** (`POST /api/music/start` → HTTP 400). Audio capture
  relied on the external `parec` command (`pulseaudio-utils`), which PipeWire desktops do not install by
  default. Linux capture now uses **libpulse-simple** directly (`libpulse0` / `pulseaudio-libs`, already a
  package dependency) with `@DEFAULT_MONITOR@`, retries with the real `<default sink>.monitor` name from
  `pactl get-default-sink` when needed, and still falls back to `parec` if the library is missing. The audio
  device list no longer depends on `pactl`; the active backend is reported as `audioBackend` in
  `/api/music/status`; failures now log the real reason instead of just a 400.
- **Fixed: slow device commands** — the notification listener held the device lock during timed HID reads
  (Windows: 50–400 ms per read due to hidapi CancelIoEx; Linux: 50 ms, and continuous notifications could
  starve request threads). It now uses a **nonblocking read and sleeps outside the lock**. Real MK87
  (Windows) measurements: keymap matrix read **15 ms** (was ~325 ms via API), per-key LED read **24 ms**
  (was 100–250 ms), device info **2 ms**; music streaming stays at 20.0 fps.
- **Stall diagnostics** — process watchdog (logs gaps >2 s, i.e. whole-process freezes), device-lock waits
  >0.3 s, slow HID writes/reads, and `MK87Error` messages for HTTP 400s. This addresses the 2026-11-04 log,
  which had several 2–9 s windows with no log lines at all.
- **Tests**: 245 unit tests green (12 new Linux audio tests + nonblocking listener/read tests).
- **Linux users**: install the deb/rpm, then start music rhythm again; `mk87 --diagnose` remains available
  for device issues.
### v0.1.6

> v0.1.6 fixes the real Linux root cause behind the v0.1.5 "device not detected" report.

- **Fixed: the keyboard is now detected on Linux** — the PyPI `hidapi` wheel ships **two** Linux extension
  modules: `hid` (built against **libusb**) and `hidraw` (built against **hidraw**). cython-hidapi's build
  defaults to libusb, so `import hid` on Linux returned the libusb backend: enumerated paths look like
  `1-1.1:1.0` instead of `/dev/hidrawN`, `usage_page` is always 0 (libusb cannot read the report descriptor
  while enumerating), opening needs `/dev/bus/usb` permissions, and it competes with the kernel HID driver.
  The tool now imports `hidraw` on Linux — paths are `/dev/hidrawN`, usage pages come from sysfs, and the
  packaged udev rules grant access. The v0.1.5 report-descriptor parser remains as a fallback. Windows keeps
  using the native `hid` module (unchanged).
- **New: built-in self check** — `mk87 --diagnose` prints the hidapi backend, raw
  `hid.enumerate()` output, parsed interfaces, every `/sys/class/hidraw/hidraw*` node (vid/pid/interface/
  usage page/permissions), udev rule state and a verdict, and saves it to
  `~/.local/state/mk87/logs/diagnose.txt`.
- **Clearer Linux failures** — if only the libusb backend is available the tool refuses to report a bogus
  connection and says how to fix it; the "device not found" message points at `--diagnose`.
- **Cleaner Linux startup** — pywebview is asked for its Qt backend directly, removing the misleading
  `GTK cannot be loaded` traceback logged before the Qt fallback.
- **Tests**: 226 unit tests green (11 new: backend preference, interface-number 0 handling, sysfs HID_ID /
  interface parsing, libusb-style path fallback, libusb-backend guard). Windows real-device regression:
  `connected=True fw=1.19 battery=100 tftMax=140`.
- **Linux users**: install the deb/rpm (the udev rules are included), then run
  `mk87 --diagnose` if anything still looks wrong and attach the output.

### v0.1.5

> v0.1.5 was a Linux hot-fix attempt built on v0.1.4. Its assumption (hidraw backend reporting
> `usage_page = 0`) turned out to be wrong — see v0.1.6. The report-descriptor parser added there is still
> used as a fallback.

- **Linux hot-fix attempt** — assumed hidapi's Linux backend left `usage_page = 0` for every interface and
  rebuilt interface identity by reading each interface's HID report descriptor (hidapi
  `get_report_descriptor()`, with a sysfs `/sys/class/hidraw/hidrawN/device/report_descriptor` fallback).
  The parser is still used as a fallback, but the actual cause was the libusb backend being imported on
  Linux — fixed in v0.1.6.
- **Better Linux diagnostics** — the device log lists every enumerated interface
  (`product / pid / usagePage / usage / interface / payload / path`), and `probe/linux_hid_check.py` prints
  the same information for support reports.
- **Tests**: 215 unit tests green (9 new Linux transport tests: descriptor parser, interface enrichment,
  hidapi/sysfs fallback, Windows no-op).

### v0.1.4

> v0.1.4 is a bug-fix release on top of v0.1.3 (official music scheme). Everything below was reproduced
> from the reports, fixed, and re-verified on a real MK87 (USB, fw 1.19).

- **Fixed: key remap / macro bindings could not be saved** — the keymap page sent `key` / `fn` / `combo`
  action types, but the backend encoder only accepted `keyboard` / `func` / `combo (mods + key)`, so every
  "Apply changes" failed with HTTP 400. The backend now accepts both shapes, the frontend emits the canonical
  schema, and `GET /api/keymap` combo entries round-trip correctly after reload. On-device saves
  (canonical, legacy `key`, combo write + restore, FN-layer no-op) all returned 200 with byte-identical
  readback.
- **Fixed: UI stutters while music is playing** — with 66 fps frame streaming the protocol layer wrote one
  DEBUG line per HID notification: **1,169,834 lines / 207 MB in 47 minutes** (414 lines/s), causing periodic
  disk-I/O stalls. Notifications are now aggregated/rate-limited (`0x32` ACKs are no longer logged at all,
  other frames summarized every ~2 s): the same workload now grows the session log by **~33 KB/min (−99.9 %)**.
  Session logs are capped at 32 MB, old session logs are pruned at startup, and the macro table is read in
  bulk (**`GET /api/macros` 48 s → 0.37 s**, 201 → 7 requests).
- **Fixed: LED color overlay now covers all dynamic modes** — modes 14–22 (restored in v0.1.3) were not
  recolored before; they now share the same palette mapping as 1/2/4/5/13 (single-color presets still keep
  each mode's brightness structure, gradients keep their positional variation). Solid modes 6–11 keep the
  official sampled colors, backgrounds are untouched, and `default` is still byte-identical
  (220-combination snapshot regression).
- **Fixed: mode 4 could flash the legacy synthetic contour** — one all-zero spectrum frame (quiet passage,
  loopback dropout, 66 fps under load) used to switch Curvature Frequency Steps back to the old curvature
  outline. After the first real spectrum frame the renderer never falls back; silence is now simply empty bars.
- **Fixed: Amplitude / Background-brightness sliders were not applied** — the official-scheme sliders'
  `onInput` handler triggered a hot update but never wrote the new value back, so every update re-sent the
  stale 50 / 100. Dragging now applies the value live.
- **Fixed: browser-mode (`run.py`) logging** — uvicorn's default log config closed the tool's log handlers,
  leaving the session log empty and flooding stderr with thousands of "Logging error" tracebacks. `run.py`
  now starts uvicorn with `log_config=None`, matching the native shell.
- **Tests**: **206 unit tests green**; 17 headless-Chrome UI checks PASS; real-device re-verification:
  keymap/macro saves OK, `GET /api/macros` 0.37 s, color overlay verified on modes 4 / 14 / 22,
  66 fps streaming at 65.9 fps measured with 0 errors for 40 s and only +22 KB of session log, stopping
  restored the original lighting exactly (`0affffffff000000010603000000aa55`).

### v0.1.3

- **Music rhythm · Official scheme now matches the official v1 truth**: the display-mode dropdown has
  **21 modes** — the 12 exposed by the official v1 UI plus the 9 modes (14–22) previously reverse-engineered
  but not surfaced by the official UI. Mode 4 **Curvature Frequency Steps** was rewritten from fresh sampling
  of the official MusicPlug.exe: 17 frequency columns, bottom-aligned (1200/1200 frames), left-low →
  right-high on a log scale (~110 Hz–12 kHz), with a radial hue palette (origin `(2,8)`) rotating ~275°/s.
  Mode 100 (screen-light linkage) still falls back to Dance to the Beat.
- **LED color overlay (our enhancement)**: a third dropdown adds **default (official palette) + 9 presets** —
  ice blue `#00E5FF`, violet `#B36CFF`, hot pink `#FF2E88`, lime `#A8FF3E`, warm amber `#FF6A00`, sakura
  `#FF7AB6→#B36CFF`, aurora `#3EFF9A→#00E5FF→#7A5CFF`, sunset `#FFC400→#FF6A00→#FF2E88`, ice-fire
  `#00E5FF→#FEFEFE→#FF6A00`. It recolors all dynamic multicolor modes (**1/2/4/5/13 + 14–22**), keeps their
  animation, leaves solid modes 6–11 and the background untouched, and `default` is byte-for-byte identical
  to v0.1.2 (220-combination snapshot regression).
- **Native 20 / 60 / 66 fps (default 66)**: the official v1 plugin sends 530.5 packets/s ÷ 8 packets/frame
  ≈ **66.3 fps**, so the official scheme defaults to 66 fps (Current keeps 15/20/30). ≤30 fps keeps
  per-packet ACK; ≥60 fps writes 7 packets back-to-back and drains ACKs asynchronously (synchronous
  frame-end drain measured 19.8 ms/frame → 45.96 fps; async 8.85 ms/frame → 66 fps). Animation is
  `dt`-normalized, so playback speed is unchanged. On a real MK87 (USB, fw 1.19) 66 fps held
  **65.78–65.89 fps for 100 s** (0 errors); 60 fps = 60.06, 20 fps = 19.97. 21 modes × 10 colors switched
  with 0 errors; stopping restored mode 11 / brightness 6 / speed 3 (raw
  `0bffffffff000000010603000000aa55`).
- **Battery / lighting robustness**: battery, charging and work mode now refresh and log on every read
  (the connection log carries battery/charging/workMode/transport, plus a delayed 2 s re-read after connect);
  2.4G battery uses cmd `0x37` (first packet + `GET_ALL_LIGHTS_RGB_24G` response) with a 3-failure /
  5-minute circuit breaker that falls back to the USB path. The stuck-lighting bug is fixed at the root: the
  old music start wrote LED mode **128**, which fw 1.19 solidified into a per-key custom table when the
  restore never ran (process killed during shutdown). The music path now **never writes 128**, enters frame mode
  with 20/21 and verifies by readback, refuses to restore snapshots whose mode is 0/invalid, restores
  lighting before closing the device manager, and reports `isCustom` via `GET_ALL_LIGHTS_RGB` when the mode
  reads back 0. (The "looks like game mode after reboot" report had the same cause; no game-mode `0x21`
  command was ever sent.)
- **Tests**: 152 unit tests green; 17 headless-Chrome UI checks PASS (21 modes / 3 dropdowns / 10 colors /
  3 frame-rate tiers, live switching, no Chinese leakage in the English UI).

## Download

| Platform | File | Notes |
|---|---|---|
| Windows | `MK87Studio-*-win64-portable.zip` | Portable: unzip and run `MK87Config.exe` |
| Windows | `MK87Studio-*-win64-setup.exe` | Installer: shortcuts, optional autostart |
| Linux · Debian/Ubuntu | `mk87_*_amd64.deb` | `sudo apt install ./mk87_*.deb` |
| Linux · Fedora/openSUSE | `mk87-*.x86_64.rpm` | `sudo dnf install ./mk87-*.rpm` |

Linux packages ship the udev rules (root-free HID access); replug the keyboard after install.
Checksums are attached as `SHA256SUMS.txt`.

## Features (summary)

- **Key mapping / FN** — 87-key normal + FN layers; HID keys, combos, macros, media keys, firmware FUNC
  actions, disabled, restore-defaults; live 4-byte encoding preview.
- **Macros** — 100 slots / 3072 B: record keys, delays, press/release, repeat N times, press-to-stop.
- **Lighting** — 19 presets with color / brightness / speed / direction; RGB or single color.
- **Per-key RGB** — 87-key canvas with paint / erase / fill / eyedropper and drag-paint.
- **Music rhythm (USB only)** — system audio loopback → official renderers → native 20/60/66 fps per-key
  frame stream (official scheme defaults to 66; official v1 measured ≈66.3 fps). 21 display modes (12 official
  v1 modes + 9 restored modes 14–22), 11 background modes, LED color overlay (default + 9 presets); mode 4 is
  a 17-column bottom-aligned spectrum, mode 100 falls back to Dance to the Beat.
- **TFT screen (240×135)** — image / GIF / animated WebP / APNG compression & upload (≤140 frames, RGB565,
  per-packet ACK), time sync, restore official default animation.
- **Wireless** — 2.4G status, battery, sleep timer, disconnect / wake notification log.
- **Key test** — Windows RawInput / Linux evdev capture, 87-key tri-state highlight, event log and stats.
- **Device info** — firmware / battery / capability matrix, game mode, time sync, raw command console.
- **Backup & restore**, full logging with one-click diagnostic export, system tray, single instance,
  light / dark / system theme, Chinese / English live switch.

## Known limitations

- **Music rhythm is USB-only** (officially unsupported over 2.4G).
- **Music mode 100** (screen-light linkage) is computed by the official Music.exe, so it falls back to
  Dance to the Beat; the LED color overlay applies to all dynamic modes (6–11 stay their official colors).
- **TFT upload takes exclusive bus access**: don't use other features while uploading.
- Screen content is **write-only** — it cannot be read back; replacing or restoring it means re-uploading.
- With the 2.4G receiver and the keyboard USB sharing one USB 2.0 hub, Windows may fail to start the
  later-enumerated composite device (`0xC000009A`); see `docs/TEST-REPORT.md` §8.7.
- Magnetic switches, GIF lighting, on-board profiles and built-in screen pages are not supported by the
  firmware / hardware.

## Run from source

```bash
git clone https://github.com/w32394045-dotcom/ajazz-mk87.git
cd ajazz-mk87/driver
python -m venv .venv

# Windows
.venv\Scripts\pip install -r packaging\requirements.txt
.venv\Scripts\python shell.py      # native window
# .venv\Scripts\python run.py      # browser mode

# Linux
.venv/bin/pip install -r packaging/requirements.txt
.venv/bin/python shell.py           # native window (needs Qt WebEngine)
# .venv/bin/python run.py           # browser mode
```

## Documentation

- [docs/FEATURES.md](https://github.com/w32394045-dotcom/ajazz-mk87/blob/main/docs/FEATURES.md) — capability matrix
- [docs/TEST-REPORT.md](https://github.com/w32394045-dotcom/ajazz-mk87/blob/main/docs/TEST-REPORT.md) — on-device test report
- [docs/protocol.md](https://github.com/w32394045-dotcom/ajazz-mk87/blob/main/docs/protocol.md) — frame format & command table
- [docs/music-rhythm.md](https://github.com/w32394045-dotcom/ajazz-mk87/blob/main/docs/music-rhythm.md) — music rhythm & frame stream
- [docs/tft-page.md](https://github.com/w32394045-dotcom/ajazz-mk87/blob/main/docs/tft-page.md) — TFT screen protocol
- [docs/keymap.md](https://github.com/w32394045-dotcom/ajazz-mk87/blob/main/docs/keymap.md) — key mapping & macro format
- [docs/lighting.md](https://github.com/w32394045-dotcom/ajazz-mk87/blob/main/docs/lighting.md) — lighting protocol
- [driver/README.md](https://github.com/w32394045-dotcom/ajazz-mk87/blob/main/driver/README.md) — tool documentation

## License

MIT — see [LICENSE](https://github.com/w32394045-dotcom/ajazz-mk87/blob/main/LICENSE).

> Extracted vendor assets (`assets/`, `tools/Music.exe`, official bundle snippets under `docs/`) remain
> copyright of their respective owners and are **not covered** by the MIT license.

## Disclaimer

This is an unofficial reverse-engineering project for research and personal use only, not affiliated with
AJAZZ. Device firmware / protocol may change; back up your settings before any write operation.

---

*This page is built and published automatically by GitHub Actions.*
