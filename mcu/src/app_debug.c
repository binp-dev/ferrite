#include "app_debug.h"

#ifdef APP_DEBUG_IO_RPMSG
volatile uint8_t __app_io_rpmsg_enabled = 0;
uint8_t __app_io_rpmsg_buffer[0x100] = {0};

void APP_Debug_IO_RPMSG_Enable() {
    __app_io_rpmsg_enabled = 1;
}

void APP_Debug_IO_RPMSG_Send(int len) {
    if (__app_io_rpmsg_enabled) {
        if (len < 0) {
            return;
        }
        if (len > 0x100 - 3) {
            len = 0x100 - 3;
        }
        __app_io_rpmsg_buffer[0] = PSCM_MESSAGE;
        __app_io_rpmsg_buffer[1] = (uint8_t)len + 1;
        __app_io_rpmsg_buffer[0xFF] = 0;
        
        APP_RPMSG_Send(__app_io_rpmsg_buffer, len + 3);
    }
}
#endif // APP_DEBUG_IO_RPMSG
