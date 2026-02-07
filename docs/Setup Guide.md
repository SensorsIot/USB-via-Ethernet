# Serial Portal User Manual

How to use the Serial Portal — connecting to serial devices over the network via RFC2217 and using the WiFi test instrument.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          Network (192.168.0.x)                           │
└──────────────────────────────────────────────────────────────────────────┘
       │  eth0 (USB Ethernet)                          │
       │                                               │
       ▼                                               ▼
┌─────────────────────────┐              ┌─────────────────────────────────┐
│  Serial Portal Pi       │              │  Your Machine / Containers      │
│  192.168.0.87           │              │                                 │
│                         │              │  ┌─────────────────────┐        │
│  ┌───────────┐          │              │  │ Container A         │        │
│  │ SLOT1     │──────────┼─ :4001 ──────┼──│ rfc2217://:4001     │        │
│  └───────────┘          │              │  └─────────────────────┘        │
│  ┌───────────┐          │              │  ┌─────────────────────┐        │
│  │ SLOT2     │──────────┼─ :4002 ──────┼──│ Container B         │        │
│  └───────────┘          │              │  │ rfc2217://:4002     │        │
│  ┌───────────┐          │              │  └─────────────────────┘        │
│  │ SLOT3     │──────────┼─ :4003       │                                 │
│  └───────────┘          │              └─────────────────────────────────┘
│                         │
│  ┌───────────────────┐  │
│  │ WiFi Tester       │  │
│  │ wlan0 (onboard)   │  │
│  │  AP: 192.168.4.1  │  │
│  └───────────────────┘  │
│                         │
│  Web Portal ────────────┼─ :8080
└─────────────────────────┘
```

### WiFi Tester Architecture

```
Your machine                         Pi Zero W
───────────                          ─────────
pytest                               portal.py :8080
  └─ WiFiTesterDriver ──HTTP──►        └─ wifi_controller.py
                                          ├─ hostapd    (AP mode)
                                          ├─ dnsmasq    (DHCP)
                                          ├─ wpa_supplicant (STA mode)
                                          ├─ iw scan
                                          └─ urllib     (HTTP relay)
```

The Pi connects to your network via **eth0** (USB Ethernet adapter). The **wlan0** radio is freed for testing.

### Key Concepts

- **Slot** — a physical USB hub connector, identified by `slot_key` (udev `ID_PATH`)
- **Same connector = same TCP port**, regardless of device or devnode name
- **Two WiFi modes** — WiFi-Testing (default, wlan0 = instrument) and Serial Interface (wlan0 = LAN)

## How RFC2217 Works

RFC2217 is a Telnet protocol extension that allows serial port control over TCP/IP. The Pi runs an RFC2217 server per USB serial device, each on a fixed TCP port determined by which physical USB hub connector (slot) the device is plugged into.

**Benefits over USB/IP:**
- No kernel modules required
- No VM configuration needed
- Works through firewalls (just TCP)
- Native support in esptool, pyserial, PlatformIO

**Limitations:**
- Serial only (no USB HID, JTAG, etc.)
- One client per device at a time
- Slightly higher latency than local serial

---

## Prerequisites

```bash
# Python with pyserial
pip3 install pyserial

# Optional: esptool for flashing
pip3 install esptool
```

Your machine must be able to reach the Pi's IP address on ports 4001–4003 and 8080.

---

## Connecting to Devices

### Query Slot Status

```bash
curl http://192.168.0.87:8080/api/devices
```

Response:

```json
{
  "slots": [
    {
      "label": "SLOT1",
      "slot_key": "platform-...-usb-0:1.1:1.0",
      "tcp_port": 4001,
      "present": true,
      "running": true,
      "devnode": "/dev/ttyACM0",
      "url": "rfc2217://192.168.0.87:4001"
    }
  ],
  "host_ip": "192.168.0.87",
  "hostname": "192.168.0.87"
}
```

### Connect from Python

```python
import serial

# Connect to SLOT1
ser = serial.serial_for_url("rfc2217://192.168.0.87:4001", baudrate=115200, timeout=1)
print(f"Connected")

while True:
    line = ser.readline()
    if line:
        print(line.decode('utf-8', errors='replace').strip())
```

### Flash with esptool

```bash
# Read chip info
esptool --port 'rfc2217://192.168.0.87:4001?ign_set_control' chip_id

# Flash firmware
esptool --port 'rfc2217://192.168.0.87:4001?ign_set_control' \
    write_flash 0x0 firmware.bin

