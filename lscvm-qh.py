from translator import Translator

# the length of source compiled to lscvm
# lucky guess to find 232, should be possible to bruteforce
COMPILED_CODE_LENGTH = 232

source = """data_len = {}
i = 0
while i < data_len:
    num = stack_find(1 + data_len - i)
    first = 1
    while num > 0:
        if num > 9:
            putchar(0x6A)
            num -= 9
        else:
            putchar(0x61 + num)
            num = 0

        if first == 0:
            putchar(0x41)
        
        first = 0
    i += 1

i = 0
while i < data_len:
    num = stack_find(1 + data_len - i)
    putchar(0x40 + num)
    i += 1"""

def naive_num(num):
    opcodes = ""

    first = 1
    while num > 0:
        if num > 9:
            opcodes += "j"
            num -= 9
        else:
            opcodes += chr(0x61 + num)
            num = 0
        
        if first == 0:
            opcodes += "A"
        
        first = 0

    return opcodes

t = Translator()
code = t.translate(source.format(COMPILED_CODE_LENGTH))
print("Compiled length: {}".format(len(code)))
assert COMPILED_CODE_LENGTH == len(code)

data_block = ""
for c in code:
    opcodes = naive_num(ord(c) - 0x40)
    data_block += opcodes

print(data_block + code)
