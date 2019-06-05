import ast
import logging
import opcodes
import helpers
from heap import Heap
from translatorbase import TranslatorBase
from functiontranslator import FunctionTranslator

class Translator():
    def __init__(self):
        self.heap = Heap()

        self.opcodes = ""

        # function table containing offsets at which 
        # functions can be found at, starting at 0
        # key: name of function
        # val: offset of function
        self.functions = {}
        # tracks total length of functions
        # to calculate future offsets
        self.funcs_len = 0

        self.logger = helpers.init_logger("TRANSLATOR")

    
    def translate(self, code):
        # translates code to lscvm

        tree = ast.parse(code)

        for node in ast.iter_child_nodes(tree):
            self.logger.debug(ast.dump(node))

            node_name = helpers.class_name(node)
            if node_name == "FunctionDef":
                func = FunctionTranslator(self.heap)
                func.translate_function(node)
                func_opcodes = func.opcodes

                self.opcodes += func_opcodes
                self.functions[func.name] = self.funcs_len
                self.funcs_len += len(func_opcodes)
            else:
                self.logger.warning("Missing handler for {}".format(node_name))
