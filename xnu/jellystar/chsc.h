/* CHSC wire protocol. Original implementation; no firmware or transport code. */
#ifndef JELLYSTAR_CHSC_H
#define JELLYSTAR_CHSC_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define CHSC_REPORT_ADDR 0x2000002cu
#define CHSC_REPORT_BYTES 28u
#define CHSC_RECORDS 5u
#define CHSC_SLOT_COUNT 15u
#define CHSC_HEADER_ADDR 0x20000014u
#define CHSC_HEADER_BYTES 16u

enum chsc_report_kind {
	CHSC_REPORT_TOUCH = 1,
	CHSC_REPORT_IGNORED = 2,
	CHSC_REPORT_GESTURE = 3
};

enum chsc_startup_status {
	CHSC_STARTUP_WAITING = 0,
	CHSC_STARTUP_RUNNING = 1,
	CHSC_STARTUP_ERROR = 2
};

struct chsc_contact {
	uint16_t x, y;
	uint8_t slot, event, major, active;
};

struct chsc_report {
	uint8_t kind, status, reported_count, contact_count, gesture;
	struct chsc_contact contacts[CHSC_RECORDS];
};

struct chsc_state {
	struct chsc_contact slots[CHSC_SLOT_COUNT];
};

struct chsc_startup {
	uint32_t signature, vendor_product;
	uint16_t firmware_version, raw_offset, diff_offset;
	uint8_t status;
};

void chsc_address(uint32_t address, uint8_t command[4]);
int chsc_decode_startup(const uint8_t *data, size_t bytes, struct chsc_startup *out);
int chsc_decode_report(const uint8_t *data, size_t bytes, struct chsc_report *out);
void chsc_state_init(struct chsc_state *state);
/* Apply decoded protocol-B events; omitted slots retain their previous state. */
int chsc_apply_report(const struct chsc_report *report, struct chsc_state *state);
uint16_t chsc_active_mask(const struct chsc_state *state);

#ifdef __cplusplus
}
#endif
#endif
