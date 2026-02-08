#!/usr/bin/env python3
"""
Test: ESP32-C3 native USB boot mode switching.

Runs ON THE PI where /dev/ttyACM0 is physically connected.
Tests switching between download mode and running (SPI boot) mode
via the USB-Serial/JTAG controller's DTR/RTS mechanism.

Usage:
    ssh pi@192.168.0.87 "python3 /tmp/c3_reset_test.py"
"""
import os
import serial
import subprocess
import sys
import time


PORT = "/dev/ttyACM0"
BAUD = 115200
ESPTOOL = "python3 -m esptool"


def read_serial_state(timeout=5):
    """Open serial, read output, detect boot mode. Returns (state, output)."""
    try:
        ser = serial.Serial(PORT, BAUD, timeout=2)
        ser.dtr = False
        output = ""
        deadline = time.time() + timeout
        while time.time() < deadline:
            data = ser.read(1024)
            if data:
                text = data.decode("utf-8", errors="replace")
                output += text
                # Check for definitive state indicators
                if "waiting for download" in output:
                    ser.close()
                    return "download", output
                if "MODBUS PROXY" in output or "SPI_FAST_FLASH_BOOT" in output:
                    ser.close()
                    return "running", output
        ser.close()
        if "DOWNLOAD" in output:
            return "download", output
        if output.strip():
            return "unknown", output
        return "no_output", output
    except Exception as e:
        return "error", str(e)


def enter_download_mode():
    """Put C3 into download mode using esptool's USB reset sequence."""
    print("  Entering download mode via esptool chip-id...")
    result = subprocess.run(
        f"{ESPTOOL} --chip esp32c3 --port {PORT} --before=usb-reset chip-id",
        shell=True, capture_output=True, text=True, timeout=15
    )
    # esptool enters download mode, reads chip-id, then does hard reset.
    # But the hard reset is a core reset which doesn't exit download mode
    # on USB-Serial/JTAG. So the chip stays in download mode.
    # Actually, we want to STAY in download mode, so use --after=no-reset
    result = subprocess.run(
        f"{ESPTOOL} --chip esp32c3 --port {PORT} --before=usb-reset --after=no-reset chip-id",
        shell=True, capture_output=True, text=True, timeout=15
    )
    print(f"  esptool exit code: {result.returncode}")
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[-200:]}")
    return result.returncode == 0


def exit_to_running_mode():
    """Exit download mode to running (SPI boot) via watchdog reset."""
    print("  Exiting to running mode via watchdog reset...")
    result = subprocess.run(
        f"{ESPTOOL} --chip esp32c3 --port {PORT} --before=usb-reset --after=watchdog-reset chip-id",
        shell=True, capture_output=True, text=True, timeout=15
    )
    print(f"  esptool exit code: {result.returncode}")
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[-200:]}")
    return result.returncode == 0


def main():
    print("=" * 60)
    print("ESP32-C3 Native USB Boot Mode Test")
    print("=" * 60)
    print(f"Port: {PORT}")
    print()

    # Test 1: Check current state
    print("[TEST 1] Read current state (5s)...")
    state, output = read_serial_state(5)
    print(f"  State: {state}")
    if output:
        lines = output.strip().split("\n")
        for line in lines[:5]:
            print(f"  | {line}")
    print()

    # Test 2: Enter download mode
    print("[TEST 2] Enter download mode...")
    ok = enter_download_mode()
    if not ok:
        print("  FAILED to enter download mode")
        return 1
    time.sleep(2)
    state, output = read_serial_state(3)
    print(f"  State after: {state}")
    if state == "download":
        print("  PASS: In download mode")
    else:
        print(f"  FAIL: Expected download, got {state}")
    print()

    # Test 3: Exit to running mode via watchdog reset
    print("[TEST 3] Exit to running mode (watchdog reset)...")
    ok = exit_to_running_mode()
    if not ok:
        print("  FAILED to trigger watchdog reset")
        return 1

    # Critical: wait for chip to boot WITHOUT opening the serial port
    print("  Waiting 5s for chip to boot (port closed)...")
    time.sleep(5)

    state, output = read_serial_state(8)
    print(f"  State after: {state}")
    if state == "running":
        print("  PASS: Chip is running!")
        lines = output.strip().split("\n")
        for line in lines[:8]:
            print(f"  | {line}")
    else:
        print(f"  FAIL: Expected running, got {state}")
        if output:
            lines = output.strip().split("\n")
            for line in lines[:5]:
                print(f"  | {line}")
    print()

    # Test 4: Enter download mode again (from running state)
    print("[TEST 4] Enter download mode again (from running)...")
    ok = enter_download_mode()
    if not ok:
        print("  FAILED")
        return 1
    time.sleep(2)
    state, output = read_serial_state(3)
    print(f"  State after: {state}")
    if state == "download":
        print("  PASS: Back in download mode")
    else:
        print(f"  FAIL: Expected download, got {state}")
    print()

    # Test 5: Exit to running again
    print("[TEST 5] Exit to running again (watchdog reset)...")
    ok = exit_to_running_mode()
    if not ok:
        print("  FAILED")
        return 1
    print("  Waiting 5s for boot...")
    time.sleep(5)
    state, output = read_serial_state(8)
    print(f"  State after: {state}")
    if state == "running":
        print("  PASS: Chip running again!")
    else:
        print(f"  FAIL: Expected running, got {state}")
    print()

    print("=" * 60)
    print("Test complete")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
