#!/bin/bash
# Bind all USB serial devices for USB/IP
for dev in /sys/bus/usb/devices/*/bInterfaceClass; do
    class=$(cat "$dev" 2>/dev/null)
    # 02 = CDC, ff = vendor specific (many serial adapters)
    if [[ "$class" == "02" || "$class" == "ff" ]]; then
        busid=$(echo "$dev" | grep -oP '\d+-[\d.]+'| head -1)
        if [ -n "$busid" ]; then
            /usr/sbin/usbip bind -b "$busid" 2>/dev/null
        fi
    fi
done
