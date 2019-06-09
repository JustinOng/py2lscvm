import ast
import logging
import collections
import opcodes as OPCODES
import helpers
from heap import Heap

# the constants declared here are to make some assumptions
# about the structure and layout of the program
# these can be adjusted if they are exceeded

# starts at 10 so that a JMP can be inserted
# before the functions to skip past it to
# main program execution
FUNCTION_OFFSET_START = 10
# allocate MAX_VARIABLES spaces at VARIABLE_OFFSET
# to hold globals, and args and local variables of a function
MAX_VARIABLES = 32
# offset on the heap at which to store variables
VARIABLE_OFFSET = 0

# allocate MAX_ARRAY spaces at ARRAY_OFFSET
# to hold the contents of arrays
MAX_ARRAY = 128
ARRAY_OFFSET = 32

class TranslationError(Exception):
    pass

# this error is thrown when some limit is exceeded
# and should be fixable by correcting some assumptions
# (the constants defined above)
class TranslationFail(TranslationError):
    pass

# this error is thrown when the compiler does not know
# how to translate the ast. should be fixable by actually
# implementing the translation code for the case
class TranslationUnknown(TranslationError):
    pass

class VariableCounter(ast.NodeVisitor):
    # this class serves to count the number of variables
    # used in childs of the node passed to it
    def __init__(self, tree):
        # key: name of variable
        # val: size (in words)
        self.variables = {}
        self.node_name = helpers.class_name(tree)

        self.visit(tree)
    
    def visit_FunctionDef(self, node):
        # pass so that it does not check inside function definitions
        # but will look into the function if visit is
        # explicitly called on a function
        if self.node_name == "FunctionDef":
            super().generic_visit(node)

    def visit_Assign(self, node):
        if helpers.class_name(node.value) == "List":
            self.variables[node.targets[0].id] = len(node.value.elts)
        elif helpers.class_name(node.targets[0]) != "Subscript":
            self.variables[node.targets[0].id] = 1

    def visit_AugAssign(self, node):
        self.variables[node.target.id] = 1

