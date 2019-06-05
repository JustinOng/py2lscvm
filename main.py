import logging
import ast
import helpers
import opcodes
from heap import Heap

def class_name(instance):
    return type(instance).__name__

class VariableCounter(ast.NodeVisitor):
    # this class serves to count the number of variables
    # used in childs of the node passed to it
    def __init__(self):
        self.variables = set()

    def visit_Assign(self, node):
        self.variables.add(node.targets[0].id)

class Function():
    def __init__(self, heap):
        self.heap = heap

        self.name = False
        self.args = []
        # key: name of local variable
        # val: heap offset
        self.variables = {}

        self.opcodes = ""
        
        self.logger = logging.getLogger("Function")
        self.logger.setLevel(logging.DEBUG)

        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter("[%(name)s] %(levelname)s - %(message)s"))
        self.logger.addHandler(ch)
    
    def read_var(self, name):
        # return opcodes for retrieving value of variable "name"
        if name in self.args:
            # name is in args, retrieve from back of stack
            # offset from end of stack
            offset = len(self.args) - self.args.index(name)
            return helpers.num(offset) + opcodes.STACK_FIND
        elif name in self.variables.keys():
            # name is in local variable list, retrieve from heap
            offset = self.variables[name]
            return helpers.num(offset) + opcodes.HEAP_READ
        else:
            raise Exception("Cannot locate variable {}".format(name))

    def build_from(self, node):
        # builds a function from a ast node
        print(ast.dump(node))
        self.name = node.name

        # load name of args
        for arg in node.args.args:
            self.args.append(arg.arg)

        self.logger.info("Building function {} with args {}".format(self.name, self.args))
        
        # scan through to identify all the variables
        # that are assigned to
        counter = VariableCounter()
        counter.visit(node)

        # allocate space on the heap for each of the local vars
        var_offset = self.heap.allocate_func(len(counter.variables))

        # store the heap address for local vars
        for i, var in enumerate(counter.variables):
            self.variables[var] = var_offset + i

        self.logger.info("Variables used: {}".format(["{} at heap[{}]".format(k, v) for k, v in self.variables.items()]))

        # handle the actual code in the function
        for node in node.body:
            node_name = class_name(node)

            opcode_change = ""
            if node_name == "Assign":
                # sanity check: cannot assign to function parameters
                # because there is no stack write opcode
                var_name = node.targets[0].id
                if var_name in self.args:
                    raise Exception("Cannot assign to {}: function parameters are immutable".format(var_name))

                # sanity check: cannot assign to more than one variable at a time
                # should be simple to do though
                if len(node.targets) > 1:
                    raise Exception("Cannot assign to more than one variable at a time")
                
                # evaluate node.value and leave it on the stack
                value = node.value
                value_name = class_name(value)
                if value_name == "BinOp":
                    # load left value onto stack first
                    opcode_change += self.read_var(value.left.id)

                    # load right value onto stack
                    # RHS can be a variable or num
                    value_right_name = class_name(value.right)
                    if value_right_name == "Name":
                        opcode_change += self.read_var(value.right.id)
                    elif value_right_name == "Num":
                        opcode_change += helpers.num(value.right.n)
                    else:
                        self.logger.warning("Missing handler for BinOp.right {}".format(value_right_name))
                    
                    op_name = class_name(value.op)
                    if op_name == "Add":
                        opcode_change += opcodes.STACK_ADD
                    elif op_name == "Mult":
                        opcode_change += opcodes.STACK_MULTIPLY
                    else:
                        self.logger.warning("Missing handler for op {}".format(op_name))
                else:
                    self.logger.warning("Missing handler for value {}".format(value_name))
                
                # load the value into the local variable
                opcode_change += helpers.num(self.variables[node.targets[0].id])
                opcode_change += opcodes.HEAP_WRITE
            else:
                self.logger.warning("Missing handler for node {}".format(node_name))
            
            self.logger.debug("{}: {}".format(ast.dump(node), opcode_change))
            self.opcodes += opcode_change

        # at the end, destroy the variables on the stack
        # that were used as arguments for the function
        # then push the return value (if applicable)

        self.heap.release_func()


class Transpiler(ast.NodeVisitor):
    def __init__(self):
        self.opcodes = ""
        self.heap = Heap()

    def visit_FunctionDef(self, node):
        #logger.info("Visiting FunctionDef")
        function = Function(self.heap)
        function.build_from(node)

    def generic_visit(self, node):
        #print(class_name(node))
        #print(list(ast.iter_fields(node)))
        super().generic_visit(node)

def main():
    tree = ast.parse("""
#def foo(a, b):
#  return a + b

def bar(a, b):
    c = a + b
    d = c * 2
    return d

k = 1
while k < 5:
  foo(k, 5)
    """)
    #print(ast.dump(tree))
    Transpiler().visit(tree)

main()
