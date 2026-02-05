# ESP32 Serial Sharing via RFC2217

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Platform](https://img.shields.io/badge/Platform-Raspberry%20Pi-red.svg)](https://www.raspberrypi.org/)
[![Proxmox](https://img.shields.io/badge/Proxmox-Containers-orange.svg)](https://www.proxmox.com/)
[![RFC2217](https://img.shields.io/badge/Protocol-RFC2217-green.svg)](https://datatracker.ietf.org/doc/html/rfc2217)
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![ESP32](https://img.shields.io/badge/Devices-ESP32%20%7C%20Arduino-brightgreen.svg)](https://www.espressif.com/)

## 🎯 The Problem

Proxmox (and other hypervisors) can only pass an **entire USB controller** to a single VM — not individual ports. If you have three ESP32 boards on one USB controller, only one VM can access them. You can't split them across containers or VMs.

Buying a dedicated USB PCIe card per VM gets expensive fast and doesn't help with containers (LXC), which can't do USB passthrough at all.

## 💡 The Solution

Move the USB devices to a **cheap Raspberry Pi** (even a Pi Zero works) and share them over the network using the RFC2217 serial protocol. Any number of VMs and containers can each connect to their own device — no USB passthrough needed.

From any container or VM on the network, connect with a single line:

```python
ser = serial.serial_for_url("rfc2217://serial1:4001?ign_set_control")
```

## 📋 What It Does

- **Plug in a device** → the Pi automatically starts an RFC2217 server for it on a fixed TCP port
- **Unplug it** → the server stops cleanly
- **Swap boards freely** — the TCP port is tied to the physical USB connector, not the device
- **Flash firmware remotely** — works with esptool, PlatformIO, and ESP-IDF over the network
- **Monitor serial output** — stream ESP32 logs to any container or VM in real time
- **Web portal** at port 8080 — see what's connected, copy connection URLs, start/stop servers
- **Serial traffic logging** — all traffic timestamped and logged on the Pi for post-mortem analysis
- One client per device at a time (RFC2217 protocol limitation)

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

Each physical USB port on the Pi's hub is a **slot** with a fixed TCP port. The mapping is based on the physical connector position — not the device plugged into it — so you can swap boards and the port stays the same. When a device resets or reconnects, it keeps its port automatically.

---

## ⚡ Installation & Usage

### Prerequisites

- Raspberry Pi (Zero, Zero W, 3, 4, or 5) with Raspbian/Raspberry Pi OS
- USB hub (if more than one device)
- Python 3.9+
- Network connectivity between Pi and your VMs/containers

### 🚀 Quick Start

```bash
git clone https://github.com/SensorsIot/Serial-via-Ethernet.git
cd Serial-via-Ethernet/pi
bash install.sh
```

After installation, discover your USB port slots:

```bash
rfc2217-learn-slots
```

Review and edit the slot configuration:

```bash
sudo nano /etc/rfc2217/slots.json
```

### 🔧 Configuration

Slot configuration maps physical USB ports to TCP ports in `/etc/rfc2217/slots.json`:

```json
{
  "slots": [
    {"slot_key": "platform-3f980000.usb-usb-0:1.2:1.0", "label": "ESP32-A", "tcp_port": 4001},
    {"slot_key": "platform-3f980000.usb-usb-0:1.3:1.0", "label": "ESP32-B", "tcp_port": 4002}
  ]
}
```

Use `rfc2217-learn-slots` to discover the `slot_key` values — plug each device in one at a time and run the tool.

### 🖥️ Web Portal

Open **http://\<pi-ip\>:8080** in your browser.

- See connected devices and their status
- Start/stop RFC2217 servers per slot
- Click to copy connection URLs

### 🛠️ Usage Examples

**Python with pyserial:**

```python
import serial

ser = serial.serial_for_url("rfc2217://serial1:4001?ign_set_control", baudrate=115200)
while True:
    line = ser.readline()
    if line:
        print(line.decode('utf-8', errors='replace').strip())
```

**esptool (flashing):**

```bash
esptool --port 'rfc2217://serial1:4001?ign_set_control' write_flash 0x0 firmware.bin
esptool --port 'rfc2217://serial1:4001?ign_set_control' chip_id
```

**PlatformIO:**

```ini
; platformio.ini
[env:esp32]
platform = espressif32
board = esp32dev
upload_port = rfc2217://serial1:4001?ign_set_control
monitor_port = rfc2217://serial1:4001?ign_set_control
```

**ESP-IDF:**

```bash
export ESPPORT='rfc2217://serial1:4001?ign_set_control'
idf.py flash monitor
```

**Local /dev/tty via socat** (for tools that need a device path):

```bash
apt install -y socat
socat pty,link=/dev/ttyESP32,raw,echo=0 tcp:serial1:4001 &
cat /dev/ttyESP32
```

### 🔌 Container Setup

**Docker:**

```yaml
# docker-compose.yml
services:
  esp32-monitor:
    image: python:3.11-slim
    command: python /app/monitor.py
    volumes:
      - ./monitor.py:/app/monitor.py
    environment:
      - ESP32_PORT=rfc2217://serial1:4001?ign_set_control
```

**LXC Container:**

```bash
apt update && apt install -y python3-pip
pip3 install pyserial
```

**DevContainer (VS Code):**

```json
{
  "name": "ESP32 Dev",
  "image": "python:3.11",
  "postCreateCommand": "pip install pyserial esptool"
}
```

### ❓ Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Connection refused | Proxy not running | Check portal at :8080; verify device is plugged in |
| Timeout during flash | Network latency | Use `esptool --no-stub` for reliability over network |
| Port busy | Another client connected | Close the other connection first (one client per device) |
| Hotplug events not reaching portal | udev `PrivateNetwork` sandbox blocks `curl` to localhost | Use `systemd-run --no-block` in udev rules (already done in included rules). If writing custom rules, wrap your script with `systemd-run`. |
| Device not detected | USB issue | Run `ls /dev/ttyUSB* /dev/ttyACM*` and `dmesg | tail` on the Pi |

---

## 🔧 Under the Hood

### 📋 Serial Logging

All serial traffic is logged with timestamps to `/var/log/serial/` on the Pi:

```
[2026-02-03 19:32:00.154] [RX] Boot message from ESP32...
[2026-02-03 19:32:00.258] [INFO] Baudrate changed to 115200
```

View logs: `tail -f /var/log/serial/*.log`
Portal logs: `journalctl -u rfc2217-portal -f`

### 📡 API Endpoints

The portal exposes a JSON API on port 8080:

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/devices` | List all slots with current status |
| GET | `/api/info` | System info (host IP, slot counts) |
| POST | `/api/hotplug` | Receive udev hotplug events |
| POST | `/api/start` | Manually start a proxy (`slot_key`, `devnode`) |
| POST | `/api/stop` | Manually stop a proxy (`slot_key`) |

```bash
curl http://serial1:8080/api/devices
curl http://serial1:8080/api/info
```

### 📂 Files

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

### 🌐 Network Ports

| Port | Direction | Purpose |
|------|-----------|---------|
| 8080 | Browser/API → Pi | Web portal and REST API |
| 4001+ | Container/VM → Pi | RFC2217 serial connections |

---

## 📚 Attributions & References

- [RFC 2217](https://datatracker.ietf.org/doc/html/rfc2217) — Telnet Com Port Control Option
- [pyserial](https://pyserial.readthedocs.io/) — Python serial port library with RFC2217 support
- [esptool](https://github.com/espressif/esptool) — ESP32 flashing tool (also provides `esp_rfc2217_server.py`)
- [PlatformIO](https://platformio.org/) — Embedded development platform
- [ESP-IDF](https://docs.espressif.com/projects/esp-idf/) — Espressif IoT Development Framework

## 📄 License

MIT License — feel free to use and modify.
