"""Schlanke Hardware-Schicht für die Waveshare-Treiber.

Ersetzt Waveshares epdconfig.py (das gpiozero bzw. Jetson-/Sunrise-Code mitbringt)
durch das Nötigste für den Raspberry Pi: spidev für SPI, RPi.GPIO für die Pins.
Die Funktionsnamen entsprechen dem Original, damit epd2in13_V4.py unverändert bleibt.
"""
import time

RST_PIN = 17
DC_PIN = 25
CS_PIN = 8          # wird von spidev selbst bedient
BUSY_PIN = 24
PWR_PIN = 18

_spi = None
_gpio = None


def digital_write(pin, value):
    if pin == CS_PIN:
        return
    _gpio.output(pin, 1 if value else 0)


def digital_read(pin):
    return _gpio.input(pin)


def delay_ms(ms):
    time.sleep(ms / 1000.0)


def spi_writebyte(data):
    _spi.writebytes(data)


def spi_writebyte2(data):
    _spi.writebytes2(data)


def module_init(cleanup=False):
    global _spi, _gpio
    import RPi.GPIO as GPIO
    import spidev
    _gpio = GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(RST_PIN, GPIO.OUT)
    GPIO.setup(DC_PIN, GPIO.OUT)
    GPIO.setup(PWR_PIN, GPIO.OUT)
    GPIO.setup(BUSY_PIN, GPIO.IN, pull_up_down=GPIO.PUD_OFF)
    GPIO.output(PWR_PIN, 1)
    if _spi is None:
        _spi = spidev.SpiDev()
        _spi.open(0, 0)
        _spi.max_speed_hz = 4000000
        _spi.mode = 0b00
    return 0


def module_exit(cleanup=False):
    global _spi
    if _spi is not None:
        _spi.close()
        _spi = None
    if _gpio is not None:
        _gpio.output(RST_PIN, 0)
        _gpio.output(DC_PIN, 0)
        _gpio.output(PWR_PIN, 0)
        _gpio.cleanup([RST_PIN, DC_PIN, PWR_PIN, BUSY_PIN])
