# USB via Ethernet for Proxmox

## Overview

This project enables USB serial devices (ESP32, Arduino, etc.) connected to a Raspberry Pi to be used by containers running on Proxmox VMs over the network. The solution supports two modes:

- **USB/IP**: Full USB device passthrough using kernel modules (supports any USB device)
- **RFC2217**: Serial-over-TCP using esptool's RFC2217 server (simpler, ESP32-optimized)

The Pi web portal allows per-device mode selection. USB/IP uses a push-based architecture where the Pi controls all USB state.

## Problem Statement

When developing embedded firmware on a Proxmox VM:
- USB devices are physically distant from the VM
- Containers cannot directly access USB hardware
- USB passthrough to VMs is inflexible
- USB over network solutions often have stale connection issues

## Solution Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           DEVELOPMENT SETUP                               │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────┐                     ┌─────────────────────────────┐ │
│  │  Raspberry Pi   │                     │      Proxmox VM             │ │
│  │                 │                     │                             │ │
│  │  ┌───────────┐  │   SSH Notification  │  ┌───────────────────────┐  │ │
│  │  │  usbipd   │──┼─────────────────────┼──│  usb-event-handler    │  │ │
│  │  └───────────┘  │   "connect 1-1.1"   │  └───────────────────────┘  │ │
│  │        │        │                     │            │                │ │
│  │        │        │                     │            ▼                │ │
│  │  ┌───────────┐  │   USB/IP Protocol   │  ┌───────────────────────┐  │ │
│  │  │  USB Hub  │◄─┼─────────────────────┼──│  usbip attach         │  │ │
│  │  └───────────┘  │   Port 3240         │  └───────────────────────┘  │ │
│  │        │        │                     │            │                │ │
│  │        ▼        │                     │            ▼                │ │
│  │  ┌───────────┐  │                     │  ┌───────────────────────┐  │ │
│  │  │   ESP32   │  │                     │  │     /dev/ttyUSB0      │  │ │
│  │  └───────────┘  │                     │  └───────────────────────┘  │ │
│  │                 │                     │            │                │ │
│  │  ┌───────────┐  │                     │            ▼                │ │
│  │  │   Portal  │  │                     │  ┌───────────────────────┐  │ │
│  │  │   :8080   │  │                     │  │      Container        │  │ │
│  │  └───────────┘  │                     │  │   pio run -t upload   │  │ │
│  │                 │                     │  └───────────────────────┘  │ │
│  └─────────────────┘                     └─────────────────────────────┘ │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

## Push-Based Model

The Raspberry Pi is the **single source of truth** for USB state. This eliminates polling and stale connections.

### Event Flow

| Event | Pi Action | VM Action |
|-------|-----------|-----------|
| USB plugged in | udev triggers → bind device → SSH notify VM → verify attachment | Receive notification → attach device |
| USB unplugged | udev triggers → SSH notify VM | Receive notification → detach device |
| Pi reboots | Timer binds all devices → notify VM for each | Attach each device |
| VM reboots | - | Boot service queries Pi → attach all |

### Why Push-Based?

**Pull-based (polling) problems:**
- VM doesn't know when USB state changes
- Polling creates unnecessary load
- Stale connections when devices disappear
- Race conditions between poll and USB events

**Push-based advantages:**
- Immediate notification of USB events
- Pi verifies VM attachment succeeded
- No stale connections - Pi knows true state
- Clean disconnect when USB is unplugged

## Components

### Raspberry Pi

| Component | Purpose |
|-----------|---------|
| `usbipd` | USB/IP daemon, exports devices on port 3240 |
| `usbip-bind.sh` | Binds serial devices for export |
| `notify-vm.sh` | Notifies VM of events, verifies attachment |
| `usbip-portal` | Web UI for setup, status, and mode selection |
| `esptool` | Provides esp_rfc2217_server for RFC2217 mode |
| udev rules | Trigger on USB connect/disconnect |

### Proxmox VM

| Component | Purpose |
|-----------|---------|
| `vhci_hcd` kernel module | Virtual USB host controller |
| `usb-event-handler` | Receives notifications, attaches/detaches |
| `usb-boot-attach` | Attaches devices on boot |

### Container

| Setting | Purpose |
|---------|---------|
| `--privileged` | Full device access |
| `c 166:* rwm` | Access ttyACM devices |
| `c 188:* rwm` | Access ttyUSB devices |
| `/dev:/dev:rslave` | See host devices |

## USB Device Information

USB/IP transfers complete USB descriptors. The VM sees full device information:

| Field | Example |
|-------|---------|
| Vendor ID | 1a86 |
| Product ID | 55d4 |
| Manufacturer | QinHeng Electronics |
| Product | USB Single Serial |
| Serial Number | 58DD029450 |

This information is available via:
- `lsusb -v` on the VM
- `/sys/bus/usb/devices/*/` sysfs attributes
- udev rules on the VM

Containers with `/dev` mounted see the same device information.

## Network Requirements

| Port | Protocol | Direction | Purpose |
|------|----------|-----------|---------|
| 3240 | TCP | VM → Pi | USB/IP data |
| 22 | TCP | Pi → VM | SSH notifications |
| 8080 | TCP | Browser → Pi | Web portal |
| 4000+ | TCP | VM → Pi | RFC2217 serial (optional) |

## Pairing Relationship

This is a **1:1 pairing** between Pi and VM:
- One Pi serves one VM
- Configuration stored in `/etc/usbip/vm.conf` (Pi) and `/etc/usbip/pi.conf` (VM)
- SSH keys enable passwordless notification

