import ast
import logging
import opcodes
import helpers

class TranslatorBase():
    def __init__(self, heap):
        self.heap = heap

        # key: name of local variable
        # val: heap offset
        self.variables = {}

        self.opcodes = ""

        self.logger = helpers.init_logger("TRANS_BASE")

    def read_var(self, name):
        # return opcodes for retrieving value of variable "name"
        if name in self.variables.keys():
            # name is in local variable list, retrieve from heap
            offset = self.variables[name]
            return helpers.num(offset) + opcodes.HEAP_READ
        else:
            raise Exception("Cannot locate variable {}".format(name))
    
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
                opcode_change += opcodes.STACK_ADD
            elif op_name == "Sub":
                opcode_change += opcodes.STACK_SUBTRACT
            elif op_name == "Mult":
                opcode_change += opcodes.STACK_MULTIPLY
            elif op_name == "Div":
                opcode_change += opcodes.STACK_DIVIDE
            else:
                self.logger.warning("Missing handler for BinOp.op {}".format(op_name))
        elif node_name == "Assign":
            # sanity check: cannot assign to more than one variable at a time
            # should be simple to do though
            if len(node.targets) > 1:
                raise Exception("Cannot assign to more than one variable at a time")
            
            # evaluate node.value and leave it on the stack
            opcode_change += self.translate_node(node.value)
            
            # load the value into the local variable
            opcode_change += helpers.num(self.variables[node.targets[0].id])
            opcode_change += opcodes.HEAP_WRITE
        elif node_name == "Return":
            opcode_change += self.translate_node(node.value)
        else:
            self.logger.warning("Missing handler for node type {}".format(node_name))
        
        self.logger.debug("{}: {}".format(ast.dump(node), opcode_change))
        return opcode_change
