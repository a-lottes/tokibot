#!/bin/sh
# The root filesystem stays read-only. The boot partition (with tokibot.toml)
# is mounted at /boot, also read-only. Only /data is writable.
set -eu

mkdir -p "${TARGET_DIR}/boot"
grep -q '[[:space:]]/boot[[:space:]]' "${TARGET_DIR}/etc/fstab" || \
	echo '/dev/mmcblk0p1	/boot		vfat	ro,noatime	0	0' >> "${TARGET_DIR}/etc/fstab"

# Writable data partition for the critter's progress. nofail: boot even if it is missing.
mkdir -p "${TARGET_DIR}/data"
grep -q '[[:space:]]/data[[:space:]]' "${TARGET_DIR}/etc/fstab" || \
	echo '/dev/mmcblk0p3	/data		ext4	rw,noatime,nofail,commit=60	0	0' >> "${TARGET_DIR}/etc/fstab"

# No login on the HDMI output; the serial console stays.
sed -i '/^tty1::/d' "${TARGET_DIR}/etc/inittab"

# Write the version into the image
VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "${BR2_EXTERNAL_TOKIBOT_PATH}/../app/tokibot/__init__.py")
echo "tokibot ${VERSION}" > "${TARGET_DIR}/etc/tokibot-release"

# Make the init scripts executable (in case the checkout lost the permissions)
chmod 0755 "${TARGET_DIR}"/etc/init.d/S*
