class SimDisplay:
    """No hardware: optionally saves every frame as a PNG (for testing on a Mac/PC)."""

    def __init__(self, path):
        self.path = path

    def show(self, img, full):
        if self.path:
            img.save(self.path)

    def close(self):
        pass
