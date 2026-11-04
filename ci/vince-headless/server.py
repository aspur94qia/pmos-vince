import http.server
import socketserver
import json
import subprocess
import os

PORT = 80

class RouterAPIHandler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        if path == "/" or not path.startswith("/api/"):
            return os.path.join("/var/www/localhost/htdocs", path.lstrip("/"))
        return super().translate_path(path)

    def do_GET(self):
        if self.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            
            # Read battery & system stats
            bat_pct = self.exec_cmd("cat /sys/class/power_supply/battery/capacity 2>/dev/null || echo 100")
            charging = "1" in self.exec_cmd("cat /sys/class/power_supply/battery/status 2>/dev/null | grep -i charging || echo 0")
            temp = str(int(self.exec_cmd("cat /sys/class/power_supply/battery/temp 2>/dev/null || echo 320")) // 10)
            ram = self.exec_cmd("free -m | awk '/Mem:/ {print $3\"MB (\"int($3/$2*100)\"%)\"}'")
            cpu = self.exec_cmd("uptime | awk -F'load average:' '{print $2}'").strip()
            uptime = self.exec_cmd("uptime -p").replace("up ", "")

            data = {
                "battery_pct": bat_pct,
                "charging": charging,
                "temp": temp,
                "ram": ram,
                "cpu": cpu,
                "uptime": uptime
            }
            self.wfile.write(json.dumps(data).encode())
        elif self.path == "/api/scan-wifi":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            networks = [
                {"ssid": "Wi-Fi_Rumah_5G", "signal": 85, "security": "WPA2"},
                {"ssid": "Hotspot_Tetangga", "signal": 40, "security": "WPA2"}
            ]
            self.wfile.write(json.dumps(networks).encode())
        elif self.path == "/api/diag":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            diag_out = self.exec_cmd("/usr/bin/vince-diag 2>&1 || echo 'vince-diag executed.'")
            audio_diag = self.exec_cmd("/usr/bin/vince-audio-diag 2>&1 || echo 'vince-audio-diag executed.'")
            self.wfile.write(f"--- SYSTEM DIAG ---\n{diag_out}\n\n--- AUDIO DIAG ---\n{audio_diag}".encode())
        else:
            super().do_GET()

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode('utf-8') if length > 0 else "{}"
        data = json.loads(body)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()

        if self.path == "/api/hotspot":
            ssid, psw = data.get("ssid"), data.get("pass")
            self.exec_cmd(f"nmcli con mod Hotspot ssid '{ssid}' wpa-psk '{psw}' && nmcli con up Hotspot")
        elif self.path == "/api/connect-repeater":
            ssid, psw = data.get("ssid"), data.get("pass")
            self.exec_cmd(f"nmcli dev wifi connect '{ssid}' password '{psw}'")
        elif self.path == "/api/toggle-data":
            st = "on" if data.get("state") else "off"
            self.exec_cmd(f"nmcli networking connectivity {st}")
        elif self.path == "/api/toggle-ttl":
            if data.get("state"):
                self.exec_cmd("iptables -t mangle -A POSTROUTING -j TTL --ttl-set 64")
            else:
                self.exec_cmd("iptables -t mangle -D POSTROUTING -j TTL --ttl-set 64")
        elif self.path == "/api/imei":
            imei = data.get("imei")
            self.exec_cmd(f"echo -e 'AT+EGMR=1,7,\"{imei}\"\r' > /dev/ttyUSB0")
        elif self.path == "/api/bt-alias":
            alias = data.get("alias")
            self.exec_cmd(f"bluetoothctl system-alias '{alias}'")
        elif self.path == "/api/usb-mode":
            mode = data.get("mode")
            self.exec_cmd(f"/usr/bin/vince-usb {mode}")
        elif self.path == "/api/led-bright":
            val = data.get("val")
            self.exec_cmd(f"echo {val} > /sys/class/leds/white:status/brightness 2>/dev/null || true")
        elif self.path == "/api/restart-samba":
            self.exec_cmd("rc-service samba restart")
        elif self.path == "/api/reboot":
            self.exec_cmd("reboot")

        self.wfile.write(json.dumps({"status": "ok"}).encode())

    def exec_cmd(self, cmd):
        try:
            return subprocess.check_output(cmd, shell=True).decode('utf-8').strip()
        except Exception as e:
            return str(e)

if __name__ == '__main__':
    with socketserver.TCPServer(("", PORT), RouterAPIHandler) as httpd:
        httpd.serve_forever()
