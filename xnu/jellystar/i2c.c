/* Original MT6983-compatible transfer core, grounded in the Jelly DT and
 * HelloVolla/android_kernel_volla_mt6789 at 0b0e1435e568a4d2b5e9dceef0772bb1bc4786c5,
 * drivers/i2c/busses/i2c-mt65xx.c (v2 offsets, mt6983_compat, APDMA v1).
 * No clock, pin, reset-GPIO or firmware assumptions are made here.
 */
#include "i2c.h"

#define INTR_MASK 0x08u
#define INTR_STAT 0x0cu
#define CONTROL 0x10u
#define TRANSFER_LEN 0x14u
#define TRANSAC_LEN 0x18u
#define START 0x24u
#define FIFO_CLEAR 0x38u
#define AUX_LEN 0x44u
#define SOFTRESET 0x50u
#define SLAVE_ADDR 0x94u
#define DMA_EN 0x08u
#define DMA_RESET 0x0cu
#define DMA_CONTROL 0x18u
#define DMA_TX_ADDR 0x1cu
#define DMA_RX_ADDR 0x20u
#define DMA_TX_LEN 0x24u
#define DMA_RX_LEN 0x28u
#define DMA_TX_HIGH 0x54u
#define DMA_RX_HIGH 0x58u
#define COMPLETE 1u
#define ACK_ERRORS 6u
#define ARBITRATION_LOST 8u

static int dma_idle(struct jelly_i2c *bus)
{
	for (unsigned n = 0; n < bus->poll_limit; n++) {
		if (!(bus->io->dma_read32(bus->context, DMA_EN) & 1u)) {
			bus->dma_quiet = 1;
			return 1;
		}
		bus->io->delay_us(bus->context, 2);
	}
	return 0;
}

int jelly_i2c_quiesce(struct jelly_i2c *bus)
{
	/* APDMA warm reset, then coupled controller/DMA handshake reset.
	 * Timing configuration is not reconstructed after reset: fail closed
	 * until the caller explicitly sets the controller up again.
	 */
	bus->faulted = 1;
	bus->dma_quiet = 0;
	bus->io->dma_write32(bus->context, DMA_RESET, 1);
	bus->io->delay_us(bus->context, 10);
	bus->io->dma_write32(bus->context, DMA_RESET, 0);
	bus->io->delay_us(bus->context, 10);
	bus->io->dma_write32(bus->context, DMA_RESET, 6);
	bus->io->write16(bus->context, SOFTRESET, 0x21);
	bus->io->delay_us(bus->context, 10);
	bus->io->dma_write32(bus->context, DMA_RESET, 0);
	bus->io->write16(bus->context, SOFTRESET, 0);
	return dma_idle(bus) ? JELLY_I2C_OK : JELLY_I2C_FAULT;
}

static int dma_range(uint64_t address, size_t bytes)
{
	return address < (1ULL << 36) && bytes <= (1ULL << 36) - address;
}

int jelly_i2c_read(struct jelly_i2c *bus, uint8_t slave, uint32_t address,
                   uint8_t *output, size_t bytes)
{
	if (!bytes || bytes > 0xffffu || bytes > bus->rx_capacity || !bus->poll_limit ||
	    slave > 0x7fu || !dma_range(bus->tx_phys, 4) || !dma_range(bus->rx_phys, bytes) ||
	    bus->tx_phys % 64 || bus->rx_phys % 64 ||
	    (bus->tx_phys < bus->rx_phys + bytes && bus->rx_phys < bus->tx_phys + 64))
		return JELLY_I2C_INVALID;
	if (bus->faulted)
		return JELLY_I2C_FAULT;
	if ((bus->io->read16(bus->context, START) & 1u) ||
	    (bus->io->dma_read32(bus->context, DMA_EN) & 1u))
		return JELLY_I2C_BUSY;

	for (unsigned n = 0; n < 4; n++)
		bus->tx[n] = (uint8_t)(address >> (24 - n * 8));
	bus->io->sync(bus->context, JELLY_I2C_TX_DEVICE, 4);
	bus->io->sync(bus->context, JELLY_I2C_RX_DEVICE, bytes);
	bus->io->write16(bus->context, INTR_MASK, 0);
	bus->io->write16(bus->context, INTR_STAT, 0x1f);
	bus->io->write16(bus->context, FIFO_CLEAR, 1);
	bus->io->write16(bus->context, SLAVE_ADDR, (uint16_t)(slave << 1));
	bus->io->write16(bus->context, TRANSFER_LEN, 4);
	bus->io->write16(bus->context, AUX_LEN, (uint16_t)bytes);
	bus->io->write16(bus->context, TRANSAC_LEN, 2);
	/* Repeated START, direction change, ACK detection, clock extension,
	 * DMA handshake/async; retain the inherited unrelated control fields.
	 */
	uint16_t control = bus->io->read16(bus->context, CONTROL);
	bus->io->write16(bus->context, CONTROL, (control & ~0x37eu) | 0x33eu);
	bus->io->dma_write32(bus->context, 0x00, 0);
	bus->io->dma_write32(bus->context, 0x04, 0);
	bus->io->dma_write32(bus->context, DMA_CONTROL, 0x214);
	bus->io->dma_write32(bus->context, DMA_TX_ADDR, (uint32_t)bus->tx_phys);
	bus->io->dma_write32(bus->context, DMA_RX_ADDR, (uint32_t)bus->rx_phys);
	bus->io->dma_write32(bus->context, DMA_TX_HIGH, (uint32_t)(bus->tx_phys >> 32));
	bus->io->dma_write32(bus->context, DMA_RX_HIGH, (uint32_t)(bus->rx_phys >> 32));
	bus->io->dma_write32(bus->context, DMA_TX_LEN, 4);
	bus->io->dma_write32(bus->context, DMA_RX_LEN, (uint32_t)bytes);
	bus->dma_quiet = 0;
	bus->io->dma_write32(bus->context, DMA_EN, 1);
	bus->io->write16(bus->context, START, 1);
	int result = JELLY_I2C_TIMEOUT;
	for (unsigned n = 0; n < bus->poll_limit; n++) {
		bus->status = bus->io->read16(bus->context, INTR_STAT);
		if (bus->status & (ACK_ERRORS | ARBITRATION_LOST)) {
			result = bus->status & ARBITRATION_LOST ?
			    JELLY_I2C_ARBITRATION : JELLY_I2C_NACK;
			break;
		}
		if (bus->status & COMPLETE) {
			if (!dma_idle(bus)) break;
			bus->io->sync(bus->context, JELLY_I2C_RX_CPU, bytes);
			for (size_t i = 0; i < bytes; i++) output[i] = bus->rx[i];
			bus->io->write16(bus->context, INTR_STAT, bus->status);
			return JELLY_I2C_OK;
		}
		bus->io->delay_us(bus->context, 2);
	}
	return jelly_i2c_quiesce(bus) == JELLY_I2C_OK ? result : JELLY_I2C_FAULT;
}
