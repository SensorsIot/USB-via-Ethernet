# USB Flap Detection — Test Report

**Date:** 2026-02-07
**Portal version:** v3 (portal.py on Serial1)
**Tested on:** Raspberry Pi @ 192.168.0.87

## Summary

| | |
|---|---|
| **Tests run** | 15 |
| **Passed** | 15 |
| **Failed** | 0 |
| **Bugs found during testing** | 2 (fixed and re-tested) |

## Feature Overview

When a device enters a boot loop (crash/reboot every ~2-3s), the Pi sees rapid USB connect/disconnect cycles. Without protection, the portal spawns a new proxy thread for every "add" event, overwhelming the process and crashing the portal (SIGHUP), taking all slots offline.

**Flap detection** tracks hotplug event frequency per slot. If 6+ events occur within 30 seconds (3 connect/disconnect cycles), the slot is marked as "flapping":
- Proxy starts are suppressed
- Running proxy is stopped proactively
- UI shows a red FLAPPING badge and warning banner
- Other slots continue operating normally
- After 30 seconds of quiet, the slot auto-recovers

## Configuration

| Constant | Value | Description |
|----------|-------|-------------|
| `FLAP_WINDOW_S` | 30 | Sliding window for event counting |
| `FLAP_THRESHOLD` | 6 | Events required to trigger flapping |
| `FLAP_COOLDOWN_S` | 30 | Quiet time before auto-recovery |

## Test Method

Tests were run via simulated hotplug events using `POST /api/hotplug` from the dev container. SLOT2 (port 4002, no physical device) was used as the test target. SLOT1 had a real ESP32-C3 connected and running.

## Test Results

### TEST 1: Flapping triggers after 6 events
Sent 3 rapid add/remove cycles (6 events total) with 200ms spacing.

| Check | Expected | Actual | Result |
|-------|----------|--------|--------|
| SLOT2 `flapping` | `True` | `True` | PASS |
| SLOT2 `last_error` contains "flapping" | Yes | Yes | PASS |

### TEST 2: Additional events stay flapping
Sent 2 more events after flapping detected.

| Check | Expected | Actual | Result |
|-------|----------|--------|--------|
| SLOT2 still `flapping` | `True` | `True` | PASS |

### TEST 3: SLOT1 isolation
Verified SLOT1 (with real C3 device) is unaffected by SLOT2 flapping.

| Check | Expected | Actual | Result |
|-------|----------|--------|--------|
| SLOT1 `flapping` | `False` | `False` | PASS |
| SLOT1 `running` | `True` | `True` | PASS |

### TEST 4: SLOT3 isolation

| Check | Expected | Actual | Result |
|-------|----------|--------|--------|
| SLOT3 `flapping` | `False` | `False` | PASS |

### TEST 5: Proxy suppressed during flapping
Sent an "add" event while SLOT2 is flapping.

| Check | Expected | Actual | Result |
|-------|----------|--------|--------|
| SLOT2 `running` | `False` | `False` | PASS |

### TEST 6: API exposes flapping field
Checked `/api/devices` response for all slots.

| Check | Expected | Actual | Result |
|-------|----------|--------|--------|
| SLOT1 has `flapping` field | `True` | `True` | PASS |
| SLOT2 has `flapping` field | `True` | `True` | PASS |
| SLOT3 has `flapping` field | `True` | `True` | PASS |

### TEST 7: Hotplug response includes flapping

| Check | Expected | Actual | Result |
|-------|----------|--------|--------|
| Response has `flapping` field | `True` | `True` | PASS |

### TEST 8: Portal health during flapping

| Check | Expected | Actual | Result |
|-------|----------|--------|--------|
| `/api/devices` returns 200 | `200` | `200` | PASS |
| `/` (UI) returns 200 | `200` | `200` | PASS |

### TEST 9: Recovery after cooldown
Waited 31 seconds with no events, then sent one "add" event.

| Check | Expected | Actual | Result |
|-------|----------|--------|--------|
| SLOT2 `flapping` cleared | `False` | `False` | PASS |
| SLOT2 `last_error` cleared | `None` | `None` | PASS |

## Bugs Found and Fixed

### Bug 1: Background thread race condition
**Symptom:** `last_error` showed "Device not ready after settle timeout" instead of the flapping message.
**Cause:** Background proxy start threads spawned before flapping threshold was reached would overwrite `last_error` when `start_proxy()` failed after flapping was already detected.
**Fix:** Added flapping guard at start of `_bg_start()` to bail out if flapping detected while queued. Also restore flapping error message if flapping is set after `start_proxy()` returns.

### Bug 2: Recovery never triggers after window expiry
**Symptom:** Flapping state persisted indefinitely even after 30+ seconds of quiet.
**Cause:** After cooldown, all old events were pruned from the sliding window (older than `FLAP_WINDOW_S`), leaving only 1 event. Recovery check required `len >= 2` to compare gaps, so it never fired.
**Fix:** Added `len < 2` check — if all previous events aged out of the window, clear flapping immediately (device has been quiet for at least `FLAP_WINDOW_S`).

## Commits

| Hash | Description |
|------|-------------|
| `5ccddf6` | Add USB flap detection to prevent boot-loop proxy storms |
| `c1b1202` | Use IP address instead of hostname for slot URLs in web UI |
| `17b1541` | Fix flap recovery and bg thread race condition |

## Not Tested (requires physical boot-looping device)

- Actual C3 boot loop with real USB connect/disconnect cycling
- Proactive proxy stop when flapping first detected on a running proxy
- UI visual appearance of red FLAPPING badge and warning banner (verified HTML/CSS is served, not visually inspected)
