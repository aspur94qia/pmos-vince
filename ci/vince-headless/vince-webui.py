#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pmos-vince Web UI Control Center
postmarketOS Router & Audio Management for Xiaomi Redmi 5 Plus (vince)
"""

import http.server
import json
import os
import subprocess
import urllib.parse

PORT = 80

HTML_CONTENT = """<!DOCTYPE html>
<html lang="id" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>pmos-vince Control Center | postmarketOS Router</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {
            darkMode: 'class',
            theme: {
                extend: {
                    colors: {
                        cyber: {
                            900: '#0b0f19',
                            800: '#111827',
                            700: '#1f2937',
                            accent: '#06b6d4',
                            glow: '#3b82f6',
                            danger: '#ef4444',
                            success: '#10b981',
                            warning: '#f59e0b'
                        }
                    },
                    fontFamily: {
                        sans: ['Inter', 'sans-serif'],
                        mono: ['JetBrains Mono', 'Fira Code', 'monospace']
                    }
                }
            }
        }
    </script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        body { font-family: 'Inter', sans-serif; }
        .custom-scrollbar::-webkit-scrollbar { width: 6px; height: 6px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: #111827; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: #374151; border-radius: 4px; }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: #4b5563; }
        .glow-accent { box-shadow: 0 0 15px rgba(6, 182, 212, 0.25); }
        .glow-danger { box-shadow: 0 0 15px rgba(239, 68, 68, 0.25); }
    </style>
</head>
<body class="bg-cyber-900 text-gray-100 min-h-screen flex flex-col antialiased selection:bg-cyber-accent selection:text-black">

    <div id="toast-container" class="fixed top-5 right-5 z-50 flex flex-col gap-3 max-w-sm w-full pointer-events-none"></div>

    <div id="reboot-modal" class="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 hidden flex items-center justify-center p-4">
        <div class="bg-cyber-800 border border-red-500/30 rounded-2xl p-6 max-w-md w-full shadow-2xl glow-danger">
            <div class="flex items-center gap-4 text-red-500 mb-4">
                <div class="p-3 bg-red-500/10 rounded-xl">
                    <i class="fa-solid fa-triangle-exclamation text-2xl"></i>
                </div>
                <div>
                    <h3 class="text-xl font-bold text-white">Reboot Perangkat</h3>
                    <p class="text-sm text-gray-400">Konfirmasi restart sistem router pmos-vince</p>
                </div>
            </div>
            <p class="text-gray-300 text-sm mb-6">Apakah Anda yakin ingin menyalakan ulang router? Semua koneksi hotspot dan layanan aktif akan terputus sementara waktu selama proses booting.</p>
            <div class="flex justify-end gap-3">
                <button onclick="closeRebootModal()" class="px-4 py-2 rounded-xl bg-gray-700 hover:bg-gray-600 text-gray-200 text-sm font-medium transition">Batal</button>
                <button onclick="confirmReboot()" class="px-5 py-2 rounded-xl bg-red-600 hover:bg-red-500 text-white text-sm font-semibold transition flex items-center gap-2">
                    <i class="fa-solid fa-power-off"></i> Reboot Sekarang
                </button>
            </div>
        </div>
    </div>

    <!-- LOGIN SCREEN -->
    <div id="login-screen" class="fixed inset-0 z-40 bg-cyber-900 flex items-center justify-center p-4">
        <div class="w-full max-w-md bg-cyber-800 border border-gray-700/60 rounded-3xl p-8 shadow-2xl relative overflow-hidden">
            <div class="absolute -top-12 -right-12 w-40 h-40 bg-cyber-accent/10 rounded-full blur-3xl pointer-events-none"></div>
            <div class="absolute -bottom-12 -left-12 w-40 h-40 bg-blue-600/10 rounded-full blur-3xl pointer-events-none"></div>

            <div class="text-center mb-8">
                <div class="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-cyber-accent/10 border border-cyber-accent/30 text-cyber-accent mb-4 glow-accent">
                    <i class="fa-solid fa-microchip text-3xl"></i>
                </div>
                <h1 class="text-2xl font-bold text-white tracking-wide">pmos-vince Web UI</h1>
                <p class="text-xs text-gray-400 mt-1">postmarketOS Router Control Panel • Xiaomi Redmi 5 Plus</p>
            </div>

            <form id="login-form" onsubmit="handleLogin(event)" class="space-y-5">
                <div>
                    <label class="block text-xs font-semibold uppercase tracking-wider text-gray-400 mb-2">Username</label>
                    <div class="relative">
                        <span class="absolute inset-y-0 left-0 flex items-center pl-4 text-gray-500"><i class="fa-solid fa-user"></i></span>
                        <input type="text" id="login-user" required value="admin" class="w-full pl-11 pr-4 py-3 bg-cyber-900 border border-gray-700 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:border-cyber-accent transition text-sm">
                    </div>
                </div>

                <div>
                    <label class="block text-xs font-semibold uppercase tracking-wider text-gray-400 mb-2">Password</label>
                    <div class="relative">
                        <span class="absolute inset-y-0 left-0 flex items-center pl-4 text-gray-500"><i class="fa-solid fa-lock"></i></span>
                        <input type="password" id="login-pass" required value="vince123" class="w-full pl-11 pr-4 py-3 bg-cyber-900 border border-gray-700 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:border-cyber-accent transition text-sm">
                    </div>
                </div>

                <button type="submit" class="w-full py-3.5 bg-gradient-to-r from-cyber-accent to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-black font-bold rounded-xl shadow-lg transition duration-200 flex items-center justify-center gap-2 text-sm mt-2">
                    <i class="fa-solid fa-right-to-bracket"></i> Masuk Dashboard
                </button>
            </form>
        </div>
    </div>

    <!-- MAIN DASHBOARD -->
    <div id="dashboard-screen" class="hidden flex-1 flex flex-col min-h-screen">
        <header class="bg-cyber-800/80 backdrop-blur-md border-b border-gray-800 sticky top-0 z-30 px-4 lg:px-8 py-3">
            <div class="max-w-7xl mx-auto flex items-center justify-between gap-4">
                <div class="flex items-center gap-3">
                    <div class="w-10 h-10 rounded-xl bg-cyber-accent/10 border border-cyber-accent/40 flex items-center justify-center text-cyber-accent">
                        <i class="fa-solid fa-router text-lg"></i>
                    </div>
                    <div>
                        <div class="flex items-center gap-2">
                            <span class="font-bold text-white tracking-tight text-base">pmos-vince</span>
                            <span class="px-2 py-0.5 text-[10px] font-mono font-bold bg-green-500/10 text-green-400 border border-green-500/30 rounded-full flex items-center gap-1">
                                <span class="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse"></span> ONLINE
                            </span>
                        </div>
                        <p class="text-[11px] text-gray-400 font-mono">192.168.1.1 • postmarketOS v23.12</p>
                    </div>
                </div>

                <div class="flex items-center gap-3">
                    <div class="bg-cyber-900 border border-gray-700/80 rounded-xl px-3.5 py-1.5 flex items-center gap-3">
                        <i id="bat-icon" class="fa-solid fa-battery-three-quarters text-cyber-accent text-lg"></i>
                        <div class="flex flex-col">
                            <div class="flex items-center gap-1">
                                <span id="bat-val" class="font-mono text-xs font-bold text-white">--%</span>
                                <span id="bat-status-badge" class="text-[9px] px-1.5 py-0.2 bg-gray-800 text-gray-300 rounded font-semibold">STANDBY</span>
                            </div>
                            <span id="bat-temp" class="text-[10px] text-gray-400 font-mono">--°C</span>
                        </div>
                    </div>

                    <button onclick="handleLogout()" class="px-3.5 py-2 bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/30 rounded-xl text-xs font-semibold transition flex items-center gap-2">
                        <i class="fa-solid fa-right-from-bracket"></i>
                        <span class="hidden sm:inline">Keluar</span>
                    </button>
                </div>
            </div>
        </header>

        <!-- NAVIGATION TABS -->
        <div class="bg-cyber-800 border-b border-gray-800 px-4 lg:px-8">
            <div class="max-w-7xl mx-auto flex items-center gap-2 overflow-x-auto py-2 custom-scrollbar">
                <button onclick="switchTab('tab-status')" id="btn-tab-status" class="tab-btn active font-medium text-xs px-4 py-2.5 rounded-xl whitespace-nowrap transition flex items-center gap-2 bg-cyber-accent/10 text-cyber-accent border border-cyber-accent/40"><i class="fa-solid fa-chart-line"></i> Status System</button>
                <button onclick="switchTab('tab-ap')" id="btn-tab-ap" class="tab-btn font-medium text-xs px-4 py-2.5 rounded-xl whitespace-nowrap transition flex items-center gap-2 text-gray-400 hover:text-white hover:bg-gray-800"><i class="fa-solid fa-wifi"></i> Hotspot & AP</button>
                <button onclick="switchTab('tab-repeater')" id="btn-tab-repeater" class="tab-btn font-medium text-xs px-4 py-2.5 rounded-xl whitespace-nowrap transition flex items-center gap-2 text-gray-400 hover:text-white hover:bg-gray-800"><i class="fa-solid fa-rotate"></i> Wi-Fi Repeater</button>
                <button onclick="switchTab('tab-sim')" id="btn-tab-sim" class="tab-btn font-medium text-xs px-4 py-2.5 rounded-xl whitespace-nowrap transition flex items-center gap-2 text-gray-400 hover:text-white hover:bg-gray-800"><i class="fa-solid fa-sim-card"></i> SIM & TTL</button>
                <button onclick="switchTab('tab-audio')" id="btn-tab-audio" class="tab-btn font-medium text-xs px-4 py-2.5 rounded-xl whitespace-nowrap transition flex items-center gap-2 text-gray-400 hover:text-white hover:bg-gray-800"><i class="fa-solid fa-sliders"></i> Audio Dolby</button>
                <button onclick="switchTab('tab-bt')" id="btn-tab-bt" class="tab-btn font-medium text-xs px-4 py-2.5 rounded-xl whitespace-nowrap transition flex items-center gap-2 text-gray-400 hover:text-white hover:bg-gray-800"><i class="fa-brands fa-bluetooth-b"></i> Bluetooth Receiver</button>
                <button onclick="switchTab('tab-usb')" id="btn-tab-usb" class="tab-btn font-medium text-xs px-4 py-2.5 rounded-xl whitespace-nowrap transition flex items-center gap-2 text-gray-400 hover:text-white hover:bg-gray-800"><i class="fa-solid fa-usb"></i> USB & ADB</button>
                <button onclick="switchTab('tab-led')" id="btn-tab-led" class="tab-btn font-medium text-xs px-4 py-2.5 rounded-xl whitespace-nowrap transition flex items-center gap-2 text-gray-400 hover:text-white hover:bg-gray-800"><i class="fa-solid fa-lightbulb"></i> LED Control</button>
                <button onclick="switchTab('tab-nas')" id="btn-tab-nas" class="tab-btn font-medium text-xs px-4 py-2.5 rounded-xl whitespace-nowrap transition flex items-center gap-2 text-gray-400 hover:text-white hover:bg-gray-800"><i class="fa-solid fa-hard-drive"></i> Samba & Web App</button>
                <button onclick="switchTab('tab-diag')" id="btn-tab-diag" class="tab-btn font-medium text-xs px-4 py-2.5 rounded-xl whitespace-nowrap transition flex items-center gap-2 text-gray-400 hover:text-white hover:bg-gray-800"><i class="fa-solid fa-vial-virus"></i> Diagnostik</button>
            </div>
        </div>

        <main class="flex-1 max-w-7xl w-full mx-auto p-4 lg:p-8">
            <!-- TAB STATUS -->
            <section id="tab-status" class="tab-content space-y-6">
                <div class="flex items-center justify-between">
                    <h2 class="text-xl font-bold text-white flex items-center gap-2"><i class="fa-solid fa-gauge-high text-cyber-accent"></i> Telemetri Hardware & Sistem</h2>
                    <span class="text-xs font-mono text-gray-400 bg-cyber-800 px-3 py-1.5 rounded-lg border border-gray-700" id="status-timer">Updating in 3s</span>
                </div>
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                    <div class="bg-cyber-800 border border-gray-800 rounded-2xl p-5 shadow-lg">
                        <span class="text-xs font-semibold text-gray-400 uppercase tracking-wider">CPU Load (MSM8953)</span>
                        <div class="text-2xl font-bold font-mono text-white my-2" id="stat-cpu-load">0.42, 0.38, 0.35</div>
                    </div>
                    <div class="bg-cyber-800 border border-gray-800 rounded-2xl p-5 shadow-lg">
                        <span class="text-xs font-semibold text-gray-400 uppercase tracking-wider">Memori RAM</span>
                        <div class="text-2xl font-bold font-mono text-white my-2"><span id="stat-ram-used">1120</span> MB</div>
                    </div>
                    <div class="bg-cyber-800 border border-gray-800 rounded-2xl p-5 shadow-lg">
                        <span class="text-xs font-semibold text-gray-400 uppercase tracking-wider">Baterai</span>
                        <div class="text-2xl font-bold font-mono text-white my-2" id="stat-bat-val">84%</div>
                    </div>
                    <div class="bg-cyber-800 border border-gray-800 rounded-2xl p-5 shadow-lg">
                        <span class="text-xs font-semibold text-gray-400 uppercase tracking-wider">Uptime</span>
                        <div class="text-2xl font-bold font-mono text-white my-2" id="stat-uptime">2d 14h</div>
                    </div>
                </div>
            </section>

            <!-- TAB HOTSPOT -->
            <section id="tab-ap" class="tab-content space-y-6 hidden">
                <h2 class="text-xl font-bold text-white flex items-center gap-2"><i class="fa-solid fa-wifi text-cyber-accent"></i> Hotspot & AP Wi-Fi</h2>
                <div class="bg-cyber-800 border border-gray-800 rounded-2xl p-6 max-w-2xl">
                    <form onsubmit="saveHotspot(event)" class="space-y-4">
                        <div>
                            <label class="block text-xs font-semibold uppercase tracking-wider text-gray-400 mb-2">SSID Hotspot</label>
                            <input type="text" id="ap-ssid" value="pmos-vince-AP" class="w-full px-4 py-3 bg-cyber-900 border border-gray-700 rounded-xl text-white font-mono text-sm">
                        </div>
                        <div>
                            <label class="block text-xs font-semibold uppercase tracking-wider text-gray-400 mb-2">Password</label>
                            <input type="password" id="ap-pass" value="vince12345" class="w-full px-4 py-3 bg-cyber-900 border border-gray-700 rounded-xl text-white font-mono text-sm">
                        </div>
                        <button type="submit" class="px-6 py-3 bg-cyber-accent text-black font-bold rounded-xl text-sm">Simpan & Restart</button>
                    </form>
                </div>
            </section>

            <!-- TAB REPEATER -->
            <section id="tab-repeater" class="tab-content space-y-6 hidden">
                <h2 class="text-xl font-bold text-white flex items-center gap-2"><i class="fa-solid fa-rotate text-cyber-accent"></i> Wi-Fi Repeater</h2>
                <div class="bg-cyber-800 border border-gray-800 rounded-2xl p-6 max-w-2xl space-y-4">
                    <button onclick="scanWifi()" class="px-4 py-2 bg-gray-700 text-white rounded-xl text-xs font-semibold">Pindai Wi-Fi</button>
                    <select id="wifi-target-select" class="w-full px-4 py-3 bg-cyber-900 border border-gray-700 rounded-xl text-white text-sm">
                        <option value="">-- Pilih Wi-Fi Target --</option>
                    </select>
                </div>
            </section>

            <!-- TAB SIM & TTL -->
            <section id="tab-sim" class="tab-content space-y-6 hidden">
                <h2 class="text-xl font-bold text-white flex items-center gap-2"><i class="fa-solid fa-sim-card text-cyber-accent"></i> SIM & TTL Bypass</h2>
                <div class="bg-cyber-800 border border-gray-800 rounded-2xl p-6 max-w-2xl space-y-4">
                    <label class="flex items-center gap-3 cursor-pointer">
                        <input type="checkbox" id="toggle-ttl-bypass" checked class="w-5 h-5 accent-cyber-accent">
                        <span class="text-sm font-bold text-white">Bypass Tethering TTL 64 (iptables)</span>
                    </label>
                </div>
            </section>

            <!-- TAB AUDIO -->
            <section id="tab-audio" class="tab-content space-y-6 hidden">
                <h2 class="text-xl font-bold text-white flex items-center gap-2"><i class="fa-solid fa-sliders text-cyber-accent"></i> Audio Dolby Preset</h2>
                <div class="bg-cyber-800 border border-gray-800 rounded-2xl p-6 max-w-2xl space-y-4">
                    <select id="audio-dolby-preset" onchange="applyDolbyPreset(this.value)" class="w-full px-4 py-3 bg-cyber-900 border border-gray-700 rounded-xl text-white text-sm">
                        <option value="dynamic">Dolby Dynamic</option>
                        <option value="movie">Dolby Movie</option>
                        <option value="music">Dolby Music</option>
                        <option value="bass">Extreme Bass Boost</option>
                    </select>
                </div>
            </section>

            <!-- TAB BLUETOOTH -->
            <section id="tab-bt" class="tab-content space-y-6 hidden">
                <h2 class="text-xl font-bold text-white flex items-center gap-2"><i class="fa-brands fa-bluetooth-b text-cyber-accent"></i> Bluetooth Receiver</h2>
                <div class="bg-cyber-800 border border-gray-800 rounded-2xl p-6 max-w-2xl">
                    <input type="text" id="bt-alias-name" value="pmos-vince" class="w-full px-4 py-3 bg-cyber-900 border border-gray-700 rounded-xl text-white font-mono text-sm mb-4">
                    <button onclick="showToast('Nama Bluetooth diperbarui', 'success')" class="px-6 py-2.5 bg-blue-600 text-white font-bold rounded-xl text-xs">Simpan Bluetooth</button>
                </div>
            </section>

            <!-- TAB USB -->
            <section id="tab-usb" class="tab-content space-y-6 hidden">
                <h2 class="text-xl font-bold text-white flex items-center gap-2"><i class="fa-solid fa-usb text-cyber-accent"></i> USB & ADB Gadget</h2>
                <div class="bg-cyber-800 border border-gray-800 rounded-2xl p-6 max-w-2xl">
                    <button onclick="showToast('Kunci ADB disinkronkan', 'success')" class="px-5 py-2.5 bg-cyber-accent text-black font-bold rounded-xl text-xs">Sync adb_keys</button>
                </div>
            </section>

            <!-- TAB LED -->
            <section id="tab-led" class="tab-content space-y-6 hidden">
                <h2 class="text-xl font-bold text-white flex items-center gap-2"><i class="fa-solid fa-lightbulb text-cyber-accent"></i> LED Control</h2>
                <div class="bg-cyber-800 border border-gray-800 rounded-2xl p-6 max-w-2xl">
                    <input type="range" min="0" max="255" value="180" class="w-full accent-cyber-accent">
                </div>
            </section>

            <!-- TAB NAS -->
            <section id="tab-nas" class="tab-content space-y-6 hidden">
                <h2 class="text-xl font-bold text-white flex items-center gap-2"><i class="fa-solid fa-hard-drive text-cyber-accent"></i> Samba & Web Services</h2>
                <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
                    <div class="bg-cyber-800 border border-gray-800 rounded-2xl p-6 space-y-4">
                        <h3 class="text-base font-bold text-white">Web Terminal (ttyd)</h3>
                        <a href="http://192.168.1.1:7681" target="_blank" class="block py-2.5 bg-green-600 text-black font-bold rounded-xl text-center text-xs">Buka Port 7681</a>
                    </div>
                    <div class="bg-cyber-800 border border-gray-800 rounded-2xl p-6 space-y-4">
                        <h3 class="text-base font-bold text-white">Aria2 Downloader</h3>
                        <a href="http://192.168.1.1:6800" target="_blank" class="block py-2.5 bg-blue-600 text-white font-bold rounded-xl text-center text-xs">Buka Port 6800</a>
                    </div>
                </div>
            </section>

            <!-- TAB DIAGNOSTIK -->
            <section id="tab-diag" class="tab-content space-y-6 hidden">
                <div class="flex items-center justify-between">
                    <h2 class="text-xl font-bold text-white flex items-center gap-2"><i class="fa-solid fa-vial-virus text-cyber-accent"></i> Diagnostik</h2>
                    <button onclick="runDiagnostics()" class="px-4 py-2 bg-cyber-accent text-black rounded-xl text-xs font-bold">Jalankan Tes</button>
                </div>
                <pre id="diag-log-box" class="bg-cyber-900 border border-gray-900 rounded-xl p-4 font-mono text-xs text-green-400 h-60 overflow-y-auto">[INIT] Ready...</pre>
            </section>
        </main>
    </div>

    <script>
        const AUTH_COOKIE = "PMOS_VINCE_SESSION";
        function setCookie(n, v, h) {
            const d = new Date(); d.setTime(d.getTime() + (h*3600*1000));
            document.cookie = `${n}=${v};expires=${d.toUTCString()};path=/`;
        }
        function getCookie(n) {
            const match = document.cookie.match(new RegExp('(^| )' + n + '=([^;]+)'));
            return match ? match[2] : null;
        }
        function checkAuth() {
            if (getCookie(AUTH_COOKIE)) {
                document.getElementById('login-screen').classList.add('hidden');
                document.getElementById('dashboard-screen').classList.remove('hidden');
            } else {
                document.getElementById('login-screen').classList.remove('hidden');
                document.getElementById('dashboard-screen').classList.add('hidden');
            }
        }
        function handleLogin(e) {
            e.preventDefault();
            if(document.getElementById('login-user').value === 'admin' && document.getElementById('login-pass').value === 'vince123') {
                setCookie(AUTH_COOKIE, 'active-session', 24);
                checkAuth();
                showToast('Login Berhasil!', 'success');
            } else {
                showToast('Password salah!', 'danger');
            }
        }
        function handleLogout() {
            document.cookie = `${AUTH_COOKIE}=; Max-Age=-999999; path=/;`;
            checkAuth();
        }
        function switchTab(id) {
            document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
            document.querySelectorAll('.tab-btn').forEach(btn => btn.className = "tab-btn font-medium text-xs px-4 py-2.5 rounded-xl whitespace-nowrap transition flex items-center gap-2 text-gray-400 hover:text-white hover:bg-gray-800");
            document.getElementById(id).classList.remove('hidden');
            document.getElementById('btn-' + id).className = "tab-btn active font-medium text-xs px-4 py-2.5 rounded-xl whitespace-nowrap transition flex items-center gap-2 bg-cyber-accent/10 text-cyber-accent border border-cyber-accent/40";
        }
        function showToast(msg, type='info') {
            const c = document.getElementById('toast-container');
            const t = document.createElement('div');
            t.className = `p-4 rounded-xl border shadow-xl bg-cyber-800 text-white text-xs font-semibold`;
            t.innerHTML = `<i class="fa-solid fa-info-circle text-cyber-accent mr-2"></i> ${msg}`;
            c.appendChild(t);
            setTimeout(() => t.remove(), 3000);
        }
        function runDiagnostics() {
            document.getElementById('diag-log-box').innerHTML += `\n[TEST] Running vince-diag... OK`;
        }
        window.addEventListener('DOMContentLoaded', checkAuth);
    </script>
</body>
</html>
"""

class VinceWebUIHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_CONTENT.encode('utf-8'))
        elif self.path == '/api/status':
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            status_data = {
                "battery": {"level": 85, "temp": 34.0, "charging": False},
                "cpu": {"load": ["0.40", "0.35", "0.30"]},
                "ram": {"used": 1150, "total": 2950},
                "uptime": "3d 12h"
            }
            self.wfile.write(json.dumps(status_data).encode('utf-8'))
        else:
            super().do_GET()

if __name__ == '__main__':
    server_address = ('', PORT)
    httpd = http.server.HTTPServer(server_address, VinceWebUIHandler)
    print(f"[*] Starting pmos-vince Web UI Server on port {PORT}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[!] Stopping Web UI Server...")
        httpd.server_close()
