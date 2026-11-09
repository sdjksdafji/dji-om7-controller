"""
Minimal Osmo Mobile 7 test: nudge the gimbal left/right over Bluetooth LE.

Based on the community-documented protocol at github.com/alkersan/om-research
(verified there on OM2/OM3/OM4). Findings on the OM7 (firmware tested 2026-11):
  - SPEED command (cmd set 0x04, cmd 0x0C, mode 0x80) works: the gimbal replies 00 00 and moves.
  - ANGLE command (cmd set 0x04, cmd 0x14, relative 0x04 / absolute 0x05) is silently
    ignored: no reply, no movement.

Setup:   uv sync
Run:     uv run om7_test.py               # finds a paired/advertising device named "OM..." / "Osmo..."
         uv run om7_test.py AA:BB:CC:...  # or pass the address directly (macOS: a UUID)

Before running: unfold and power on the gimbal, mount a phone (it's the counterweight),
and make sure DJI Mimo is closed so it isn't holding the Bluetooth connection.
"""
import asyncio
import sys
from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

NOTIFY = "0000fff4-0000-1000-8000-00805f9b34fb"
WRITE  = "0000fff5-0000-1000-8000-00805f9b34fb"

# Command-type byte (frame byte 8). om-research's gimbal.py sends 0x00, but the real
# frames captured from DJI Mimo (in om-research's CRC notes) use 0x40, which asks the
# gimbal to send back a reply. The reply tells us whether the gimbal accepted the command.
CMD_TYPE = 0x40

# Mode byte -> command id, as in om-research's gimbal.py.
MODE_RELATIVE = 0x04   # cmd 0x14, angle in 0.1 deg -- ignored by the OM7
MODE_ABSOLUTE = 0x05   # cmd 0x14, angle in 0.1 deg -- ignored by the OM7
MODE_SPEED    = 0x80   # cmd 0x0C, speed -- works on the OM7


def crc16(data: bytes, crc: int = 0xDF0C) -> int:
    # Reflected CRC-16 (poly 0x1021); the init already accounts for the 4-byte header.
    # (0xDF0C = standard DJI DUML seed 0x3692 run over the header bytes 55 15 04 A9.)
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
    return crc


def gimbal_frame(yaw: int, pitch: int = 0, roll: int = 0, mode: int = MODE_SPEED,
                 duration_s: float = 1.0, seq: int = 1) -> bytes:
    """Build a 21-byte gimbal move frame.

    yaw/pitch/roll are raw signed 16-bit values: 0.1 deg for the angle modes, speed for
    MODE_SPEED (on the OM7, yaw=300 for 1 s turned the gimbal roughly 15 deg).
    duration_s is sent in 0.1 s units (max 25.5 s).
    """
    cmd = 0x0C if mode == MODE_SPEED else 0x14
    header = bytes([0x55, 0x15, 0x04, 0xA9])              # sync, length=21, version, header CRC8
    body = (
        bytes([0x02, 0x04])                               # sender (app), receiver (gimbal)
        + (seq & 0xFFFF).to_bytes(2, "little")            # sequence number
        + bytes([CMD_TYPE, 0x04, cmd])                    # type, cmd set (gimbal), cmd
    )
    payload = (
        int(yaw).to_bytes(2, "little", signed=True)
        + int(roll).to_bytes(2, "little", signed=True)
        + int(pitch).to_bytes(2, "little", signed=True)
        + bytes([mode, int(duration_s * 10)])
    )
    return header + body + payload + crc16(body + payload).to_bytes(2, "little")


def looks_like_gimbal(name: str | None) -> bool:
    if not name:
        return False
    upper = name.upper()
    return upper.startswith("OM") or "OSMO" in upper


async def find_paired_gimbal_windows() -> str | None:
    """Look up a gimbal that is already paired with Windows.

    A BLE device that is paired and connected to Windows usually stops advertising,
    so a scan can't see it. Windows still knows its name and address, so ask Windows.
    """
    from winrt.windows.devices.bluetooth import BluetoothLEDevice
    from winrt.windows.devices.enumeration import DeviceInformation

    selector = BluetoothLEDevice.get_device_selector_from_pairing_state(True)
    for info in await DeviceInformation.find_all_async(selector, None):
        if not looks_like_gimbal(info.name):
            continue
        device = await BluetoothLEDevice.from_id_async(info.id)
        if device is None:
            continue
        raw = f"{device.bluetooth_address:012X}"
        device.close()
        address = ":".join(raw[i:i + 2] for i in range(0, 12, 2))
        print(f"Found paired {info.name} at {address}")
        return address
    return None


