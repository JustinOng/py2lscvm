import array
import logging

class Heap:
    # this class represents the heap
    # i will arbitrarily make use of the memory from working_offset
    # to allocate space for local variables in a function
    def __init__(self, size=0x1000, working_offset=0x00):
        self.heap = array.array('l', (0 for _ in range(size)))

        if size < working_offset:
            raise Exception("working area offset({}) is greater than size of the heap({}".format(working_offset, size))
        self.working_offset = working_offset

        self.allocated_func_len = 0
        self.allocated_func_space = []
        
        self.logger = logging.getLogger("Heap")
        self.logger.setLevel(logging.DEBUG)

        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter("[%(name)s] %(levelname)s - %(message)s"))
        self.logger.addHandler(ch)

    def write(self, addr, data):
        self.heap[addr] = data

    def read(self, addr):
        return self.heap[addr]

    def allocate_func(self, size):
        # allocate a chunk of data for a function
        # is released after the function returns
        # and the contents are not guaranteed,
        # so remember to initialise variables
        
        # track allocations by pushing (offset, size)
        self.allocated_func_space.append((self.working_offset + self.allocated_func_len, size))
        alloc_offset, alloc_size = self.allocated_func_space[-1]
        self.logger.info("Allocated size={} at offset={}".format(alloc_size, alloc_offset))
        self.allocated_func_len += size

        return alloc_offset

    def release_func(self):
        # this will release the latest function space allocated
        alloc_offset, alloc_size = self.allocated_func_space.pop()
        self.logger.info("Released size={} at offset={}".format(alloc_size, alloc_offset))
        self.allocated_func_len -= alloc_size
