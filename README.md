# ESP32 Serial Sharing via RFC2217

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Platform](https://img.shields.io/badge/Platform-Raspberry%20Pi-red.svg)](https://www.raspberrypi.org/)
[![Proxmox](https://img.shields.io/badge/Proxmox-Containers-orange.svg)](https://www.proxmox.com/)
[![RFC2217](https://img.shields.io/badge/Protocol-RFC2217-green.svg)](https://datatracker.ietf.org/doc/html/rfc2217)
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)

## The Problem

Proxmox (and other hypervisors) can only pass an **entire USB controller** to a single VM — not individual ports. If you have three ESP32 boards on one USB controller, only one VM can access them. You can't split them across containers or VMs.

Buying a dedicated USB PCIe card per VM gets expensive fast and doesn't help with containers (LXC), which can't do USB passthrough at all.

## The Solution

Move the USB devices to a **cheap Raspberry Pi** (even a Pi Zero works) and share them over the network using the RFC2217 serial protocol. Any number of VMs and containers can each connect to their own device — no USB passthrough needed.

Plug a device in, and the Pi automatically starts an RFC2217 server for it on a fixed TCP port. Unplug it, and the server stops. A web portal shows what's running and lets you copy connection URLs.

From any container or VM on the network, connect with a single line:

```python
ser = serial.serial_for_url("rfc2217://192.168.0.87:4001?ign_set_control")
```

This works for **monitoring**, **flashing** (esptool, PlatformIO, ESP-IDF), and any tool that supports RFC2217 or pyserial.

---

## 📡 How It Works

```
                                    Proxmox Host
                                   ┌─────────────────────────────────┐
┌──────────────┐                   │  VM                             │
│ Raspberry Pi │                   │ ┌─────────────────────────────┐ │
│    Zero      │    Network        │ │ Container A                 │ │
│              │◄──────────────────┼─┤   rfc2217://pi:4001         │ │
│ ESP32 #1 ────┼── Port 4001       │ │   (monitors ESP32 #1)       │ │
│ ESP32 #2 ────┼── Port 4002       │ └─────────────────────────────┘ │
│              │                   │ ┌─────────────────────────────┐ │
│ Web Portal ──┼── Port 8080       │ │ Container B                 │ │
│              │◄──────────────────┼─┤   rfc2217://pi:4002         │ │
└──────────────┘                   │ │   (monitors ESP32 #2)       │ │
                                   │ └─────────────────────────────┘ │
                                   └─────────────────────────────────┘
```

Each physical USB port on the Pi's hub is a **slot** with a fixed TCP port. The mapping is based on the physical connector position — not the device plugged into it — so you can swap boards and the port stays the same.

---

## ⚡ Quick Start

### 1. Setup Raspberry Pi Zero

```bash
git clone https://github.com/SensorsIot/Serial-via-Ethernet.git
cd Serial-via-Ethernet/pi
bash install.sh
```

After installation, discover your USB port slots and generate the configuration:

```bash
rfc2217-learn-slots
```

Review and edit the slot configuration as needed:

```bash
sudo nano /etc/rfc2217/slots.json
```

### 2. 🖥️ Access Web Portal

Open **http://\<pi-ip\>:8080** in your browser.

- See connected devices
- Start/Stop RFC2217 servers
- Copy connection URLs

### 3. Connect from Containers

**Option A: Query the devices API**

```bash
# List all configured slots and their status
curl http://PI_IP:8080/api/devices
# Returns: {"slots": [{"label": "ESP32-A", "tcp_port": 4001, "running": true, ...}, ...]}
```

**Option B: Direct URL (slot-based ports)**

```python
import serial

# Container A (Slot 1 — port 4001)
ser = serial.serial_for_url("rfc2217://PI_IP:4001", baudrate=115200)

# Container B (Slot 2 — port 4002)
ser = serial.serial_for_url("rfc2217://PI_IP:4002", baudrate=115200)
```

---

## 🔌 Container Setup

### Docker

```yaml
# docker-compose.yml
services:
  esp32-monitor-a:
    image: python:3.11-slim
    command: python /app/monitor.py
    volumes:
      - ./monitor.py:/app/monitor.py
    environment:
      - ESP32_PORT=rfc2217://PI_IP:4001?ign_set_control
    network_mode: bridge

  esp32-monitor-b:
    image: python:3.11-slim
    command: python /app/monitor.py
    volumes:
      - ./monitor.py:/app/monitor.py
    environment:
      - ESP32_PORT=rfc2217://PI_IP:4002?ign_set_control
    network_mode: bridge
```

### LXC Container

No special configuration needed. Just install pyserial:

```bash
apt update && apt install -y python3-pip
pip3 install pyserial
```

### DevContainer (VS Code)

```json
{
  "name": "ESP32 Dev",
  "image": "python:3.11",
  "features": {
    "ghcr.io/devcontainers/features/python:1": {}
  },
  "postCreateCommand": "pip install pyserial esptool"
}
```

---

## 🛠️ Usage Examples

### Python with pyserial

```python
import serial
import os

PORT = os.environ.get('ESP32_PORT', 'rfc2217://192.168.0.87:4001?ign_set_control')
ser = serial.serial_for_url(PORT, baudrate=115200, timeout=1)

# Read serial data
while True:
    line = ser.readline()
    if line:
        text = line.decode('utf-8', errors='replace').strip()
        print(text)

        # Simple AI-like monitoring
        if 'Guru Meditation' in text or 'Backtrace:' in text:
            print("ALERT: Crash detected!")
        if 'heap' in text.lower() and 'free' in text.lower():
            # Parse heap info
            pass
```

### esptool (Flashing)

```bash
# Flash firmware
esptool --port 'rfc2217://PI_IP:4001?ign_set_control' \
    write_flash 0x0 firmware.bin

# Read chip info
esptool --port 'rfc2217://PI_IP:4001?ign_set_control' chip_id
```

### PlatformIO

```ini
; platformio.ini
[env:esp32]
platform = espressif32
board = esp32dev
upload_port = rfc2217://PI_IP:4001?ign_set_control
monitor_port = rfc2217://PI_IP:4001?ign_set_control
```

### ESP-IDF

```bash
export ESPPORT='rfc2217://PI_IP:4001?ign_set_control'
idf.py flash monitor
```

### Local /dev/tty via socat

If your tool requires a local device path:

```bash
# In the container
apt install -y socat

# Create virtual serial port
socat pty,link=/dev/ttyESP32,raw,echo=0 tcp:PI_IP:4001 &

# Now use /dev/ttyESP32 as normal
cat /dev/ttyESP32
```

---

## 🤖 AI Monitoring Example

```python
#!/usr/bin/env python3
"""ESP32 AI Monitor - Detect patterns and alert on issues"""

import serial
import json
import re
import os
from datetime import datetime

PORT = os.environ.get('ESP32_PORT', 'rfc2217://192.168.0.87:4001?ign_set_control')

# Alert patterns
PATTERNS = {
    'crash': [r'Guru Meditation', r'Backtrace:', r'assert failed'],
    'memory': [r'heap.*free.*(\d+)', r'MALLOC_CAP'],
    'wifi': [r'WIFI.*DISCONNECT', r'wifi:.*reason'],
    'boot': [r'rst:.*boot:', r'configsip:'],
}

def analyze_line(line):
    """Analyze a line for patterns"""
    alerts = []
    for category, patterns in PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, line, re.IGNORECASE):
                alerts.append({
                    'category': category,
                    'pattern': pattern,
                    'line': line,
                    'timestamp': datetime.now().isoformat()
                })
    return alerts

def main():
    print(f"Connecting to {PORT}...")
    ser = serial.serial_for_url(PORT, baudrate=115200, timeout=1)
    print("Connected. Monitoring...")

    while True:
        try:
            line = ser.readline()
            if not line:
                continue

            text = line.decode('utf-8', errors='replace').strip()
            if not text:
                continue

            # Print the line
            print(text)

            # Analyze for alerts
            alerts = analyze_line(text)
            for alert in alerts:
                print(f"\n*** ALERT [{alert['category']}] ***")
                print(json.dumps(alert, indent=2))
                print()

        except Exception as e:
            print(f"Error: {e}")
            break

if __name__ == '__main__':
    main()
```

---

## 🔗 Port Assignment

Ports are assigned based on **slot** — the physical USB port position on the Pi (or hub). This means a device always gets the same TCP port regardless of which `/dev/ttyUSBx` name the kernel assigns, as long as it is plugged into the same physical port.

Slot configuration is stored in `/etc/rfc2217/slots.json`:

```json
{
  "slots": [
    {"slot_key": "platform-3f980000.usb-usb-0:1.2:1.0", "label": "ESP32-A", "tcp_port": 4001},
    {"slot_key": "platform-3f980000.usb-usb-0:1.3:1.0", "label": "ESP32-B", "tcp_port": 4002}
  ]
}
```

Use `rfc2217-learn-slots` to discover the slot keys for your connected devices, then edit the file to assign labels and ports.

**Key feature:** When an ESP32 resets or reconnects, it keeps the same port as long as it stays in the same physical USB slot. The portal supervisor automatically restarts proxies on hotplug events.

---

## 📋 Serial Logging

All serial traffic is automatically logged with timestamps to `/var/log/serial/` on the Pi.

**Log file naming:**
```
FT232R_USB_UART_A5069RR4_2026-02-03.log
CP2102_USB_to_UART_0001_2026-02-03.log
```

**Log format:**
```
[2026-02-03 19:32:00.154] [RX] Boot message from ESP32...
[2026-02-03 19:32:00.258] [INFO] Baudrate changed to 115200
[2026-02-03 19:32:00.711] [TX] Data sent to ESP32...
```

**View logs on Pi:**
```bash
tail -f /var/log/serial/*.log
```

**View portal service logs:**
```bash
journalctl -u rfc2217-portal -f
```

This allows debugging and post-mortem analysis of device behavior.

---

## 🔧 Troubleshooting

### Connection Refused

```bash
# Check if proxy is running on Pi
ss -tlnp | grep 400

# Check portal logs for errors
journalctl -u rfc2217-portal --no-pager -n 50

# Or start a proxy manually for testing
python3 /usr/local/bin/serial_proxy.py -p 4001 /dev/ttyUSB0
```

### Device Not Detected

```bash
# On Pi, check USB devices
ls -la /dev/ttyUSB* /dev/ttyACM*

# Check dmesg for USB events
dmesg | tail -20
```

### Timeout During Flash

Use `--no-stub` flag:
```bash
esptool --no-stub --port 'rfc2217://PI_IP:4001?ign_set_control' flash_id
```

### Hotplug Events Not Reaching Portal

udev runs `RUN+=` handlers inside a network-isolated sandbox (`PrivateNetwork=yes`), so `curl` to `localhost` silently fails. The fix is to wrap the notify script with `systemd-run --no-block` in the udev rule — this runs it outside the sandbox. The included `99-rfc2217-hotplug.rules` already does this. If you write custom rules, make sure to use `systemd-run`.

### Port Busy

Only one client can connect at a time. Close other connections first.

---

## 📂 Files

```
pi/
├── portal.py                     # Web portal + proxy supervisor (v3)
├── serial_proxy.py               # RFC2217 proxy with serial logging
├── install.sh                    # Installer script
├── rfc2217-learn-slots           # Slot discovery tool
├── config/
│   └── slots.json                # Slot configuration (template)
├── scripts/
│   └── rfc2217-udev-notify.sh   # udev event forwarder
├── udev/
│   └── 99-rfc2217-hotplug.rules # udev rules for hotplug events
└── systemd/
    └── rfc2217-portal.service   # systemd unit for the portal
```

---

## 📡 API Endpoints

The portal exposes a JSON API on port 8080:

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/devices` | List all slots with current status |
| GET | `/api/info` | System info (host IP, slot counts) |
| POST | `/api/hotplug` | Receive udev hotplug events (used by `rfc2217-udev-notify.sh`) |
| POST | `/api/start` | Manually start a proxy for a slot (`slot_key`, `devnode` required) |
| POST | `/api/stop` | Manually stop a proxy for a slot (`slot_key` required) |

**Example:**
```bash
# List all slots
curl http://PI_IP:8080/api/devices

# System info
curl http://PI_IP:8080/api/info

# Manually stop a slot
curl -X POST http://PI_IP:8080/api/stop \
  -H "Content-Type: application/json" \
  -d '{"slot_key": "platform-3f980000.usb-usb-0:1.2:1.0"}'
```

---

## 🌐 Network Requirements

| Port | Direction | Purpose |
|------|-----------|---------|
| 8080 | Browser -> Pi | Web portal |
| 4001+ | Container -> Pi | RFC2217 serial |

---

## 📄 License

MIT License - feel free to use and modify!