class Translator():
    def __init__(self):
        self.heap = Heap()

        # for self.globals, self.locals:
        # key: name of variable
        # val: heap offset
        self.globals = {}
        # list of args/local variables of a function
        # this will be cleared when done parsing a function
        self.locals = {}

        # list of arrays
        # key: name of array
        # val: {
        #   offset: heap offset
        #   size
        # }
        self.arrays = {}

        self.opcodes = ""

        # function table containing offsets at which 
        # functions can be found at, starting at 0
        # key: name of function
        # val: {
        #   opcodes,
        #   offset
        # }
        self.functions = collections.OrderedDict()
        # tracks total length of functions
        # to calculate future offsets
        self.funcs_len = FUNCTION_OFFSET_START

        self.logger = helpers.init_logger("TRANSLATOR")

    def translate(self, code):
        # translates code to lscvm

        tree = ast.parse(code)

        self.logger.info("Identifying globals...")
        counter = VariableCounter(tree)

        for global_var, size in counter.variables.items():
            # standard int
            if size == 1:
                self.alloc_global(global_var)
                self.logger.info("Global {} at heap[{}]".format(global_var, self.globals[global_var]))
            # array
            else:
                self.alloc_array(global_var, size)
                arr = self.arrays[global_var]
                self.logger.info("Array {} at heap[{}:{}]".format(global_var, arr["offset"], arr["offset"] + arr["size"] - 1))

        self.logger.info("Allocated {} global variables".format(len(self.globals)))

        self.logger.info("Looking for functions...")
        for node in ast.iter_child_nodes(tree):
            try:
                node_name = helpers.class_name(node)

                if node_name == "FunctionDef":
                    self.translate_function(node)
            except TranslationError as e:
                self.logger.error("Failed to translate function ({}) at line {}: {}".format(helpers.class_name(e), node.lineno, e))
                raise e
        
        if len(self.functions):
            self.logger.info("Concantenating functions...")
            total_func_length = sum([len(func["opcodes"]) for func in self.functions.values()])
            self.logger.info("Total function length: {}".format(total_func_length))

            jump_functions = helpers.num(total_func_length).ljust(FUNCTION_OFFSET_START - 1, " ") + OPCODES.GO
            if len(jump_functions) > FUNCTION_OFFSET_START:
                raise TranslationFail("JMP instruction too long. Increase FUNCTION_OFFSET_START")

            self.opcodes += jump_functions
        else:
            self.logger.info("No user defined functions, skipping function block")

        for func_name in self.functions:
            func = self.functions[func_name]
            self.opcodes += func["opcodes"]

        for node in ast.iter_child_nodes(tree):
            try:
                node_name = helpers.class_name(node)

                # silently skip "from stubs import *" because this is used
                # for testing scripts before compiling
                if node_name == "ImportFrom" and node.module == "stubs":
                    continue

                if node_name != "FunctionDef":
                    self.opcodes += self.translate_node(node)
            except TranslationError as e:
                self.logger.info(ast.dump(node))
                self.logger.error("Failed to translate at line {}: {}".format(node.lineno, e))
                raise e
            except Exception as e:
                self.logger.info(ast.dump(node))
                self.logger.error("Error parsing {}:".format(ast.dump(node)))
                raise e

        return self.opcodes

    def read_var(self, name):
        # return opcodes for retrieving value of variable "name"
        # tries to look in order: local variables, args, globals
        if name in self.locals.keys():
            offset = self.locals[name]
            return helpers.num(offset) + OPCODES.HEAP_READ
        elif name in self.globals.keys():
            # name is in local variable list, retrieve from heap
            offset = self.globals[name]
            return helpers.num(offset) + OPCODES.HEAP_READ
        else:
            raise TranslationError("Cannot read from unknown variable {}".format(name))

    def write_var(self, name):
        # writes to name (value to be written should already be on the stack)
        # tries write to locals first then globals
        # args are not writable because they're passed on the stack
        if name in self.locals.keys():
            offset = self.locals[name]
            return helpers.num(offset) + OPCODES.HEAP_WRITE
        elif name in self.globals.keys():
            offset = self.globals[name]
            return helpers.num(offset) + OPCODES.HEAP_WRITE
        else:
            raise TranslationError("Cannot write to unknown variable {}".format(name))
    
    def alloc_array(self, name, size):
        # allocate a space for `size` elements and returns the offset
        allocated = sum([array["size"] for array in self.arrays.values()])

        if allocated + size > MAX_ARRAY:
            raise TranslationFail("Cannot allocate array space. Increase MAX_ARRAY")
        
        self.arrays[name] = {
            "offset": ARRAY_OFFSET + allocated,
            "size": size
        }
    
    def alloc_global(self, name):
        # globals are stored starting at VARIABLE_OFFSET
        heap_offset = VARIABLE_OFFSET + len(self.globals)
        if heap_offset >= (VARIABLE_OFFSET + MAX_VARIABLES):
            raise TranslationFail("Failed to allocate global variable {}. Try increasing MAX_VARIABLES?".format(name))

        self.globals[name] = heap_offset

    def alloc_local(self, name):
        # args and locals are stored starting at
        # VARIABLE_OFFSET + len(self.globals)

        heap_offset = VARIABLE_OFFSET + len(self.globals) + len(self.locals)
        if heap_offset >= (VARIABLE_OFFSET + MAX_VARIABLES):
            raise TranslationFail("Failed to allocate local variable {}. Try increasing MAX_VARIABLES?".format(name))

        self.locals[name] = heap_offset

    def translate_nodes(self, nodes):
        opcodes = ""
        for node in nodes:
            opcodes += self.translate_node(node)

        return opcodes

    def translate_node(self, node):
        # translates a python node into a series of lscvm instructions

        opcode_change = ""

        node_name = helpers.class_name(node)
        if node_name == "Name":
            opcode_change += self.read_var(node.id)
        elif node_name == "Num":
            opcode_change += helpers.num(node.n)
        # a[1]
        elif node_name == "Subscript":
            # resolve array index position on the heap
            opcode_change += helpers.num(self.arrays[node.value.id]["offset"])
            opcode_change += self.translate_node(node.slice.value)
            opcode_change += OPCODES.STACK_ADD

            ctx_name = helpers.class_name(node.ctx)
            if ctx_name == "Store":
                opcode_change += OPCODES.HEAP_WRITE
            elif ctx_name == "Load":
                opcode_change += OPCODES.HEAP_READ
            else:
                self.logger.info(ast.dump(node))
                raise TranslationUnknown("Unknown Subscript.ctx {}".format(ctx_name))
        elif node_name == "BinOp":
            # load left value onto stack first, then right
            opcode_change += self.translate_node(node.left)
            opcode_change += self.translate_node(node.right)
            
            op_name = helpers.class_name(node.op)
            if op_name == "Add":
                opcode_change += OPCODES.STACK_ADD
            elif op_name == "Sub":
                opcode_change += OPCODES.STACK_SUBTRACT
            elif op_name == "Mult":
                opcode_change += OPCODES.STACK_MULTIPLY
            elif op_name == "Div":
                opcode_change += OPCODES.STACK_DIVIDE
            else:
                self.logger.info(ast.dump(node))
                raise TranslationUnknown("Missing handler for BinOp.op {}".format(op_name))
        elif node_name == "BoolOp":
            # load all the Compares onto the stack
            opcode_change += self.translate_nodes(node.values)

            op_name = helpers.class_name(node.op)
            if op_name == "And":
                # multiply all the conditions together
                # will result in 0 if any are 0
                opcode_change += OPCODES.STACK_MULTIPLY * (len(node.values) - 1)
            elif op_name == "Or":
                # add all the conditions together
                # will result in 1 if at least one is 1
                opcode_change += OPCODES.STACK_ADD * (len(node.values) - 1)
            else:
                self.logger.info(ast.dump(node))
                raise TranslationUnknown("Missing handler for BoolOp.op {}".format(op_name))
        elif node_name == "Assign":
            # sanity check: cannot assign to more than one variable at a time
            # should be simple to do though
            if len(node.targets) > 1:
                self.logger.info(ast.dump(node))
                raise TranslationUnknown("Cannot assign to more than one variable at a time")
            
            # this handles a = [1, 2, 3]
            if helpers.class_name(node.value) == "List":
                arr_name = node.targets[0].id
                if arr_name not in self.arrays:
                    raise TranslationFail("Tried to write to unknown array {}".format(arr_name))
                
                for i, val in enumerate(node.value.elts):
                    opcode_change += self.translate_node(val)
                    opcode_change += helpers.num(self.arrays[arr_name]["offset"] + i)
                    opcode_change += OPCODES.HEAP_WRITE
            elif helpers.class_name(node.targets[0]) == "Subscript":
                opcode_change += self.translate_node(node.value)
                opcode_change += self.translate_node(node.targets[0])
            else:
                # evaluate node.value and leave it on the stack
                opcode_change += self.translate_node(node.value)
                opcode_change += self.write_var(node.targets[0].id)
        elif node_name == "AugAssign":
            # a += b
            opcode_change += self.read_var(node.target.id)
            opcode_change += self.translate_node(node.value)
            
            op_name = helpers.class_name(node.op)
            if op_name == "Add":
                opcode_change += OPCODES.STACK_ADD
            elif op_name == "Sub":
                opcode_change += OPCODES.STACK_SUBTRACT
            elif op_name == "Mult":
                opcode_change += OPCODES.STACK_MULTIPLY
            elif op_name == "Div":
                opcode_change += OPCODES.STACK_DIVIDE
            else:
                self.logger.info(ast.dump(node))
                raise TranslationUnknown("Missing handler for AugAssign.op {}".format(op_name))
            
            opcode_change += self.write_var(node.target.id)
        elif node_name == "If":
            test = self.translate_node(node.test)
            body = self.translate_nodes(node.body)
            orelse = self.translate_nodes(node.orelse)

            body += helpers.num(len(orelse))
            body += OPCODES.GO

            opcode_change += test
            opcode_change += helpers.num(len(body))
            opcode_change += OPCODES.CONDITIONAL_JUMP
            opcode_change += body
            opcode_change += orelse
        elif node_name == "Compare":
            # compare will leave a 1 on the stack if true, else 0
            opcode_change += self.translate_node(node.left)

            if len(node.comparators) > 1:
                self.logger.info(ast.dump(node))
                raise TranslationUnknown("More than one comparator present")

            opcode_change += self.translate_node(node.comparators[0])

            if len(node.ops) > 1:
                self.logger.info(ast.dump(node))
                raise TranslationUnknown("More than one operator provided")
            
            op_name = helpers.class_name(node.ops[0])

            if op_name in ["NotEq"]:
                if op_name == "NotEq":
                    opcode_change += OPCODES.STACK_COMPARE
                    # 1 or -1 on stack if true
                    # changes 0 to 0, non zero to 1
                    opcode_change += OPCODES.STACK_3 + OPCODES.CONDITIONAL_JUMP # if 0, jump to STACK_1
                    opcode_change += OPCODES.STACK_1
                    opcode_change += OPCODES.STACK_1 + OPCODES.GO # then skip past the next instruction
                    opcode_change += OPCODES.STACK_0
            elif op_name in ["Eq", "Gt", "Lt"]:
                # the blocks here are responsible for leaving
                # a 0 on the stack if true
                if op_name == "Eq":
                    opcode_change += OPCODES.STACK_COMPARE
                elif op_name == "Gt":
                    opcode_change += OPCODES.STACK_COMPARE
                    # should be a 1 on the stack if true
                    opcode_change += OPCODES.STACK_1 + OPCODES.STACK_SUBTRACT # subtract 1 so becomes 0
                elif op_name == "Lt":
                    opcode_change += OPCODES.STACK_COMPARE
                    # should be a -1 on the stack if true
                    opcode_change += OPCODES.STACK_1 + OPCODES.STACK_ADD # add 1 so becomes 0

                # this changes 0 to 1, and non zero to 0
                opcode_change += OPCODES.STACK_3 + OPCODES.CONDITIONAL_JUMP # if 0, jump to STACK_1
                opcode_change += OPCODES.STACK_0              # here because not zero so add a zero
                opcode_change += OPCODES.STACK_1 + OPCODES.GO # then skip past the next instruction
                opcode_change += OPCODES.STACK_1
            elif op_name in ["GtE", "LtE"]:
                if op_name == "GtE":
                    # need to return 1 if the compare result is 1 or 0
                    # so test twice
                    opcode_change += OPCODES.STACK_COMPARE
                    opcode_change += OPCODES.STACK_0 + OPCODES.STACK_FIND # copy the compare result
                    opcode_change += OPCODES.STACK_1 + OPCODES.STACK_SUBTRACT # subtract 1 so become 0
                elif op_name == "LtE":
                    opcode_change += OPCODES.STACK_COMPARE
                    opcode_change += OPCODES.STACK_0 + OPCODES.STACK_FIND # copy the compare result
                    opcode_change += OPCODES.STACK_1 + OPCODES.STACK_ADD # add 1 so become 0
                
                # this tests the top two values on the stack and
                # returns 1 if either of them are 0
                opcode_change += OPCODES.STACK_5 + OPCODES.CONDITIONAL_JUMP # if gt, jump to STACK_DROP
                opcode_change += OPCODES.STACK_4 + OPCODES.CONDITIONAL_JUMP # if =, jump to STACK_1
                opcode_change += OPCODES.STACK_0          # add a zero as the return value
                opcode_change += OPCODES.STACK_2 + OPCODES.GO # skip next 2 instructions
                opcode_change += OPCODES.STACK_DROP       # destroy that extra value that we cloned since we never compared =
                opcode_change += OPCODES.STACK_1
            else:
                self.logger.info(ast.dump(node))
                raise TranslationUnknown("Missing handler for operator {}".format(op_name))
        elif node_name == "Call":
            if helpers.class_name(node.func) != "Name":
                raise TranslationUnknown("Calling functions this way is not supported")

            func_name = node.func.id
            if func_name not in ["putchar", "putint", "puts"] and func_name not in self.functions:
                raise TranslationError("Tried to call undefined function {}".format(func_name))

            for arg in node.args:
                opcode_change += self.translate_node(arg)

            if func_name in ["putchar", "putint", "puts"]:
                if func_name == "putchar":
                    opcode_change += OPCODES.PRINT_ASCII
                elif func_name == "putint":
                    opcode_change += OPCODES.PRINT_NUM
                elif func_name == "puts":
                    pass
            else:
                opcode_change += helpers.num(self.functions[func_name]["offset"])
                opcode_change += OPCODES.CALL
        elif node_name == "While":
            if node.orelse:
                self.logger.info(ast.dump(node))
                raise TranslationUnknown("Handling of While.orelse is not implemented")
            # build something like:
            # 1: [load -len(everything below)]
            # 2: [copy previous value] (this is so that i can calculate len(everything below)
            #                             without including the length of the actual pushing)
            # 3: [compare]
            # 4: [load len(everything below)]
            # 5: JZ
            # 6: [body]
            # 7: JMP (this jumps using -len(everything below) loaded at the start)

            # 5 to 7
            body = OPCODES.CONDITIONAL_JUMP + self.translate_nodes(node.body) + OPCODES.GO
            # 2 to 7
            opcode_change = OPCODES.STACK_0 + OPCODES.STACK_FIND
            opcode_change += self.translate_node(node.test) + helpers.num(len(body) - 1) + body
            # 1 to 7
            opcode_change = helpers.num(-len(opcode_change)) + opcode_change

            # remove the two extra jump lengths left on the stack
            opcode_change += OPCODES.STACK_DROP * 2
        elif node_name == "Expr":
            opcode_change += self.translate_node(node.value)
        elif node_name == "Return":
            opcode_change += self.translate_node(node.value)
        else:
            raise TranslationUnknown("Missing handler for node type {}: {}".format(node_name, ast.dump(node)))
        
        self.logger.debug("{}: {}".format(ast.dump(node), opcode_change))
        return opcode_change

    def translate_function(self, node):
        # builds a function from a ast node
        opcodes = ""

        func_name = node.name
        self.functions[func_name] = {
            "offset": self.funcs_len
        }

        # load name of args
        args = []
        for arg in node.args.args:
            args.append(arg.arg)
            self.alloc_local(arg.arg)
            self.logger.info("Arg {} at heap[{}]".format(arg.arg, self.locals[arg.arg]))
        
        # transfer value of args from the stack to the heap
        for arg in args[::-1]:
            opcodes += helpers.num(self.locals[arg])
            opcodes += OPCODES.HEAP_WRITE

        self.logger.info("Building function {} with args {}".format(func_name, ", ".join(args)))
        self.logger.debug(ast.dump(node))
        
        # scan through to identify all the variables
        # that are assigned to
        counter = VariableCounter(node)

        # store the heap address for local vars
        for local_var, size in counter.variables.items():
            # check if the variable is actually an argument
            if local_var in args:
                continue
            
            if size > 1:
                raise TranslationUnknown("Arrays should be declared globally, not inside a function")
            
            self.alloc_local(local_var)
            self.logger.info("Local {} at heap[{}]".format(local_var, self.locals[local_var]))

        self.logger.info("Variables used: {}".format(["{} at heap[{}]".format(k, v) for k, v in self.locals.items()]))

        # handle the actual code in the function
        opcodes += self.translate_nodes(node.body)

        opcodes += OPCODES.RETURN

        # remember to destroy variables on the stack if any extra are left

        self.locals.clear()

        self.functions[func_name]["opcodes"] = opcodes
        self.funcs_len += len(opcodes)
