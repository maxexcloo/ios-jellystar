/* SWEETXNU v1 and boot_args v2: pinned HelioDarwin mkpayload.py / XNU boot.h. */
#include "xnu.h"

static int range(uint64_t offset, uint64_t size, uint64_t limit)
{
	return offset <= limit && size <= limit - offset;
}

int xnu_layout(const void *data, size_t bytes, uint64_t phys, uint64_t memory,
               struct xnu_layout *layout)
{
	const struct xnu_payload *p = data;
	static const char magic[] = "SWEETXNU";
	if ((uintptr_t)data % 8 || bytes < sizeof(*p)) return 0;
	for (unsigned i = 0; i < 8; i++)
		if (p->magic[i] != magic[i]) return 0;
	if (p->version != 1 || !p->count || p->count > 64 ||
	    !range(sizeof(*p), (uint64_t)p->count * sizeof(p->segments[0]), bytes) ||
	    p->phys != phys || p->memory != memory || !memory || phys > UINT64_MAX - memory ||
	    p->virt % 0x2000000 || p->end < p->virt || p->end % 0x4000 ||
	    !range(p->end - p->virt, 0, memory) ||
	    p->adt_offset % 16 || !p->adt_bytes || p->adt_bytes > UINT32_MAX ||
	    !range(p->adt_offset, p->adt_bytes, bytes) || p->cmdline[607]) return 0;
	uint64_t table_end = sizeof(*p) + p->count * sizeof(p->segments[0]);
	if (p->adt_offset < table_end) return 0;
	int executable_entry = 0;
	for (unsigned i = 0; i < p->count; i++) {
		const struct xnu_segment *s = &p->segments[i];
		if (s->va < p->virt || !s->size || s->va % 0x4000 || s->size % 0x4000 ||
		    !range(s->va - p->virt, s->size, p->end - p->virt) ||
		    s->bytes > s->size || s->offset < table_end || s->offset % 8 ||
		    !range(s->offset, s->bytes, p->adt_offset)) return 0;
		if (p->entry >= s->va && p->entry - s->va < s->bytes) executable_entry = 1;
		for (unsigned j = 0; j < i; j++) {
			const struct xnu_segment *o = &p->segments[j];
			if (s->va < o->va + o->size && o->va < s->va + s->size) return 0;
		}
	}
	if (!executable_entry || p->entry % 4) return 0;
	uint64_t used = p->end - p->virt;
	if (!range(used, p->adt_bytes, memory)) return 0;
	uint64_t after = used + p->adt_bytes;
	if (after > UINT64_MAX - 0x3fff) return 0;
	uint64_t args = (after + 0x3fff) & ~0x3fffULL;
	if (!range(args, 0x4000, memory)) return 0;
	layout->entry = phys + (p->entry - p->virt);
	layout->adt = phys + used;
	layout->args = phys + args;
	layout->top = phys + args + 0x4000;
	return 1;
}

#ifndef SHIM_HOST_TEST
#include "board.h"
struct boot_video { uint64_t base, display, row_bytes, width, height, depth; };
struct boot_args {
	uint16_t revision, version;
	uint64_t virt, phys, memory, top;
	struct boot_video video;
	uint32_t machine;
	uint64_t tree;
	uint32_t tree_bytes;
	char cmdline[608];
	uint64_t flags, actual_memory;
};
_Static_assert(sizeof(struct xnu_payload) == 0x2a8, "payload ABI");
_Static_assert(sizeof(struct boot_args) == 736, "boot_args ABI");
_Static_assert(__builtin_offsetof(struct boot_args, cmdline) == 108, "command line ABI");

static void copy(uintptr_t dst, const void *src, size_t bytes)
{
	volatile uint8_t *d = (volatile uint8_t *)dst;
	const uint8_t *s = src;
	for (size_t i = 0; i < bytes; i++) d[i] = s[i];
}

void xnu_boot(const struct xnu_payload *p, const struct xnu_layout *layout)
{
	for (unsigned i = 0; i < p->count; i++) {
		const struct xnu_segment *s = &p->segments[i];
		uintptr_t dst = p->phys + (s->va - p->virt);
		copy(dst, (const uint8_t *)p + s->offset, s->bytes);
		volatile uint8_t *tail = (volatile uint8_t *)(dst + s->bytes);
		for (uint64_t n = s->bytes; n < s->size; n++) *tail++ = 0;
	}
	copy(layout->adt, (const uint8_t *)p + p->adt_offset, p->adt_bytes);
	volatile uint8_t *page = (volatile uint8_t *)layout->args;
	for (unsigned i = 0; i < 0x4000; i++) page[i] = 0;
	volatile struct boot_args *b = (volatile struct boot_args *)layout->args;
	b->revision = b->version = 2;
	b->virt = p->virt;
	b->phys = p->phys;
	b->memory = b->actual_memory = p->memory;
	b->top = layout->top;
	b->video.base = XNU_FB;
	b->video.display = 1;
	b->video.row_bytes = PANEL_WIDTH * 4;
	b->video.width = PANEL_WIDTH;
	b->video.height = PANEL_HEIGHT;
	b->video.depth = 32;
	b->tree = p->virt + (layout->adt - p->phys);
	b->tree_bytes = p->adt_bytes;
	copy((uintptr_t)b->cmdline, p->cmdline, sizeof(b->cmdline));
	__asm__ volatile("dsb sy; ic iallu; dsb sy; isb" ::: "memory");
	((void (*)(uint64_t))layout->entry)(layout->args);
	/* XNU owns RAM now; returning to Android would conceal a failed handoff. */
	for (;;) __asm__ volatile("wfe");
}
#endif
