#!/bin/bash
# Notify VM of USB events and verify attachment
# Usage: notify-vm.sh <event> <busid>

EVENT="$1"
BUSID="$2"
source /etc/usbip/vm.conf 2>/dev/null || exit 0
LOG_TAG="usbip-notify"

logger -t "$LOG_TAG" "Event: $EVENT, BusID: $BUSID"

notify_and_verify() {
    # Send notification
    result=$(ssh -o ConnectTimeout=5 -o BatchMode=yes "$VM_USER@$VM_HOST" \
        "/usr/local/bin/usb-event-handler $EVENT $BUSID $(hostname)" 2>/dev/null)
    
    if [ "$result" != "OK" ]; then
        return 1
    fi
    
    # For connect/boot, verify device is actually attached
    if [ "$EVENT" = "connect" ] || [ "$EVENT" = "boot" ]; then
        sleep 1
        if ssh -o ConnectTimeout=5 -o BatchMode=yes "$VM_USER@$VM_HOST" \
            "sudo /usr/sbin/usbip port 2>/dev/null | grep -q '$BUSID'" 2>/dev/null; then
            return 0
        else
            logger -t "$LOG_TAG" "Verification failed: $BUSID not attached"
            return 1
        fi
    fi
    return 0
}

# Retry until successful
MAX_RETRIES=30
for i in $(seq 1 $MAX_RETRIES); do
    if notify_and_verify; then
        logger -t "$LOG_TAG" "Success: $EVENT $BUSID (attempt $i)"
        exit 0
    fi
    logger -t "$LOG_TAG" "Retry $i/$MAX_RETRIES for $BUSID..."
    sleep 2
done

logger -t "$LOG_TAG" "Failed: $EVENT $BUSID after $MAX_RETRIES attempts"
exit 1
