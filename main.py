import logging
import helpers
import opcodes
from translator import Translator

def main():
    translator = Translator()
    with open("source.py") as f:
        lscvm = translator.translate(f.read())
    print(lscvm)

if __name__ == "__main__":
    main()
