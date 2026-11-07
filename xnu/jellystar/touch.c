/* Jelly CHSC experiment. Only the explicit /jellystar-touch ADT node enables it.
 * Register facts: saved Jelly DT; MT6789 pin/clock definitions and MT6983
 * I2C v2 reset/timing layout in the pinned references recorded in README.
 * No reset-GPIO pulse, power-rail changes, firmware upload or IRQ routing.
 */
#include <sys/param.h>
#include <sys/systm.h>
#include <kern/clock.h>
#include <kern/thread.h>
#include <kern/sched_prim.h>
#include <machine/machine_routines.h>
#include <pexpert/device_tree.h>
#include <pexpert/arm64/jellystar.h>
#include <arm/caches_internal.h>
#include <vm/pmap.h>
#include <vm/vm_kern.h>
#include "chsc.h"
#include "i2c.h"

extern vm_offset_t ml_io_map(vm_offset_t, vm_size_t);
extern ppnum_t pmap_find_phys(pmap_t, addr64_t);
extern kern_return_t thread_terminate(thread_t);
extern int sweet_hid_touch_frame(uint32_t, const int *, const int *);

static struct {
	vm_offset_t controller, dma, gpio, pads, infra, top, wrapper, memory;
	struct jelly_i2c bus;
	int sleep_channel;
} touch;

static uint32_t read32(vm_offset_t address)
{
	uint32_t value = *(volatile uint32_t *)address;
	__asm__ volatile("dmb oshld" ::: "memory");
	return value;
}
static void write32(vm_offset_t address, uint32_t value)
{
	__asm__ volatile("dmb oshst" ::: "memory");
	*(volatile uint32_t *)address = value;
	__asm__ volatile("dsb osh" ::: "memory");
}
static uint16_t control_read(void *context, unsigned offset)
{
	(void)context;
	uint16_t value = *(volatile uint16_t *)(touch.controller + offset);
	__asm__ volatile("dmb oshld" ::: "memory");
	return value;
}
static void control_write(void *context, unsigned offset, uint16_t value)
{
	(void)context;
	__asm__ volatile("dmb oshst" ::: "memory");
	*(volatile uint16_t *)(touch.controller + offset) = value;
	__asm__ volatile("dsb osh" ::: "memory");
}
static uint32_t dma_read(void *context, unsigned offset)
{
	(void)context;
	return read32(touch.dma + offset);
}
static void dma_write(void *context, unsigned offset, uint32_t value)
{
	(void)context;
	write32(touch.dma + offset, value);
}
static void wait_us(void *context, unsigned usec)
{
	(void)context;
	delay(usec);
}
static void sync_dma(void *context, enum jelly_i2c_sync direction, size_t bytes)
{
	(void)context;
	unsigned size = (unsigned)((bytes + 63) & ~63UL);
	if (direction == JELLY_I2C_TX_DEVICE)
		clean_dcache64(touch.bus.tx_phys, size, TRUE);
	else
		flush_dcache64(touch.bus.rx_phys, size, TRUE);
	__asm__ volatile("dsb sy" ::: "memory");
}
static const struct jelly_i2c_io io = {
	control_read, control_write, dma_read, dma_write, wait_us, sync_dma
};

static void sleep_ms(unsigned ms)
{
	uint64_t deadline;
	clock_interval_to_deadline(ms, NSEC_PER_MSEC, &deadline);
	(void)assert_wait_deadline(&touch.sleep_channel, THREAD_UNINT, deadline);
	thread_block(THREAD_CONTINUE_NULL);
}
static void pin_mode(unsigned pin, unsigned function)
{
	unsigned reg = 0x300 + (pin / 8) * 0x10, shift = (pin % 8) * 4;
	write32(touch.gpio + reg + 8, 15u << shift);
	write32(touch.gpio + reg + 4, function << shift);
}

