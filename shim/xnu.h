#pragma once
#include <stddef.h>
#include <stdint.h>

struct xnu_segment { uint64_t va, size, offset, bytes; };
struct xnu_payload {
	char magic[8];
	uint32_t version, count;
	uint64_t virt, entry, adt_offset, adt_bytes, end, phys, memory;
	char cmdline[608];
	struct xnu_segment segments[];
};
struct xnu_layout { uint64_t entry, adt, args, top; };
int xnu_layout(const void *data, size_t bytes, uint64_t phys, uint64_t memory,
               struct xnu_layout *layout);
#ifndef SHIM_HOST_TEST
void xnu_boot(const struct xnu_payload *p, const struct xnu_layout *layout)
	__attribute__((noreturn));
#endif
