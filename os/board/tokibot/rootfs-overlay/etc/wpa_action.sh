#!/bin/sh
# Called by wpa_cli (see S46wifi) with: interface event.
# After joining a network, drop the old DHCP lease and ask for a new one, so a
# switch from home Wi-Fi to the phone hotspot (or back) gets a working address.
[ "$2" = "CONNECTED" ] || exit 0
pid=$(cat "/run/udhcpc.$1.pid" 2>/dev/null) || exit 0
kill -USR2 "$pid" 2>/dev/null       # release the lease
kill -USR1 "$pid" 2>/dev/null       # and start over: discover, request
