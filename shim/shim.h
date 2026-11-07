#pragma once
#include <stddef.h>
#include <stdint.h>

struct framebuffer {
	uintptr_t base;
	uint64_t size;
};

int framebuffer_from_fdt(const void *blob, struct framebuffer *fb);
int take_marker(volatile void *zone, size_t bytes, const char *marker, size_t length);
int take_trigger(volatile void *zone, size_t bytes);
void shim_main(uintptr_t dtb);
