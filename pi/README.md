# Serial Portal - Raspberry Pi Setup

RFC2217 serial portal that provides network access to USB serial devices. Supports automatic proxy management via udev hotplug, WiFi testing instrument, and ESP32-C3 native USB flashing.

## Quick Install

```bash
cd pi
sudo bash install.sh
```

This installs all components, configures systemd/udev, and starts the portal on port 8080.

## After Installation

1. **Discover slot keys** by plugging in devices:
```bash
rfc2217-learn-slots
```

2. **Edit slot configuration**:
```bash
sudo nano /etc/rfc2217/slots.json
```

3. **Restart portal**:
```bash
sudo systemctl restart rfc2217-portal
```

## Architecture

```
USB Hub Slots              Portal (:8080)              Clients
─────────────              ──────────────              ───────
SLOT1 (ttyUSB0) ───► esp_rfc2217_server :4001 ◄──── esptool / pyserial
SLOT2 (ttyACM0) ───► plain_rfc2217_server :4002 ◄── esptool (ESP32-C3)
SLOT3 (ttyUSB1) ───► esp_rfc2217_server :4003 ◄──── esptool / pyserial
```

The portal automatically selects the right RFC2217 server based on device type:
- **ttyUSB** (UART bridges like CP2102/CH340): `esp_rfc2217_server` (Espressif)
- **ttyACM** (native USB CDC like ESP32-C3): `plain_rfc2217_server` (direct DTR/RTS passthrough)

### Why Two Servers?

ESP32-C3's native USB Serial/JTAG controller handles bootloader entry internally via DTR/RTS signals. Espressif's `esp_rfc2217_server` uses `EspPortManager` which **intercepts** DTR/RTS to run its own reset sequence — this works for UART bridge chips but breaks C3 native USB. The plain server uses pyserial's standard `PortManager` which passes DTR/RTS directly to the device.

## Components

| File | Installs to | Purpose |
|------|-------------|---------|
| `portal.py` | `/usr/local/bin/rfc2217-portal` | HTTP portal + proxy supervisor |
| `serial_proxy.py` | `/usr/local/bin/serial_proxy.py` | RFC2217 server with logging |
| `plain_rfc2217_server.py` | `/usr/local/bin/plain_rfc2217_server.py` | Plain RFC2217 for ttyACM devices |
| `wifi_controller.py` | `/usr/local/bin/wifi_controller.py` | WiFi test instrument controller |
| `rfc2217-learn-slots` | `/usr/local/bin/rfc2217-learn-slots` | Discover USB hub slot keys |

## API

```bash
# List devices
curl http://192.168.0.87:8080/api/devices

# Portal info
curl http://192.168.0.87:8080/api/info
```

## Flashing ESP32-C3 (No Buttons)

```bash
# Check which port the C3 is on
curl -s http://192.168.0.87:8080/api/devices

# Flash at 921600 baud (replace port with actual slot)
python3 -m esptool --chip esp32c3 \
  --port "rfc2217://192.168.0.87:4002" \
  --baud 921600 \
  write-flash -z 0x0 firmware.bin
```

## Flashing ESP32 DevKit (ttyUSB)

```bash
python3 -m esptool --chip esp32 \
  --port "rfc2217://192.168.0.87:4001?ign_set_control" \
  --baud 921600 \
  write-flash -z 0x0 firmware.bin
```

Note: `ign_set_control` is needed for `esp_rfc2217_server` to avoid RFC2217 control negotiation timeouts.

## Serial Logging

When `serial_proxy.py` is used, all traffic is logged to `/var/log/serial/`:

```bash
tail -f /var/log/serial/*.log
```

## Troubleshooting

```bash
# Check portal status
sudo systemctl status rfc2217-portal

# View portal logs
sudo journalctl -u rfc2217-portal -f

# Check connected devices
ls -la /dev/ttyUSB* /dev/ttyACM*

# Check listening ports
ss -tlnp | grep 400

# Restart portal
sudo systemctl restart rfc2217-portal
```

### Common Issues

| Issue | Solution |
|-------|----------|
| Connection refused | Check `curl http://192.168.0.87:8080/api/devices` — proxy may not be running |
| Timeout during flash | Try `--no-stub` flag with esptool |
| "Wrong boot mode" on C3 | Ensure plain_rfc2217_server is being used (check portal logs for "using plain RFC2217") |
| Port busy | Only one client can connect at a time — close other connections |
