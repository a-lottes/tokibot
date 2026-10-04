class SimDisplay:
    """Ohne Hardware: speichert jedes Bild als PNG (zum Testen am Mac/PC)."""

    def __init__(self, path):
        self.path = path

    def show(self, img, full):
        if self.path:
            img.save(self.path)

    def close(self):
        pass
