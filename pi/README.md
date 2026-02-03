# Raspberry Pi Setup

## Prerequisites

```bash
sudo apt update && sudo apt install usbip

# Optional: For RFC2217 mode (serial-over-TCP alternative to USB/IP)
# Must be system-wide since portal runs as root
sudo pip3 install esptool --break-system-packages
```

## Installation

```bash
# Copy scripts
sudo cp scripts/*.sh /usr/local/bin/
sudo cp portal.py /usr/local/bin/usbip-portal
sudo chmod +x /usr/local/bin/*.sh /usr/local/bin/usbip-portal

# Install systemd services
sudo cp systemd/* /etc/systemd/system/

# Install udev rules
sudo cp udev/* /etc/udev/rules.d/
sudo udevadm control --reload-rules

# Enable kernel modules
echo "usbip_host" | sudo tee -a /etc/modules
sudo modprobe usbip_host

# Enable services
sudo systemctl daemon-reload
sudo systemctl enable --now usbipd usbip-bind.service usbip-bind.timer usbip-notify-boot usbip-portal
```

## Configuration

Create `/etc/usbip/vm.conf`:

```bash
sudo mkdir -p /etc/usbip
echo "VM_HOST=<vm-ip-address>" | sudo tee /etc/usbip/vm.conf
echo "VM_USER=dev" | sudo tee -a /etc/usbip/vm.conf
```

## SSH Key Setup

```bash
# Generate key
ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519

# Copy to VM
ssh-copy-id dev@<vm-ip>

# Also copy to root (for portal)
sudo mkdir -p /root/.ssh
sudo cp ~/.ssh/id_ed25519* /root/.ssh/
sudo ssh-keyscan -H <vm-ip> | sudo tee -a /root/.ssh/known_hosts
```

## Web Portal

Access at **http://\<pi-ip\>:8080**
