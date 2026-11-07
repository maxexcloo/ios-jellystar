#pragma once
#include <stddef.h>
#include <stdint.h>

/* Caller owns one controller/channel, enabled clocks, pinmux and bus timing.
 * Every callback performs the required I/O or cache ordering before returning.
 */
enum jelly_i2c_sync {
	JELLY_I2C_TX_DEVICE,
	JELLY_I2C_RX_DEVICE,
	JELLY_I2C_RX_CPU,
};
struct jelly_i2c_io {
	uint16_t (*read16)(void *context, unsigned offset);
	void (*write16)(void *context, unsigned offset, uint16_t value);
	uint32_t (*dma_read32)(void *context, unsigned offset);
	void (*dma_write32)(void *context, unsigned offset, uint32_t value);
	void (*delay_us)(void *context, unsigned usec);
	void (*sync)(void *context, enum jelly_i2c_sync direction, size_t bytes);
};
struct jelly_i2c {
	const struct jelly_i2c_io *io;
	void *context;
	uint8_t *tx, *rx;
	uint64_t tx_phys, rx_phys;
	size_t rx_capacity;
	unsigned poll_limit;
	/* A failed reset can leave DMA owning these buffers. Do not free/reuse
	 * them unless dma_quiet is true. Any transfer fault requires re-setup.
	 */
	int faulted, dma_quiet;
	uint16_t status;
};
enum jelly_i2c_result {
	JELLY_I2C_OK = 0,
	JELLY_I2C_INVALID = -1,
	JELLY_I2C_BUSY = -2,
	JELLY_I2C_NACK = -3,
	JELLY_I2C_TIMEOUT = -4,
	JELLY_I2C_FAULT = -5,
	JELLY_I2C_ARBITRATION = -6,
};

/* One BE32 register-address write followed by a repeated-start DMA read.
 * TX needs four bytes; TX/RX buffers occupy separate 64-byte cache lines.
 * The saved Jelly DT selects mt6983-compatible v2 I2C + APDMA v1, 36-bit PA.
 */
#ifdef __cplusplus
extern "C" {
#endif
/* Reset/quiesce before setup or after transfer failure. A successful return
 * permits buffer reuse, but faulted remains set until the caller reconfigures
 * the controller and explicitly clears it.
 */
int jelly_i2c_quiesce(struct jelly_i2c *bus);
int jelly_i2c_read(struct jelly_i2c *bus, uint8_t slave, uint32_t address,
                   uint8_t *output, size_t bytes);
#ifdef __cplusplus
}
#endif
