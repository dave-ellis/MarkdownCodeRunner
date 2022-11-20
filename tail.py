import os


class CyclicBuffer:
    def __init__(self, maximum):
        self.maximum = maximum
        self.size = 0
        self.position = 0
        self.list = [None] * maximum

    def add(self, line):
        self.list[self.position] = line
        if self.size < self.maximum:
            self.size += 1
        self.position = (self.position + 1) % self.maximum

    def text(self):
        text = ""

        if self.size > 0:
            start = self.position % self.maximum
            for i in range(self.size):
                position = (start + i) % self.size
                text += self.list[position] + os.linesep

        return text.strip()
