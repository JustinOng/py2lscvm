import logging
from math import sqrt
from functools import reduce

def num(i):
    opcodes = ""

    if i <= 9:
        return chr(0x61 + i)
    
    # if less than 18, can be built with sum(9+(i-9))
    if i <= 18:
        opcodes += chr(0x61 + 9)
        opcodes += chr(0x61 + (i - 9))
        opcodes += "A"
        return opcodes

    first_opcode = True
    for factor in compress_factors(factorise(i)):
        if factor <= 9:
            opcodes += chr(0x61 + factor)
        else:
            if factor <= 18:
                opcodes += num(factor)
            else:
                # still cannot resolve, subtract 1 and try again
                opcodes += chr(0x61 + 1)
                opcodes += num(factor - 1)
                opcodes += "A"

        if not first_opcode:
            opcodes += "M"
        
        first_opcode = False
    
    return opcodes

def compress_factors(factors):
    # given factors like [2,2,3], return [4, 3]

    temp = []
    out = []
    for factor in factors:
        mult_temp = reduce(lambda x, y: x*y, temp) if temp else 1
        if (mult_temp * factor) > 9:
            out.append(mult_temp)
            temp.clear()

        temp.append(factor)
    
    if temp:
        mult_temp = reduce(lambda x, y: x*y, temp)
        if mult_temp <= 9:
            out.append(mult_temp)
            temp.clear()

    return out + temp

# https://stackoverflow.com/a/16060180
def factorise(n):    # (cf. https://stackoverflow.com/a/15703327/849891)
    j = 2
    while n > 1:
        for i in range(j, int(sqrt(n+0.05)) + 1):
            if n % i == 0:
                n /= i ; j = i
                yield i
                break
        else:
            if n > 1:
                yield int(n); break

def class_name(instance):
    return type(instance).__name__

def init_logger(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("[%(name)s] %(levelname)s - %(message)s"))
    logger.addHandler(ch)

    return logger
