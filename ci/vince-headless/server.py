import http.server
import socketserver
import json
import subprocess
import os

PORT = 80
DOCROOT = "/var/www/localhost/htdocs"


class RouterAPIHandler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        if path.startswith("/api/"):
            return super().translate_path(path)
        return os.path.join(DOCROOT, path.lstrip("/"))

    def do_GET(self):
        if self.path == "/api/status":
            bat_pct = self.exec_cmd("cat /sys/class/power_supply/battery/capacity 2>/dev/null || echo 100")
            charging = "1" in self.exec_cmd("cat /sys/class/power_supply/battery/status 2>/dev/null | grep -i charging || echo 0")
            temp = str(int(self.exec_cmd("cat /sys/class/power_supply/battery/temp 2>/dev/null || echo 320") or "320") // 10)
            ram = self.exec_cmd("free -m | awk '/Mem:/ {print $3\"MB (\"int($3/$2*100)\"%)\"}'")
            cpu = self.exec_cmd("uptime | awk -F'load average:' '{print $2}'").strip()
            uptime = self.exec_cmd("uptime -p").replace("up ", "")
            self._json(200, {
                "battery_pct": bat_pct, "charging": charging, "temp": temp,
                "ram": ram, "cpu": cpu, "uptime": uptime,
            })
        elif self.path == "/api/scan-wifi":
            out = self.exec_cmd("iw dev wlan0 scan 2>/dev/null | awk '/SSID:/ {s=$2} /signal:/ {print s, $2}'")
            nets = []
            for line in out.splitlines():
                parts = line.rsplit(" ", 1)
                if len(parts) == 2:
                    nets.append({"ssid": parts[0], "signal": parts[1], "security": "?"})
            self._json(200, nets)
        elif self.path == "/api/diag":
            diag_out = self.exec_cmd("/usr/bin/vince-diag 2>&1 || echo 'vince-diag executed.'")
            audio_diag = self.exec_cmd("/usr/bin/vince-audio-diag 2>&1 || echo 'vince-audio-diag executed.'")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"--- SYSTEM DIAG ---\n{diag_out}\n\n--- AUDIO DIAG ---\n{audio_diag}".encode())
        else:
            super().do_GET()

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            data = json.loads(raw.decode('utf-8'))
        except Exception:
            self._json(400, {"status": "error", "error": "invalid json"})
            return

        handlers = {
            "/api/hotspot": lambda: self.exec_cmd(
                "nmcli con mod Hotspot ssid '%s' wpa-psk '%s' && nmcli con up Hotspot" % (data.get('ssid'), data.get('pass'))),
            "/api/connect-repeater": lambda: self.exec_cmd(
                "nmcli dev wifi connect '%s' password '%s'" % (data.get('ssid'), data.get('pass'))),
            "/api/toggle-data": lambda: self.exec_cmd(
                "nmcli networking connectivity %s" % ('on' if data.get('state') else 'off')),
            "/api/toggle-ttl": lambda: self.exec_cmd(
                "iptables -t mangle -A POSTROUTING -j TTL --ttl-set 64" if data.get("state")
                else "iptables -t mangle -D POSTROUTING -j TTL --ttl-set 64"),
            "/api/imei": lambda: self.exec_cmd(
                "echo -e 'AT+EGMR=1,7,\"%s\"\\r' > /dev/ttyUSB0" % data.get('imei')),
            "/api/bt-alias": lambda: self.exec_cmd(
                "bluetoothctl system-alias '%s'" % data.get('alias')),
            "/api/usb-mode": lambda: self.exec_cmd(
                "/usr/bin/vince-usb %s" % data.get('mode')),
            "/api/led-bright": lambda: self.exec_cmd(
                "echo %s > /sys/class/leds/white:status/brightness 2>/dev/null || true" % data.get('val')),
            "/api/led-trigger": lambda: self.exec_cmd(
                "echo %s > /sys/class/leds/white:status/trigger 2>/dev/null || true" % data.get('trigger')),
            "/api/restart-samba": lambda: self.exec_cmd("rc-service samba restart"),
            "/api/reboot": lambda: self.exec_cmd("reboot"),
            "/api/eq": lambda: self.apply_eq(data.get('g')),
            "/api/apn": lambda: self.exec_cmd(
                "printf '%s\\n\\n\\n' '%s' > /home/user/share/apn.txt" % (data.get('apn') or 'internet')),
            "/api/lock-lte": lambda: self.exec_cmd(
                "printf '%s' > /home/user/share/lock-lte.txt" % (data.get('mode') or 'auto')),
            "/api/audio-preset": lambda: self.apply_eq({
                "off":     [0, 0, 0, 0, 0],
                "dynamic": [3, 2, 0, 2, 4],
                "movie":   [5, 3, 0, 2, 3],
                "music":   [2, 1, 0, 1, 2],
                "game":    [4, 2, -1, 3, 4],
                "bass":    [8, 6, 2, 0, 0],
            }.get(data.get('preset'), [0,0,0,0,0])),
            "/api/adb-keys": lambda: None,
            "/api/imei-backup": lambda: None,
        }
        h = handlers.get(self.path)
        if h is None:
            self._json(404, {"status": "error", "error": "unknown endpoint"})
            return
        try:
            h()
        except Exception as e:
            self._json(500, {"status": "error", "error": str(e)})
            return
        self._json(200, {"status": "ok"})

    def apply_eq(self, gains):
        try:
            g = [float(x) for x in (gains or [0,0,0,0,0])]
            g += [0.0] * (5 - len(g))
        except Exception:
            g = [0.0, 0.0, 0.0, 0.0, 0.0]
        m = [g[0],g[0], g[1],g[1],g[1],g[1], g[2],g[2],g[2],g[2], g[3],g[3],g[3], g[4],g[4]]
        ctrl = ",".join("%.1f" % x for x in m)
        master = "alsa_output.platform-soc_sound.analog-stereo"
        self.exec_cmd("for i in $(pactl list short modules 2>/dev/null | awk '/ladspa-sink/{print $1}'); do pactl unload-module $i 2>/dev/null; done")
        self.exec_cmd("pactl load-module module-ladspa-sink sink_name=eq master=%s plugin=mbeq_1197 label=mbeq control='%s'" % (master, ctrl))
        self.exec_cmd("pactl set-default-sink eq 2>/dev/null || true")
        self.exec_cmd("for i in $(pactl list short sink-inputs 2>/dev/null | cut -f1); do pactl move-sink-input $i eq 2>/dev/null; done")

    def _json(self, code, obj):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(obj).encode())

    def exec_cmd(self, cmd):
        try:
            return subprocess.check_output(cmd, shell=True).decode('utf-8').strip()
        except Exception as e:
            return str(e)

    def log_message(self, fmt, *args):
        pass


class ThreadingServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == '__main__':
    os.chdir(DOCROOT)
    with ThreadingServer(("", PORT), RouterAPIHandler) as httpd:
        httpd.serve_forever()
