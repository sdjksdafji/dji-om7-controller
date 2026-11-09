# om7-test

Control a **DJI Osmo Mobile 7** smartphone gimbal from a computer over Bluetooth LE, using Python and [bleak](https://github.com/hbldh/bleak). No DJI app or SDK is needed.

```bash
uv sync
uv run om7_test.py     # pans the gimbal right → center → left → center
```

> [!IMPORTANT]
> **This project targets the Osmo Mobile 7 (OM7) only.** It was developed and tested on a single OM7 on Windows 11 in November 2026. Other Osmo Mobile models, other firmware versions, macOS and Linux are untested. For OM2, OM3 and OM4, see [alkersan/om-research](https://github.com/alkersan/om-research), which this project builds on.
>
> This is an independent project. It is not affiliated with, endorsed by or supported by DJI. Use it at your own risk.

## Contents

- [What works](#what-works)
- [Quick start](#quick-start)
- [Usage](#usage)
- [Why the original om-research approach doesn't work on the OM7](#why-the-original-om-research-approach-doesnt-work-on-the-om7)
- [Troubleshooting](#troubleshooting)
- [Protocol reference](#protocol-reference)
- [Known limitations and open questions](#known-limitations-and-open-questions)
- [Contributing](#contributing)
- [Credits](#credits)
- [License](#license)

---

## What works

Tested on the OM7:

| Capability | Status |
|---|---|
| Connecting over BLE, with no pairing handshake or encryption needed | ✅ Works |
| Finding a gimbal that is already paired with Windows | ✅ Works |
| Speed-based moves (cmd set `04`, cmd `0c`, mode `80`), with the gimbal confirming each command | ✅ Works |
| Reading the gimbal's periodic status (used here to confirm motion) | ✅ Works, field meanings not fully decoded |
| Angle-based moves (cmd set `04`, cmd `14`, relative or absolute) | ❌ **Silently ignored by the OM7.** See [why](#why-the-original-om-research-approach-doesnt-work-on-the-om7). |

## Quick start

### Requirements

- A computer with Bluetooth LE. Tested on Windows 11 with a built-in Intel adapter.
- [uv](https://docs.astral.sh/uv/). It installs Python 3.12 for you if needed.
- A DJI Osmo Mobile 7, charged.
- A phone mounted in the clamp. The gimbal uses it as a counterweight and won't balance or move properly without it.

### Install

```bash
git clone <this-repo-url>
cd om7-test
uv sync
```

`uv sync` creates `.venv/` and installs `bleak` at the version pinned in `uv.lock`.

### Pre-flight checklist

A BLE device usually accepts only **one** connection at a time, and stray connections are the most common reason a run fails. Before each run:

1. **Unfold** the gimbal and **power it on**. Wait until it finishes its startup motion and is holding the phone level.
2. **Close DJI Mimo completely** on every phone that has paired with the gimbal. Swipe it away; don't just background it.
3. **Turn off Bluetooth on the mounted phone** (and on any other phone that has used Mimo). Otherwise it may reconnect on its own and take the only connection slot.
4. **Windows:** pair the gimbal once under *Settings → Bluetooth & devices*. It appears as `OM7-XXXXXX`. Pairing is optional but the most reliable setup, because the script finds the gimbal through Windows' list of paired devices.
5. Keep the gimbal within ~1 m of the computer, with nothing in the way of its arm, the phone or the cable.

### Run

```bash
uv run om7_test.py
```

The gimbal pans about 15° right, back to center, about 15° left, and back to center.

---

## Usage

### Finding the gimbal

With no arguments, the script looks for a device whose name starts with `OM` or contains `Osmo`:

1. **Windows:** it first checks Windows' list of paired Bluetooth LE devices. No scan is needed.
2. **Otherwise** (or if nothing paired matches): it scans the air for 8 seconds. If that finds nothing too, it lists every named device it saw.

You can also pass an address. On Windows and Linux this is a MAC address; on macOS it's a UUID:

```bash
uv run om7_test.py AA:BB:CC:DD:EE:FF
```

### Example output

```
Found paired OM7-XXXXXX at AA:BB:CC:DD:EE:FF
Connected. Listening for gimbal messages...
   telemetry before:  +171.6    +0.1    -2.9   +13.4    -3.7
-> right  (yaw speed +300): 55 15 04 a9 02 04 01 00 40 04 0c 2c 01 00 00 00 00 80 0a 6e 9f
  <- reply seq=1 set=04 cmd=0c OK (payload 00 00)
   telemetry after:   +171.6    +0.1   +12.5   +13.4   -19.5
-> center (yaw speed -300): 55 15 04 a9 02 04 02 00 40 04 0c d4 fe 00 00 00 00 80 0a 1b 71
  <- reply seq=2 set=04 cmd=0c OK (payload 00 00)
   telemetry after:   +171.6    +0.1    -2.9   +13.4    -3.7
-> left   (yaw speed -300): 55 15 04 a9 02 04 03 00 40 04 0c d4 fe 00 00 00 00 80 0a b6 74
  <- reply seq=3 set=04 cmd=0c OK (payload 00 00)
   telemetry after:   +171.6    +0.1   -17.9   +13.4   +12.1
-> center (yaw speed +300): 55 15 04 a9 02 04 04 00 40 04 0c 2c 01 00 00 00 00 80 0a 77 8c
  <- reply seq=4 set=04 cmd=0c OK (payload 00 00)
   telemetry after:   +171.6    +0.1    -2.9   +13.4    -3.7
Other (periodic) gimbal messages received: set=00 cmd=00 x8, ... set=05 cmd=06 x22
Done.
```

| Line | Meaning |
|---|---|
| `-> …` | The frame sent to the gimbal. The bytes are deterministic, so if yours differ, the code has changed. |
| `<- reply … OK` | The gimbal accepted the command. Any other status is printed as an error code. |
| `telemetry` | The first five values of the gimbal's ~1 Hz status message (`set=04 cmd=05`), in 0.1° units. The third value follows the pan. |

### Writing your own moves

`gimbal_frame()` builds one move command. Send it to the `WRITE` characteristic:

```python
from om7_test import WRITE, MODE_SPEED, gimbal_frame

frame = gimbal_frame(yaw=300, pitch=0, mode=MODE_SPEED, duration_s=1.0, seq=1)
await client.write_gatt_char(WRITE, frame, response=False)
```

- `yaw`, `pitch` and `roll` are signed 16-bit values. On the OM7, `yaw=300` for 1 second turned the gimbal about 15°. The exact speed unit isn't confirmed.
- `duration_s` is sent in 0.1 s steps, up to 25.5 s.
- Give each frame a new `seq` number.
- Start with small values. Larger speeds or durations swing further.

### Diagnostic tools

Both are read-only: they never move the gimbal. They find it the same way `om7_test.py` does, or you can pass an address.

| Command | What it does |
|---|---|
| `uv run probe.py` | Sends a DJI "get version" query (cmd set `00`, cmd `01`) and reports whether the gimbal replies. A reply proves the connection, frame format and checksums are correct. |
| `uv run list_services.py` | Prints every BLE (GATT) service and characteristic the gimbal exposes. |

On the OM7, gimbal control uses service `0000fff0-…`:

```
0000fff0-0000-1000-8000-00805f9b34fb  Vendor specific
    0000fff4-0000-1000-8000-00805f9b34fb  notify                         <- gimbal -> computer
    0000fff5-0000-1000-8000-00805f9b34fb  write-without-response,write   <- computer -> gimbal
    0000fff3-0000-1000-8000-00805f9b34fb  notify,write                   (doesn't answer queries)
```

---

## Why the original om-research approach doesn't work on the OM7

This project started from a short sample script based on the [om-research](https://github.com/alkersan/om-research) protocol notes, which were confirmed on OM2, OM3 and OM4. On the OM7 that script **connected but never moved the gimbal**. There were two separate problems, plus a third that made them hard to diagnose.

### 1. The gimbal couldn't be found: a paired OM7 stops advertising

The original script found the gimbal by **scanning for BLE advertisements**, the short broadcasts a device sends while waiting for a connection. It then matched the name.

Once the OM7 was paired with Windows, it **stopped advertising**. A 10-second scan saw six nearby devices, but not the gimbal, so the script exited with `No gimbal found`. Passing the address directly didn't help either: on Windows, `BleakClient("<address>")` scans before it connects, and failed in the same way.

**Fix:** on Windows, `find_paired_gimbal_windows()` reads the gimbal's name and address from Windows' list of paired devices. `connect_target()` then wraps the address in a `BLEDevice`, which makes bleak connect through Windows directly with no scan.

### 2. The OM7 ignores the angle command the original script sent

The original script moved the gimbal with the **angle** command, *rotate by N degrees*: cmd set `0x04`, cmd `0x14`, relative mode `0x04`. Its frame was byte-for-byte identical to om-research's reference code:

```
55 15 04 a9 02 04 01 00 00 04 14 2c 01 00 00 00 00 04 0a 99 39
                        ^^    ^^                   ^^
                        type  cmd 0x14 (angle)     mode 0x04 (relative)
```

The OM7 **silently drops this command**. It sends no error, no reply and no movement, in both relative and absolute mode. The **speed** command, *turn at speed N for T seconds* (cmd `0x0c`, mode `0x80`), works. It's the same command om-research's own `rotate.py` example uses:

```
55 15 04 a9 02 04 01 00 40 04 0c 2c 01 00 00 00 00 80 0a 6e 9f
                        ^^    ^^                   ^^
                        type  cmd 0x0c (speed)     mode 0x80 (speed)
```

**Fix:** `om7_test.py` now moves the gimbal with speed commands.

### 3. The original frames asked for no reply, so failures were invisible

Byte 8 of each frame (the *command type*) was `0x00`, which means "don't reply". When the gimbal ignored the command, there was nothing to see. It was impossible to tell whether the frame arrived and was rejected, or never arrived at all.

**Fix:** frames now use type `0x40`, "reply after executing". The real frames captured from DJI Mimo in om-research's notes use the same value. Accepted commands now print `OK`, and silence clearly means the command was ignored.

### How this was established

Each step changed one thing and checked the result:

| Step | Test | Result | Conclusion |
|---|---|---|---|
| 1 | Check Windows' Bluetooth device list | OM7 listed, paired, with service `fff0` | Windows can reach the gimbal |
| 2 | 10-second BLE scan with full advertisement data | Gimbal not among 6 devices seen | A paired OM7 doesn't advertise |
| 3 | Connect via `BLEDevice`, skipping the scan | Connected; `fff4`/`fff5` present | Connection and characteristics are fine |
| 4 | Recompute both checksums; check them against 4 captured Mimo frames | All match | The frame format is correct |
| 5 | Send the angle command asking for a reply (`0x40`) | No reply, no movement, while status messages kept arriving | The gimbal ignores the command |
| 6 | Send a "get version" query (`probe.py`) | Reply with status `00` | The gimbal does process our frames |
| 7 | Angle command, absolute mode, exact layout of the Mimo captures | No reply, telemetry unchanged | Ignored in every mode |
| 8 | Speed command `04/0c`, yaw ±300 for 1 s | Reply `00 00`, telemetry moved about 15° each way | **Speed control works** |

Smaller fixes made along the way:
- The sequence number now increments per frame. The original reused `1`, and DJI devices may drop repeated sequence numbers as retransmissions.
- The device-name filter is tighter. `"OM" in name` also matched names like "Comcast" or "Room".

---

## Troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| `No gimbal found` | Not paired with Windows, and not advertising, often because a phone holds the connection. | Pair the gimbal in Windows Bluetooth settings, or go through the [pre-flight checklist](#pre-flight-checklist). Power-cycle the gimbal. |
| Connection times out | The gimbal is off, out of range, or connected to a phone. | Power-cycle the gimbal and turn off the phone's Bluetooth. Toggle the computer's Bluetooth. |
| Connects, but no `reply` lines and no movement | A firmware change, or a different model. | Run `uv run probe.py`. If it gets replies, the connection is fine and the move command itself has changed. Consider [capturing Mimo's traffic](#capturing-dji-mimos-traffic). |
| `reply … error 0x..` | The gimbal understood the command and rejected it. | Check the payload: speed values, duration, mode byte. |
| `Characteristic … was not found` | The firmware uses different BLE UUIDs. | Run `uv run list_services.py` and update `NOTIFY` / `WRITE` in `om7_test.py`. |
| `GATT Protocol Error: Database Out Of Sync` | Windows' cached copy of the gimbal's services is out of date. | Run again; it's usually transient. If it keeps happening, remove and re-pair the gimbal. |

### Capturing DJI Mimo's traffic

If a firmware update breaks things, or you want commands beyond speed control, record the official app talking to the gimbal:

1. On an Android phone, enable **Developer options → Enable Bluetooth HCI snoop log**, then toggle Bluetooth off and on.
2. Open Mimo, connect to the OM7, and do one action at a time (e.g. push the joystick right for 2 seconds). Note what you did and when.
3. Collect the log with `adb bugreport` (the file is `btsnoop_hci.log` inside the zip) and open it in **Wireshark**.
4. Filter with `btatt`. Look at writes to `fff5` and compare them with the [frame layout](#protocol-reference).

---

## Protocol reference

The gimbal speaks DJI's **DUML** protocol over BLE characteristic `fff5` (write) and `fff4` (notify). A move frame is 21 bytes, little-endian:

| Bytes | Field | Value used here |
|---|---|---|
| 0 | Sync | `55` |
| 1–2 | Length (10 bits) + version (6 bits) | `15 04` → 21 bytes, version 1 |
| 3 | Header CRC8 over bytes 0–2 | `a9` |
| 4 | Sender | `02` (app) |
| 5 | Receiver | `04` (gimbal) |
| 6–7 | Sequence number | increments per frame |
| 8 | Command type | `40` = request, reply wanted · `00` = no reply · replies arrive with bit 7 set (`80`) |
| 9 | Command set | `04` (gimbal) |
| 10 | Command | `0c` = speed ✅ · `14` = angle ❌ ignored on OM7 |
| 11–12 | Yaw, signed int16 | speed: `2c 01` = 300 · angle: 0.1° units |
| 13–14 | Roll, signed int16 | `00 00` |
| 15–16 | Pitch, signed int16 | `00 00` |
| 17 | Mode | `80` = speed · `04` = relative angle · `05` = absolute angle |
| 18 | Duration, 0.1 s units | `0a` = 1.0 s |
| 19–20 | CRC16 over the whole frame | |

**Replies** use the same framing with sender and receiver swapped, the same sequence number, and type `80`. The first payload byte is the status: `00` means success.

**Checksums:** CRC8 uses seed `0x77` and reflected polynomial `0x8C`. CRC16 uses seed `0x3692` and reflected polynomial `0x8408`. `om7_test.py` starts its CRC16 from `0xDF0C`, which is the result of running it over the fixed 4-byte header first. That shortcut only works while the frame is 21 bytes long; `probe.py` has a general builder for frames of any length. Both checksums were checked against four real Mimo frames recorded in om-research.

**Status messages from the gimbal:** the OM7 sends dozens of messages per second without being asked. The ones seen so far:

| Cmd set / cmd | Approx. rate | Notes |
|---|---|---|
| `04/05` | ~1 Hz | Gimbal status. The first fields look like angles in 0.1°; the third follows the pan. |
| `04/27`, `04/57`, `04/6f`, `04/1c`, `04/38` | various | Not decoded. `04/57` is sent from address `0x27` and asks for a reply. |
| `05/06` | ~2 Hz | Battery, according to om-research. |
| `00/32` | ~1 Hz | Contains the device's serial number as ASCII. |
| `00/00`, `00/f1` | ~1 Hz | `00/00` asks for a reply (type `0x20`). |

## Known limitations and open questions

- **OM7 only.** Tested on one unit, one firmware version, on Windows 11. Reports for other setups are welcome; see [Contributing](#contributing).
- **No angle positioning.** Without the `04/14` command you can't say "point at 30°". You can only turn at a speed for a time. Closed-loop positioning built on the `04/05` telemetry is possible, but not implemented.
- **Speed units unknown.** A yaw value of 300 for 1 s gives about 15°, and the scaling hasn't been measured.
- **Telemetry fields not fully decoded.** Which `04/05` field is which axis is a guess.
- **Gimbal requests go unanswered.** The gimbal sends messages that ask for a reply (`00/00`, `04/57`). The script ignores them, and so far that hasn't mattered.
- **Unexplored service.** The OM7 has a second vendor service, `15f1e600-a277-43fc-a484-dd39ef8a9100`, whose purpose is unknown.
- **macOS and Linux:** the paired-device lookup is Windows-only. Elsewhere the script falls back to scanning, so the gimbal must be advertising, i.e. not connected to anything. On Linux, om-research notes the gimbal must not be connected to the host for bleak to connect.

## Contributing

Issues and pull requests are welcome. These are especially useful:

- **Results from other setups:** another OM7 firmware version, macOS or Linux. Include the full output of `uv run probe.py` and `uv run om7_test.py` (remove your device's MAC address if you like).
- **Decoded fields:** anything about the `04/05` telemetry, the speed units or the undecoded messages.
- **Mimo captures:** HCI snoop logs of specific actions, especially anything that sets an absolute angle on the OM7.

Please keep changes OM7-focused. Support for other models belongs upstream in om-research or in a separate module.

By contributing, you agree that your contributions are licensed under the project's [Apache License 2.0](#license).

## Credits

- [alkersan/om-research](https://github.com/alkersan/om-research): the reverse-engineered Osmo Mobile BLE protocol (frame layout, characteristics, commands) that this project is built on.
- [bleak](https://github.com/hbldh/bleak): the cross-platform Python BLE library.

## License

Licensed under the [Apache License, Version 2.0](LICENSE). You may use, modify and distribute this project under its terms. It is distributed on an "AS IS" basis, without warranties or conditions of any kind.

## Safety and disclaimer

- The gimbal moves on its own. Keep fingers, cables and anything fragile clear of it, and be ready to power it off.
- These scripts only send motion commands and read-only queries. They don't write firmware or settings.
- "DJI", "Osmo" and "Mimo" are trademarks of SZ DJI Technology Co., Ltd. This project is not affiliated with or endorsed by DJI. It's provided as-is, without warranty, for interoperability and educational purposes.
