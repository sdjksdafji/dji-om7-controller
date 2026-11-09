"""
Diagnostic: does the gimbal process ANY frame we send? (No movement.)

Sends a harmless DUML "get version" request (cmd set 0x00, cmd 0x01, reply requested)
through each writable characteristic of the gimbal's FFF0 service, with and without
write-response, and reports which combinations get a reply addressed to us.

Run:  uv run probe.py            # find the gimbal like om7_test.py
      uv run probe.py <address>
"""
import asyncio
import sys
from bleak import BleakClient
from om7_test import NOTIFY, connect_target, find_gimbal

WRITABLE = {
    "fff5": "0000fff5-0000-1000-8000-00805f9b34fb",
    "fff3": "0000fff3-0000-1000-8000-00805f9b34fb",
}
APP, GIMBAL = 0x02, 0x04


def crc8(data: bytes, crc: int = 0x77) -> int:
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8C if crc & 1 else crc >> 1
    return crc


def crc16(data: bytes, crc: int = 0x3692) -> int:
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
    return crc


def duml_frame(seq: int, cmd_set: int, cmd: int, payload: bytes = b"",
               cmd_type: int = 0x40, sender: int = APP, receiver: int = GIMBAL) -> bytes:
    """Build a DUML frame of any length, with standard DJI CRC seeds over the whole frame."""
    length = 13 + len(payload)
    head = bytes([0x55, length & 0xFF, 0x04 | (length >> 8)])
    frame = (head + bytes([crc8(head), sender, receiver]) + seq.to_bytes(2, "little")
             + bytes([cmd_type, cmd_set, cmd]) + payload)
    return frame + crc16(frame).to_bytes(2, "little")


async def main():
    address = sys.argv[1] if len(sys.argv) > 1 else await find_gimbal()
    replies: list[bytes] = []

    def on_notify(_, data: bytearray):
        if len(data) >= 13 and data[8] & 0x80:      # bit 7 of the type byte = this is a reply
            replies.append(bytes(data))

    async with BleakClient(connect_target(address), timeout=20) as client:
        await client.start_notify(NOTIFY, on_notify)
        seq = 0x100
        for name, uuid in WRITABLE.items():
            for response in (False, True):
                seq += 1
                replies.clear()
                frame = duml_frame(seq, 0x00, 0x01)
                label = f"{name} {'with' if response else 'without'} response"
                try:
                    await client.write_gatt_char(uuid, frame, response=response)
                except Exception as e:                # noqa: BLE001 -- report and keep probing
                    print(f"{label:28} write failed: {e}")
                    continue
                await asyncio.sleep(1.5)
                ours = [r for r in replies if int.from_bytes(r[6:8], "little") == seq]
                print(f"{label:28} -> {frame.hex(' ')}")
                if ours:
                    for r in ours:
                        print(f"{'':28}    REPLY {r.hex(' ')}")
                else:
                    other = f" ({len(replies)} other replies)" if replies else ""
                    print(f"{'':28}    no reply{other}")
        await client.stop_notify(NOTIFY)


if __name__ == "__main__":
    asyncio.run(main())
