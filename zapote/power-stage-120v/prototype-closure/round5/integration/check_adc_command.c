/* Independent DIN framing oracle, ADS131M08 SBAS950B Figures8-18/8-25.
 * CRC constants independently reproduced with Python stdlib crc_hqx(seedFFFF).
 * This is a test of the production builder, not a replacement driver.
 */
#include "acquisition.h"
#include <stdio.h>
#include <string.h>

int main(void)
{
    static const struct {
        unsigned command, data;
        unsigned char expected[ADS_FRAME_BYTES];
    } cases[] = {
        {0x0000, 0, {0x00, 0x00, 0x00, 0xcc, 0x9c, 0x00}},
        {0x0555, 0, {0x05, 0x55, 0x00, 0xd6, 0x26, 0x00}},
        {0x6100, 0x3000,
         {0x61, 0x00, 0x00, 0x30, 0x00, 0x00, 0xd1, 0x0d, 0x00}},
    };
    int failures = 0;
    for (unsigned i = 0; i < sizeof(cases) / sizeof(cases[0]); ++i) {
        unsigned char frame[ADS_FRAME_BYTES];
        ads_command(cases[i].command, cases[i].data, frame);
        if (memcmp(frame, cases[i].expected, sizeof(frame))) {
            printf("FAIL command %04x: actual", cases[i].command);
            for (unsigned j = 0; j < sizeof(frame); ++j)
                printf(" %02x", frame[j]);
            puts("");
            ++failures;
        }
    }
    printf("Independent DIN frame vectors: %u cases, %d failures\n",
           (unsigned)(sizeof(cases) / sizeof(cases[0])), failures);
    return failures != 0;
}
