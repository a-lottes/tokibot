"""Radios for the social module: how gotchis hear each other.

  BleRadio   Bluetooth LE on the device. Talks raw HCI to the kernel, so no
             bluetoothd and no D-Bus are needed: non-connectable advertising with a
             random, rotating address, plus passive scanning.
  UdpRadio   The simulator: packets go over UDP on localhost, so two simulators
             (or the fake gotchi) on one computer can meet.

Both cycle through a list of packets (see social.py) and call
on_packet(address, rssi, payload) for every Tokibot packet they hear.
"""
import errno
import fcntl
import logging
import os
import select
import socket
import struct
import threading

log = logging.getLogger("tokibot.radio")

SLOT = 0.25                    # seconds per packet before the next one goes out
COMPANY = b"\xff\xff"          # manufacturer id 0xFFFF: reserved for testing / internal use
UDP_PORTS = range(48760, 48780)


class Radio:
    def __init__(self):
        self.packets, self.on_packet = [], None
        self.lock = threading.Lock()
        self.stop_evt = threading.Event()

    def set_packets(self, packets):
        with self.lock:
            self.packets = list(packets)

    def rotate_address(self):
        pass

    def stop(self):
        self.stop_evt.set()

    def _cycle(self):
        i = 0
        while not self.stop_evt.is_set():
            with self.lock:
                pkt = self.packets[i % len(self.packets)] if self.packets else None
            i += 1
            yield pkt


class UdpRadio(Radio):
    def __init__(self, rssi=-50):
        super().__init__()
        self.rssi = rssi
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        for port in UDP_PORTS:
            try:
                self.sock.bind(("127.0.0.1", port))
                break
            except OSError:
                continue
        else:
            raise OSError("no free UDP port for the simulated radio")
        self.port = self.sock.getsockname()[1]

    def start(self, on_packet):
        self.on_packet = on_packet
        threading.Thread(target=self._send, daemon=True, name="udp-radio-tx").start()
        threading.Thread(target=self._receive, daemon=True, name="udp-radio-rx").start()
        log.info("Simulated radio on UDP port %d", self.port)

    def _send(self):
        for pkt in self._cycle():
            if pkt:
                for port in UDP_PORTS:
                    if port != self.port:
                        try:
                            self.sock.sendto(pkt, ("127.0.0.1", port))
                        except OSError:
                            pass
            self.stop_evt.wait(SLOT)

    def _receive(self):
        self.sock.settimeout(1.0)
        while not self.stop_evt.is_set():
            try:
                data, (_, port) = self.sock.recvfrom(64)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                self.on_packet(f"udp:{port}", self.rssi, data)
            except Exception:
                log.exception("Handling a packet failed")


# --- Bluetooth LE over raw HCI ---------------------------------------------------------

HCIDEVUP = 0x400448C9
OGF_LE = 0x08
LE_SET_RANDOM_ADDRESS = 0x0005
LE_SET_ADV_PARAMS = 0x0006
LE_SET_ADV_DATA = 0x0008
LE_SET_ADV_ENABLE = 0x000A
LE_SET_SCAN_PARAMS = 0x000B
LE_SET_SCAN_ENABLE = 0x000C


def ad_payload(pkt):
    """Advertising data: one manufacturer-specific AD structure, padded to 31 bytes."""
    md = COMPANY + pkt
    ad = bytes([len(md) + 1, 0xFF]) + md
    return bytes([len(ad)]) + ad.ljust(31, b"\0")


def parse_reports(evt):
    """LE Advertising Report event (without the 0x04 packet type byte) ->
    [(address, rssi, tokibot payload)]."""
    out = []
    if len(evt) < 4 or evt[0] != 0x3E or evt[2] != 0x02:
        return out
    pos = 4
    for _ in range(evt[3]):
        if pos + 9 > len(evt):
            break
        addr = evt[pos + 2:pos + 8][::-1].hex(":")
        n = evt[pos + 8]
        data = evt[pos + 9:pos + 9 + n]
        if pos + 9 + n >= len(evt):
            break
        rssi = struct.unpack("b", evt[pos + 9 + n:pos + 10 + n])[0]
        pos += 10 + n
        i = 0
        while i + 1 < len(data):
            length, typ = data[i], data[i + 1]
            if length == 0:
                break
            field = data[i + 2:i + 1 + length]
            if typ == 0xFF and field[:2] == COMPANY:
                out.append((addr, rssi, field[2:]))
            i += 1 + length
    return out


