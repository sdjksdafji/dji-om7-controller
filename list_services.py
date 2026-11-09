"""
Diagnostic: connect to a BLE device and print its GATT services and characteristics.

Run:  uv run list_services.py                     # find the gimbal the same way om7_test.py does
      uv run list_services.py AA:BB:CC:DD:EE:FF   # or pass the address

Read-only: it never writes to the device, so the gimbal won't move.
"""
import asyncio
import sys
from bleak import BleakClient
from om7_test import connect_target, find_gimbal


async def main():
    address = sys.argv[1] if len(sys.argv) > 1 else await find_gimbal()
    async with BleakClient(connect_target(address), timeout=20) as client:
        print(f"Connected to {address}")
        for service in client.services:
            print(f"{service.uuid}  {service.description}")
            for ch in service.characteristics:
                print(f"    {ch.uuid}  {','.join(ch.properties)}")


if __name__ == "__main__":
    asyncio.run(main())
