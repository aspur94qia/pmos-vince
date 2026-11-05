#!/usr/bin/env python3
"""Web UI pmOS Vince (port 80). Login: admin atau user + password sistem (/etc/vince/smb-pass)."""
import hmac
import html
import http.server
import json
import os
import re
import secrets
import shutil
import subprocess
import time
import urllib.parse

PORT = int(os.environ.get("VINCE_PORT", "80"))
PASSFILE = os.environ.get("VINCE_PASSFILE", "/etc/vince/smb-pass")
NMC = os.environ.get("VINCE_NMC", "/etc/NetworkManager/system-connections/Hotspot.nmconnection")
RCFG = os.environ.get("VINCE_RCFG", "/home/user/share/repeater.txt")
APNF = os.environ.get("VINCE_APNF", "/home/user/share/apn.txt")
NETMODE = os.environ.get("VINCE_NETMODE", "/etc/vince/netmode")
BTNAME = os.environ.get("VINCE_BTNAME", "/etc/vince/bt-name")
DATAOFF = os.environ.get("VINCE_DATAOFF", "/etc/vince/data-off")
USERS = ("admin", "user")
SESSION_TTL = 12 * 3600
os.environ.setdefault("PULSE_SERVER", "unix:/var/run/pulse/native")

SESSIONS = {}      # token -> waktu kedaluwarsa
FAILS = {}         # ip -> (jumlah gagal, terkunci sampai)
SERVICES = ["vince-ap", "vince-sim", "vince-ttyd", "vince-aria2", "vince-ariang",
            "samba", "vince-bluetooth", "vince-audio", "vince-usb"]


# ---------- util ----------
def run(args, timeout=20):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except FileNotFoundError:
        return 127, f"{args[0]}: tidak ditemukan"
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    except Exception as e:  # noqa: BLE001
        return 1, str(e)


def later(shell_cmd, delay=2):
    """Jalankan perintah tetap (bukan input pengguna) di latar belakang setelah jeda."""
    subprocess.run(["sh", "-c", f"(sleep {int(delay)}; {shell_cmd}) >/dev/null 2>&1 &"],
                   start_new_session=True)


def read_file(path, default=""):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return default


def write_file(path, text, mode=0o600, owner=None):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(tmp, mode)
    if owner:
        try:
            shutil.chown(tmp, owner, owner)
        except (LookupError, PermissionError, OSError):
            pass
    os.replace(tmp, path)


def valid_ssid(s):
    return 1 <= len(s.encode("utf-8")) <= 32 and not re.search(r"[\x00-\x1f\x7f\\]", s)


def valid_psk(s, allow_empty=False):
    if s == "" and allow_empty:
        return True
    return 8 <= len(s) <= 63 and re.fullmatch(r"[\x20-\x7e]+", s) is not None and "\\" not in s


def get_password():
    return read_file(PASSFILE).strip()


# ---------- data status ----------
def get_battery_info():
    cap, status, temp = "N/A", "Unknown", "N/A"
    for b in ("battery", "bms"):
        base = f"/sys/class/power_supply/{b}"
        if os.path.exists(f"{base}/capacity"):
            cap = read_file(f"{base}/capacity").strip() + "%"
            status = read_file(f"{base}/status").strip() or "Unknown"
            t = read_file(f"{base}/temp").strip()
            if t.lstrip("-").isdigit():
                temp = f"{int(t) / 10:.1f}°C"
            break
    return cap, status, temp


def get_sys_stats():
    ram = cpu = uptime = "N/A"
    try:
        mem = {}
        for line in read_file("/proc/meminfo").splitlines():
            k, _, v = line.partition(":")
            mem[k] = int(v.split()[0])
        tot, avail = mem["MemTotal"], mem.get("MemAvailable", mem.get("MemFree", 0))
        used = tot - avail
        ram = f"{used // 1024}MB / {tot // 1024}MB ({used * 100 // tot}%)"
    except (KeyError, ValueError, ZeroDivisionError):
        pass
    try:
        cpu = read_file("/proc/loadavg").split()[0]
        secs = int(float(read_file("/proc/uptime").split()[0]))
        uptime = f"{secs // 3600}h {(secs % 3600) // 60}m"
    except (IndexError, ValueError):
        pass
    return ram, cpu, uptime