def random_address():
    """A non-resolvable private address: random, top two bits 00."""
    b = bytearray(os.urandom(6))
    b[5] &= 0x3F
    if b == bytearray(6) or b[:5] == b"\xff" * 5:
        b[0] ^= 1
    return bytes(b)


class BleRadio(Radio):
    def __init__(self, dev=0):
        super().__init__()
        self.dev = dev
        self.sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_RAW, socket.BTPROTO_HCI)
        try:
            fcntl.ioctl(self.sock.fileno(), HCIDEVUP, dev)
        except OSError as e:
            if e.errno != errno.EALREADY:
                raise
        self.sock.bind((dev,))
        # Only HCI event packets, all events
        self.sock.setsockopt(socket.SOL_HCI, socket.HCI_FILTER,
                             struct.pack("<IIIH", 1 << 4, 0xFFFFFFFF, 0xFFFFFFFF, 0))
        self.cmd_lock = threading.Lock()

    def cmd(self, ocf, params=b""):
        with self.cmd_lock:
            self.sock.send(struct.pack("<BHB", 0x01, ocf | (OGF_LE << 10), len(params)) + params)

    def start(self, on_packet):
        self.on_packet = on_packet
        self.cmd(LE_SET_SCAN_ENABLE, b"\x00\x00")
        # passive scan, interval = window = 30 ms, own address random, accept all
        self.cmd(LE_SET_SCAN_PARAMS, struct.pack("<BHHBB", 0x00, 0x0030, 0x0030, 0x01, 0x00))
        self.cmd(LE_SET_SCAN_ENABLE, b"\x01\x00")              # no duplicate filter
        self._advertise_with_new_address()
        threading.Thread(target=self._send, daemon=True, name="ble-tx").start()
        threading.Thread(target=self._receive, daemon=True, name="ble-rx").start()
        log.info("Bluetooth LE radio on hci%d", self.dev)

    def _advertise_with_new_address(self):
        self.cmd(LE_SET_ADV_ENABLE, b"\x00")
        self.cmd(LE_SET_RANDOM_ADDRESS, random_address())
        # 100 ms, ADV_NONCONN_IND, random own address, all three channels
        self.cmd(LE_SET_ADV_PARAMS, struct.pack("<HHBBB6sBB", 0x00A0, 0x00A0, 0x03, 0x01, 0x00,
                                                bytes(6), 0x07, 0x00))
        with self.lock:
            first = self.packets[0] if self.packets else None
        if first:
            self.cmd(LE_SET_ADV_DATA, ad_payload(first))
        self.cmd(LE_SET_ADV_ENABLE, b"\x01")

    def rotate_address(self):
        try:
            self._advertise_with_new_address()
        except OSError as e:
            log.warning("Could not rotate the Bluetooth address: %s", e)

    def _send(self):
        for pkt in self._cycle():
            if pkt:
                try:
                    self.cmd(LE_SET_ADV_DATA, ad_payload(pkt))
                except OSError as e:
                    log.warning("Bluetooth send failed: %s", e)
                    self.stop_evt.wait(5)
            self.stop_evt.wait(SLOT)

    def _receive(self):
        while not self.stop_evt.is_set():
            r, _, _ = select.select([self.sock], [], [], 1.0)
            if not r:
                continue
            try:
                pkt = self.sock.recv(300)
            except OSError as e:
                log.warning("Bluetooth receive failed: %s", e)
                self.stop_evt.wait(5)
                continue
            if pkt[:1] != b"\x04":
                continue
            for addr, rssi, payload in parse_reports(pkt[1:]):
                try:
                    self.on_packet(addr, rssi, payload)
                except Exception:
                    log.exception("Handling a packet failed")

    def stop(self):
        super().stop()
        try:
            self.cmd(LE_SET_ADV_ENABLE, b"\x00")
            self.cmd(LE_SET_SCAN_ENABLE, b"\x00\x00")
        except OSError:
            pass


def open_radio(kind, sim):
    """kind: "auto", "ble", "udp" or "off". Returns a radio or None."""
    if kind == "off":
        return None
    if kind == "udp" or (kind == "auto" and sim):
        try:
            return UdpRadio()
        except OSError as e:
            log.warning("Simulated radio unavailable: %s", e)
            return None
    if not hasattr(socket, "AF_BLUETOOTH"):
        log.warning("This Python has no Bluetooth support; social features are off")
        return None
    try:
        return BleRadio()
    except OSError as e:
        log.warning("Bluetooth is not available (%s); social features are off", e)
        return None
