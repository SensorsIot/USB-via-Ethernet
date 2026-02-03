#!/usr/bin/env python3
"""USB/IP Setup Portal - Web interface for configuring Pi-VM pairing"""

import http.server
import json
import subprocess
import socket
import os
import re
import socketserver
import signal
import time
from urllib.parse import urlparse

PORT = 8080
CONFIG_FILE = "/etc/usbip/vm.conf"
DEVICES_CONFIG = "/etc/usbip/devices.conf"
RFC2217_BASE_PORT = 4000  # First RFC2217 port, increments per device

HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <title>USB/IP Setup Portal</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               max-width: 800px; margin: 0 auto; padding: 20px; background: #f5f5f5; }
        h1 { color: #333; border-bottom: 2px solid #007bff; padding-bottom: 10px; }
        .card { background: white; border-radius: 8px; padding: 20px; margin: 15px 0;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .status { padding: 10px 15px; border-radius: 5px; margin: 10px 0; }
        .status.connected { background: #d4edda; color: #155724; }
        .status.disconnected { background: #f8d7da; color: #721c24; }
        input[type="text"] { width: 100%; padding: 10px; border: 1px solid #ddd;
                            border-radius: 4px; font-size: 16px; }
        button { background: #007bff; color: white; border: none; padding: 10px 20px;
                border-radius: 4px; cursor: pointer; font-size: 16px; margin: 5px 5px 5px 0; }
        button:hover { background: #0056b3; }
        button.danger { background: #dc3545; }
        button.success { background: #28a745; }
        .log { background: #1e1e1e; color: #0f0; padding: 15px; border-radius: 4px;
               font-family: monospace; font-size: 13px; max-height: 200px; overflow-y: auto; }
        .device { padding: 10px; background: #f8f9fa; margin: 5px 0; border-radius: 4px; }
        .device.attached { border-left: 4px solid #28a745; }
        .device.bound { border-left: 4px solid #ffc107; }
        .device.rfc2217 { border-left: 4px solid #17a2b8; }
        .device-header { display: flex; justify-content: space-between; align-items: center; }
        .device-controls { margin-top: 8px; display: flex; gap: 10px; align-items: center; }
        .mode-select { padding: 5px; border-radius: 4px; border: 1px solid #ddd; }
        .mode-badge { font-size: 11px; padding: 2px 6px; border-radius: 3px; }
        .mode-badge.usbip { background: #ffc107; color: #000; }
        .mode-badge.rfc2217 { background: #17a2b8; color: #fff; }
        .port-info { font-size: 12px; color: #666; }
        .vm-option { padding: 10px; margin: 5px 0; background: #f8f9fa; border-radius: 4px;
                    cursor: pointer; border: 2px solid transparent; }
        .vm-option:hover { border-color: #007bff; }
        .vm-option.configured { border-left: 4px solid #28a745; }
        #log { white-space: pre-wrap; }
        .refresh-btn { font-size: 12px; padding: 5px 10px; }
    </style>
</head>
<body>
    <h1>USB/IP Setup Portal</h1>
    <div class="card">
        <h3>Status</h3>
        <div id="status" class="status disconnected">Loading...</div>
    </div>
    <div class="card">
        <h3>USB Devices <button class="refresh-btn" onclick="loadDevices()">Refresh</button></h3>
        <div id="devices">Loading...</div>
    </div>
    <div class="card">
        <h3>VM Configuration</h3>
        <div id="vm-list"><p>Scanning...</p></div>
        <p style="margin-top:15px"><strong>Or enter manually:</strong></p>
        <input type="text" id="vm-input" placeholder="hostname or IP"><p style="margin-top:10px"><strong>Username:</strong></p><input type="text" id="vm-user" value="dev" placeholder="dev">
        <div style="margin-top:15px">
            <button onclick="testConnection()">Test Connection</button>
            <button onclick="setupPairing()" class="success">Setup Pairing</button>
            <button onclick="attachAll()" class="success">Attach All</button>
            <button onclick="disconnect()" class="danger">Disconnect</button>
        </div>
    </div>
    <div class="card">
        <h3>Log</h3>
        <div class="log"><div id="log">Ready.</div></div>
    </div>
    <script>
        let selectedVm = '';
        function log(msg) {
            const el = document.getElementById('log');
            el.textContent += '\\n> ' + msg;
            el.parentElement.scrollTop = el.parentElement.scrollHeight;
        }
        async function api(endpoint, method='GET', body=null) {
            const opts = { method };
            if (body) { opts.headers = {'Content-Type':'application/json'}; opts.body = JSON.stringify(body); }
            const res = await fetch('/api/' + endpoint, opts);
            return res.json();
        }
        async function loadStatus() {
            const data = await api('status');
            const el = document.getElementById('status');
            if (data.vm_host) {
                el.className = 'status connected';
                el.innerHTML = '&#9679; Connected to <strong>' + data.vm_user + '@' + data.vm_host + '</strong>';
                document.getElementById('vm-input').value = data.vm_host;
                document.getElementById('vm-user').value = data.vm_user || 'dev';
                selectedVm = data.vm_host;
            } else {
                el.className = 'status disconnected';
                el.textContent = 'Not configured';
            }
        }
        async function loadDevices() {
            const data = await api('devices');
            const el = document.getElementById('devices');
            const devices = (data.devices || []).filter(d => !d.skipped);
            if (devices.length > 0) {
                el.innerHTML = devices.map(d => {
                    let info = d.product || d.name;
                    if (d.serial) info += ' <small style="color:#666">[' + d.serial + ']</small>';
                    const mode = d.mode || 'usbip';
                    const modeClass = mode === 'rfc2217' ? 'rfc2217' : (d.attached ? 'attached' : 'bound');
                    let status = '';
                    if (mode === 'rfc2217') {
                        status = d.rfc2217_active ?
                            '<span class="mode-badge rfc2217">RFC2217 :' + d.rfc2217_port + '</span>' :
                            '<span class="mode-badge rfc2217">RFC2217 stopped</span>';
                    } else {
                        status = d.attached ? '&#10003; attached' : '&#9679; bound';
                    }
                    return '<div class="device ' + modeClass + '">' +
                        '<div class="device-header">' +
                        '<div><strong>' + d.busid + '</strong>: ' + info + '</div>' +
                        '<div>' + status + '</div></div>' +
                        '<div class="device-controls">' +
                        '<select class="mode-select" onchange="setMode(\\'' + d.busid + '\\', this.value)">' +
                        '<option value="usbip"' + (mode==='usbip' ? ' selected' : '') + '>USB/IP</option>' +
                        '<option value="rfc2217"' + (mode==='rfc2217' ? ' selected' : '') + '>RFC2217</option>' +
                        '</select>' +
                        (mode === 'rfc2217' ? '<span class="port-info">Port: ' + (d.rfc2217_port || '?') + '</span>' : '') +
                        '</div></div>';
                }).join('');
            } else { el.innerHTML = '<p>No serial devices</p>'; }
        }
        async function setMode(busid, mode) {
            log('Setting ' + busid + ' to ' + mode + ' mode...');
            const data = await api('set-mode', 'POST', { busid, mode });
            log(data.message || data.error);
            loadDevices();
        }
        async function loadVms() {
            const data = await api('scan');
            const el = document.getElementById('vm-list');
            if (data.vms && data.vms.length > 0) {
                el.innerHTML = '<p><strong>Discovered:</strong></p>' +
                    data.vms.map(vm => 
                        '<div class="vm-option' + (vm.configured ? ' configured' : '') + '" onclick="selectVm(this, \\'' + vm.ip + '\\')">' +
                        (vm.host || vm.ip) + ' (' + vm.ip + ')' + (vm.configured ? ' &#10003;' : '') + '</div>'
                    ).join('');
            } else { el.innerHTML = '<p>No VMs discovered. Enter IP below.</p>'; }
        }
        function selectVm(el, host) {
            document.querySelectorAll('.vm-option').forEach(e => e.classList.remove('selected'));
            el.classList.add('selected');
            document.getElementById('vm-input').value = host;
            selectedVm = host;
        }
        function getVmHost() { return document.getElementById('vm-input').value.trim() || selectedVm; }
        function getVmUser() { return document.getElementById('vm-user').value.trim() || 'dev'; }
        async function testConnection() {
            const host = getVmHost();
            const user = getVmUser();
            if (!host) { log('Enter VM address'); return; }
            log('Testing ' + user + '@' + host + '...');
            const data = await api('test', 'POST', { host, user });
            log(data.message);
        }
        async function setupPairing() {
            const host = getVmHost();
            const user = getVmUser();
            if (!host) { log('Enter VM address'); return; }
            log('Setting up ' + user + '@' + host + '...');
            const data = await api('setup', 'POST', { host, user });
            for (const msg of data.log || []) { log(msg); }
            log(data.success ? 'Setup complete!' : 'Failed: ' + data.error);
            loadStatus(); loadDevices();
        }
        async function attachAll() {
            log('Attaching all devices...');
            const data = await api('attach-all', 'POST');
            for (const msg of data.log || []) { log(msg); }
            loadDevices();
        }
        async function disconnect() {
            if (!confirm('Remove pairing?')) return;
            log('Disconnecting...');
            const data = await api('disconnect', 'POST');
            log(data.message);
            loadStatus(); loadDevices();
        }
        loadStatus(); loadDevices(); loadVms();
        setInterval(loadDevices, 10000);
    </script>
</body>
</html>
"""

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args): pass
    
    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def send_html(self, html):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(html.encode())
    
    def read_config(self):
        config = {'vm_host': '', 'vm_user': 'dev'}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE) as f:
                for line in f:
                    if '=' in line and not line.strip().startswith('#'):
                        k, v = line.strip().split('=', 1)
                        if k == 'VM_HOST': config['vm_host'] = v
                        if k == 'VM_USER': config['vm_user'] = v
        return config
    
    def write_config(self, host, user='dev'):
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, 'w') as f:
            f.write(f"VM_HOST={host}\nVM_USER={user}\n")

    def read_devices_config(self):
        """Read per-device mode config: {busid: {mode: 'usbip'|'rfc2217', port: int}}"""
        config = {}
        if os.path.exists(DEVICES_CONFIG):
            with open(DEVICES_CONFIG) as f:
                for line in f:
                    if '=' in line and not line.strip().startswith('#'):
                        busid, rest = line.strip().split('=', 1)
                        parts = rest.split(',')
                        mode = parts[0] if parts else 'usbip'
                        port = int(parts[1]) if len(parts) > 1 and parts[1] and parts[1] != 'None' else None
                        config[busid] = {'mode': mode, 'port': port}
        return config

    def write_devices_config(self, config):
        """Write per-device mode config"""
        os.makedirs(os.path.dirname(DEVICES_CONFIG), exist_ok=True)
        with open(DEVICES_CONFIG, 'w') as f:
            f.write("# Device mode config: busid=mode,port\n")
            for busid, data in config.items():
                port = data.get('port') or ''
                f.write(f"{busid}={data['mode']},{port}\n")

    def get_next_rfc2217_port(self, config):
        """Get next available RFC2217 port"""
        used_ports = {d.get('port') for d in config.values() if d.get('port')}
        port = RFC2217_BASE_PORT
        while port in used_ports:
            port += 1
        return port

    def get_tty_for_busid(self, busid):
        """Find /dev/ttyUSB* for a busid"""
        try:
            # Look in sysfs for the tty
            sysfs = f"/sys/bus/usb/devices/{busid}"
            for root, dirs, files in os.walk(sysfs):
                if 'tty' in dirs:
                    tty_dir = os.path.join(root, 'tty')
                    ttys = os.listdir(tty_dir)
                    if ttys:
                        return f"/dev/{ttys[0]}"
            # Fallback: check all ttyUSB devices
            for tty in os.listdir('/dev'):
                if tty.startswith('ttyUSB') or tty.startswith('ttyACM'):
                    return f"/dev/{tty}"
        except: pass
        return None

    def get_rfc2217_pids(self):
        """Get running esp_rfc2217_server processes: {port: pid}"""
        pids = {}
        try:
            result = subprocess.run(['pgrep', '-a', '-f', 'esp_rfc2217_server'],
                capture_output=True, text=True)
            for line in result.stdout.strip().split('\n'):
                if line:
                    parts = line.split()
                    pid = int(parts[0])
                    # Find port in args
                    for i, arg in enumerate(parts):
                        if arg == '-p' and i+1 < len(parts):
                            try:
                                port = int(parts[i+1])
                                pids[port] = pid
                            except: pass
        except: pass
        return pids

    def start_rfc2217(self, busid, port):
        """Start RFC2217 server for device"""
        # First unbind from usbip to release the device
        subprocess.run(['/usr/sbin/usbip', 'unbind', '-b', busid],
            capture_output=True, timeout=10)

        # Wait for tty to appear (kernel needs to rebind to serial driver)
        tty = None
        for _ in range(20):  # Wait up to 2 seconds
            time.sleep(0.1)
            tty = self.get_tty_for_busid(busid)
            if tty:
                break

        if not tty:
            # Re-bind to usbip since RFC2217 failed
            subprocess.run(['/usr/sbin/usbip', 'bind', '-b', busid],
                capture_output=True, timeout=10)
            return False, f"No tty appeared for {busid} after unbind"

        # Start esp_rfc2217_server
        try:
            proc = subprocess.Popen(
                ['/usr/local/bin/esp_rfc2217_server', '-p', str(port), tty],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True)
            return True, f"Started RFC2217 on port {port} for {tty}"
        except Exception as e:
            return False, str(e)

    def stop_rfc2217(self, port):
        """Stop RFC2217 server on port"""
        pids = self.get_rfc2217_pids()
        if port in pids:
            try:
                os.kill(pids[port], signal.SIGTERM)
                return True, f"Stopped RFC2217 on port {port}"
            except Exception as e:
                return False, str(e)
        return True, "Not running"

    def set_device_mode(self, busid, mode):
        """Set device mode and start/stop appropriate service"""
        config = self.read_devices_config()
        old_mode = config.get(busid, {}).get('mode', 'usbip')
        old_port = config.get(busid, {}).get('port')

        if mode == 'rfc2217':
            # Stop usbip, start RFC2217
            port = old_port or self.get_next_rfc2217_port(config)
            config[busid] = {'mode': 'rfc2217', 'port': port}
            self.write_devices_config(config)
            ok, msg = self.start_rfc2217(busid, port)
            return ok, msg
        else:
            # Stop RFC2217 if running, bind to usbip
            if old_port:
                self.stop_rfc2217(old_port)
            config[busid] = {'mode': 'usbip', 'port': None}
            self.write_devices_config(config)
            subprocess.run(['/usr/sbin/usbip', 'bind', '-b', busid],
                capture_output=True, timeout=10)
            return True, f"Set {busid} to USB/IP mode"
    
    def get_vm_attached(self):
        """Get busids attached on VM"""
        attached = set()
        try:
            config = self.read_config()
            if config.get('vm_host'):
                result = subprocess.run(
                    ['ssh', '-o', 'ConnectTimeout=3', '-o', 'BatchMode=yes',
                     f"{config['vm_user']}@{config['vm_host']}",
                     'sudo /usr/sbin/usbip port 2>/dev/null'],
                    capture_output=True, text=True, timeout=10)
                for line in result.stdout.split('\n'):
                    m = re.search(r'usbip://[^/]+/([0-9]+-[0-9.]+)', line)
                    if m:
                        attached.add(m.group(1))
        except: pass
        return attached
    
    def get_device_info(self, busid):
        """Read device info from sysfs"""
        info = {}
        sysfs = f"/sys/bus/usb/devices/{busid}"
        for attr in ['product', 'serial', 'manufacturer', 'idVendor', 'idProduct']:
            try:
                with open(f"{sysfs}/{attr}") as f:
                    info[attr] = f.read().strip()
            except: pass
        return info

    def get_devices(self):
        devices = []
        seen_busids = set()
        attached = self.get_vm_attached()
        dev_config = self.read_devices_config()
        rfc2217_pids = self.get_rfc2217_pids()

        # Get devices from usbip list
        try:
            result = subprocess.run(['/usr/sbin/usbip', 'list', '-l'], capture_output=True, text=True)
            current_busid = None
            for line in result.stdout.split('\n'):
                m = re.match(r'\s+-\s+busid\s+(\S+)\s+\(([0-9a-f:]+)\)', line)
                if m:
                    current_busid = m.group(1)
                elif current_busid and line.strip() and not line.startswith(' -'):
                    name = line.strip()
                    skipped = 'ethernet' in name.lower()
                    info = self.get_device_info(current_busid)
                    mode_info = dev_config.get(current_busid, {'mode': 'usbip'})
                    mode = mode_info.get('mode', 'usbip')
                    port = mode_info.get('port')
                    devices.append({
                        'busid': current_busid,
                        'name': name,
                        'product': info.get('product', ''),
                        'serial': info.get('serial', ''),
                        'skipped': skipped,
                        'attached': current_busid in attached,
                        'mode': mode,
                        'rfc2217_port': port,
                        'rfc2217_active': port in rfc2217_pids if port else False
                    })
                    seen_busids.add(current_busid)
                    current_busid = None
        except: pass

        # Also check devices in RFC2217 mode (not shown by usbip list)
        for busid, mode_info in dev_config.items():
            if busid not in seen_busids and mode_info.get('mode') == 'rfc2217':
                info = self.get_device_info(busid)
                port = mode_info.get('port')
                # Check if device still exists
                if os.path.exists(f"/sys/bus/usb/devices/{busid}"):
                    devices.append({
                        'busid': busid,
                        'name': info.get('product', 'Serial Device'),
                        'product': info.get('product', ''),
                        'serial': info.get('serial', ''),
                        'skipped': False,
                        'attached': False,
                        'mode': 'rfc2217',
                        'rfc2217_port': port,
                        'rfc2217_active': port in rfc2217_pids if port else False
                    })

        return devices
    
    def scan_vms(self):
        vms = []
        seen = set()
        config = self.read_config()
        if config.get('vm_host'):
            vms.append({'host': config['vm_host'], 'ip': config['vm_host'], 'configured': True})
            seen.add(config['vm_host'])
        for name in ['dev-1.local', 'dev-2.local']:
            try:
                ip = socket.gethostbyname(name)
                if ip not in seen:
                    vms.append({'host': name.replace('.local',''), 'ip': ip})
                    seen.add(ip)
            except: pass
        return vms
    
    def test_connection(self, host, user='dev'):
        try:
            result = subprocess.run(
                ['ssh', '-o', 'ConnectTimeout=5', '-o', 'BatchMode=yes', f'{user}@{host}', 'echo OK'],
                capture_output=True, text=True, timeout=10)
            return result.returncode == 0, result.stdout.strip() or result.stderr.strip()
        except Exception as e:
            return False, str(e)
    
    def setup_pairing(self, host, user='dev'):
        log = []
        try:
            log.append(f"Testing SSH to {user}@{host}...")
            ok, msg = self.test_connection(host, user)
            if not ok:
                return False, f"SSH failed: {msg}", log
            log.append("SSH OK")
            
            log.append("Saving config...")
            self.write_config(host, user)
            
            log.append("Attaching all devices...")
            for d in self.get_devices():
                if not d['skipped'] and not d['attached']:
                    result = subprocess.run(['/usr/local/bin/notify-vm.sh', 'boot', d['busid']],
                        capture_output=True, text=True, timeout=60)
                    if 'Success' in result.stderr or result.returncode == 0:
                        log.append(f"  {d['busid']}: attached")
                    else:
                        log.append(f"  {d['busid']}: failed")
            
            return True, "Setup complete", log
        except Exception as e:
            log.append(f"Error: {e}")
            return False, str(e), log
    
    def attach_all(self):
        log = []
        config = self.read_config()
        if not config.get('vm_host'):
            return False, "Not configured", log
        
        for d in self.get_devices():
            if not d['skipped'] and not d['attached']:
                result = subprocess.run(['/usr/local/bin/notify-vm.sh', 'boot', d['busid']],
                    capture_output=True, text=True, timeout=60)
                log.append(f"{d['busid']}: {'attached' if result.returncode == 0 else 'failed'}")
        
        if not log:
            log.append("All devices already attached")
        return True, "Done", log
    
    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/': self.send_html(HTML_TEMPLATE)
        elif path == '/api/status': self.send_json(self.read_config())
        elif path == '/api/devices': self.send_json({'devices': self.get_devices()})
        elif path == '/api/scan': self.send_json({'vms': self.scan_vms()})
        else: self.send_json({'error': 'Not found'}, 404)
    
    def do_POST(self):
        path = urlparse(self.path).path
        content_len = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(content_len)) if content_len else {}
        
        if path == '/api/set-mode':
            busid = body.get('busid', '')
            mode = body.get('mode', 'usbip')
            if not busid:
                self.send_json({'success': False, 'error': 'Missing busid'})
                return
            ok, msg = self.set_device_mode(busid, mode)
            self.send_json({'success': ok, 'message': msg if ok else None, 'error': msg if not ok else None})
        elif path == '/api/test':
            ok, msg = self.test_connection(body.get('host', ''), body.get('user', 'dev'))
            self.send_json({'success': ok, 'message': f"{'OK' if ok else 'Failed'}: {msg}"})
        elif path == '/api/setup':
            ok, msg, log = self.setup_pairing(body.get('host', ''), body.get('user', 'dev'))
            self.send_json({'success': ok, 'error': msg if not ok else '', 'log': log})
        elif path == '/api/attach-all':
            ok, msg, log = self.attach_all()
            self.send_json({'success': ok, 'log': log})
        elif path == '/api/disconnect':
            if os.path.exists(CONFIG_FILE): os.remove(CONFIG_FILE)
            self.send_json({'success': True, 'message': 'Disconnected'})
        else: self.send_json({'error': 'Not found'}, 404)

if __name__ == '__main__':
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(('', PORT), Handler) as httpd:
        print(f"Portal running on http://0.0.0.0:{PORT}")
        httpd.serve_forever()