# If timeout errors, use --no-stub
esptool --no-stub --port 'rfc2217://192.168.0.87:4001?ign_set_control' \
    write_flash 0x0 firmware.bin
```

### PlatformIO

```ini
; platformio.ini
[env:esp32]
platform = espressif32
board = esp32dev
framework = arduino

upload_port = rfc2217://192.168.0.87:4001?ign_set_control
monitor_port = rfc2217://192.168.0.87:4001?ign_set_control
monitor_speed = 115200
```

### ESP-IDF

```bash
export ESPPORT='rfc2217://192.168.0.87:4001?ign_set_control'
idf.py flash monitor
```

### Create Local /dev/tty with socat

If your tool requires a local device path:

```bash
# Install socat
apt install -y socat

# Create virtual serial port
socat pty,link=/dev/ttyESP32,raw,echo=0 tcp:192.168.0.87:4001 &

# Now use /dev/ttyESP32
cat /dev/ttyESP32
```

---

## WiFi Tester

The Pi's onboard wlan0 radio doubles as a WiFi test instrument, controlled entirely via HTTP.

### Operating Modes

| Mode | wlan0 | WiFi Tester |
|------|-------|-------------|
| WiFi-Testing (default) | Test instrument | Active |
| Serial Interface | Joins WiFi for LAN | Disabled |

Switch via web UI toggle or API:

```bash
# Switch to serial-interface mode (wlan0 joins WiFi)
curl -X POST http://192.168.0.87:8080/api/wifi/mode \
  -H 'Content-Type: application/json' \
  -d '{"mode": "serial-interface", "ssid": "MyWiFi", "pass": "password"}'

# Switch back to wifi-testing mode
curl -X POST http://192.168.0.87:8080/api/wifi/mode \
  -H 'Content-Type: application/json' \
  -d '{"mode": "wifi-testing"}'
```

### API Reference

All endpoints return `{"ok": true, ...}` or `{"ok": false, "error": "message"}`.

| Endpoint | Method | Body | Returns |
|----------|--------|------|---------|
| `/api/wifi/ping` | GET | — | `fw_version`, `uptime` |
| `/api/wifi/mode` | GET | — | `{mode, ssid?, ip?}` |
| `/api/wifi/mode` | POST | `{mode, ssid?, pass?}` | `{mode, ssid?, ip?}` |
| `/api/wifi/ap_start` | POST | `{ssid, pass?, channel?}` | `{ip}` |
| `/api/wifi/ap_stop` | POST | — | — |
| `/api/wifi/ap_status` | GET | — | `{active, ssid, channel, stations}` |
| `/api/wifi/sta_join` | POST | `{ssid, pass?, timeout?}` | `{ip, gateway}` |
| `/api/wifi/sta_leave` | POST | — | — |
| `/api/wifi/http` | POST | `{method, url, headers?, body?, timeout?}` | `{status, headers, body}` |
| `/api/wifi/scan` | GET | — | `{networks: [{ssid, rssi, auth}]}` |
| `/api/wifi/events` | GET | `?timeout=N` | `{events: [...]}` |

### Python Driver Usage

```python
from wifi_tester_driver import WiFiTesterDriver

wt = WiFiTesterDriver("http://192.168.1.50:8080")
wt.open()

# Ping
info = wt.ping()

# Start AP
wt.ap_start("MyTestAP", "password123", channel=6)
status = wt.ap_status()

# Wait for a device to connect
station = wt.wait_for_station(timeout=30)
print(f"Station joined: {station['mac']} at {station['ip']}")

# HTTP relay (request goes out via Pi's wlan0)
resp = wt.http_get(f"http://{station['ip']}/")
print(resp.status_code, resp.text)

# Scan
result = wt.scan()
for net in result["networks"]:
    print(f"  {net['ssid']}  {net['rssi']} dBm  {net['auth']}")

# STA mode (joins an external network)
wt.sta_join("HomeWiFi", "secret", timeout=15)
resp = wt.http_get("http://example.com")
wt.sta_leave()

# Cleanup
wt.ap_stop()
wt.close()
```

### Start a SoftAP

```bash
curl -X POST http://192.168.0.87:8080/api/wifi/ap_start \
  -H 'Content-Type: application/json' \
  -d '{"ssid": "TestNetwork", "pass": "password123", "channel": 6}'
```

The AP runs at `192.168.4.1/24` with DHCP range `.2`–`.20`.

### Scan for Networks

```bash
curl http://192.168.0.87:8080/api/wifi/scan
```

### Run WiFi Tests

```bash
cd pytest
pip install pytest

