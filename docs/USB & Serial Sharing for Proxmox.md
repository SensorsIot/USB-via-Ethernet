# USB & Serial Sharing for Proxmox

This project enables USB and serial devices connected to a Raspberry Pi to be used by Proxmox VMs over the network. Choose the method that fits your needs:

| Method | Best For | Complexity |
|--------|----------|------------|
| **USB/IP** | Any USB device (JTAG, HID, serial) | Higher (kernel modules on VM) |
| **RFC2217** | ESP32/Arduino serial only | Lower (userspace only) |

Both methods use a web portal on the Pi for configuration and status monitoring.

---

# Part 1: USB Sharing (USB/IP)

USB/IP provides full USB device passthrough over the network. The VM sees the device as if it were physically connected, with full USB descriptors (vendor ID, product ID, serial number).

## When to Use USB/IP

- Need non-serial USB devices (JTAG debuggers, HID devices)
- Software requires a real `/dev/ttyUSB*` or `/dev/ttyACM*` path
- Need full USB descriptor information on the VM
- Multiple device types on same Pi

## Architecture

```
┌─────────────────┐                     ┌─────────────────────────────┐
│  Raspberry Pi   │                     │      Proxmox VM             │
│                 │                     │                             │
│  ┌───────────┐  │   SSH Notification  │  ┌───────────────────────┐  │
│  │  usbipd   │──┼─────────────────────┼──│  usb-event-handler    │  │
│  └───────────┘  │   "connect 1-1.1"   │  └───────────────────────┘  │
│        │        │                     │            │                │
│        │        │                     │            ▼                │
│  ┌───────────┐  │   USB/IP Protocol   │  ┌───────────────────────┐  │
│  │  USB Hub  │◄─┼─────────────────────┼──│  usbip attach         │  │
│  └───────────┘  │   Port 3240         │  └───────────────────────┘  │
│        │        │                     │            │                │
│        ▼        │                     │            ▼                │
│  ┌───────────┐  │                     │  ┌───────────────────────┐  │
│  │   ESP32   │  │                     │  │     /dev/ttyUSB0      │  │
│  └───────────┘  │                     │  └───────────────────────┘  │
│                 │                     │            │                │
│  ┌───────────┐  │                     │            ▼                │
│  │   Portal  │  │                     │  ┌───────────────────────┐  │
│  │   :8080   │  │                     │  │      Container        │  │
│  └───────────┘  │                     │  │   pio run -t upload   │  │
│                 │                     │  └───────────────────────┘  │
└─────────────────┘                     └─────────────────────────────┘
```

## Push-Based Model

The Raspberry Pi is the **single source of truth** for USB state. This eliminates polling and stale connections.

| Event | Pi Action | VM Action |
|-------|-----------|-----------|
| USB plugged in | udev triggers → bind device → SSH notify VM | Receive notification → attach device |
| USB unplugged | udev triggers → SSH notify VM | Receive notification → detach device |
| Pi reboots | Timer binds all devices → notify VM for each | Attach each device |
| VM reboots | - | Boot service queries Pi → attach all |

**Why push-based?** Pull-based polling creates stale connections when devices disappear. The Pi knows the true USB state and notifies the VM immediately.

## USB/IP Components

### Raspberry Pi

| Component | Purpose |
|-----------|---------|
| `usbipd` | USB/IP daemon, exports devices on port 3240 |
| `usbip-bind.sh` | Binds serial devices for export |
| `notify-vm.sh` | Notifies VM of events via SSH |
| `usbip-portal` | Web UI for setup and status |
| udev rules | Trigger on USB connect/disconnect |

### Proxmox VM

| Component | Purpose |
|-----------|---------|
| `vhci_hcd` kernel module | Virtual USB host controller |
| `usb-event-handler` | Receives notifications, attaches/detaches |
| `usb-boot-attach` | Attaches devices on boot |

### Container Access

