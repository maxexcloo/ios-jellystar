/* Wire fields were established by Jelly vendor-module disassembly and checked
 * against HelloVolla/android_kernel_volla_mt6789, 0b0e1435e568a4d2b5e9dceef0772bb1bc4786c5,
 * drivers/input/touchscreen/chsc5xxx/{head_def.h,semi_touch_device.c,semi_touch_function.c}.
 * Protocol facts are implemented here without copying that GPL driver.
 */
#include "chsc.h"

static uint16_t le16(const uint8_t *p)
{
	return (uint16_t)p[0] | (uint16_t)p[1] << 8;
}

static uint32_t le32(const uint8_t *p)
{
	return (uint32_t)p[0] | (uint32_t)p[1] << 8 |
	       (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

void chsc_address(uint32_t address, uint8_t command[4])
{
	for (unsigned i = 0; i < 4; i++)
		command[i] = (uint8_t)(address >> (24 - i * 8));
}

int chsc_decode_startup(const uint8_t *data, size_t bytes, struct chsc_startup *out)
{
	if (bytes != CHSC_HEADER_BYTES) return 0;
	struct chsc_startup header = {0};
	header.firmware_version = le16(data);
	header.signature = le32(data + 4);
	header.vendor_product = le32(data + 8);
	header.raw_offset = le16(data + 12);
	header.diff_offset = le16(data + 14);
	if (header.signature == 0x43534843u)
		header.status = CHSC_STARTUP_RUNNING;
	else if (header.signature == 0x4f525245u)
		header.status = CHSC_STARTUP_ERROR;
	else
		header.status = CHSC_STARTUP_WAITING;
	*out = header;
	return 1;
}

int chsc_decode_report(const uint8_t *data, size_t bytes, struct chsc_report *out)
{
	if (bytes != CHSC_REPORT_BYTES) return 0;
	struct chsc_report report = {0};
	report.status = data[0];
	if (data[0] == 0xfc || data[0] == 0xfd) {
		report.kind = CHSC_REPORT_IGNORED;
	} else if (data[0] == 0xfe) {
		report.kind = CHSC_REPORT_GESTURE;
		report.gesture = data[1];
	} else {
		report.kind = CHSC_REPORT_TOUCH;
		report.reported_count = data[1] & 15;
		for (unsigned i = 0; i < CHSC_RECORDS; i++) {
			const uint8_t *p = data + 2 + i * 5;
			uint8_t slot = p[4] & 15;
			if (slot == 15) continue;
			struct chsc_contact *contact = &report.contacts[report.contact_count++];
			contact->x = (uint16_t)p[0] | (uint16_t)(p[3] & 15) << 8;
			contact->y = (uint16_t)p[1] | (uint16_t)(p[3] >> 4) << 8;
			contact->slot = slot;
			contact->event = p[4] >> 4;
			contact->major = p[2];
			contact->active = contact->event != 4;
		}
	}
	*out = report;
	return 1;
}

void chsc_state_init(struct chsc_state *state)
{
	for (unsigned i = 0; i < CHSC_SLOT_COUNT; i++) {
		struct chsc_contact contact = {0};
		contact.slot = (uint8_t)i;
		contact.event = 4;
		state->slots[i] = contact;
	}
}

int chsc_apply_report(const struct chsc_report *report, struct chsc_state *state)
{
	if (report->kind != CHSC_REPORT_TOUCH) return 0;
	for (unsigned i = 0; i < report->contact_count; i++) {
		const struct chsc_contact *contact = &report->contacts[i];
		struct chsc_contact *slot = &state->slots[contact->slot];
		if (contact->active) {
			*slot = *contact;
		} else {
			/* An up record need not carry valid coordinates. Keep the last
			 * position for a frontend that emits a release event there.
			 */
			slot->active = 0;
			slot->event = contact->event;
		}
	}
	if (report->reported_count == 0) {
		for (unsigned i = 0; i < CHSC_SLOT_COUNT; i++) {
			state->slots[i].active = 0;
			state->slots[i].event = 4;
		}
	}
	return 1;
}

uint16_t chsc_active_mask(const struct chsc_state *state)
{
	uint16_t mask = 0;
	for (unsigned i = 0; i < CHSC_SLOT_COUNT; i++)
		if (state->slots[i].active) mask |= (uint16_t)(1u << i);
	return mask;
}