static int setup(void)
{
	touch.top = ml_io_map(JELLY_TOUCH_TOPCKGEN, 0x1000);
	touch.infra = ml_io_map(JELLY_TOUCH_INFRA, 0x1000);
	touch.wrapper = ml_io_map(JELLY_TOUCH_CLOCK, 0x1000);
	touch.gpio = ml_io_map(JELLY_TOUCH_GPIO, 0x1000);
	touch.pads = ml_io_map(JELLY_TOUCH_IOCFG_LM, 0x1000);
	touch.controller = ml_io_map(JELLY_TOUCH_I2C, JELLY_TOUCH_I2C_SIZE);
	touch.dma = ml_io_map(JELLY_TOUCH_DMA, JELLY_TOUCH_DMA_SIZE);
	if (!touch.top || !touch.infra || !touch.wrapper || !touch.gpio ||
	    !touch.pads || !touch.controller || !touch.dma) return 0;

	/* CLK_TOP_I2C_SEL: parent 0 is the 26 MHz crystal, PDN bit 15.
	 * Enable only I2C/APDMA pseudo clocks, its DMA gate and I2C0 wrapper.
	 */
	write32(touch.top + 0xb8, 0x8300);
	write32(touch.top + 8, 1u << 10);
	unsigned n;
	for (n = 0; n < 1000 && (read32(touch.top + 8) & (1u << 10)); n++) delay(1);
	if (n == 1000 || (read32(touch.top + 0xb0) & 0x8300)) return 0;
	write32(touch.infra + 0x84, (1u << 11) | (1u << 12));
	write32(touch.infra + 0xd4, 1u << 31);
	write32(touch.wrapper + 0xe04, 1);
	if ((read32(touch.infra + 0x90) & ((1u << 11) | (1u << 12))) ||
	    (read32(touch.infra + 0xd8) & (1u << 31)) ||
	    (read32(touch.wrapper + 0xe00) & 1)) return 0;

	pin_mode(JELLY_TOUCH_SCL, 1);
	pin_mode(JELLY_TOUCH_SDA, 1);
	write32(touch.pads + 0xd4, 1u << 29); /* GPIO130 input enable */
	write32(touch.pads + 0xe4, 1u << 3);  /* GPIO131 input enable */
	/* Both lines must be idle high; no guessed bus-recovery pulses. */
	if ((read32(touch.gpio + 0x240) & 12u) != 12u) return 0;

	if (kmem_alloc_contig(kernel_map, &touch.memory, PAGE_SIZE, PAGE_MASK, 0, 0,
	    KMA_DATA | KMA_ZERO | KMA_PERMANENT, VM_KERN_MEMORY_IOKIT) != KERN_SUCCESS)
		return 0;
	ppnum_t page = pmap_find_phys(kernel_pmap, (addr64_t)touch.memory);
	if (!page) return 0;
	touch.bus.io = &io;
	touch.bus.tx = (uint8_t *)touch.memory;
	touch.bus.rx = (uint8_t *)(touch.memory + 128);
	touch.bus.tx_phys = ptoa_64(page);
	touch.bus.rx_phys = touch.bus.tx_phys + 128;
	touch.bus.rx_capacity = 64;
	touch.bus.poll_limit = 10000;
	if ((touch.bus.tx_phys + PAGE_SIZE - 1) >> 36) return 0;
	if (jelly_i2c_quiesce(&touch.bus) != JELLY_I2C_OK) return 0;

	/* Standard-mode probe at ~98.5 kHz, below the DT's 400 kHz ceiling.
	 * 26 MHz / (3 * (41+47)); MediaTek standard-mode AC margins:
	 * setup=137 crystal ticks, SDA hold=12 sample ticks. Same v2 timing
	 * configuration as the pinned MT6789 reference; no fast-mode guess.
	 */
	control_write(0, 0x08, 0);
	control_write(0, 0x0c, 0x1f);
	control_write(0, 0x34, 3);
	control_write(0, 0x48, 0);
	control_write(0, 0x30, 0);
	control_write(0, 0x20, 0x0228);
	control_write(0, 0x2c, 0x00ae);
	control_write(0, 0x28, 0x8901);
	control_write(0, 0x3c, 0x100c);
	control_write(0, 0x90, 0);
	control_write(0, 0x1c, 2);
	control_write(0, 0x38, 1);
	if (control_read(0, 0x20) != 0x0228 || control_read(0, 0x2c) != 0x00ae ||
	    control_read(0, 0x28) != 0x8901 || (control_read(0, 0x24) & 1)) return 0;
	touch.bus.faulted = 0;
	return 1;
}

