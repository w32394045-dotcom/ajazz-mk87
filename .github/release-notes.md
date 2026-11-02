# MK87 Studio · AJAZZ MK87 Cross-platform Configuration Tool

> Unofficial reverse-engineering project · **Windows + Linux** · fully offline & local
> 中文说明 / Chinese documentation: [README.zh-CN.md](https://github.com/w32394045-dotcom/ajazz-mk87/blob/main/README.zh-CN.md)

**MK87 Studio** is a cross-platform configuration tool for the AJAZZ MK87 mechanical keyboard
(USB `0C45:8047` / 2.4G `0C45:FEFE`), built from a complete reverse engineering of its protocol.
It runs fully locally: **no network access, no telemetry, no vendor driver required**.

Screenshots and the full feature list live in the repository README:
**[README.md (English)](https://github.com/w32394045-dotcom/ajazz-mk87/blob/main/README.md)** ·
**[README.zh-CN.md (简体中文)](https://github.com/w32394045-dotcom/ajazz-mk87/blob/main/README.zh-CN.md)**

## What's new in v0.1.2

- **Music rhythm · Official scheme**: the music page now has two schemes. **Official** (default) uses the exact
  same settings as the official v1 plugin — 12 display modes, 11 background modes, background brightness and
  amplitude — and renders the keyboard with the official renderer code.
- **Hot switching**: switch schemes, display/background modes or move the sliders while music is playing —
  no stop/restart needed (`POST /api/music/update` applies all changes live).
- **11 of the 12 official renderers are now direct ports** of the official code (modes 1, 4, 13–22), including
  the built-in dual-heart coordinate tables for mode 22. Mode 100 (screen-light linkage) is computed by the
  official Music.exe, so it falls back to Dance to the Beat.
- Bilingual README (English default + Simplified Chinese) with embedded screenshots; MIT license.
- English UI fix: `<html lang>` was not set on first paint, so dynamic mode names stayed Chinese.

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
- **Music rhythm (USB only)** — system audio loopback → official renderers (Dance to the Beat / Dust Glow
  Spiral / Firefly Trail / Curvature Frequency Steps) → 20 fps per-key frame stream.
- **TFT screen (240×135)** — image / GIF / animated WebP / APNG compression & upload (≤140 frames, RGB565,
  per-packet ACK), time sync, restore official default animation.
- **Wireless** — 2.4G status, battery, sleep timer, disconnect / wake notification log.
- **Key test** — Windows RawInput / Linux evdev capture, 87-key tri-state highlight, event log and stats.
- **Device info** — firmware / battery / capability matrix, game mode, time sync, raw command console.
- **Backup & restore**, full logging with one-click diagnostic export, system tray, single instance,
  light / dark / system theme, Chinese / English live switch.

## Known limitations

- **Music rhythm is USB-only** (officially unsupported over 2.4G).
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
