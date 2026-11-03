#!/bin/bash
set -euo pipefail

WORK="$HOME/.local/var/pmbootstrap"
PMAPORTS="$WORK/cache_git/pmaports"
PKG_SRC="$PWD/ci/vince-headless"

mkdir -p "$WORK/cache_git"
[ -f "$WORK/version" ] || echo 8 > "$WORK/version"
[ -d "$PMAPORTS/.git" ] || git clone --depth 1 \
  https://gitlab.postmarketos.org/postmarketOS/pmaports.git "$PMAPORTS"

DEVDIR="$(find "$PMAPORTS/device" -maxdepth 2 -type d -name device-xiaomi-vince | head -n1)"
if [ -z "$DEVDIR" ]; then
  echo "ERROR: device-xiaomi-vince tidak ada di pmaports" >&2
  exit 1
fi
echo "Device package: $DEVDIR"

DEST="$PMAPORTS/temp/vince-headless"
rm -rf "$DEST"
mkdir -p "$PMAPORTS/temp"
cp -r "$PKG_SRC" "$DEST"

# --- isi password dari secrets (tidak pernah masuk repo) ---
esc() { printf '%s' "$1" | sed 's/[&|\\]/\\&/g'; }
PSK="${HOTSPOT_PSK:-vince12345}"
PW="${PMOS_PASSWORD:-147147}"
sed -i "s|__HOTSPOT_PSK__|$(esc "$PSK")|" "$DEST/Hotspot.nmconnection"
sed -i "s|__RPC_SECRET__|$(esc "$PW")|" "$DEST/aria2.conf"
printf '%s\n' "$PW" > "$DEST/smb-pass"

# --- AriaNg (web UI aria2), diunduh saat build ---
ARIANG_VER="1.3.7"
TMP="$(mktemp -d)"
mkdir -p "$TMP/ariang"
if curl -fsSL -o "$TMP/a.zip" \
     "https://github.com/mayswind/AriaNg/releases/download/${ARIANG_VER}/AriaNg-${ARIANG_VER}.zip" \
   && unzip -q "$TMP/a.zip" -d "$TMP/ariang"; then
  echo "AriaNg ${ARIANG_VER} OK"
else
  echo "PERINGATAN: AriaNg gagal diunduh, pakai halaman pengganti"
  echo '<!doctype html><meta charset="utf-8"><h1>AriaNg gagal diunduh saat build</h1><p>RPC aria2 tetap aktif di port 6800.</p>' > "$TMP/ariang/index.html"
fi
tar -C "$TMP" -czf "$DEST/ariang.tar.gz" ariang

# --- konfigurasi pmbootstrap ---
CFG="$HOME/.config/pmbootstrap_v3.cfg"; mkdir -p "$HOME/.config"; echo "[pmbootstrap]" > "$CFG"; pmbootstrap() { command pmbootstrap --config "$CFG" "$@"; }
pmbootstrap config device xiaomi-vince
pmbootstrap config ui none
pmbootstrap config service_manager openrc
pmbootstrap config hostname vince
pmbootstrap config jobs "$(nproc)"

# buang paket yang tidak ada di repo (supaya build tidak berhenti di satu nama)
pmbootstrap chroot -- apk update >/dev/null 2>&1 || true
for p in $(awk '/^depends="/{f=1;next} f&&/^"/{exit} f{print $1}' "$DEST/APKBUILD"); do
  if [ -z "$(pmbootstrap chroot -- apk search -e "$p" 2>/dev/null)" ]; then
    echo "PERINGATAN: '$p' tidak ada di repo, dibuang dari depends"
    sed -i "/^[[:space:]]*$p\$/d" "$DEST/APKBUILD"
  fi
done
pmbootstrap checksum vince-headless
pmbootstrap -y build vince-headless

pmbootstrap -y install --password "$PW" --add vince-headless

rm -rf /tmp/pmos-export
pmbootstrap -y export /tmp/pmos-export

mkdir -p output
sudo cp -L /tmp/pmos-export/* output/
sudo chown -R "$(id -u):$(id -g)" output
ls -lh output
[ -n "$(ls -A output)" ] || { echo "ERROR: output kosong" >&2; exit 1; }