static void release_contacts(void)
{
	int x[10] = {0}, y[10] = {0};
	(void)sweet_hid_touch_frame(0, x, y);
}
static void run(void *argument, wait_result_t result)
{
	(void)argument;
	(void)result;
	sleep_ms(5000);
	if (!setup()) {
		printf("JELLY TOUCH: controller/pin/clock setup refused; no firmware written\n");
		goto out;
	}
	uint8_t bytes[CHSC_REPORT_BYTES];
	struct chsc_startup startup = {0};
	int error = 0;
	for (unsigned n = 0; n < 10; n++) {
		error = jelly_i2c_read(&touch.bus, JELLY_TOUCH_ADDRESS, CHSC_HEADER_ADDR,
		                       bytes, CHSC_HEADER_BYTES);
		if (error) break;
		(void)chsc_decode_startup(bytes, CHSC_HEADER_BYTES, &startup);
		if (startup.status != CHSC_STARTUP_WAITING) break;
		sleep_ms(10);
	}
	if (error || startup.status != CHSC_STARTUP_RUNNING) {
		printf("JELLY TOUCH: resident firmware unavailable status=%u bus=%d; stopping\n",
		    startup.status, error);
		goto out;
	}
	printf("JELLY TOUCH: resident firmware ready; 28-byte DMA reports, no reset/upload\n");
	struct chsc_state state;
	chsc_state_init(&state);
	unsigned frames = 0;
	for (;;) {
		error = jelly_i2c_read(&touch.bus, JELLY_TOUCH_ADDRESS, CHSC_REPORT_ADDR,
		                       bytes, CHSC_REPORT_BYTES);
		if (error) {
			printf("JELLY TOUCH: stopped bus=%d status=%#x dma_quiet=%d\n",
			    error, touch.bus.status, touch.bus.dma_quiet);
			release_contacts();
			break;
		}
		struct chsc_report report;
		if (chsc_decode_report(bytes, sizeof(bytes), &report) && chsc_apply_report(&report, &state)) {
			int x[10] = {0}, y[10] = {0};
			uint32_t mask = 0;
			for (unsigned i = 0; i < JELLY_TOUCH_MAX && i < 10; i++) {
				if (!state.slots[i].active || state.slots[i].x >= JELLY_TOUCH_XRES ||
				    state.slots[i].y >= JELLY_TOUCH_YRES) continue;
				mask |= 1u << i;
				x[i] = state.slots[i].x;
				y[i] = state.slots[i].y;
			}
			(void)sweet_hid_touch_frame(mask, x, y);
			if (++frames <= 3 || frames % 500 == 0)
				printf("JELLY TOUCH: reports=%u active=%#x\n", frames, mask);
		}
		sleep_ms(20);
	}
out:
	/* The page remains pinned even on failure: DMA may still own it. */
	(void)thread_terminate(current_thread());
	thread_block(THREAD_CONTINUE_NULL);
}

int jelly_touch_present(void)
{
	DTEntry node;
	const void *value;
	unsigned size;
	static const char compatible[] = "unihertz,chsc5xxx";
	return SecureDTLookupEntry(NULL, "/jellystar-touch", &node) == kSuccess &&
	    SecureDTGetProperty(node, "compatible", &value, &size) == kSuccess &&
	    size == sizeof(compatible) && memcmp(value, compatible, sizeof(compatible)) == 0;
}
void jelly_touch_start(void)
{
	static int started;
	if (started || !jelly_touch_present()) return;
	started = 1;
	thread_t thread;
	if (kernel_thread_start(run, NULL, &thread) == KERN_SUCCESS)
		thread_deallocate(thread);
}