| Setting | Purpose |
|---------|---------|
| `--privileged` | Full device access |
| `c 166:* rwm` | Access ttyACM devices |
| `c 188:* rwm` | Access ttyUSB devices |
| `/dev:/dev:rslave` | See host devices |

## USB Device Information

USB/IP transfers complete USB descriptors. The VM sees:

| Field | Example |
|-------|---------|
| Vendor ID | 1a86 |
| Product ID | 55d4 |
| Manufacturer | QinHeng Electronics |
| Product | USB Single Serial |
| Serial Number | 58DD029450 |

Available via `lsusb -v`, `/sys/bus/usb/devices/*/`, and udev rules.

## USB/IP Troubleshooting

### Check Pi Status

```bash
systemctl status usbipd          # Daemon running?
usbip list -l                    # Devices bound?
systemctl status usbip-portal    # Portal running?
```

### Check VM Status

```bash
lsmod | grep vhci                # Kernel module loaded?
sudo usbip port                  # Devices attached?
ls -la /dev/ttyUSB* /dev/ttyACM* # Serial devices visible?
```

### Common USB/IP Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| Device not attaching | Kernel module missing | `sudo modprobe vhci_hcd` |
| SSH fails | Host key not in known_hosts | `ssh-keyscan <vm-ip> >> ~/.ssh/known_hosts` |
| Permission denied | Sudoers not configured | Add usbip to sudoers.d |

---

# Part 2: Serial Sharing (RFC2217)

RFC2217 exposes serial ports directly over TCP using esptool's RFC2217 server. No kernel modules required on the VM - it's entirely userspace.

## When to Use RFC2217

- ESP32/ESP8266 development (flashing + monitoring)
- You want simplicity and reliability over full USB passthrough
- No VM kernel module setup desired
- Tools support RFC2217 URLs (esptool, ESP-IDF, PlatformIO)

## Architecture

```
┌─────────────────┐                     ┌─────────────────────────────┐
│  Raspberry Pi   │                     │      Proxmox VM             │
│                 │                     │                             │
│  ┌───────────┐  │                     │  ┌───────────────────────┐  │
│  │  ESP32    │  │                     │  │      Container        │  │
│  └─────┬─────┘  │                     │  │                       │  │
│        │        │                     │  │  esptool --port       │  │
│        ▼        │   RFC2217 (TCP)     │  │  rfc2217://pi:4000    │  │
│  ┌───────────┐  │◄────────────────────┼──│                       │  │
│  │ rfc2217   │  │   Port 4000+        │  └───────────────────────┘  │
│  │ server    │  │                     │                             │
│  └───────────┘  │                     │                             │
│                 │                     │                             │
│  ┌───────────┐  │                     │                             │
│  │  Portal   │  │                     │                             │
│  │  :8080    │  │                     │                             │
│  └───────────┘  │                     │                             │
└─────────────────┘                     └─────────────────────────────┘
```

## RFC2217 Components

### Raspberry Pi

| Component | Purpose |
|-----------|---------|
| `esp_rfc2217_server` | Serial-to-TCP bridge (from esptool) |
| `usbip-portal` | Web UI for mode selection and status |
| udev rules | Start/stop RFC2217 server on USB events |

### VM / Container

No special components needed. Tools connect directly to the RFC2217 URL.

## Using RFC2217

### esptool

```bash
# Use --no-stub for reliability
esptool --no-stub --port 'rfc2217://192.168.0.87:4000?ign_set_control' chip_id
esptool --no-stub --port 'rfc2217://192.168.0.87:4000?ign_set_control' flash_id
```

### ESP-IDF

```bash
export ESPPORT='rfc2217://192.168.0.87:4000?ign_set_control'
idf.py flash monitor
```

### PlatformIO

In `platformio.ini`:
```ini
upload_port = rfc2217://192.168.0.87:4000?ign_set_control
monitor_port = rfc2217://192.168.0.87:4000?ign_set_control
```

## RFC2217 Port Assignment

