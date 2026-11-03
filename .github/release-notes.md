# MK87 Studio · AJAZZ MK87 Cross-platform Configuration Tool

> Unofficial reverse-engineering project · **Windows + Linux** · fully offline & local
> 中文说明 / Chinese documentation: [README.zh-CN.md](https://github.com/w32394045-dotcom/ajazz-mk87/blob/main/README.zh-CN.md)

**MK87 Studio** is a cross-platform configuration tool for the AJAZZ MK87 mechanical keyboard
(USB `0C45:8047` / 2.4G `0C45:FEFE`), built from a complete reverse engineering of its protocol.
It runs fully locally: **no network access, no telemetry, no vendor driver required**.

Screenshots and the full feature list live in the repository README:
**[README.md (English)](https://github.com/w32394045-dotcom/ajazz-mk87/blob/main/README.md)** ·
**[README.zh-CN.md (简体中文)](https://github.com/w32394045-dotcom/ajazz-mk87/blob/main/README.zh-CN.md)**

## What's new in v0.1.3

- **Music rhythm · Official scheme now matches the official v1 truth**: the display-mode dropdown has
  **21 modes** — the 12 exposed by the official v1 UI plus the 9 modes (14–22) previously reverse-engineered
  but not surfaced by the official UI. Mode 4 **Curvature Frequency Steps** was rewritten from fresh sampling
  of the official MusicPlug.exe: 17 frequency columns, bottom-aligned (1200/1200 frames), left-low →
  right-high on a log scale (~110 Hz–12 kHz), with a radial hue palette (origin `(2,8)`) rotating ~275°/s.
  Mode 100 (screen-light linkage) still falls back to Dance to the Beat.
- **LED color overlay (our enhancement)**: a third dropdown adds **default (official palette) + 9 presets** —
  ice blue `#00E5FF`, violet `#B36CFF`, hot pink `#FF2E88`, lime `#A8FF3E`, warm amber `#FF6A00`, sakura
  `#FF7AB6→#B36CFF`, aurora `#3EFF9A→#00E5FF→#7A5CFF`, sunset `#FFC400→#FF6A00→#FF2E88`, ice-fire
  `#00E5FF→#FEFEFE→#FF6A00`. It recolors only the dynamic multicolor modes **1/2/4/5/13**, keeps their
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
  Dance to the Beat; the LED color overlay applies to modes 1/2/4/5/13 only.
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
