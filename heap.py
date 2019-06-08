import array
import logging
import helpers

class Heap:
    # this class represents the heap
    def __init__(self, size=0x1000):
        self.heap = array.array('l', (0 for _ in range(size)))
        self.logger = helpers.init_logger("HEAP")

    def write(self, addr, data):
        self.heap[addr] = data

    def read(self, addr):
        return self.heap[addr]
