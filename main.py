import logging
import helpers
import opcodes
from translator import Translator

def main():
    translator = Translator()
    lscvm = translator.translate("""
def bar(a, b):
    c = a + b
    d = c * 2
    return d

bar(5, 10)""")
    print(lscvm)

if __name__ == "__main__":
    main()
