class Waveshare2in13V4:
    """Waveshare 2.13" V4 (250 × 122) with partial refresh."""

    SIZE = (250, 122)

    def __init__(self, rotate):
        from .waveshare import epd2in13_V4
        self.rotate = rotate
        self.epd = epd2in13_V4.EPD()
        self.epd.init()
        self.epd.Clear(0xFF)

    def show(self, img, full):
        if self.rotate:
            img = img.rotate(self.rotate)
        buf = self.epd.getbuffer(img)
        if full:
            self.epd.init()
            self.epd.displayPartBaseImage(buf)   # full refresh, sets the base for partial updates
        else:
            self.epd.displayPartial(buf)

    def close(self):
        self.epd.sleep()