def connect_target(address: str) -> str | BLEDevice:
    # On Windows, BleakClient(<address string>) scans for an advertisement before
    # connecting, which fails for a paired gimbal that has stopped advertising.
    # Passing a BLEDevice skips that scan and connects through Windows directly.
    if sys.platform == "win32":
        return BLEDevice(address, None, None)
    return address


async def find_gimbal() -> str:
    if sys.platform == "win32":
        address = await find_paired_gimbal_windows()
        if address:
            return address
        print("No paired gimbal found in Windows; falling back to a scan.")
    print("Scanning for 8 seconds...")
    devices = await BleakScanner.discover(timeout=8)
    for d in devices:
        if looks_like_gimbal(d.name):
            print(f"Found {d.name} at {d.address}")
            return d.address
    print("Named devices seen:")
    for d in devices:
        if d.name:
            print(f"  {d.address}  {d.name}")
    sys.exit("No gimbal found. Is it on, and is Mimo closed? You can also pass the address.")


def make_notify_handler(state: dict):
    """Print replies to our commands, remember the latest attitude push, count the rest."""
    def on_notify(_, data: bytearray):
        if len(data) < 13 or data[0] != 0x55:
            print("  <- (unparsed)", data.hex(" "))
            return
        cmd_type, cmd_set, cmd = data[8], data[9], data[10]
        if cmd_type & 0x80:
            seq = int.from_bytes(data[6:8], "little")
            status = "OK" if data[11] == 0 else f"error {data[11]:#04x}"
            print(f"  <- reply seq={seq} set={cmd_set:02x} cmd={cmd:02x} {status} "
                  f"(payload {data[11:-2].hex(' ')})")
        elif (cmd_set, cmd) == (0x04, 0x05):
            # Periodic gimbal push (~1 Hz). The first five int16 fields look like angles in
            # 0.1 deg; fields 3 and 5 changed when the gimbal panned. Meaning is unconfirmed.
            p = data[11:21]
            state["attitude"] = [int.from_bytes(p[i:i + 2], "little", signed=True) / 10
                                 for i in range(0, 10, 2)]
        else:
            key = f"set={cmd_set:02x} cmd={cmd:02x}"
            state["counts"][key] = state["counts"].get(key, 0) + 1
    return on_notify


def fmt_attitude(state: dict) -> str:
    a = state.get("attitude")
    return " ".join(f"{v:+7.1f}" for v in a) if a else "(none yet)"


async def main():
    address = sys.argv[1] if len(sys.argv) > 1 else await find_gimbal()
    state: dict = {"counts": {}}
    async with BleakClient(connect_target(address), timeout=20) as client:
        print("Connected. Listening for gimbal messages...")
        await client.start_notify(NOTIFY, make_notify_handler(state))
        await asyncio.sleep(1.5)
        print(f"   telemetry before: {fmt_attitude(state)}")

        # Pan right, back to center, left, back to center (each ~15 deg on the OM7).
        moves = [("right", 300), ("center", -300), ("left", -300), ("center", 300)]
        for seq, (label, yaw_speed) in enumerate(moves, start=1):
            frame = gimbal_frame(yaw=yaw_speed, mode=MODE_SPEED, duration_s=1.0, seq=seq)
            print(f"-> {label:6} (yaw speed {yaw_speed:+}): {frame.hex(' ')}")
            await client.write_gatt_char(WRITE, frame, response=False)
            await asyncio.sleep(2.5)
            print(f"   telemetry after:  {fmt_attitude(state)}")

        await client.stop_notify(NOTIFY)
    print("Other (periodic) gimbal messages received:",
          ", ".join(f"{k} x{n}" for k, n in sorted(state["counts"].items())) or "none")
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
