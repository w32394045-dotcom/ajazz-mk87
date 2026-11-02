# AJAZZ MK87 · Reverse Engineering + Cross-platform Config Tool

**English** · [简体中文](README.zh-CN.md)

**MK87 Studio** is an unofficial, fully offline **cross-platform configuration tool** (Windows + Linux) for the
**AJAZZ MK87** mechanical keyboard, built from a complete reverse engineering of its USB / 2.4G protocol.

- **Device**: USB `VID 0x0C45 / PID 0x8047`; 2.4G receiver `VID 0x0C45 / PID 0xFEFE`
- **Official web driver** (reverse-engineered): `https://ajazz.driveall.cn`
- **Everything local**: no network access, no telemetry, no vendor driver required
- **Latest release**: [v0.1.1](https://github.com/w32394045-dotcom/ajazz-mk87/releases/latest)

## Screenshots

| Lighting (light · Chinese) | Dark UI (English) |
|---|---|
| <img src="driver/docs/screenshots/ui-light-zh.png" width="480" alt="Lighting page, light theme"> | <img src="driver/docs/screenshots/ui-dark-en.png" width="480" alt="Lighting page, dark theme"> |

| Music rhythm · Current | Music rhythm · Official |
|---|---|
| <img src="capture/ui_music_preview/03-music-current-running.png" width="480" alt="Music rhythm, Current scheme"> | <img src="capture/ui_music_preview/02-music-official-running.png" width="480" alt="Music rhythm, Official scheme"> |

| TFT screen (240×135) | Logs & diagnostics |
|---|---|
| <img src="driver/docs/screenshots/tft-upload-limits.png" width="480" alt="TFT screen upload"> | <img src="driver/docs/screenshots/logs-settings.png" width="480" alt="Logs and diagnostics"> |

> The two music screenshots are from demo mode (no keyboard attached); the others are real-device UI.

## Download

👉 **https://github.com/w32394045-dotcom/ajazz-mk87/releases/latest**

| Platform | File | Notes |
|---|---|---|
| Windows | `MK87Studio-*-win64-portable.zip` | Portable: unzip and run `MK87Config.exe` |
| Windows | `MK87Studio-*-win64-setup.exe` | Installer: shortcuts, optional autostart |
| Linux · Debian/Ubuntu | `mk87_*_amd64.deb` | `sudo apt install ./mk87_*.deb` |
| Linux · Fedora/openSUSE | `mk87-*.x86_64.rpm` | `sudo dnf install ./mk87-*.rpm` |

Linux packages ship the udev rules (root-free HID access); replug the keyboard after install.
Releases are built by GitHub Actions and come with a `SHA256SUMS.txt`.

## What's new in v0.1.1

- **Music rhythm** keyboard preview now has two tabs — **Current** (local spectrum animation) and **Official**
  (replays the exact per-key frames the backend sends to the keyboard, frame-accurate).
- Fixed the English UI: `<html lang>` was not set on first paint, so dynamic mode names stayed Chinese.
- Added offline regression tests for the music preview and a headless-Chrome UI self-check script.

## Features

- **Lighting** — 19 presets with color / brightness (1–6) / speed (1–6) / direction; RGB or single color.
- **Per-key RGB** — 87-key canvas: paint, erase, fill, eyedropper, drag-paint, presets; writes the custom LED
  table shared by firmware modes 20 / 21 / 128.
- **TFT screen (240×135)** — image / GIF / animated WebP / APNG → compression pipeline (downscale, frame
  extraction, dedupe, RGB565 dithering) → animation upload (≤140 frames), time sync, restore official animation.
- **Macros** — 100 slots / 3072 B editor: record keys, delays, press/release, repeat N times, press-to-stop.
- **Key mapping / FN** — 87-key normal + FN layers: HID keys, combos, macros, firmware FUNC actions, disabled,
  restore-defaults, live 4-byte encoding preview. FN layer is read-only over 2.4G.
- **Music rhythm (USB only)** — two schemes: **Official** (identical settings to the official v1 plugin:
  12 display modes / 11 background modes / background brightness / amplitude — hot-switchable while playing)
  and **Current** (this tool's own mode / frame rate / sensitivity) → 20 fps per-key frame stream.
  11 of the 12 official renderers (1/4/13–22) are direct ports of the official code; mode 100 (screen
  linkage) is computed by Music.exe, so it falls back to Dance to the Beat.
- **Wireless** — 2.4G status, battery, sleep timer (0/1/10/20/30 min), disconnect / wake notification log.
- **Key test** — OS-level capture (Windows RawInput / Linux evdev), 87-key tri-state highlight, event log, stats.
- **Device info** — firmware / battery / capability matrix, game-mode fields, time sync, raw command console.
- **Backup & restore** — full JSON export / import with confirmation before restore.
- **Settings** — light / dark / system theme, Chinese / English live switch, autostart, clean quit.
- **Misc** — system tray, single instance, full logging with one-click diagnostic export.

## Device capabilities (verified on hardware)

| Capability | Status |
|---|---|
| 87-key remapping (HID / combos / macros / FN / media keys) | ✅ read & write |
| FN layer remapping (26 default actions) | ✅ read & write |
| 19 lighting effects + brightness / speed + per-key custom LEDs | ✅ |
| Per-key live frame stream (20 fps, music / AI effects) | ✅ USB only (2.4G not supported by firmware) |
| Macros: 100 slots / 3072 B, format fully decoded | ✅ read & write |
| TFT 240×135 custom animation (≤140 frames, ~63 KB/s) | ✅ upload & play |
| Screen time sync | ✅ |
| Game mode / sleep settings, battery / firmware info | ✅ partial fields |
| 2.4G wireless (shares config with USB, same matrix) + disconnect / wake notifications | ✅ |
| Magnetic switches, GIF lighting, on-board profiles, built-in screen pages, 12/24h display | ⛔ not supported by firmware / hardware |

## Repository contents

1. **Reverse-engineering docs (`docs/`)** — protocol frame format, 66 command table, key/macro binary formats,
   19 lighting effect parameters, per-key LED frame stream, TFT screen (240×135 animation / time sync),
   music rhythm, 2.4G wireless (sleep/wake notifications), official i18n strings and an unknown-items list.
2. **Reference implementations & probes (`scripts/`, `probe/`, `capture/`)** — codec reference implementations
   with self-check assertions, Python HID clients that drive the device directly, and Chrome CDP WebHID capture tools.
3. **Cross-platform tool (`driver/`)** — the released Windows + Linux app covering all verified capabilities.

```
docs/       reverse-engineering docs and measured data (JSON evidence)
scripts/    reference implementations and extraction scripts (Node/Python)
probe/      on-device test scripts (Python + hidapi)
capture/    Chrome CDP WebHID captures and recorded evidence
assets/     official web-driver bundle extracts (analysis input)
driver/     cross-platform configuration tool (released)
```

## Reverse-engineering docs

- [docs/FEATURES.md](docs/FEATURES.md) — capability matrix and corrections (start here)
- [docs/TEST-REPORT.md](docs/TEST-REPORT.md) — on-device test report (Phase 0–7 with evidence)
- [docs/protocol.md](docs/protocol.md) — frame format and command table
- [docs/deepdive-mk87.md](docs/deepdive-mk87.md) — device info / game mode / screen time
- [docs/keymap.md](docs/keymap.md) — key mapping and macro binary format (§16)
- [docs/lighting.md](docs/lighting.md) — lighting protocol
- [docs/tft-page.md](docs/tft-page.md) — TFT screen protocol
- [docs/music-rhythm.md](docs/music-rhythm.md) — music rhythm and per-key frame stream
- [docs/wireless-profiles-led-animation.md](docs/wireless-profiles-led-animation.md) — 2.4G wireless
- [docs/key-events.md](docs/key-events.md) — key event capture (no vendor event frames; RawInput/evdev required)
- [docs/i18n-and-unknowns.md](docs/i18n-and-unknowns.md) — official strings and open questions
- [driver/README.md](driver/README.md) — the tool itself (Chinese)

## Build & run from source

```bash
git clone https://github.com/w32394045-dotcom/ajazz-mk87.git
cd ajazz-mk87/driver
python -m venv .venv

# Windows
.venv\Scripts\pip install -r packaging\requirements.txt
.venv\Scripts\python shell.py      # native window (recommended)
# .venv\Scripts\python run.py      # browser mode

# Linux
.venv/bin/pip install -r packaging/requirements.txt
.venv/bin/python shell.py           # native window (needs Qt WebEngine)
# .venv/bin/python run.py           # browser mode
```

## License

MIT — see [LICENSE](LICENSE).

> Extracted vendor assets (`assets/`, `tools/Music.exe`, official bundle snippets under `docs/`) remain
> copyright of their respective owners and are **not covered** by the MIT license.

## Disclaimer

This is an unofficial reverse-engineering project for research and personal use only, not affiliated with
AJAZZ. Device firmware / protocol may change; back up your settings before any write operation.