For multiple VMs, use multiple Pis.

## Supported USB Devices

The system supports serial devices with these drivers:

| Driver | Chips | Device Node |
|--------|-------|-------------|
| cp210x | CP210x (Silicon Labs) | /dev/ttyUSB* |
| ch341 | CH340, CH341 | /dev/ttyUSB* |
| ftdi_sio | FT232, FT2232 | /dev/ttyUSB* |
| cdc_acm | CDC-ACM (Arduino native USB) | /dev/ttyACM* |

Ethernet adapters are automatically skipped.

## Web Portal

The Pi provides a setup portal at `http://<pi-ip>:8080`:

### Features

- **Status**: Current VM pairing with user@host format
- **USB Devices**: Real-time list with attachment status
  - Green (attached): Device connected to VM
  - Yellow (bound): Device available but not attached
- **VM Discovery**: mDNS discovery of VMs on local network
- **Configuration**:
  - VM hostname/IP
  - Username (default: dev)
- **Actions**:
  - Test Connection: Verify SSH connectivity
  - Setup Pairing: Save config and attach all devices
  - Attach All: Manual fallback to attach unattached devices
  - Disconnect: Remove pairing

## Troubleshooting

### Check Pi Status

```bash
# USB/IP daemon running?
systemctl status usbipd

# Devices bound?
usbip list -l

# Portal running?
systemctl status usbip-portal
```

### Check VM Status

```bash
# Kernel module loaded?
lsmod | grep vhci

# Devices attached?
sudo usbip port

# Serial devices visible?
ls -la /dev/ttyUSB* /dev/ttyACM*
```

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| SSH fails | Host key not in known_hosts | `ssh-keyscan <vm-ip> >> ~/.ssh/known_hosts` |
| Device not attaching | Kernel module missing | `sudo modprobe vhci_hcd` |
| Permission denied | Sudoers not configured | Add usbip to sudoers.d |
| Portal can't SSH | Root key missing | Copy SSH key to /root/.ssh/ |

## Security Considerations

- SSH keys should be specific to this use case
- USB/IP port 3240 should be on trusted network
- Consider firewall rules limiting access
- Portal runs as root for device access

## RFC2217 Alternative (ESP32 Development)

For ESP32/ESP8266 development, RFC2217 provides a simpler alternative to USB/IP. It exposes the serial port directly over TCP without kernel modules.

### Comparison

| Feature | USB/IP | RFC2217 |
|---------|--------|---------|
| Complexity | High (kernel modules) | Low (userspace only) |
| Blocking risk | Yes (kernel hangs) | No |
| Device appears as | /dev/ttyUSB0 | Network socket |
| esptool support | Native | Native (`rfc2217://host:port`) |
| Other USB devices | Yes (any USB) | No (serial only) |

### When to Use RFC2217

- ESP32/ESP8266 development only
- You only need serial (flashing + monitoring)
- You want reliability over complexity

### When to Use USB/IP

- Need non-serial USB devices (JTAG, HID, etc.)
- Software requires a real /dev/ttyUSB* path
- Multiple device types on same Pi

### Per-Device Mode Selection

The web portal allows selecting USB/IP or RFC2217 mode per device:

1. Open the portal at `http://<pi-ip>:8080`
2. Find the device in the USB Devices list
3. Use the mode dropdown to select "USB/IP" or "RFC2217"
4. RFC2217 devices show their port number (e.g., 4000)

### Using RFC2217 from Containers

```bash
# esptool (use --no-stub for reliability)
esptool --no-stub --port 'rfc2217://192.168.0.87:4000?ign_set_control' chip_id
esptool --no-stub --port 'rfc2217://192.168.0.87:4000?ign_set_control' flash_id

# ESP-IDF
export ESPPORT='rfc2217://192.168.0.87:4000?ign_set_control'
idf.py flash monitor

# PlatformIO (platformio.ini)
upload_port = rfc2217://192.168.0.87:4000?ign_set_control
monitor_port = rfc2217://192.168.0.87:4000?ign_set_control
```

### RFC2217 Network Ports

| Port | Purpose |
|------|---------|
| 4000 | First RFC2217 device |
| 4001 | Second RFC2217 device |
| ... | Additional devices |

## Performance Notes

- USB/IP adds minimal latency for serial devices
- RFC2217 may have slightly higher latency but better reliability
- Baud rates up to 921600 work reliably
- Use wired Ethernet over Wi-Fi for stability
- Short USB cables reduce signal issues

## Files Reference

### Pi Files

| Path | Purpose |
|------|---------|
| `/usr/local/bin/notify-vm.sh` | Notify VM of USB events |
| `/usr/local/bin/usbip-bind.sh` | Bind devices for export |
| `/usr/local/bin/usbip-portal` | Web portal |
| `/etc/usbip/vm.conf` | VM_HOST, VM_USER config |
| `/etc/systemd/system/usbip*` | Service files |
| `/etc/udev/rules.d/99-usbip.rules` | USB event triggers |

### VM Files

| Path | Purpose |
|------|---------|
| `/usr/local/bin/usb-event-handler` | Handle Pi notifications |
| `/usr/local/bin/usb-boot-attach` | Attach on boot |
| `/etc/usbip/pi.conf` | DEFAULT_PI_HOST config |
| `/etc/sudoers.d/usbip` | Passwordless usbip access |
