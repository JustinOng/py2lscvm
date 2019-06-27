# py2lscvm

A basic translator for the interpreted language for the Light Speed Corp Virtual Machine (used during the Cyber Defenders Discovery Camp 2019), capable of translating Python into a format that the virtual machine can run.

For example, one of the challenges was to write a quine (this was solved after end of the qualifiers).

This translator will translate the following code:

```
data_len = 232
i = 0
while i < data_len:
    num = stack_find(1 + data_len - i)
    first = 1
    while num > 0:
        if num > 9:
            putchar(0x6A)
            num -= 9
        else:
            putchar(0x61 + num)
            num = 0

        if first == 0:
            putchar(0x41)
        
        first = 0
    i += 1

i = 0
while i < data_len:
    num = stack_find(1 + data_len - i)
    putchar(0x40 + num)
    i += 1
```

into

```
ibehMAMaKabKaibjjAAMSaFbEaEJbAdZabGbbbgdMhMAMZbaEAbESFcKbdKachMhMSaFcEaJbSdZabGbebjjAAMZcEjJbSdZabGbefMZcbejeAMAMPcEjScKjhAGbbieMdMAMcEAPacKdEaJdZabGbiZfjeAMPaGadKGDDbEbAbKGDDabKabbghMAMSaFbEaEJbAdZabGbidMZbaEAbESFcKiiMcEAPbEbAbKGDD
```

Refer to JustinOng/lscvm-debugger for the opcodes.

There are a few odd things about the language that makes writing a translator really hard - namely the lack of random writes to the stack.

This, along with the lack of any form of registers like `esp` and `ebp`, makes it impossible to use traditional stack frames to handle local variables.

As such, I resorted to storing all (both global and local) variables in the heap because that can be randomly read and written to.

Of course, I realised after everything was over that I did _not_ need to go to such lengths - in the finals, only the ability to write to the heap was needed - something doable easily even without this project.