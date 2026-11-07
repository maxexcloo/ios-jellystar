/* Jelly display diagnostic. The only presentation call is explicit --pattern.
 * Selector/record ABI: pinned SweetFramebuffer.cpp, consumed by the Jelly port.
 */
#include <stddef.h>
#include <stdint.h>

#ifndef JELLY_WIDTH
#error JELLY_WIDTH must come from shim/soc.args
#endif
#ifndef JELLY_HEIGHT
#error JELLY_HEIGHT must come from shim/soc.args
#endif

int jelly_display_pattern(void *memory, size_t bytes, size_t stride)
{
	if (stride < JELLY_WIDTH * 4u || stride > bytes / JELLY_HEIGHT) return 0;
	uint8_t *pixels = memory;
	for (unsigned y = 0; y < JELLY_HEIGHT; y++) {
		for (unsigned x = 0; x < JELLY_WIDTH; x++) {
			uint8_t *p = pixels + (size_t)y * stride + (size_t)x * 4;
			p[0] = p[1] = p[2] = 0;
			p[3] = 255;
			if (y < 64 && x < 192) p[2 - x / 64] = 255;
		}
	}
	return 1;
}

#ifndef DISPLAY_PROBE_HOST_TEST
#include <CoreFoundation/CoreFoundation.h>
#include <IOSurface/IOSurfaceRef.h>
#include <dlfcn.h>
#include <mach/mach.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

/* Public IOKitLib signatures, loaded dynamically because the iOS SDK does not
 * expose the macOS IOKitLib header/framework stub. Handles are Mach ports.
 */
static struct {
	CFMutableDictionaryRef (*matching)(const char *);
	mach_port_t (*service)(mach_port_t, CFDictionaryRef);
	kern_return_t (*parent)(mach_port_t, const char *, mach_port_t *);
	CFTypeRef (*property)(mach_port_t, CFStringRef, CFAllocatorRef, uint32_t);
	kern_return_t (*open)(mach_port_t, mach_port_t, uint32_t, mach_port_t *);
	kern_return_t (*close)(mach_port_t);
	kern_return_t (*release)(mach_port_t);
	kern_return_t (*call)(mach_port_t, uint32_t, const uint64_t *, uint32_t,
	    const void *, size_t, uint64_t *, uint32_t *, void *, size_t *);
} io;

static int provider_is_jelly(mach_port_t service)
{
	mach_port_t provider = MACH_PORT_NULL;
	if (io.parent(service, "IOService", &provider) != KERN_SUCCESS) return 0;
	CFTypeRef value = io.property(provider, CFSTR("compatible"), kCFAllocatorDefault, 0);
	io.release(provider);
	int found = 0;
	if (value && CFGetTypeID(value) == CFDataGetTypeID()) {
		const uint8_t *data = CFDataGetBytePtr((CFDataRef)value);
		CFIndex size = CFDataGetLength((CFDataRef)value);
		static const char marker[] = "unihertz,jellystar-framebuffer";
		for (CFIndex offset = 0; offset < size;) {
			CFIndex length = 0;
			while (offset + length < size && data[offset + length]) length++;
			if (length == sizeof(marker) - 1 &&
			    memcmp(data + offset, marker, sizeof(marker) - 1) == 0) found = 1;
			offset += length + 1;
		}
	}
	if (value) CFRelease(value);
	return found;
}

static int number(CFMutableDictionaryRef dictionary, CFStringRef key, int32_t value)
{
	CFNumberRef item = CFNumberCreate(kCFAllocatorDefault, kCFNumberSInt32Type, &value);
	if (!item) return 0;
	CFDictionarySetValue(dictionary, key, item);
	CFRelease(item);
	return 1;
}

static void put32(uint8_t *record, unsigned offset, uint32_t value)
{
	for (unsigned i = 0; i < 4; i++) record[offset + i] = (uint8_t)(value >> (i * 8));
}