_SVC_CACHE = {"t": 0.0, "v": {}}


def service_states():
    if time.time() - _SVC_CACHE["t"] < 10:
        return _SVC_CACHE["v"]
    out = {}
    for s in SERVICES:
        rc, _ = run(["rc-service", s, "status"], timeout=5)
        out[s] = (rc == 0)
    _SVC_CACHE.update(t=time.time(), v=out)
    return out


def default_route():
    rc, out = run(["ip", "-4", "route", "show", "default"], timeout=5)
    first = out.splitlines()[0] if out else ""
    m = re.search(r"dev (\S+)", first)
    return m.group(1) if m else "tidak ada"


def scan_wifi_networks():
    rc, out = run(["iw", "dev", "wlan0", "scan"], timeout=25)
    if rc != 0:
        return [], ("Scan gagal: " + (out.splitlines()[-1] if out else f"kode {rc}") +
                    " (wlan0 sedang dipakai hotspot). Ketik nama WiFi secara manual.")
    nets, cur = {}, None
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("BSS "):
            cur = {"ssid": "", "signal": 0, "security": "Open"}
            nets[id(cur)] = cur
        elif cur is not None:
            if line.startswith("signal:"):
                try:
                    dbm = float(line.split()[1])
                    cur["signal"] = max(0, min(100, int(2 * (dbm + 100))))
                except (IndexError, ValueError):
                    pass
            elif line.startswith("SSID:"):
                cur["ssid"] = line[5:].strip()
            elif line.startswith("RSN:") or line.startswith("WPA:"):
                cur["security"] = "WPA"
    best = {}
    for n in nets.values():
        if n["ssid"] and (n["ssid"] not in best or n["signal"] > best[n["ssid"]]["signal"]):
            best[n["ssid"]] = n
    return sorted(best.values(), key=lambda n: -n["signal"]), ""


def modem_id():
    rc, out = run(["mmcli", "-L"], timeout=10)
    m = re.search(r"/Modem/(\d+)", out)
    return m.group(1) if m else None


