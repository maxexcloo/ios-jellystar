/* Android-default chainloader diagnostic. The Android path never touches MMIO. */
#include "shim.h"

static uint32_t be32(const uint8_t *p)
{
	return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 |
	       (uint32_t)p[2] << 8 | p[3];
}

static int equal(const char *a, const char *b)
{
	while (*a && *a == *b) {
		a++;
		b++;
	}
	return *a == *b;
}

/* Only a live framebuffer reservation matching /chosen permits a write. */
int framebuffer_from_fdt(const void *blob, struct framebuffer *fb)
{
	const uint8_t *b = blob;
	if (!b || be32(b) != 0xd00dfeed)
		return 0;
	uint32_t total = be32(b + 4), p = be32(b + 8);
	uint32_t strings = be32(b + 12), strings_size = be32(b + 32);
	if (total < 40 || strings > total || strings_size > total - strings)
		return 0;
	int depth = 0, chosen = 0, reserved = 0, framebuffer = 0;
	uint64_t chosen_base = 0, reserved_base = 0, reserved_size = 0;
	while (p <= total && total - p >= 4) {
		uint32_t token = be32(b + p);
		p += 4;
		if (token == 1) {
			uint32_t start = p;
			while (p < total && b[p])
				p++;
			if (p == total)
				return 0;
			depth++;
			const char *name = (const char *)(b + start);
			if (depth == 2 && equal(name, "chosen"))
				chosen = depth;
			if (depth == 2 && equal(name, "reserved-memory"))
				reserved = depth;
			if (reserved && depth == 3 && equal(name, "mblock-13-framebuffer"))
				framebuffer = depth;
			p = (p + 4) & ~3U;
		} else if (token == 2) {
			if (chosen == depth) chosen = 0;
			if (framebuffer == depth) framebuffer = 0;
			if (reserved == depth) reserved = 0;
			if (--depth < 0) return 0;
		} else if (token == 3) {
			if (total - p < 8) return 0;
			uint32_t len = be32(b + p), nameoff = be32(b + p + 4);
			p += 8;
			if (len > total - p || nameoff >= strings_size) return 0;
			uint32_t end = strings + nameoff;
			while (end < strings + strings_size && b[end]) end++;
			if (end == strings + strings_size) return 0;
			const char *name = (const char *)(b + strings + nameoff);
			if (chosen == depth && len == 4) {
				if (equal(name, "atag,videolfb-fb_base_l"))
					chosen_base = (chosen_base & 0xffffffff00000000ULL) | be32(b + p);
				if (equal(name, "atag,videolfb-fb_base_h"))
					chosen_base = (chosen_base & 0xffffffffULL) | (uint64_t)be32(b + p) << 32;
			}
			if (framebuffer == depth && len == 16 && equal(name, "reg")) {
				reserved_base = (uint64_t)be32(b + p) << 32 | be32(b + p + 4);
				reserved_size = (uint64_t)be32(b + p + 8) << 32 | be32(b + p + 12);
			}
			p = (p + len + 3) & ~3U;
		} else if (token == 9) {
			if (!chosen_base || chosen_base != reserved_base || !reserved_size)
				return 0;
			fb->base = (uintptr_t)reserved_base;
			fb->size = reserved_size;
			return 1;
		} else if (token != 4) {
			return 0;
		}
	}
	return 0;
}

/* Linux persistent_ram_buffer: signature, next-write position, valid bytes.
 * Consume only the marker, including a marker split across the ring boundary.
 * Never dump the pmsg contents: Android logd may put private data there.
 */
int take_trigger(volatile void *zone, size_t bytes)
{
	static const char marker[] = "JELLYSTAR:DIAGNOSTIC";
	volatile uint32_t *h = zone;
	if (bytes < 12 || h[0] != 0x43474244)
		return 0;
	size_t capacity = bytes - 12, start = h[1], size = h[2];
	if (start > size || size > capacity || size < sizeof(marker) - 1)
		return 0;
	volatile uint8_t *data = (volatile uint8_t *)zone + 12;
	size_t oldest = start % size;
	int found = 0;
	for (size_t i = 0; i + sizeof(marker) - 1 <= size; i++) {
		size_t j = 0;
		while (j < sizeof(marker) - 1 && data[(oldest + i + j) % size] == marker[j])
			j++;
		if (j == sizeof(marker) - 1) {
			for (j = 0; j < sizeof(marker) - 1; j++)
				data[(oldest + i + j) % size] = 0;
			found = 1;
		}
	}
	return found;
}

#ifndef SHIM_HOST_TEST
#include "board.h"

static inline void write32(uintptr_t address, uint32_t value)
{
	*(volatile uint32_t *)address = value;
}

static uint64_t ticks(void)
{
	uint64_t value;
	__asm__ volatile("isb; mrs %0, cntpct_el0" : "=r"(value));
	return value;
}

static void wait_ms(unsigned ms)
{
	uint64_t frequency;
	__asm__ volatile("mrs %0, cntfrq_el0" : "=r"(frequency));
	uint64_t start = ticks(), duration = frequency / 1000 * ms;
	while (ticks() - start < duration) {
		write32(SOC_TOPRGU + 8, 0x1971);
		/* No event source is armed; WFE here could wait forever. */
		__asm__ volatile("yield");
	}
}

void shim_main(uintptr_t dtb)
{
	if (!PMSG_ADDRESS || !take_trigger((volatile void *)PMSG_ADDRESS, PMSG_SIZE))
		return;
	/* Consume before drawing so the next reset takes the Android path. */
	__asm__ volatile("dsb sy" ::: "memory");
	struct framebuffer fb;
	if (framebuffer_from_fdt((const void *)dtb, &fb) &&
	    fb.base % 4 == 0 && fb.size >= (uint64_t)PANEL_WIDTH * PANEL_HEIGHT * 4) {
		volatile uint32_t *pixels = (volatile uint32_t *)fb.base;
		for (unsigned i = 0; i < PANEL_WIDTH * PANEL_HEIGHT; i++)
			pixels[i] = 0xff00ff00;
		__asm__ volatile("dsb sy" ::: "memory");
		wait_ms(5000);
	}
	/* Continue directly into Android; no dependence on PSCI or watchdog reset. */
}
#endif
