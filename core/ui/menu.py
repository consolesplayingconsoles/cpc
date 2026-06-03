class Menu:
    def __init__(self, items: list):
        self.items  = items
        self.cursor = 0

    def up(self):
        self.cursor = (self.cursor - 1) % len(self.items)

    def down(self):
        self.cursor = (self.cursor + 1) % len(self.items)

    @property
    def selected(self) -> str:
        return self.items[self.cursor]