# ---------- aksi ----------
def do_action(cmd, d):
    g = lambda k, dflt="": d.get(k, [dflt])[0].strip()  # noqa: E731

    if cmd == "set_hotspot":
        ssid, psk = g("ssid"), g("psk")
        if not valid_ssid(ssid):
            return "SSID tidak valid (1-32 karakter, tanpa \\ dan karakter kontrol)."
        if not valid_psk(psk):
            return "Password hotspot harus 8-63 karakter ASCII, tanpa \\."
        txt = read_file(NMC)
        if not txt:
            return "Profil Hotspot.nmconnection tidak ditemukan."
        txt = re.sub(r"(?m)^ssid=.*$", lambda m: "ssid=" + ssid, txt, count=1)
        txt = re.sub(r"(?m)^psk=.*$", lambda m: "psk=" + psk, txt, count=1)
        write_file(NMC, txt, 0o600)
        later("rc-service vince-ap restart")
        return f"Hotspot disimpan: '{ssid}'. Hotspot restart beberapa detik, sambung ulang dengan password baru."

    if cmd == "set_repeater":
        ssid = g("target_ssid_manual") or g("target_ssid")
        psk = d.get("target_psk", [""])[0]
        if not valid_ssid(ssid):
            return "Pilih atau ketik nama WiFi sumber yang valid."
        if not valid_psk(psk, allow_empty=True):
            return "Password WiFi sumber harus 8-63 karakter (atau kosong bila WiFi terbuka)."
        write_file(RCFG, f"{ssid}\n{psk}\n", 0o600, "user")
        later("rc-service vince-repeater restart")
        return f"Repeater: sumber '{ssid}' disimpan dan layanan repeater dimulai ulang."

    if cmd == "clear_repeater":
        write_file(RCFG, "ISI-NAMA-WIFI-SUMBER\nISI-PASSWORD-WIFI\n", 0o600, "user")
        later("rc-service vince-repeater restart")
        return "Repeater dimatikan (kembali mode hotspot saja)."

    if cmd == "set_mobile_data":
        on = g("state", "on") == "on"
        if on:
            try:
                os.remove(DATAOFF)
            except FileNotFoundError:
                pass
        else:
            write_file(DATAOFF, "1\n", 0o644)
        rc, out = run(["nmcli", "-w", "60", "connection", "up" if on else "down", "AutoSIM"], timeout=70)
        return ("Data seluler ON" if on else "Data seluler OFF") + ("" if rc == 0 else f" (nmcli: {out[:120]})")

    if cmd == "set_apn":
        apn, user, pw = g("apn"), g("apn_user"), g("apn_pass")
        if apn and not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", apn):
            return "APN tidak valid."
        if not re.fullmatch(r"[\x21-\x7e]{0,64}", user) or not re.fullmatch(r"[\x21-\x7e]{0,64}", pw):
            return "Username/password APN tidak valid."
        write_file(APNF, f"{apn or 'OTOMATIS'}\n{user}\n{pw}\n", 0o600, "user")
        return ("APN manual: " + apn if apn else "APN otomatis") + ". Diterapkan oleh vince-sim dalam ~10 detik."

    if cmd == "set_network_mode":
        modes = {"4g": "4g", "3g": "3g", "2g": "2g", "auto": "2g|3g|4g"}
        key = g("mode", "4g")
        if key not in modes:
            return "Mode tidak dikenal."
        write_file(NETMODE, modes[key] + "\n", 0o644)
        mid = modem_id()
        if not mid:
            return "Mode disimpan, tapi modem belum terdeteksi."
        rc, out = run(["mmcli", "-m", mid, f"--set-allowed-modes={modes[key]}"], timeout=30)
        return f"Mode jaringan: {key.upper()}" + ("" if rc == 0 else f" (mmcli: {out[:120]})")

    if cmd == "set_ttl":
        on = g("ttl_state", "on") == "on"
        run(["nft", "delete", "table", "ip", "vince"])
        if on:
            run(["nft", "add", "table", "ip", "vince"])
            run(["nft", "add", "chain", "ip", "vince", "post", "{ type filter hook postrouting priority 300 ; }"])
            rc, out = run(["nft", "add", "rule", "ip", "vince", "post", "ip", "ttl", "set", "64"])
            return "TTL 64 aktif." if rc == 0 else f"TTL gagal: {out[:120]}"
        return "TTL 64 dimatikan (aktif lagi setelah reboot)."

    if cmd == "set_volume":
        vol = g("volume", "100")
        if not vol.isdigit() or not 0 <= int(vol) <= 150:
            return "Volume harus 0-150."
        rc, out = run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{vol}%"])
        return f"Volume {vol}%" if rc == 0 else f"pactl gagal: {out[:120]}"

    if cmd == "toggle_mute":
        rc, out = run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"])
        return "Mute diubah." if rc == 0 else f"pactl gagal: {out[:120]}"

    if cmd == "set_bt_name":
        name = g("bt_name")
        if not re.fullmatch(r"[\x20-\x7e]{1,32}", name):
            return "Nama Bluetooth 1-32 karakter ASCII."
        write_file(BTNAME, name + "\n", 0o644)
        later("rc-service vince-bluetooth restart")
        return f"Nama Bluetooth: '{name}' (layanan dimulai ulang)."

    if cmd == "set_bt_service":
        st = g("bt_state")
        if st not in ("start", "stop"):
            return "Perintah tidak dikenal."
        rc, out = run(["rc-service", "vince-bluetooth", st], timeout=30)
        return f"Bluetooth {st}" + ("" if rc == 0 else f" ({out[:120]})")

    if cmd == "restart_usb":
        later("rc-service vince-usb restart")
        return "Jaringan USB dimulai ulang."

    if cmd == "set_led_service":
        st = g("led_state")
        if st not in ("start", "stop"):
            return "Perintah tidak dikenal."
        rc, out = run(["rc-service", "vince-led", st], timeout=30)
        return f"LED {st}" + ("" if rc == 0 else f" ({out[:120]})")

    if cmd == "restart_samba":
        rc, out = run(["rc-service", "samba", "restart"], timeout=60)
        return "Samba direstart." if rc == 0 else f"Samba gagal: {out[:120]}"

    if cmd == "reboot":
        later("reboot")
        return "Reboot dalam 2 detik..."

    return "Perintah tidak dikenal."