# Basic tests (no DUT needed)
pytest test_instrument.py --wt-url http://192.168.0.87:8080

# Full tests (requires a WiFi device connected to the AP)
pytest test_instrument.py --wt-url http://192.168.0.87:8080 --run-dut
```

### Test Coverage

| Suite | Status |
|-------|--------|
| WT-100 (ping) | pass |
| WT-104 (rapid commands) | pass |
| WT-2xx (AP management) | pass |
| WT-3xx (station events) | pass (requires DUT) |
| WT-4xx (STA mode) | pass (requires DUT) |
| WT-5xx (HTTP relay) | pass (requires DUT) |
| WT-6xx (scan) | pass |

### Networking Notes

- **AP IP** is always `192.168.4.1/24`, DHCP range `.2`–`.20` (matches ESP32)
- AP and STA modes are mutually exclusive (starting one stops the other)
- Station connect/disconnect events arrive via dnsmasq lease callbacks
- The `body` field in HTTP relay requests/responses is **base64-encoded**
- Long-poll events with `GET /api/wifi/events?timeout=5` (seconds)

---

## Serial Logging

All serial traffic is logged when using the fallback proxy (`serial_proxy.py`).

### Log Format

```
[2026-02-03 19:32:00.154] [RX] ESP32 boot message here...
[2026-02-03 19:32:00.258] [INFO] Baudrate changed to 115200
[2026-02-03 19:32:00.711] [TX] Data sent to ESP32...
```

- **[RX]** — Data received from device
- **[TX]** — Data sent to device
- **[INFO]** — Protocol events (baudrate changes, connections)

### View Logs

```bash
# Portal logs (via SSH)
ssh pi@192.168.0.87 journalctl -u rfc2217-portal -f
```

---

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| Connection refused | Proxy not running or device unplugged | Check `curl http://192.168.0.87:8080/api/devices` |
| Timeout during flash | Network latency | Use `esptool --no-stub` |
| Port busy | Another client connected | Close the other connection first |
| Wrong slot after replug | Normal | `slot_key` ensures same port; devnode may change |
| WiFi ping fails | Portal not running | Check `curl http://192.168.0.87:8080/api/wifi/ping` |
| wlan0 not available | Wrong WiFi mode | Switch to wifi-testing mode via API |
| AP won't start | hostapd not installed on Pi | Contact Pi administrator |

```bash
# Check network connectivity
ping 192.168.0.87

# Check serial status
curl http://192.168.0.87:8080/api/devices

# Check WiFi tester
curl http://192.168.0.87:8080/api/wifi/ping

# Check wlan0 exists (via SSH)
ssh pi@192.168.0.87 iw dev
```

---

## Network Requirements

| Port | Direction | Purpose |
|------|-----------|---------|
| 8080 | Client → Pi | Web portal and REST API |
| 4001–4003 | Client → Pi | RFC2217 serial connections |
| 192.168.4.x | WiFi devices → Pi | WiFi AP subnet (when AP active) |

---

## Security Considerations

- RFC2217 has **no authentication** — anyone who can reach the port can connect
- Keep on a trusted network or use VPN/firewall
- Consider SSH tunnel for remote access:

```bash
# On client, create tunnel
ssh -L 4001:localhost:4001 -L 8080:localhost:8080 pi@192.168.0.87

# Then connect to localhost
curl http://localhost:8080/api/devices
```

---

## Quick Reference

**Check status:**
```bash
curl http://192.168.0.87:8080/api/devices
curl http://192.168.0.87:8080/api/info
```

**Connect from Python:**
```python
import serial
ser = serial.serial_for_url("rfc2217://192.168.0.87:4001", baudrate=115200)
```

**Flash with esptool:**
```bash
esptool --port 'rfc2217://192.168.0.87:4001?ign_set_control' write_flash 0x0 fw.bin
```

**WiFi tester:**
```bash
# Ping
curl http://192.168.0.87:8080/api/wifi/ping

# Start AP
curl -X POST http://192.168.0.87:8080/api/wifi/ap_start \
  -H 'Content-Type: application/json' -d '{"ssid":"Test","pass":"pass1234"}'

# Check AP status
curl http://192.168.0.87:8080/api/wifi/ap_status

# Scan
curl http://192.168.0.87:8080/api/wifi/scan

# Check mode
curl http://192.168.0.87:8080/api/wifi/mode

# Stop AP
curl -X POST http://192.168.0.87:8080/api/wifi/ap_stop
```

**Web portal:** Open `http://192.168.0.87:8080` in a browser.
