import ast
import opcodes
import helpers
from translatorbase import TranslatorBase

class VariableCounter(ast.NodeVisitor):
    # this class serves to count the number of variables
    # used in childs of the node passed to it
    def __init__(self):
        self.variables = set()

    def visit_Assign(self, node):
        self.variables.update([a.id for a in node.targets])

class FunctionTranslator(TranslatorBase):
    def __init__(self, heap):
        super().__init__(heap)
        self.name = ""
        self.args = []

        self.logger = helpers.init_logger("FUNCTION_TRANS")

    def read_var(self, name):
        # override base method to check if variable is in args
        if name in self.args:
            # name is in args, retrieve from back of stack
            # offset from end of stack
            offset = len(self.args) - self.args.index(name)
            return helpers.num(offset) + opcodes.STACK_FIND
        
        return super().read_var(name)

    def translate_function(self, node):
        # builds a function from a ast node
        self.name = node.name

        # load name of args
        for arg in node.args.args:
            self.args.append(arg.arg)

        self.logger.info("Building function {} with args {}".format(self.name, self.args))
        self.logger.debug(ast.dump(node))
        
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
            self.opcodes += self.translate_node(node)

        # remember to destroy variables on the stack if any extra are left

        self.heap.release_func()
