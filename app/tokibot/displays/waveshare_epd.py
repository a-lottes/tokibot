"""Wrappers around the Waveshare e-paper drivers, all with show(img, full) and close().

The painter draws 250 × 122. Panels of that size get the picture as is, larger ones
get it centred on a white canvas. PARTIAL = False marks panels without a partial
refresh: every update is a full one, so the renderer draws them less often.
"""
from PIL import Image


class _Epaper:
    SIZE = (250, 122)           # the panel in landscape
    PARTIAL = True
    MIN_INTERVAL = 0.0          # seconds between updates, on top of the renderer's own

    def __init__(self, rotate):
        self.rotate = rotate
        self.epd = self.open()

    def fit(self, img):
        if self.rotate:
            img = img.rotate(self.rotate)
        if img.size != self.SIZE:
            canvas = Image.new("1", self.SIZE, 255)
            canvas.paste(img, ((self.SIZE[0] - img.width) // 2, (self.SIZE[1] - img.height) // 2))
            img = canvas
        return img

    def buffer(self, img):
        return self.epd.getbuffer(self.fit(img))

    def close(self):
        self.epd.sleep()


class Waveshare2in13V1(_Epaper):
    """2.13" V1 (250 × 122): the partial look-up table stays loaded between updates."""

    def open(self):
        from .waveshare import epd2in13
        epd = epd2in13.EPD()
        epd.init(epd.lut_full_update)
        epd.Clear(0xFF)
        epd.init(epd.lut_partial_update)
        return epd

    def show(self, img, full):
        buf = self.buffer(img)
        if full:
            self.epd.init(self.epd.lut_full_update)
            self.epd.display(buf)
            self.epd.init(self.epd.lut_partial_update)
        else:
            self.epd.display(buf)


class Waveshare2in13V2(_Epaper):
    """2.13" V2 (250 × 122)."""

    def open(self):
        from .waveshare import epd2in13_V2
        epd = epd2in13_V2.EPD()
        epd.init(epd.FULL_UPDATE)
        epd.Clear(0xFF)
        return epd

    def show(self, img, full):
        buf = self.buffer(img)
        if full:
            self.epd.init(self.epd.FULL_UPDATE)
            self.epd.displayPartBaseImage(buf)   # full refresh, sets the base for partial updates
            self.epd.init(self.epd.PART_UPDATE)
        else:
            self.epd.displayPartial(buf)


class Waveshare2in13V4(_Epaper):
    """2.13" V4 (250 × 122)."""

    def open(self):
        from .waveshare import epd2in13_V4
        return self.start(epd2in13_V4.EPD())

    def start(self, epd):
        epd.init()
        epd.Clear(0xFF)
        return epd

    def show(self, img, full):
        buf = self.buffer(img)
        if full:
            self.epd.init()
            self.epd.displayPartBaseImage(buf)   # full refresh, sets the base for partial updates
        else:
            self.epd.displayPartial(buf)


class Waveshare2in13V3(Waveshare2in13V4):
    """2.13" V3 (250 × 122): same commands as the V4."""

    def open(self):
        from .waveshare import epd2in13_V3
        return self.start(epd2in13_V3.EPD())


class Waveshare2in13bV4(_Epaper):
    """2.13" B V4 (250 × 122, black, white and red). Only full refreshes, about 15 s each;
    the critter is drawn in black only."""

    PARTIAL = False
    MIN_INTERVAL = 60.0

    def open(self):
        from .waveshare import epd2in13b_V4
        epd = epd2in13b_V4.EPD()
        epd.init()
        epd.Clear()
        self.no_red = epd.getbuffer(Image.new("1", self.SIZE, 255))
        return epd

    def show(self, img, full):
        self.epd.init()                          # wakes it up again after a long pause
        self.epd.display(self.buffer(img), self.no_red)


class Waveshare2in7V1(_Epaper):
    """2.7" V1 (264 × 176). Only full refreshes."""

    SIZE = (264, 176)
    PARTIAL = False
    MIN_INTERVAL = 20.0

    def open(self):
        from .waveshare import epd2in7
        epd = epd2in7.EPD()
        epd.init()
        epd.Clear(0xFF)
        return epd

    def show(self, img, full):
        self.epd.display(self.buffer(img))


class Waveshare2in7V2(_Epaper):
    """2.7" V2 (264 × 176) with partial refresh."""

    SIZE = (264, 176)

    def open(self):
        from .waveshare import epd2in7_V2
        epd = epd2in7_V2.EPD()
        epd.init()
        epd.Clear()
        return epd

    def show(self, img, full):
        buf = self.buffer(img)
        if full:
            self.epd.init()
            self.epd.display_Base(buf)           # full refresh, sets the base for partial updates
        else:
            self.epd.display_Partial(buf, 0, 0, self.epd.width, self.epd.height)