static int present_pattern(mach_port_t connection)
{
	int result = 1;
	CFMutableDictionaryRef properties = CFDictionaryCreateMutable(kCFAllocatorDefault,
	    5, &kCFTypeDictionaryKeyCallBacks, &kCFTypeDictionaryValueCallBacks);
	if (!properties) return 1;
	int ok = number(properties, kIOSurfaceWidth, JELLY_WIDTH) &&
	    number(properties, kIOSurfaceHeight, JELLY_HEIGHT) &&
	    number(properties, kIOSurfaceBytesPerRow, JELLY_WIDTH * 4) &&
	    number(properties, kIOSurfaceBytesPerElement, 4) &&
	    number(properties, kIOSurfacePixelFormat, 0x42475241); /* BGRA */
	IOSurfaceRef surface = ok ? IOSurfaceCreate(properties) : NULL;
	CFRelease(properties);
	if (!surface) { fputs("IOSurface creation failed\n", stderr); return 1; }
	if (IOSurfaceGetWidth(surface) != JELLY_WIDTH || IOSurfaceGetHeight(surface) != JELLY_HEIGHT ||
	    IOSurfaceGetBytesPerElement(surface) != 4 || IOSurfaceLock(surface, 0, NULL) != KERN_SUCCESS)
		goto out;
	void *pixels = IOSurfaceGetBaseAddress(surface);
	ok = pixels && jelly_display_pattern(pixels, IOSurfaceGetAllocSize(surface), IOSurfaceGetBytesPerRow(surface));
	kern_return_t error = IOSurfaceUnlock(surface, 0, NULL);
	if (!ok || error != KERN_SUCCESS) goto out;

	uint64_t swap = 0;
	uint32_t count = 1;
	error = io.call(connection, 4, NULL, 0, NULL, 0, &swap, &count, NULL, NULL);
	if (error != KERN_SUCCESS || count != 1) {
		fprintf(stderr, "SwapBegin failed: %#x, scalar count %u\n", error, count);
		goto out;
	}
	uint8_t record[0x46c] = {0};
	put32(record, 0x50, (uint32_t)swap);
	IOSurfaceID surface_id = IOSurfaceGetID(surface);
	if (!surface_id) { fputs("IOSurface has no kernel ID\n", stderr); goto out; }
	put32(record, 0x54, surface_id);
	put32(record, 0x6c, JELLY_WIDTH);
	put32(record, 0x70, JELLY_HEIGHT);
	put32(record, 0xcc, JELLY_WIDTH);
	put32(record, 0xd0, JELLY_HEIGHT);
	put32(record, 0x104, 1);
	error = io.call(connection, 5, NULL, 0, record, sizeof(record), NULL, NULL, NULL, NULL);
	if (error != KERN_SUCCESS) {
		fprintf(stderr, "SwapEnd failed: %#x\n", error);
		goto out;
	}
	puts("BGRA pattern queued: red/green/blue squares on black. Visible pixels need observation.");
	/* SwapEnd queues work for the kernel's timer; this is not a presentation fence. */
	sleep(1);
	result = 0;
out:
	if (result) fputs("Pattern preparation or submission failed\n", stderr);
	CFRelease(surface);
	return result;
}

int main(int argc, char **argv)
{
	int pattern = argc == 2 && strcmp(argv[1], "--pattern") == 0;
	if (argc != 1 && !pattern) { fputs("usage: jelly-display-probe [--pattern]\n", stderr); return 2; }
	void *library = dlopen("/System/Library/Frameworks/IOKit.framework/IOKit", RTLD_NOW | RTLD_LOCAL);
	if (!library) { fputs("IOKit is unavailable\n", stderr); return 1; }
#define LOAD(field, symbol) do { \
	io.field = dlsym(library, symbol); \
	if (!io.field) { fprintf(stderr, "Missing IOKit symbol: %s\n", symbol); return 1; } \
} while (0)
	LOAD(matching, "IOServiceMatching");
	LOAD(service, "IOServiceGetMatchingService");
	LOAD(parent, "IORegistryEntryGetParentEntry");
	LOAD(property, "IORegistryEntryCreateCFProperty");
	LOAD(open, "IOServiceOpen");
	LOAD(close, "IOServiceClose");
	LOAD(release, "IOObjectRelease");
	LOAD(call, "IOConnectCallMethod");
#undef LOAD
	CFMutableDictionaryRef matching = io.matching("AppleCLCD");
	mach_port_t service = matching ? io.service(MACH_PORT_NULL, matching) : MACH_PORT_NULL;
	int result = 1;
	mach_port_t connection = MACH_PORT_NULL;
	if (!service || !provider_is_jelly(service)) {
		fputs("No Jelly framebuffer provider; no selectors called\n", stderr);
		goto out;
	}
	kern_return_t error = io.open(service, mach_task_self(), 0, &connection);
	if (error != KERN_SUCCESS) { fprintf(stderr, "IOServiceOpen failed: %#x\n", error); goto out; }
	uint64_t dimensions[2] = {0};
	uint32_t count = 2;
	error = io.call(connection, 8, NULL, 0, NULL, 0, dimensions, &count, NULL, NULL);
	if (error != KERN_SUCCESS || count != 2) {
		fprintf(stderr, "GetDisplaySize failed: %#x, scalar count %u\n", error, count);
		goto out;
	}
	printf("Jelly AppleCLCD: %llu x %llu\n", dimensions[0], dimensions[1]);
	if (dimensions[0] != JELLY_WIDTH || dimensions[1] != JELLY_HEIGHT) goto out;
	result = pattern ? present_pattern(connection) : 0;
out:
	if (connection) io.close(connection);
	if (service) io.release(service);
	dlclose(library);
	return result;
}
#endif
