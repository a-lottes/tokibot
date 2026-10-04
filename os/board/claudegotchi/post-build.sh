#!/bin/sh
# Root-Dateisystem bleibt nur lesbar. Die Boot-Partition (mit claudegotchi.toml)
# wird nach /boot eingebunden, ebenfalls nur lesbar.
set -eu

mkdir -p "${TARGET_DIR}/boot"
grep -q '[[:space:]]/boot[[:space:]]' "${TARGET_DIR}/etc/fstab" || \
	echo '/dev/mmcblk0p1	/boot		vfat	ro,noatime	0	0' >> "${TARGET_DIR}/etc/fstab"

# Kein Login auf dem HDMI-Ausgang nötig; die serielle Konsole bleibt.
sed -i '/^tty1::/d' "${TARGET_DIR}/etc/inittab"

# Version ins Image schreiben
VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "${BR2_EXTERNAL_CLAUDEGOTCHI_PATH}/../app/claudegotchi/__init__.py")
echo "claudegotchi ${VERSION}" > "${TARGET_DIR}/etc/claudegotchi-release"