# ---------- halaman ----------
STYLE = """
:root{--bg:#0b0f19;--card:#141c2e;--accent:#38bdf8;--text:#f8fafc;--muted:#64748b}
*{box-sizing:border-box;font-family:system-ui}
body{background:var(--bg);color:var(--text);margin:0;padding:15px}
.header{display:flex;justify-content:space-between;max-width:1200px;margin:auto;padding-bottom:10px;border-bottom:1px solid #1e293b}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:15px;max-width:1200px;margin:15px auto}
.card{background:var(--card);padding:15px;border-radius:10px;border:1px solid #1e293b}
.card h3{margin-top:0;color:var(--accent);font-size:15px;border-bottom:1px solid #1e293b;padding-bottom:6px}
label{font-size:12px;color:var(--muted);display:block;margin-top:8px}
input,select,button,a.btn{width:100%;padding:8px;margin-top:4px;border-radius:6px;border:1px solid #334155;background:#0b0f19;color:#fff;font-size:12px}
button,a.btn{background:var(--accent);color:#000;font-weight:bold;cursor:pointer;border:none;margin-top:10px;text-align:center;text-decoration:none;display:inline-block}
.sec{background:#1e293b!important;color:#fff!important;border:1px solid #334155!important}
.row{display:flex;justify-content:space-between;padding:4px 0;font-size:12px;border-bottom:1px dashed #1e293b}
.flex{display:flex;gap:8px}
.note{font-size:11px;color:#94a3b8;margin:6px 0 0}
.msg{max-width:1200px;margin:10px auto;padding:10px;border-radius:8px;background:#0c4a6e;font-size:13px}
.ok{color:#22c55e}.bad{color:#ef4444}
pre{background:#090d16;padding:8px;border-radius:6px;font-size:11px;color:#38bdf8;overflow:auto;max-height:240px;white-space:pre-wrap}
"""

LOGIN_PAGE = """<!DOCTYPE html><html lang="id"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Login - pmOS Vince</title>
<style>body{background:#090d16;color:#f8fafc;font-family:system-ui;display:flex;justify-content:center;align-items:center;height:100vh;margin:0}
.card{background:#131b2e;padding:30px;border-radius:12px;border:1px solid #1e293b;width:320px;text-align:center}
input,button{width:100%;padding:10px;margin-top:10px;border-radius:6px;border:1px solid #334155;background:#0b0f19;color:#fff;box-sizing:border-box}
button{background:#38bdf8;color:#000;font-weight:bold;cursor:pointer;border:none}.e{color:#f87171;font-size:13px}</style></head>
<body><div class="card"><h2>⚡ pmOS Vince</h2>{ERR}
<form method="POST" action="/login"><input type="text" name="user" placeholder="Username (admin)" required autocomplete="username">
<input type="password" name="pass" placeholder="Password" required autocomplete="current-password">
<button type="submit">MASUK</button></form></div></body></html>"""

