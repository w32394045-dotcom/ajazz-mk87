# AJAZZ MK87 · Reverse Engineering + Cross-platform Config Tool

**English** · [简体中文](README.zh-CN.md)

**MK87 Studio** is an unofficial, fully offline **cross-platform configuration tool** (Windows + Linux) for the
**AJAZZ MK87** mechanical keyboard, built from a complete reverse engineering of its USB / 2.4G protocol.

- **Device**: USB `VID 0x0C45 / PID 0x8047`; 2.4G receiver `VID 0x0C45 / PID 0xFEFE`
- **Official web driver** (reverse-engineered): `https://ajazz.driveall.cn`
- **Everything local**: no network access, no telemetry, no vendor driver required
- **Latest release**: [v0.1.8.7](https://github.com/w32394045-dotcom/ajazz-mk87/releases/latest)

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
| Windows | `MK87Studio-*-win64-setup.exe` | Installer: selectable Start Menu / desktop shortcuts |
| Linux · Debian/Ubuntu | `mk87_*_amd64.deb` | `sudo apt install ./mk87_*.deb` |
| Linux · Fedora/openSUSE | `mk87-*.x86_64.rpm` | `sudo dnf install ./mk87-*.rpm` |

Linux packages ship the udev rules (root-free HID access); replug the keyboard after install.
Releases are built by GitHub Actions and come with a `SHA256SUMS.txt`.

If the app does not detect the keyboard on Linux, run the built-in self check first:

```bash
mk87 --diagnose     # prints hidapi backend, hidraw nodes, usage pages, permissions
```

It writes the same report to `~/.local/state/mk87/logs/diagnose.txt`. The app must use hidapi's **hidraw**
backend on Linux (module `hidraw`, paths `/dev/hidrawN`); the `hid` module bundled in the PyPI wheel is the
**libusb** backend and cannot be used for this keyboard (wrong device paths, no usage pages, USB-device
permissions and kernel-driver conflicts). See "What's new in v0.1.6".

### Windows installer troubleshooting

If the Windows installer stops with

> Setup was unable to create the directory "C:\Users\<name>\AppData\Local\Temp\is-XXXX.tmp".
> Error 5: Access denied.

**the download is not corrupt and the app is not at fault** - Windows refused to let the installer
unpack itself into the current user's `%TEMP%` folder. This happens *before* the installer asks for
administrator rights, so it is unrelated to the install location, and it does not affect the
portable build. Typical causes: security software scanning/intercepting the freshly downloaded
unsigned exe, a Temp folder whose permissions were changed by a cleanup/optimizer tool, or the
installer being launched from a restricted context.

Fix it in this order (item 1 has been verified on the user machine):

1. **Right-click `MK87Studio-*-win64-setup.exe` -> "Run as administrator".** This is the quickest
   fix and the one confirmed to work; if the file is still in `Downloads`, you can also just retry -
   the error is often transient.
2. Repair the current user's Temp permissions (normal PowerShell, no admin needed):
   ```powershell
   icacls "$env:LOCALAPPDATA\Temp" /grant "$env:USERDOMAIN\$env:USERNAME:(OI)(CI)F" /T /C
   ```
3. If Windows Defender is intercepting the unsigned installer, add it as an exclusion
   (Windows Security -> Virus & threat protection -> Manage settings -> Exclusions), or pause
   real-time protection for the duration of the install, then turn it back on.
4. Move the installer out of `Downloads` (some security tools add extra deny rules to that folder)
   into e.g. the Desktop or `C:\Temp`, and run it again.
5. Fall back to the portable build: download `MK87Studio-*-win64-portable.zip`, unzip anywhere and
   run `MK87Config.exe`. It never unpacks to `%TEMP%` and installs nothing.

Since v0.1.8.5 the installer also writes a log to `%TEMP%\Setup Log <date> #<n>.txt`; if none of
the above helps, attach that log and the output of `icacls "$env:LOCALAPPDATA\Temp"` to your report.

### Windows Defender false positive (v0.1.8.7)

> Windows Defender flags the **CI-built** `MK87Config.exe` inside the official v0.1.8.7 installer
> as `Trojan:Win32/Bearfoos.A!ml` (it removes the exe during install, together with the Start-Menu
> shortcut / uninstall key). This is a machine-learning false positive common to unsigned
> PyInstaller binaries - **not an infection**: a local build of the same commit with the same
> PyInstaller 6.22.3 scans and installs clean, only the CI-built hash is flagged, and the installer
> SHA256 matches the release
> (`54fbbaae6eb2c6565dba76a923b58e3e1beab3bd83454b07267589ecde3d6c5f`).
> We intentionally do **not** re-pack a build to dodge the signature - the right fix is
> whitelisting + a false-positive report so Microsoft updates the definition.

### One-shot fix (script, administrator required)

The repository ships
[`driver/tools/whitelist_defender.ps1`](https://github.com/w32394045-dotcom/ajazz-mk87/blob/main/driver/tools/whitelist_defender.ps1):

1. Right-click -> "Run with PowerShell" (it self-elevates via UAC);
2. it adds `C:\Program Files\MK87 Studio` and the installer to the Defender exclusions, tries to
   restore the quarantined `MK87Config.exe`, then prints the next steps;
3. re-run the official `MK87Studio-0.1.8.7-win64-setup.exe`.

Doing it by hand instead:

- **Restore**: Windows Security -> Virus & threat protection -> Protection history -> open the
  `Trojan:Win32/Bearfoos.A!ml` entry -> Actions -> Restore / Allow on device (if it says removed,
  just reinstall);
- **Exclusion**: Windows Security -> Virus & threat protection -> Manage settings -> Exclusions ->
  add the folder `C:\Program Files\MK87 Studio` (and the installer path if needed);
- re-run the official installer.

### Report the false positive (the real fix, 2 minutes)

<https://www.microsoft.com/en-us/wdsi/filesubmission> -> "Software developer" ->
"I believe this file is incorrectly detected (false positive)" -> upload
`MK87Studio-0.1.8.7-win64-setup.exe`, threat name `Trojan:Win32/Bearfoos.A!ml`, detection date
2026-11-07, SHA256 `54fbbaae…d6c5f`, plus the repository link. ML false positives are usually
corrected within a day.

### After Microsoft fixes it

Remove the temporary exclusion (administrator PowerShell):

```powershell
Remove-MpPreference -ExclusionPath "C:\Program Files\MK87 Studio"
```

Then re-download the official installer from
[Releases](https://github.com/w32394045-dotcom/ajazz-mk87/releases/latest) and confirm it installs
without a warning.

### Why it happens / long-term fix

The `!ml` suffix means no malware signature matched - it is an ML heuristic score on the binary;
unsigned, low-reputation PyInstaller bundles are a known false-positive class (for example
Microsoft's own `microsoft/apm` issue #487, `Bearfoos.B!ml`). The durable fix is a **code-signing
certificate** (OV/EV) plus submitting each release for whitelisting. Until then, follow the steps
above and report the false positive so the definition gets corrected.

### Linux tray icon

Launching from the app menu no longer opens a terminal window (v0.1.8: `Terminal=false` in the `.desktop`
file). The tray icon uses Qt's `QSystemTrayIcon`, which renders the native StatusNotifierItem/dbusmenu on
KDE, XFCE, Cinnamon, MATE and Ubuntu GNOME: **left-click shows the window, right-click opens the menu**
(Show window / Launch at start-up / Quit).

**GNOME Shell shows no tray icons at all** without the `gnome-shell-extension-appindicator` extension.
Since v0.1.8.6 you no longer have to install it in a terminal: when GNOME is missing the extension, the
main window shows a one-time banner and **Settings → System tray** is pinned to the top with a prominent
**"Install AppIndicator extension (one admin password)"** button. The app installs the distro package via
`pkexec` (a system password prompt — **enter the password of your logged-in user once**), enables the
extension automatically, and then asks you to log out and back in (Wayland) or press `Alt+F2` → `r` (X11)
so the tray icon appears.

- If the extension is installed but disabled, the button becomes "Enable extension (no admin password)".
- If installation fails, the card explains why (cancelled elevation / stale package lists / no network /
  package manager busy) and offers **copyable manual commands**. They are only a fallback:
  ```bash
  # Debian / Ubuntu
  sudo apt update && sudo apt install -y gnome-shell-extension-appindicator
  # Fedora / RHEL
  sudo dnf install -y gnome-shell-extension-appindicator
  # openSUSE
  sudo zypper install -y gnome-shell-extension-appindicator
  # Arch
  sudo pacman -S --noconfirm gnome-shell-extension-appindicator
  gnome-extensions enable appindicatorsupport@rgcjonas.gmail.com
  # Wayland: log out and back in; X11: Alt+F2 -> r
  ```
- Browser mode (a page served by `python run.py`) has no elevation entry point; the button becomes
  "Copy install commands" there. Use the desktop build (deb / rpm) for the one-click install.
- If there is no tray host at all, closing the window quits the app (no invisible background process).

## What's new in v0.1.8.7

> **Reliability release: your lighting no longer gets lost.** Fixes GIF/TFT uploads failing while
> Music Rhythm is running, and the systemic "keyboard falls back to per-key lighting" bug after a
> rhythm stop, a crash, a USB replug or an upload.

- **Lighting ledger** (persisted in `%APPDATA%\mk87\lighting_state.json`, atomic write). Every
  effect change is recorded (effect / off / per-key custom), and before a frame stream starts the
  app persists what to restore afterwards. Restore chain: runtime snapshot → ledger → static white
  fallback, with read-back verification (mode for normal effects, `GET_ALL_LIGHTS_RGB` vs the
  per-key table for custom). If the keyboard is offline, the pending restore is retried on
  reconnect and on the next launch.
- **Per-key lighting can be restored too.** Measured on hardware: writing `SET_LED_EFFECT` with
  mode 20/21/128 enters the per-key display (`0x33` returns the per-key table); mode 0 is a real
  "lights off". This corrects the 2026-11-01 note that mode 128 only turns the LEDs off.
- **Crash / replug recovery.** If the app is killed while Music Rhythm is playing, the pending
  target is already on disk; the next launch restores it ~1–2 s after the device connects (verified
  on the user machine: killed mid-stream, reconnect 17:13:09, restored 17:13:10.57).
- **GIF / TFT upload auto-pauses Music Rhythm.** The TFT upload needs the whole device; the app
  pauses Music Rhythm right before the first packet is written and resumes it with the same
  parameters afterwards (success, failure, cancel or reconnect-retry). The screen page shows
  "Music Rhythm paused automatically; it will resume when finished".
- **Changing an effect in the Lighting page stops Music Rhythm first**, so frame streaming can no
  longer overwrite the new effect.
- **UI:** the Lighting page now shows a read-only "Current effect" badge and a "Changed on
  keyboard" hint when the device was changed externally. `settings.json` is written atomically.
- Tests: **592 unit tests OK (skipped=1)**, including 40 new ledger/restore cases.
  See [DEVLOG §31](docs/DEVLOG.md) and [TEST-REPORT §27](docs/TEST-REPORT.md).

### v0.1.8.6 (previous release)

> **Diagnostic/reliability release.** Adds keyboard Win/Mac mode detection, Music Rhythm recovery
> after a mode switch, fixes the Key Test crash (`access violation`) and the `VK_0x12` unknown key,
> makes the Windows tray verifiable/self-healing, and surfaces the Linux one-click AppIndicator
> install.

- **Keyboard Win/Mac mode (the usual cause of "keys are swapped").** The MK87 has a **physical
  Win/Mac slide switch on its back**. In Mac mode the firmware swaps **Win and Alt**: measured on the
  user machine, the physical Win key reports `vkey=0x5B` (L-Win, HID 227, scan 0x5B) in Windows mode
  but `vkey=0x12` (VK_MENU/Alt, HID 226, scan 0x38) in Mac mode. New **Key Test → Keyboard mode
  check** asks you to press the key labelled Win (⊞), stores the answer and shows a red banner on the
  **Key mapping** page while Mac mode is active. Remapping itself is not blocked. The vendor protocol
  does not expose the mode (`systemMode` stays 0), hence the guided one-key check. See the dedicated
  section below.
- **Music Rhythm recovers after a Win/Mac switch.** Flipping the switch re-enumerates the keyboard;
  the app now reconnects (0.25 s polling), runs a frame-stream watchdog (rebuild after 2 s without a
  successful frame, force-abort a stuck HID call after 3 s) and tears sessions down with time limits,
  so recovery is not blocked by a dead handle. Mode/amplitude/back-mode/FPS/colour are preserved.
- **Key Test no longer crashes.** Fixed an access violation in `keyscan.py` (a temporary `WNDPROC`
  was garbage-collected while the window class still pointed at it). Reproduced before the fix
  (8 start/stop cycles → 24 fatal exceptions); 50 cycles after it: 0. `VK_MENU (0x12)` now shows
  **L-Alt / HID 226** instead of `VK_0x12 / slot —`, left/right modifiers are resolved from the scan
  code + E0 flag, and the event log reads `hid` correctly.
- **Windows tray: verified and self-healing.** The shell now checks that the icon is really
  registered (`Shell_NotifyIconGetRect`) and distinguishes visible / in "Show hidden icons" /
  unconfirmed / temporarily unavailable. A watchdog re-adds or recreates the icon after an
  **Explorer restart**; closing the window when the tray is unusable only **minimizes** it with a
  one-time explanation (never hides the app into nowhere). Duplicate launches now activate the
  existing instance, or show a message and exit - never a silent second copy.
- **Linux one-click AppIndicator install is now easy to find.** On GNOME without the extension,
  Settings → System tray is promoted to the top with a clear alert and a big **one-click install**
  button (one `pkexec` admin password, `apt-get update && apt-get install`, auto-enable, then log
  out/in or Alt+F2 → r). Failures are explained in plain language with copyable manual commands; the
  deb/rpm packages now declare the pkexec/polkit dependencies.
- **Verification status.** Key Test crash, VK mapping and the Win/Mac key values were verified on the
  user machine (Windows 10 LTSC 1809). Music Rhythm reconnection and tray Explorer-restart recovery
  are unit-tested and still need a real-device retest with this build. The Linux one-click install is
  unit-tested but not yet tried on a real Linux desktop (target: Ubuntu 24.04 GNOME Wayland).

### Keyboard Win/Mac mode (read this if keys seem "swapped")

1. Look at the **back/side of the MK87**: there is a **Win/Mac slide switch**. In Mac mode the
   firmware swaps Win and Alt; Windows then sees "Win pressed" as Alt and vice versa.
2. Open **Key Test → Keyboard mode check**, click **Start check** and press the key labelled **Win
   (⊞)** once. The app reports **Windows mode** or **Mac mode** and remembers it; the **Key mapping**
   page shows a red Mac-mode banner until you re-check.
3. Slide the switch back to **Windows**. The keyboard re-enumerates on USB (a few seconds; Music
   Rhythm briefly stops and recovers automatically). Then run the check again.
4. If a mode switch ever leaves the app unable to talk to the keyboard ("protocol interface not
   responding"), unplug/replug the USB cable once, or restart the app. v0.1.8.6 also shows a hint
   for this case.

### v0.1.8.5

> **Installer-only release (Windows): choose your shortcuts, get a setup log, and a documented fix
> for the `Error 5` install failure.** The application itself is unchanged.

- **Selectable shortcuts** - the Windows installer's "Select Additional Tasks" page now has two
  independent check boxes: **Start Menu shortcut** and **Desktop shortcut**, both checked by
  default. Clearing the Start Menu one creates no Start Menu folder at all (the uninstall
  shortcut lives there too; uninstall is still available from Windows Settings -> Apps).
- **Setup log** - the installer writes `%TEMP%\Setup Log <date> #<n>.txt`. On a machine where
  installation dies before any window appears, that file is the first thing to look at.
- **README: Windows installer troubleshooting** - documents the
  `Setup was unable to create the directory ... Error 5: Access denied` failure: why the downloaded
  file is fine, and the fix order - run the setup **as administrator** first (verified on the user
  machine), then repair Temp permissions / exclude it in Defender / move it out of `Downloads`,
  with the portable build as the final fallback.

### v0.1.8.4

> **Fixed: Music Rhythm used to keep showing "running" after the keyboard stream silently stopped**
> (Windows + Linux). Real-device logs (Surface Laptop 2 · Windows 11 · keyboard USB fw1.19) show
> `Kernel-Power 506: 系统正在进入连接待机状态 原因: Lid` at 2026-11-06 13:37:16 — the lid was closed,
> Windows entered Modern Standby and the USB HID interface was suspended. From 13:37:17.888 every music
> frame write reported `WriteFile 失败: 995` (`ERROR_OPERATION_ABORTED`); after 51 failures the old code
> silently quit the thread (`errors > 50` → `break`). The other path (reproduced at 21:25) had `WriteFile`
> **block forever** inside the `mk87-music` thread (py-spy stack: `NativeHidChannel.write`), while the
> audio capture thread hung in WASAPI — frames stopped with no error at all. The old frontend only updated
> `running` when the user pressed start/stop, and its 3 s poll only synced fps, so the UI kept showing
> "running" with a frozen level bar after the backend had stopped or hung. This is not a keyboard or
> user-system problem: the tool lacked detection and recovery for system standby / device loss / capture
> stalls, and it had no keep-awake.

- **HID writes can now time out (Windows)** — in `mk87lib/winhid.py` the write handle is opened as
  **overlapped** with a **0.25 s timeout** and `CancelIoEx`; if cancellation cannot complete (device really
  suspended) the channel is marked stuck and rebuilt by the layer above. In-flight IO channels are pinned
  in a module-level keep-alive list, so a pending transfer's memory is never freed under a dangling
  `CloseHandle`. The normal path stays synchronous, so 20/60/66 fps is unaffected.
- **Music-session supervision and automatic recovery** (`mk87lib/music.py`) — a broken
  "audio capture + frame stream" session is rebuilt automatically with backoff **0.5 → 1 → 2 → 5 s**; if the
  keyboard drops off, the app waits for auto-reconnect and then **resumes playback by itself** — only the
  user's "Stop" really ends the session; audio capture with no new data for **2.0 s** counts as stalled
  (a WASAPI hang after standby used to be completely silent); **5 consecutive HID send failures** rebuild
  the channel; a vanished audio device (headphones unplugged / default output switched) falls back to the
  default-output loopback; live parameter changes survive a recovery.
- **Keep-awake: Windows** (new `mk87lib/powerkeep.py`) — while Music Rhythm is running, a resident thread
  holds `SetThreadExecutionState(ES_CONTINUOUS|ES_SYSTEM_REQUIRED)` + `timeBeginPeriod(1)` to prevent
  **idle** system sleep and keep the 60 fps schedule stable; at startup
  `SetProcessInformation(ProcessPowerThrottling)` disables Windows **EcoQoS** power throttling and ignores
  timer-precision requests (the boot log records `power-throttle-optout`).
- **Keep-awake: Linux** — `systemd-inhibit --what=sleep` blocks sleep and degrades to a no-op when
  `systemd-inhibit` is unavailable. Deliberate user sleep (e.g. closing the lid) still happens; the
  auto-recovery above is what handles wake-up.
- **`/api/music/status` reports real health** — new `health` (`starting` / `ok` / `recovering` /
  `waiting-device` / `stopped`), `recoveries`, `lastRecovery`, `frameAgeMs`, `keepAwake`,
  `deviceConnected`, `audioFallback`, `stoppedByUser`; new WebSocket events `music_health` /
  `music_stopped`.
- **The UI follows the backend's real state** — the 3 s poll now syncs the backend's real `running` value;
  the badge shows **rhythm running / recovering… / waiting for keyboard**, a successful recovery announces
  "recovered N times automatically" (「已自动恢复 N 次」), and when the backend stops the page switches back
  to "not started" and shows the reason.
- **Tests** — 339 unit tests green (39 new: 23 keep-awake, 8 session guard / auto-recovery, 5 winhid write
  timeout, 3 health-event contract); a real FastAPI + WebSocket smoke test also covered the HTTP/WS path
  (the new `/api/music/status` fields, the `music_health` / `music_stopped` events, and a clean 503 from
  `start` while the device is offline).
- **Hardware verification status** — the root cause comes from the user's real-device logs and a live
  process thread dump; the fix is covered by unit tests and a process-level smoke test, but a **full
  standby-and-wake retest on the user's machine is still pending**.

### v0.1.8.3

> **Second fix: v0.1.8.2 cured the `GLIBC_2.43` error, but QtWebEngine then died with a segfault
> (`段错误 (核心已转储)`) after EGL initialisation failed.** Root cause: PyInstaller still bundled the
> **entire system library stack** from the Ubuntu 22.04 build machine (glib / libstdc++ / wayland /
> xcb / Mesa-related) into `_internal/`. The frozen app puts `_internal` first on the library search
> path, so on Ubuntu 24.04 the system components loaded the bundled **older** copies:
> GIO modules (`libdconfsettings.so`) hit `undefined symbol: g_assertion_message_cmpint` (bundled glib),
> the iHD DRI driver hit `GLIBCXX_3.4.32 not found` (bundled libstdc++), and Mesa/EGL got bundled
> **wayland/xcb/gbm** → `qt.qpa.wayland: EGL not available` → QRhi failed → segfault.
> v0.1.6 only worked because it happened to be built on 24.04, matching the user's system.

- **Host system libraries are no longer bundled** — the new `driver/packaging/libfilter.py` strips every
  shared library that comes from the build machine's system directories. Only Qt/WebEngine, the Python
  runtime and wheel-provided third-party libraries are shipped; glib / GTK / X11 / Wayland / the graphics
  stack / NSS now come from the distro (the same copies every other app uses). deb `Depends` and rpm
  `Requires` were rewritten accordingly, with Ubuntu 24.04 `t64 | old-name` alternatives. Because the app
  now *depends* on those packages, a missing entry would break startup — which is why CI installs the
  package in clean containers and fails on any `ldd ... not found`.
- **Launcher crash fallback** — `/usr/bin/mk87` now retries only when the app is **killed by a signal**
  (exit ≥ 128, e.g. 139 = segfault, 134 = abort): default → **XWayland** (`QT_QPA_PLATFORM=xcb`) →
  **software rendering** (`LIBGL_ALWAYS_SOFTWARE=1` + Chromium `--disable-gpu`). Normal quits are never
  retried. Logs: `~/.cache/mk87/launcher.log` and `~/.cache/mk87/launcher-console.log`. Manual knobs:
  `QT_QPA_PLATFORM=xcb mk87`, `MK87_SOFTWARE_RENDERING=1 mk87`, `MK87_NO_FALLBACK=1 mk87`.
- **Stricter release gates** — the build fails if a host system library sneaks into the bundle; the deb is
  installed in clean `ubuntu:22.04` / `ubuntu:24.04` containers, every bundled ELF is checked with `ldd`
  for missing libraries, and the app must stay alive for 40 s under Xvfb and reach WebEngine
  initialisation. Both gates are exactly the failure modes of this bug.
- **Tests**: 300 unit tests (16 new: bundle filtering rules + fallback environment).
- **Known issue**: the Fedora `.rpm` may still fail on very new glibc with PyInstaller/OpenBLAS
  `ELF load command address/offset not page-aligned` (that check is informational, it does not block the
  release); this release focuses on the Ubuntu/Debian `.deb`.

If it still fails, these three files pinpoint the crashing stage:

```bash
cat ~/.mk87-boot.log                          # startup stages (where it died)
cat ~/.cache/mk87/launcher.log                # launcher retry history
cat ~/.local/state/mk87/logs/crash.log        # Python faulthandler crash stack
```

### v0.1.8.2

> **The real fix for the Ubuntu startup crash (v0.1.7/v0.1.8)**: the app exited before showing a window
> because the bundled **PyQt6 failed to import**. PyInstaller bundles system libraries from the build
> machine, and GitHub moved its `ubuntu-latest` runner from 24.04 to **26.04 (glibc 2.43)** between the
> v0.1.6 and v0.1.7 builds — on Ubuntu 24.04 (glibc 2.39) those libs fail with `GLIBC_2.43 not found`,
> so Qt disappeared and the app crashed silently. (v0.1.6 worked because it was built on Ubuntu 24.04.)

- **Linux packages are now built on Ubuntu 22.04 (glibc 2.35)** — the packaging runner is pinned, so
  bundled system libraries stay compatible with Ubuntu 22.04 and newer; a runner upgrade can no longer
  produce packages that crash on users' machines.
- **Extra Qt 6.12 libraries are bundled** (PyInstaller spec collects `libpcre2-16`, `libdouble-conversion`,
  `libb2`, `libmd4c` and the missing `libxcb`/`libwayland` pieces), so the package is self-contained and
  also survives a `dpkg -i` force-install that skips dependencies.
- **deb/rpm dependencies completed** — `Depends` covers the Qt 6.12 runtime and X11/Wayland/GTK runtime
  with `t64 | plain` alternatives (Ubuntu 22.04 + 24.04); RPM `Requires` lists the Fedora equivalents.
  `sudo apt install ./mk87_*.deb` / `sudo dnf install ./mk87*.rpm` installs everything in one go.
- **New CI gate** — each release installs the built `.deb` in a clean `ubuntu:24.04` container (and the
  `.rpm` in a clean `fedora` container), starts the packaged app under Xvfb and fails the release if it
  exits early. This kind of packaging bug can no longer be released.
- **Startup preflight** — if PyQt6 still fails to import, the **full traceback** is written to
  `~/.mk87-boot.log` and `<log dir>/qt-error.txt` and a desktop error dialog points at it, instead of the
  opaque pywebview "No Qt bindings could be found". `QT_API` is forced to the bundled `pyqt6`.
- Tests: **284 unit tests green**.

### v0.1.8.1

- **Boot-stage log `~/.mk87-boot.log`** — timestamped markers from the very start of the program to
  tray creation (`main-start` → `logging-ready` → `server-started` → `window-created` → `qt-tray-*`),
  flushed immediately, so a startup crash can be located even when the normal log folder looks empty.
  Run `mk87` in a terminal to also capture the Python traceback if the app exits before the GUI shows.
- **`--no-tray` safety mode** — `mk87 --no-tray` (or `MK87_NO_TRAY=1`) starts without any system tray;
  closing the window then quits the app. Use it to keep working if the tray path is what crashes.
- **Hardened Qt tray** — unhandled exceptions in Qt slots make PyQt6 call `qFatal()` (instant abort that
  looks like a crash). Tray/menu callbacks now never throw, log the error and fall back to "no tray";
  on GNOME without the AppIndicator extension the Qt tray is not even created (it could never show).
- **CI (faster)** — `main` pushes now only run unit tests on two runners (~2 min); `.deb`/`.rpm` are
  built on two **parallel** runners and packages are only produced for `v*` tags or manual runs. A new
  manual `linux-smoke` workflow builds the packaged app and runs it under Xvfb, uploading the boot log,
  stderr and session logs for quick Linux checks without publishing a release.

### v0.1.8

- **Fixed: a terminal window no longer opens on Linux** — the packaged `.desktop` file had `Terminal=true`,
  so starting MK87 Studio from the app menu spawned a terminal that hosted the app. It is now
  `Terminal=false` (the autostart entry already was).
- **Fixed: right-clicking the Linux tray icon did nothing** — the tray used `pystray`, which in our bundle has
  neither the AppIndicator nor the GTK backend available, so it always fell back to its X11 backend. That
  backend sets `HAS_MENU = False` and only handles left-click activate, so an icon appeared but the context
  menu was impossible to implement. Linux now uses **Qt `QSystemTrayIcon` + `QMenu`** (PyQt6 is already
  bundled by `pywebview[qt]`, no new runtime dependency): left-click shows the window, right-click shows the
  native menu on KDE / XFCE / Cinnamon / MATE / Ubuntu GNOME. Windows keeps pystray unchanged.
- **New: "System tray" settings card + one-click GNOME extension install** — `GET /api/tray/status` reports
  the real tray backend and host availability, desktop environment, session type (Wayland/X11), GNOME Shell
  version, and whether the AppIndicator extension is installed/enabled. On plain GNOME the card offers
  **one-click install** (distro package, one `pkexec` password prompt; `dnf` / `apt` / `zypper` / `pacman` /
  `rpm-ostree` are auto-detected) plus a "copy commands" fallback and an "enable extension" action when it is
  installed but disabled. Windows/non-GNOME desktops simply report "no extension needed".
- **No zombie windows** — if the desktop really has no tray host, closing the window now quits the program
  (before, the window hid into nowhere); the main window shows a banner explaining it during that session.
- **Tests**: **277 unit tests green** (32 new tray environment tests). The settings card and both languages
  were smoke-tested with a linkedom DOM harness (16 assertions). Linux tray/extension behaviour still needs
  real-device verification on the user's machine.

### v0.1.7

- **Fixed: music rhythm could not start on Linux (HTTP 400)** — audio capture relied on the external `parec`
  command (`pulseaudio-utils`), which PipeWire desktops (Fedora, current Debian/Ubuntu) do not install by
  default, so `POST /api/music/start` failed instantly with "音频采集打开失败". Linux capture now uses
  **libpulse-simple** directly (part of `libpulse0` / `pulseaudio-libs`, already a package dependency;
  works with both PulseAudio and PipeWire's pulse compatibility layer) via `@DEFAULT_MONITOR@`, retries with
  the real `<default sink>.monitor` name from `pactl get-default-sink` when the special name is not resolved,
  and still falls back to `parec` if the library is unavailable. The audio-device list no longer depends on
  `pactl` either (falls back to "默认输出回环"), the chosen backend is exposed as
  `audioBackend` in `/api/music/status`, and the exact failure reason is written to the log
  (`MK87Error ... : message`).
- **Fixed: device commands were needlessly slow** — the notification listener held the device lock while
  doing a *timed* HID read every cycle. On Windows each such read costs 50~400 ms to return (hidapi
  CancelIoEx cancellation), so every keymap / macro / LED request waited ~0.3 s; on Linux it was 50 ms, and
  a continuous notification stream could even starve request threads. The listener now does a **nonblocking
  read and sleeps outside the lock** (`timeout <= 0` path; note cython-hidapi's `read(len, 0)` is actually
  blocking, so it uses `set_nonblocking(1)` + `read(len)`). Measured on a real MK87 (Windows): keymap read
  **15 ms** (was ~325 ms via the API), LED custom read **24 ms** (was 100–250 ms), device info **2 ms**;
  music streaming still holds 20.0 fps.
- **Better stall diagnostics** — a process watchdog logs gaps >2 s (whole process frozen / suspended vs. a
  single blocked thread), device-lock waits >0.3 s and slow HID writes/reads are logged, and HTTP 400s now
  record the actual `MK87Error` message. These come from the 2026-11-04 user log, which contained several
  2–9 s windows with no log lines at all — next report will show whether the process was frozen or a device
  operation stalled.
- **Tests**: **245 unit tests green** (12 new Linux audio tests + nonblocking-listener/read tests).
  Linux real-device verification for the music fix still needs the user's machine.
### v0.1.6

- **Fixed: Linux still could not detect the keyboard (root cause of the v0.1.5 report)** — the PyPI `hidapi`
  wheel ships **two** extension modules on Linux: `hid` (built against **libusb**) and `hidraw` (built
  against **hidraw**). cython-hidapi's build defaults to libusb, so `import hid` on Linux returned the libusb
  backend: `enumerate()` paths look like `1-1.1:1.0` instead of `/dev/hidrawN`, `usage_page` is always 0
  (libusb cannot read the descriptor during enumeration), opening needs `/dev/bus/usb` permissions and fights
  the kernel HID driver. The tool now selects `hidraw` on Linux, which reports `/dev/hidrawN` paths and fills
  usage pages straight from sysfs — the v0.1.5 report-descriptor parsing stays as a fallback. Windows keeps
  using the native `hid` module; behaviour there is unchanged.
- **New: `--diagnose` self check** — `mk87 --diagnose` (or `python3 probe/linux_hid_check.py`
  from a source checkout) prints the hidapi backend, raw enumeration, parsed interfaces, every
  `/sys/class/hidraw/hidraw*` node with vid/pid/interface/usage page/permissions, the udev rule state and a
  verdict, and saves it to `~/.local/state/mk87/logs/diagnose.txt`.
- **Linux: clearer failures** — if only the libusb backend is present the tool now refuses to "connect" and
  tells you to install the official wheel / upgrade the package; the "not found" message points at
  `--diagnose`.
- **Linux: quieter startup** — pywebview is told to use its Qt backend directly, so the packaged app no
  longer logs a misleading `GTK cannot be loaded` traceback before falling back to Qt.
- Tests: **226 unit tests green** (11 new: backend selection/preference, interface-number 0 handling,
  sysfs HID_ID/interface parsing, libusb-style path fallback, libusb-backend guard). Windows regression
  re-checked on a real MK87: `connected=True fw=1.19 battery=100 tftMax=140`.

### v0.1.5

- **Attempted Linux fix (report-descriptor parsing)** — v0.1.5 assumed hidapi's hidraw backend leaves
  `usage_page = 0` on Linux and rebuilt interface identity by parsing each interface's HID report descriptor
  (hidapi `get_report_descriptor()`, falling back to
  `/sys/class/hidraw/hidrawN/device/report_descriptor`). The parsing is still used as a fallback, but the
  real problem was the **libusb** backend being imported — see v0.1.6.
- Diagnostics: the device log lists every enumerated interface (`product / pid / usagePage / usage /
  interface / payload / path`), and `probe/linux_hid_check.py` printed the same information.
- Tests: 215 unit tests green (9 Linux transport tests).

### v0.1.4

- **Fixed: key remapping / macro bindings could not be saved** — the keymap page sent `key` / `fn` / `combo`
  wire types while the backend encoder only accepted `keyboard` / `func` / `combo (mods + key)`, so every
  "Apply changes" returned HTTP 400. Backend now accepts both forms and the frontend emits the canonical
  schema; combo keys also round-trip correctly after a page reload. Verified on a real MK87 (canonical,
  alias-key, combo write + restore and FN-layer no-op saves all returned 200 with byte-identical readback).
- **Fixed: UI hiccups while music is playing** — the protocol layer logged every HID notification frame at
  DEBUG level (1,169,834 lines / 207 MB in one 47-minute 66 fps session). Notifications are now aggregated
  and rate-limited (≈33 KB/min, −99.9 %), session logs are capped at 32 MB and old sessions are pruned, and
  the macro table is read in bulk (`GET /api/macros` 48 s → 0.37 s; 201 → 7 requests).
- **Fixed: LED color overlay now covers every dynamic mode** — previously only 1/2/4/5/13; the restored
  modes 14–22 are now recolored too. Solid modes 6–11 keep their official sampled colors and `default`
  remains byte-for-byte identical (220-combination snapshot regression).
- **Fixed: mode 4 could flash the old synthetic contour** — a single frame with an all-zero spectrum (quiet
  passage / loopback dropout) used to switch Curvature Frequency Steps back to the legacy curvature outline.
  Once real spectrum has been received the renderer never falls back; silence means empty bars.
- **Fixed: Amplitude / Background-brightness sliders did not send their values** — their `onInput` handler
  never wrote the new value back, so hot-update always sent the previous 50/100. Dragging now applies live.
- **Fixed: browser-mode (`run.py`) logging** — uvicorn's default log config closed the tool's log handlers
  (empty session log + thousands of "Logging error" tracebacks on stderr). uvicorn now starts with
  `log_config=None`, same as the native shell.

### v0.1.3

- **Music rhythm · Official scheme aligned with the official v1 truth** — the display-mode dropdown is now
  **21 modes**: the 12 exposed by the official v1 UI plus the 9 modes (14–22) that had already been
  reverse-engineered but were not surfaced by the official UI. Mode 4 **Curvature Frequency Steps** was
  rewritten from fresh sampling of the official MusicPlug.exe: 17 frequency columns, bottom-aligned
  (1200/1200 frames), left-low → right-high on a log scale (~110 Hz–12 kHz), with a radial hue palette
  (origin `(2,8)`) rotating ~275°/s. Mode 100 (screen-light linkage) still falls back to Dance to the Beat.
- **LED color overlay (this tool's own enhancement)** — a third dropdown offers **default (official palette)
  + 9 presets**: ice blue `#00E5FF`, violet `#B36CFF`, hot pink `#FF2E88`, lime `#A8FF3E`, warm amber
  `#FF6A00`, sakura `#FF7AB6→#B36CFF`, aurora `#3EFF9A→#00E5FF→#7A5CFF`, sunset
  `#FFC400→#FF6A00→#FF2E88`, ice-fire `#00E5FF→#FEFEFE→#FF6A00`. It recolors all dynamic multicolor
  modes **1/2/4/5/13 and the restored 14–22**, keeping their original animation; solid modes 6–11 and the
  background are untouched, and `default` is byte-for-byte identical to v0.1.2 (220-combination snapshot
  regression).
- **Native 20 / 60 / 66 fps, default 66** — the official v1 plugin sends 530.5 packets/s ÷ 8 packets/frame
  ≈ **66.3 fps**, so the official scheme now defaults to 66 fps (Current keeps 15/20/30). ≤30 fps keeps
  per-packet ACK; ≥60 fps writes 7 packets back-to-back and drains ACKs asynchronously (synchronous
  frame-end drain measured 19.8 ms/frame → 45.96 fps; async 8.85 ms/frame → 66 fps). Animation is
  `dt`-normalized, so motion speed does not change with fps. The page shows measured fps; the status
  contract is `fps` (float|null, measured) / `targetFps` (int, configured), and WS preview is capped at 30 Hz.
  On a real MK87 (USB, fw 1.19) 66 fps held
  **65.78–65.89 fps for 100 s** (0 errors); 60 fps = 60.06, 20 fps = 19.97. 21 modes × 10 colors switched
  with 0 errors; stopping restored mode 11 / brightness 6 / speed 3.
- **Battery / lighting robustness** — battery, charging and work mode are re-read and logged on every poll
  (the connection log now carries battery/charging/workMode/transport, plus a delayed 2 s re-read after
  connect). 2.4G battery uses cmd `0x37` (first packet + `GET_ALL_LIGHTS_RGB_24G` response), with a
  3-failure / 5-minute circuit breaker that falls back to the USB path. The stuck-custom-lighting bug is
  fixed at the root: v0.1.2's music start wrote LED mode **128**, and if the process was killed during
  shutdown the restore never ran, so fw 1.19 turned 128 into a per-key custom table. The music path now
  **never writes 128**, enters frame mode with 20/21 and verifies by readback, refuses to restore
  snapshots whose mode is 0/invalid, restores lighting before closing the device manager, and marks `isCustom` via
  `GET_ALL_LIGHTS_RGB` when the mode reads back 0. (The "looks like game mode after reboot" report had the
  same cause; full logs show the tool never sent a game-mode `0x21` command — 0 entries.)
- **Quality** — 152 unit tests green; 17 headless-Chrome UI checks PASS (21 modes / 3 dropdowns / 10 colors /
  3 frame-rate tiers, live switching, no Chinese leakage in the English UI).

## Features

- **Lighting** — 19 presets with color / brightness (1–6) / speed (1–6) / direction; RGB or single color.
- **Per-key RGB** — 87-key canvas: paint, erase, fill, eyedropper, drag-paint, presets; writes the custom LED
  table shared by firmware modes 20 / 21 / 128.
- **TFT screen (240×135)** — image / GIF / animated WebP / APNG → compression pipeline (downscale, frame
  extraction, dedupe, RGB565 dithering) → animation upload (≤140 frames), time sync, restore official animation.
- **Macros** — 100 slots / 3072 B editor: record keys, delays, press/release, repeat N times, press-to-stop.
- **Key mapping / FN** — 87-key normal + FN layers: HID keys, combos, macros, firmware FUNC actions, disabled,
  restore-defaults, live 4-byte encoding preview. FN layer is read-only over 2.4G.
- **Music rhythm (USB only)** — two schemes: **Official** (21 display modes — the 12 official v1 modes plus
  the 9 restored modes 14–22 — 11 background modes, background brightness, amplitude and LED color overlay;
  hot-switchable while playing) and **Current** (this tool's own mode / frame rate / sensitivity) → native
  **20/60/66 fps** per-key frame stream (official scheme defaults to 66; official v1 measured ≈66.3 fps).
  Mode 4 is a 17-column bottom-aligned spectrum matching the official sampler, and the LED color overlay
  (default + 9 presets) recolors every dynamic mode (1/2/4/5/13 + the restored 14–22). Mode 100 (screen
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
| Per-key live frame stream (native 20/60/66 fps, default 66; official v1 ≈66.3 fps; music / AI effects) | ✅ USB only (2.4G not supported by firmware) |
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
