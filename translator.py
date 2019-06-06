import ast
import logging
import collections
import opcodes as OPCODES
import helpers
from heap import Heap

# starts at 10 so that a JMP can be inserted
# before the functions to skip past it to
# main program execution
FUNCTION_OFFSET_START = 10

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

        # key: name of global/local variable
        # val: heap offset
        self.globals = {}
        self.locals = {}

        # list of args passed to function
        # this will be cleared when done parsing a function
        self.args = []

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
            node_name = helpers.class_name(node)
            if node_name == "FunctionDef":
                self.translate_function(node)
        
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
            node_name = helpers.class_name(node)
            if node_name != "FunctionDef":
                self.opcodes += self.translate_node(node)

        return self.opcodes

    def read_var(self, name):
        # return opcodes for retrieving value of variable "name"
        # tries to look in order: local variables, args, globals
        if name in self.locals.keys():
            offset = self.locals[name]
            return helpers.num(offset) + OPCODES.HEAP_READ
        elif name in self.args:
            # name is in args, retrieve from back of stack
            # offset from end of stack
            offset = len(self.args) - self.args.index(name)
            return helpers.num(offset) + OPCODES.STACK_FIND
        elif name in self.globals.keys():
            # name is in local variable list, retrieve from heap
            offset = self.globals[name]
            return helpers.num(offset) + OPCODES.HEAP_READ
        else:
            raise Exception("Cannot read from unknown variable {}".format(name))

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
            raise Exception("Cannot write to unknown variable {}".format(name))

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
                raise Exception("Cannot assign to more than one variable at a time")
            
            # evaluate node.value and leave it on the stack
            opcode_change += self.translate_node(node.value)

            opcode_change += self.write_var(node.targets[0].id)
        elif node_name == "Call":
            if node.func.id not in self.functions:
                raise Exception("Tried to call undefined function {}".format(node.func.id))

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
            self.logger.warning("Missing handler for node type {}".format(node_name))
            return ""
        
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
        for arg in node.args.args:
            self.args.append(arg.arg)

        self.logger.info("Building function {} with args {}".format(func_name, ",".join(self.args)))
        self.logger.debug(ast.dump(node))
        
        # scan through to identify all the variables
        # that are assigned to
        counter = VariableCounter()
        counter.visit(node)

        # allocate space on the heap for each of the local vars
        var_offset = self.heap.allocate_func(len(counter.variables))

        # store the heap address for local vars
        for i, var in enumerate(counter.variables):
            self.locals[var] = var_offset + i

        self.logger.info("Variables used: {}".format(["{} at heap[{}]".format(k, v) for k, v in self.locals.items()]))

        # handle the actual code in the function
        for node in node.body:
            opcodes += self.translate_node(node)

        opcodes += OPCODES.RETURN

        # remember to destroy variables on the stack if any extra are left

        self.args.clear()
        self.locals.clear()

        self.heap.release_func()

        self.functions[func_name]["opcodes"] = opcodes
        self.funcs_len += len(opcodes)