DASH = """<!DOCTYPE html><html lang="id"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0"><title>pmOS Vince Control Panel</title>
<style>{STYLE}</style></head><body>
<div class="header"><h2 style="margin:0;color:#38bdf8">⚡ pmOS Vince</h2>
<div><span id="bat-val">🔋 ...</span> | <a href="/logout" style="color:#ef4444;text-decoration:none;font-weight:bold">Keluar</a></div></div>
{MSG}
<div class="grid">

<div class="card"><h3>📊 Status</h3>
<div class="row"><span>Baterai:</span><strong id="st-bat">-</strong></div>
<div class="row"><span>Suhu baterai:</span><strong id="st-temp">-</strong></div>
<div class="row"><span>RAM:</span><strong id="st-ram">-</strong></div>
<div class="row"><span>CPU load:</span><strong id="st-cpu">-</strong></div>
<div class="row"><span>Uptime:</span><strong id="st-up">-</strong></div>
<div class="row"><span>Internet lewat:</span><strong id="st-route">-</strong></div>
<div id="svc" style="margin-top:8px"></div></div>

<div class="card"><h3>📡 Hotspot WiFi</h3>
<form method="POST" action="/action"><input type="hidden" name="cmd" value="set_hotspot">
<label>Nama WiFi (SSID)</label><input type="text" name="ssid" value="{SSID}" maxlength="32" required>
<label>Password baru (8-63 karakter)</label><input type="password" name="psk" minlength="8" maxlength="63" required>
<button type="submit">Simpan &amp; Restart Hotspot</button></form>
<p class="note">Hotspot restart ±5 detik. Alamat panel dari hotspot: http://192.168.50.1</p></div>

<div class="card"><h3>🔄 WiFi Repeater</h3>
<form method="POST" action="/action"><input type="hidden" name="cmd" value="set_repeater">
<label>WiFi sumber (hasil pindai)</label><select name="target_ssid" id="wifi-list"><option value="">-- klik Pindai --</option></select>
<button type="button" class="sec" onclick="scanWifi()" id="btn-scan">🔍 Pindai WiFi</button>
<label>…atau ketik nama WiFi sumber</label><input type="text" name="target_ssid_manual" maxlength="32">
<label>Password WiFi sumber (kosong jika terbuka)</label><input type="password" name="target_psk" maxlength="63">
<button type="submit">Hubungkan Repeater</button></form>
<form method="POST" action="/action"><input type="hidden" name="cmd" value="clear_repeater">
<button type="submit" class="sec">Matikan Repeater</button></form>
<p class="note" id="scan-note">Pindai bisa gagal saat hotspot aktif; gunakan kolom ketik manual.</p></div>

<div class="card"><h3>📶 Data Seluler</h3>
<form method="POST" action="/action"><input type="hidden" name="cmd" value="set_mobile_data">
<div class="flex"><button type="submit" name="state" value="on" style="background:#22c55e">Data ON</button>
<button type="submit" name="state" value="off" style="background:#ef4444;color:#fff">Data OFF</button></div></form>
<form method="POST" action="/action" style="margin-top:8px"><input type="hidden" name="cmd" value="set_apn">
<label>APN (kosong = otomatis dari jaringan SIM)</label><input type="text" name="apn" value="{APN}" maxlength="100">
<label>Username APN (opsional)</label><input type="text" name="apn_user" value="{APNU}" maxlength="64">
<label>Password APN (opsional)</label><input type="password" name="apn_pass" maxlength="64">
<button type="submit" class="sec">Simpan APN</button></form>
<form method="POST" action="/action" style="margin-top:8px"><input type="hidden" name="cmd" value="set_network_mode">
<label>Mode jaringan</label><select name="mode"><option value="4g">4G LTE saja (default)</option>
<option value="auto">Otomatis 2G/3G/4G</option><option value="3g">3G saja</option><option value="2g">2G saja</option></select>
<button type="submit">Terapkan</button></form>
<form method="POST" action="/action" style="margin-top:8px"><input type="hidden" name="cmd" value="set_ttl">
<label>TTL 64 (bypass batas tethering)</label>
<div class="flex"><button type="submit" name="ttl_state" value="on">TTL 64 ON</button>
<button type="submit" name="ttl_state" value="off" class="sec">OFF</button></div></form></div>

<div class="card"><h3>🔊 Audio</h3>
<form method="POST" action="/action"><input type="hidden" name="cmd" value="set_volume">
<label>Volume (0-150%)</label><input type="range" name="volume" min="0" max="150" value="100" oninput="this.nextElementSibling.value=this.value+'%'">
<output style="font-size:11px">100%</output><button type="submit">Terapkan Volume</button></form>
<form method="POST" action="/action"><input type="hidden" name="cmd" value="toggle_mute">
<button type="submit" class="sec">🔇 Mute / Unmute</button></form>
<p class="note">Output (speaker/headset) dan EQ dipilih otomatis oleh vince-audio.</p></div>

<div class="card"><h3>🔵 Bluetooth Receiver</h3>
<form method="POST" action="/action"><input type="hidden" name="cmd" value="set_bt_name">
<label>Nama Bluetooth</label><input type="text" name="bt_name" value="{BTNAME}" maxlength="32" required>
<button type="submit">Simpan Nama</button></form>
<form method="POST" action="/action"><input type="hidden" name="cmd" value="set_bt_service">
<div class="flex"><button type="submit" name="bt_state" value="start" style="background:#22c55e">Start</button>
<button type="submit" name="bt_state" value="stop" style="background:#ef4444;color:#fff">Stop</button></div></form></div>

<div class="card"><h3>💾 Layanan Web &amp; NAS</h3>
<a class="btn" href="http://{HOST}:7681" target="_blank">💻 Web Terminal (login: user + password)</a>
<a class="btn sec" href="http://{HOST}:6801" target="_blank">📥 AriaNg (RPC secret = password login)</a>
<form method="POST" action="/action"><input type="hidden" name="cmd" value="restart_samba"><button type="submit" class="sec">🔄 Restart Samba</button></form>
<form method="POST" action="/action"><input type="hidden" name="cmd" value="restart_usb"><button type="submit" class="sec">🔌 Restart jaringan USB</button></form>
<form method="POST" action="/action"><input type="hidden" name="cmd" value="set_led_service">
<label>LED notifikasi (vince-led)</label><div class="flex"><button type="submit" name="led_state" value="start" style="background:#22c55e">Start</button>
<button type="submit" name="led_state" value="stop" class="sec">Stop</button></div></form></div>

<div class="card"><h3>🧪 Diagnostik &amp; Daya</h3>
<button type="button" class="sec" onclick="loadDiag()">Jalankan diagnostik</button>
<pre id="diag">Klik tombol di atas.</pre>
<form method="POST" action="/action" onsubmit="return confirm('Reboot HP sekarang?')"><input type="hidden" name="cmd" value="reboot">
<button type="submit" style="background:#ef4444;color:#fff">⚠️ Reboot</button></form></div>
</div>
<script>
function j(u){return fetch(u).then(function(r){if(r.status===401){location.reload();throw 0}return r.json()})}
function updateStats(){j('/api/status').then(function(d){
 document.getElementById('bat-val').innerText='🔋 '+d.battery_cap+' ('+d.battery_status+')';
 document.getElementById('st-bat').innerText=d.battery_cap+' '+d.battery_status;
 document.getElementById('st-temp').innerText=d.battery_temp;document.getElementById('st-ram').innerText=d.ram;
 document.getElementById('st-cpu').innerText=d.cpu;document.getElementById('st-up').innerText=d.uptime;
 document.getElementById('st-route').innerText=d.route;
 var h='';for(var k in d.services){h+='<div class="row"><span>'+k+'</span><strong class="'+(d.services[k]?'ok':'bad')+'">'+(d.services[k]?'jalan':'mati')+'</strong></div>'}
 document.getElementById('svc').innerHTML=h}).catch(function(){})}
function scanWifi(){var b=document.getElementById('btn-scan'),s=document.getElementById('wifi-list'),n=document.getElementById('scan-note');
 b.innerText='⏳ Memindai...';b.disabled=true;
 j('/api/scan-wifi').then(function(d){s.innerHTML='';
  if(!d.networks.length){s.innerHTML='<option value="">Tidak ada WiFi</option>'}
  d.networks.forEach(function(x){var o=document.createElement('option');o.value=x.ssid;o.textContent=x.ssid+' ('+x.signal+'% | '+x.security+')';s.appendChild(o)});
  if(d.error){n.textContent=d.error}
  b.innerText='🔍 Pindai WiFi';b.disabled=false}).catch(function(){b.innerText='❌ Gagal';b.disabled=false})}
function loadDiag(){var b=document.getElementById('diag');b.innerText='⏳ Memproses...';
 j('/api/diag').then(function(d){b.innerText='=== SISTEM ===\\n'+d.sys_diag+'\\n\\n=== AUDIO ===\\n'+d.audio_diag}).catch(function(){b.innerText='Gagal memuat.'})}
setInterval(updateStats,5000);updateStats();
</script></body></html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "vince-webui"
    sys_version = ""

    def log_message(self, fmt, *args):
        pass

    # --- helper respons ---
    def send(self, code, body, ctype="text/html; charset=utf-8", extra=()):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cache-Control", "no-store")
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def redirect(self, loc, extra=()):
        self.send_response(302)
        self.send_header("Location", loc)
        self.send_header("Content-Length", "0")
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()

    def json(self, obj, code=200):
        self.send(code, json.dumps(obj), "application/json")

    def token(self):
        for part in self.headers.get("Cookie", "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == "session_id":
                return v
        return ""

    def authed(self):
        now = time.time()
        for t in [t for t, exp in SESSIONS.items() if exp < now]:
            del SESSIONS[t]
        return self.token() in SESSIONS

    def host(self):
        h = self.headers.get("Host", "")
        h = h.rsplit(":", 1)[0] if not h.startswith("[") else h.split("]")[0] + "]"
        return h if re.fullmatch(r"[A-Za-z0-9.\-\[\]:]{1,100}", h) else "192.168.50.1"

    # --- GET ---
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/logout":
            SESSIONS.pop(self.token(), None)
            return self.redirect("/", [("Set-Cookie", "session_id=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict")])
        if not self.authed():
            if path.startswith("/api/"):
                return self.json({"error": "login"}, 401)
            return self.send(200, LOGIN_PAGE.replace("{ERR}", ""))

        if path == "/api/status":
            cap, status, temp = get_battery_info()
            ram, cpu, uptime = get_sys_stats()
            return self.json({"battery_cap": cap, "battery_status": status, "battery_temp": temp,
                              "ram": ram, "cpu": cpu, "uptime": uptime,
                              "route": default_route(), "services": service_states()})
        if path == "/api/scan-wifi":
            nets, err = scan_wifi_networks()
            return self.json({"networks": nets, "error": err})
        if path == "/api/diag":
            return self.json({"sys_diag": run(["/usr/bin/vince-diag"], 40)[1],
                              "audio_diag": run(["/usr/bin/vince-audio-diag"], 40)[1]})

        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        msg = q.get("m", [""])[0][:300]
        ssid = (re.search(r"(?m)^ssid=(.*)$", read_file(NMC)) or [None, "pmOS-Vince"])[1]
        apn_lines = (read_file(APNF).splitlines() + ["", "", ""])[:3]
        apn = "" if apn_lines[0].startswith("OTOMATIS") else apn_lines[0]
        btname = read_file(BTNAME).strip() or "Vince Speaker"
        page = (DASH.replace("{STYLE}", STYLE)
                .replace("{MSG}", f'<div class="msg">{html.escape(msg)}</div>' if msg else "")
                .replace("{SSID}", html.escape(ssid, quote=True))
                .replace("{APN}", html.escape(apn, quote=True))
                .replace("{APNU}", html.escape(apn_lines[1], quote=True))
                .replace("{BTNAME}", html.escape(btname, quote=True))
                .replace("{HOST}", html.escape(self.host(), quote=True)))
        self.send(200, page)

    # --- POST ---
    def do_POST(self):
        try:
            length = min(int(self.headers.get("Content-Length", 0)), 65536)
        except ValueError:
            length = 0
        body = self.rfile.read(length).decode("utf-8", "replace")
        data = urllib.parse.parse_qs(body)
        path = self.path.split("?")[0]

        origin = self.headers.get("Origin")
        if origin and urllib.parse.urlparse(origin).netloc != self.headers.get("Host", ""):
            return self.send(403, "Origin tidak cocok")

        if path == "/login":
            ip = self.client_address[0]
            cnt, until = FAILS.get(ip, (0, 0))
            if until > time.time():
                return self.send(429, LOGIN_PAGE.replace("{ERR}", '<p class="e">Terlalu banyak percobaan. Tunggu 1 menit.</p>'))
            user = data.get("user", [""])[0]
            pwd = data.get("pass", [""])[0]
            real = get_password()
            if not real:
                return self.send(503, LOGIN_PAGE.replace("{ERR}", '<p class="e">Password sistem belum di-set (/etc/vince/smb-pass).</p>'))
            if user in USERS and hmac.compare_digest(pwd.encode(), real.encode()):
                FAILS.pop(ip, None)
                tok = secrets.token_hex(24)
                SESSIONS[tok] = time.time() + SESSION_TTL
                return self.redirect("/", [("Set-Cookie", f"session_id={tok}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_TTL}")])
            cnt += 1
            FAILS[ip] = (cnt, time.time() + 60 if cnt >= 5 else 0)
            time.sleep(1)
            return self.send(401, LOGIN_PAGE.replace("{ERR}", '<p class="e">Username atau password salah.</p>'))

        if not self.authed():
            return self.redirect("/")
        if path != "/action":
            return self.send(404, "Tidak ditemukan")
        try:
            msg = do_action(data.get("cmd", [""])[0], data)
        except Exception as e:  # noqa: BLE001
            msg = f"Error: {e}"
        self.redirect("/?m=" + urllib.parse.quote(msg))


class Server(http.server.ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    Server(("", PORT), Handler).serve_forever()
