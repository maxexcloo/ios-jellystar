ENTRY(_head)
SECTIONS
{
	. = 0;
	.text : { KEEP(*(.text.head)) *(.text*) }
	.rodata : { *(.rodata*) }
	.data : {
		*(.data*) *(.bss*) *(COMMON)
		. = ALIGN(16);
		. += 0x4000;
		_stack_top = .;
		QUAD(0)
	}
	. = ALIGN(0x200000) + ANDROID_TEXT_OFFSET;
	.android : { KEEP(*(.android)) }
	. = ALIGN(4096);
	_end = .;
	/DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
}
