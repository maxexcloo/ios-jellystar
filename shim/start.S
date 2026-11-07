/* Linux Image wrapper. LK supplies the original FDT in x0. */
	.section .text.head, "ax"
	.globl _head
_head:
	b _start
	.long 0
	.quad 0
	.quad _end
	.quad 0xa
	.quad 0, 0, 0
	.ascii "ARM\x64"
	.long 0

	.text
_start:
	msr daifset, #0xf
	/* Keep LK's MMU/cache/EL state. Android receives the same FDT and ramdisk. */
	mov x19, x0
	adrp x1, _stack_top
	add x1, x1, :lo12:_stack_top
	mov sp, x1
	bl shim_main
	mov x0, x19
	mov x1, xzr
	mov x2, xzr
	mov x3, xzr
	adrp x4, android_image
	add x4, x4, :lo12:android_image
	ic iallu
	dsb sy
	isb
	br x4