| Port | Device |
|------|--------|
| 4000 | First RFC2217 device |
| 4001 | Second RFC2217 device |
| ... | Additional devices |

Ports are assigned automatically. Check the web portal for the port number of each device.

## RFC2217 Troubleshooting

### Check Pi Status

```bash
systemctl status usbip-portal    # Portal running?
ss -tlnp | grep 400              # RFC2217 ports listening?
```

### Common RFC2217 Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| Connection refused | Server not running | Check portal, verify device is in RFC2217 mode |
| Timeout during flash | Network latency | Use `--no-stub` flag, check network |
| Port busy | Another connection active | Close other terminal/tool |

---

# Common Information

## Web Portal

The Pi provides a setup portal at `http://<pi-ip>:8080`:

- **Status**: Current VM pairing (for USB/IP mode)
- **USB Devices**: Real-time list with mode selection (USB/IP or RFC2217)
- **VM Discovery**: mDNS discovery of VMs on local network
- **Actions**: Test connection, setup pairing, attach all, disconnect

## Network Requirements

| Port | Protocol | Direction | Purpose |
|------|----------|-----------|---------|
| 3240 | TCP | VM → Pi | USB/IP data |
| 22 | TCP | Pi → VM | SSH notifications (USB/IP only) |
| 8080 | TCP | Browser → Pi | Web portal |
| 4000+ | TCP | VM → Pi | RFC2217 serial |

## Pairing (USB/IP Only)

USB/IP uses a **1:1 pairing** between Pi and VM:
- One Pi serves one VM
- Configuration stored in `/etc/usbip/vm.conf` (Pi) and `/etc/usbip/pi.conf` (VM)
- SSH keys enable passwordless notification

For RFC2217, no pairing is needed - any client can connect to the TCP port.

## Supported USB Devices

| Driver | Chips | Device Node |
|--------|-------|-------------|
| cp210x | CP210x (Silicon Labs) | /dev/ttyUSB* |
| ch341 | CH340, CH341 | /dev/ttyUSB* |
| ftdi_sio | FT232, FT2232 | /dev/ttyUSB* |
| cdc_acm | CDC-ACM (Arduino native USB) | /dev/ttyACM* |

Ethernet adapters are automatically skipped.

## Comparison

| Feature | USB/IP | RFC2217 |
|---------|--------|---------|
| Complexity | Higher (kernel modules) | Lower (userspace only) |
| VM setup required | Yes | No |
| Device appears as | /dev/ttyUSB0 | Network socket |
| Full USB descriptors | Yes | No |
| Non-serial USB devices | Yes | No |
| esptool support | Native | Native |

## Security Considerations

- SSH keys should be specific to this use case (USB/IP)
- USB/IP port 3240 should be on trusted network
- RFC2217 ports (4000+) have no authentication
- Consider firewall rules limiting access
- Portal runs as root for device access

## Performance Notes

- USB/IP adds minimal latency for serial devices
- RFC2217 may have slightly higher latency but better reliability
- Baud rates up to 921600 work reliably
- Use wired Ethernet over Wi-Fi for stability

## Files Reference

### Pi Files

| Path | Purpose |
|------|---------|
| `/usr/local/bin/notify-vm.sh` | Notify VM of USB events (USB/IP) |
| `/usr/local/bin/usbip-bind.sh` | Bind devices for export (USB/IP) |
| `/usr/local/bin/usbip-portal` | Web portal |
| `/etc/usbip/vm.conf` | VM_HOST, VM_USER config |
| `/etc/systemd/system/usbip*` | Service files |
| `/etc/udev/rules.d/99-usbip.rules` | USB event triggers |

### VM Files (USB/IP Only)

| Path | Purpose |
|------|---------|
| `/usr/local/bin/usb-event-handler` | Handle Pi notifications |
| `/usr/local/bin/usb-boot-attach` | Attach on boot |
| `/etc/usbip/pi.conf` | DEFAULT_PI_HOST config |
| `/etc/sudoers.d/usbip` | Passwordless usbip access |
