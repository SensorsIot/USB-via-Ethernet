# USB & Serial Sharing for Proxmox

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Platform](https://img.shields.io/badge/Platform-Raspberry%20Pi-red.svg)](https://www.raspberrypi.org/)
[![Proxmox](https://img.shields.io/badge/Proxmox-VM-orange.svg)](https://www.proxmox.com/)

> Share USB devices and serial ports from Raspberry Pi to Proxmox VMs over the network

---

## 🎯 Goal

Enable containers running on Proxmox VMs to use USB serial devices (ESP32, Arduino, etc.) that are physically connected to a remote Raspberry Pi.

## 💡 Two Methods

| Method | Best For | Complexity |
|--------|----------|------------|
| **USB/IP** | Any USB device (JTAG, HID, serial) | Higher (VM kernel modules) |
| **RFC2217** | ESP32/Arduino serial only | Lower (userspace only) |

### USB/IP Architecture

Full USB device passthrough - VM sees device as locally connected with all USB descriptors.

```
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│  Container   │ ◄─── │   Proxmox    │ ◄─── │ Raspberry Pi │ ◄─── USB
│              │      │     VM       │      │              │
│ /dev/ttyUSB0 │      │  USB/IP      │  SSH │  udev rules  │
└──────────────┘      └──────────────┘      └──────────────┘
```

### RFC2217 Architecture

Serial-over-TCP - simpler setup, no kernel modules needed on VM.

```
┌──────────────┐      ┌──────────────┐
│  Container   │ ◄─── │ Raspberry Pi │ ◄─── USB
│              │      │              │
│  esptool     │ TCP  │  RFC2217     │
│  rfc2217://  │ 4000 │  server      │
└──────────────┘      └──────────────┘
```

## 🧩 Components

| Component | Role |
|-----------|------|
| **Raspberry Pi** | USB host, web portal, USB/IP daemon or RFC2217 server |
| **Proxmox VM** | USB/IP: receives notifications, attaches devices. RFC2217: not needed |
| **Container** | USB/IP: uses `/dev/ttyUSB*`. RFC2217: uses `rfc2217://` URLs |
| **Setup Portal** | Web UI on Pi for configuration (http://pi:8080) |

## 🛠️ Technology

- **USB/IP** - Linux kernel protocol to share USB over TCP/IP
- **RFC2217** - Serial-over-TCP using esptool's RFC2217 server
- **udev** - Detects USB connect/disconnect on Pi

---

## 📁 Repository Structure

```
├── pi/                    # Raspberry Pi setup
│   ├── scripts/           # Shell scripts
│   ├── systemd/           # Service files
│   ├── udev/              # udev rules
│   └── portal.py          # Web portal (supports USB/IP + RFC2217)
├── vm/                    # Proxmox VM setup (USB/IP only)
│   ├── scripts/           # Shell scripts
│   └── systemd/           # Service files
├── container/             # Container configuration
│   └── devcontainer.json  # Example config
├── alternatives/          # Alternative setups
│   └── ser2net-rfc2217/   # Standalone RFC2217 with ser2net
└── docs/                  # Detailed documentation
```

---

## 🚀 Quick Start

### 1️⃣ Setup Raspberry Pi (Both Methods)

```bash
# Install dependencies
sudo apt update && sudo apt install usbip python3-pip
pip3 install esptool  # For RFC2217 server

# Copy scripts and portal
sudo cp pi/scripts/* /usr/local/bin/
sudo chmod +x /usr/local/bin/*.sh
sudo cp pi/portal.py /usr/local/bin/usbip-portal
sudo chmod +x /usr/local/bin/usbip-portal

# Install services
sudo cp pi/systemd/* /etc/systemd/system/
sudo cp pi/udev/* /etc/udev/rules.d/

# Enable services
sudo systemctl daemon-reload
sudo systemctl enable --now usbipd usbip-bind.timer usbip-portal
```

### 2️⃣ Setup Proxmox VM (USB/IP Only)

*Skip this step if using RFC2217 only.*

```bash
# Install prerequisites
sudo apt update
sudo apt install linux-image-amd64 usbip avahi-daemon

# Load kernel module
sudo modprobe vhci_hcd
echo "vhci_hcd" | sudo tee -a /etc/modules

# Copy scripts
sudo cp vm/scripts/* /usr/local/bin/
sudo chmod +x /usr/local/bin/*

# Install services
sudo cp vm/systemd/* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable usb-boot-attach

# Setup sudoers
echo 'dev ALL=(root) NOPASSWD: /usr/sbin/usbip, /bin/fuser' | sudo tee /etc/sudoers.d/usbip
```

### 3️⃣ Configure via Web Portal

1. Open **http://\<pi-ip\>:8080** in browser
2. **For USB/IP**: Enter VM IP and click **Setup Pairing**
3. **For RFC2217**: Select RFC2217 mode for each device - note the port number

---

## 🌐 Setup Portal

The Pi provides a web-based setup portal at **http://\<pi-ip\>:8080**

### Features

- **Status** - Shows current VM pairing (USB/IP)
- **USB Devices** - Real-time list with mode selection per device
  - Select USB/IP or RFC2217 mode for each device
  - See attachment status and RFC2217 port numbers
- **VM Discovery** - mDNS discovery of VMs (USB/IP)
- **Test Connection** - Verify SSH connectivity (USB/IP)
- **Setup Pairing** - One-click configuration (USB/IP)

---

## 📋 Event Flow (USB/IP)

| Event | Pi Action | VM Action | Container Sees |
|-------|-----------|-----------|----------------|
| USB plugged in | Bind, notify VM, verify | Attach device | `/dev/ttyUSB0` appears |
| USB unplugged | Notify VM | Detach device | Device disappears |
| Pi reboots | Bind all, notify VM | Attach devices | Devices reappear |
| VM reboots | - | Query Pi, attach | Devices reappear |

For **RFC2217**, devices are available immediately when connected to the Pi. No VM setup or pairing needed - just connect to the TCP port.

---

## 📦 Container Usage

### USB/IP Mode

Devices appear as `/dev/ttyUSB*` automatically.

```bash
pio run -t upload
pio device monitor
```

**devcontainer.json:**
```json
{
  "runArgs": [
    "--privileged",
    "--device-cgroup-rule=c 166:* rwm",
    "--device-cgroup-rule=c 188:* rwm",
    "-v", "/dev:/dev:rslave"
  ]
}
```

### RFC2217 Mode

Connect directly to the RFC2217 URL.

```bash
# esptool
esptool --no-stub --port 'rfc2217://192.168.0.87:4000?ign_set_control' flash_id

# ESP-IDF
export ESPPORT='rfc2217://192.168.0.87:4000?ign_set_control'
idf.py flash monitor
```

**platformio.ini:**
```ini
upload_port = rfc2217://192.168.0.87:4000?ign_set_control
monitor_port = rfc2217://192.168.0.87:4000?ign_set_control
```

---

## 🔧 Supported Devices

| Driver | Chip | Device |
|--------|------|--------|
| cp210x | Silicon Labs CP210x | /dev/ttyUSB* |
| ch341 | QinHeng CH340/CH341 | /dev/ttyUSB* |
| ftdi_sio | FTDI | /dev/ttyUSB* |
| cdc_acm | CDC-ACM (Arduino) | /dev/ttyACM* |

---

## 💡 Tips

- 🌐 Use Ethernet over Wi-Fi for reliability
- 📏 Use short USB cables
- 1️⃣ One Pi per VM for isolation

---

## 📄 License

MIT License - feel free to use and modify!

---

## 🙏 Credits

Developed for the [Sensors IoT](https://www.youtube.com/@AndreasSpiworst) community.
