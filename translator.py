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
# allocate MAX_FUNCTION_VARIABLES spaces at VARIABLE_OFFSET
# to hold arguments and local variables of a function
MAX_FUNCTION_VARIABLES = 10
# offset on the heap at which to store
# args and local variables
VARIABLE_OFFSET = 0

class TranslationError(Exception):
    def __init__(self, message):
        super().__init__(message)

class VariableCounter(ast.NodeVisitor):
    # this class serves to count the number of variables
    # used in childs of the node passed to it
    def __init__(self):
        self.variables = set()

    def visit_Assign(self, node):
        self.variables.update([a.id for a in node.targets])

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
        self.logger.info("Looking for functions...")
        for node in ast.iter_child_nodes(tree):
            try:
                node_name = helpers.class_name(node)
                if node_name == "FunctionDef":
                    self.translate_function(node)
            except TranslationError as e:
                self.logger.error("Failed to translate function at line {}: {}".format(node.lineno, e))
                return
        
        self.logger.info("Concantenating functions...")
        total_func_length = sum([len(func["opcodes"]) for func in self.functions.values()])
        self.logger.info("Total function length: {}".format(total_func_length))

        jump_functions = helpers.num(total_func_length).ljust(FUNCTION_OFFSET_START - 1, " ") + OPCODES.GO
        if len(jump_functions) > FUNCTION_OFFSET_START:
            raise Exception("JMP instruction too long. Increase FUNCTION_OFFSET_START")

        self.opcodes += jump_functions

        for func_name in self.functions:
            func = self.functions[func_name]
            self.opcodes += func["opcodes"]

        for node in ast.iter_child_nodes(tree):
            try:
                node_name = helpers.class_name(node)
                if node_name != "FunctionDef":
                    self.opcodes += self.translate_node(node)
            except TranslationError as e:
                self.logger.error("Failed to translate at line {}: {}".format(node.lineno, e))
                return

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

    def translate_node(self, node):
        # translates a python node into a series of lscvm instructions

        opcode_change = ""

        node_name = helpers.class_name(node)
        if node_name == "Name":
            opcode_change += self.read_var(node.id)
        elif node_name == "Num":
            opcode_change += helpers.num(node.n)
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
                self.logger.warning("Missing handler for BinOp.op {}".format(op_name))
        elif node_name == "Assign":
            # sanity check: cannot assign to more than one variable at a time
            # should be simple to do though
            if len(node.targets) > 1:
                raise TranslationError("Cannot assign to more than one variable at a time")
            
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
                self.logger.warning("Missing handler for AugAssign.op {}".format(op_name))
            
            opcode_change += self.write_var(node.target.id)
        elif node_name == "Call":
            if node.func.id not in self.functions:
                raise TranslationError("Tried to call undefined function {}".format(node.func.id))

            for arg in node.args:
                opcode_change += self.translate_node(arg)
            
            # - 1 from the offset because ip is incremented after the jump instruction
            opcode_change += helpers.num(self.functions[node.func.id]["offset"] - 1)
            opcode_change += OPCODES.CALL
        elif node_name == "Expr":
            opcode_change += self.translate_node(node.value)
        elif node_name == "Return":
            opcode_change += self.translate_node(node.value)
        else:
            self.logger.warning("Missing handler for node type {}: {}".format(node_name, ast.dump(node)))
            return ""
        
        self.logger.debug("{}: {}".format(ast.dump(node), opcode_change))
        return opcode_change

    def translate_function(self, node):
        # builds a function from a ast node
        opcodes = ""

        # tracks number of variables in the function
        # this includes both arguments and local variables
        variable_offset = VARIABLE_OFFSET

        func_name = node.name
        self.functions[func_name] = {
            "offset": self.funcs_len
        }

        # load name of args
        args = []
        for arg in node.args.args:
            self.locals[arg.arg] = variable_offset
            args.append(arg.arg)
            variable_offset += 1
        
        # transfer value of args from the stack to the heap
        for arg in args[::-1]:
            opcodes += helpers.num(self.locals[arg])
            opcodes += OPCODES.HEAP_WRITE

        self.logger.info("Building function {} with args {}".format(func_name, ", ".join(args)))
        self.logger.debug(ast.dump(node))
        
        # scan through to identify all the variables
        # that are assigned to
        counter = VariableCounter()
        counter.visit(node)

        # store the heap address for local vars
        for local_var in counter.variables:
            # check if the variable is actually an argument
            if local_var in args:
                continue
            
            self.locals[local_var] = variable_offset
            variable_offset += 1

        self.logger.info("Variables used: {}".format(["{} at heap[{}]".format(k, v) for k, v in self.locals.items()]))

        # handle the actual code in the function
        for node in node.body:
            opcodes += self.translate_node(node)

        opcodes += OPCODES.RETURN

        # remember to destroy variables on the stack if any extra are left

        self.locals.clear()

        self.functions[func_name]["opcodes"] = opcodes
        self.funcs_len += len(opcodes)
