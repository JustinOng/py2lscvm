NOP = " "
CALL = "C"
RETURN = "R"
GO = "G"
CONDITIONAL_JUMP = "Z"
EXIT = "B"
PRINT_NUM = "I"
PRINT_ASCII = "P"
HEAP_READ = "E"
HEAP_WRITE = "K"
STACK_FIND = "F"
STACK_FIND_REMOVE = "H"
STACK_COMPARE = "J"
STACK_DROP = "D"
STACK_ADD = "A"
STACK_SUBTRACT = "S"
STACK_MULTIPLY = "M"
STACK_DIVIDE = "V"
STACK_0 = "a"
STACK_1 = "b"
STACK_2 = "c"
STACK_3 = "d"
STACK_4 = "e"
STACK_5 = "f"
STACK_6 = "g"
STACK_7 = "h"
STACK_8 = "i"
STACK_9 = "j"

stack_effect = {
    NOP: 0,
    CALL: -1, # pops address to jump to
    RETURN: 0,
    GO: -1,   # pops number to increment ip by
    CONDITIONAL_JUMP: -2, # pops address and condition
    EXIT: 0,
    PRINT_NUM: -1,
    PRINT_ASCII: -1,
    HEAP_READ: 0, # pops address then pushes back value
    HEAP_WRITE: -2, # pops address and value
    STACK_FIND: 0, # pops address then pushes back value
    STACK_FIND_REMOVE: -1, # pops address
    STACK_COMPARE: -1, # pops two values and pushes back compare result
    STACK_DROP: -1,
    STACK_ADD: -1,
    STACK_SUBTRACT: -1,
    STACK_MULTIPLY: -1,
    STACK_DIVIDE: -1,
    STACK_0: 1,
    STACK_1: 1,
    STACK_2: 1,
    STACK_3: 1,
    STACK_4: 1,
    STACK_5: 1,
    STACK_6: 1,
    STACK_7: 1,
    STACK_8: 1,
    STACK_9: 1
}
