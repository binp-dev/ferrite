#include <stdint.h>
#include <stdbool.h>
#include <string.h>

#include "board.h"
#include "debug_console_imx.h"

#include "FreeRTOS.h"
#include "task.h"
#include "semphr.h"

#include "app.h"
#include "app_flexcan.h"
#include "app_gpt.h"
#include "app_rpmsg.h"
#include "app_time.h"
#include "app_log.h"


#define APP_TASK_STACK_SIZE    256
#define APP_RPMSG_BUF_SIZE     256

uint8_t rpmsg_buffer[APP_RPMSG_BUF_SIZE] = {0};

static void APP_Task_Rpmsg(void *param) {
    APP_INFO("RPMSG task start");

    if (APP_RPMSG_Init() != 0) {
        PANIC_("RPMSG init error");
    }

    while(true) {
        uint32_t len = 0;
        int32_t status = APP_RPMSG_Receive(rpmsg_buffer, &len, APP_RPMSG_BUF_SIZE, APP_FOREVER_MS);
        if (status == 0) {
            ASSERT(len == APP_RPMSG_BUF_SIZE);
            /*
            PRINTF("[INFO] RPMSG: [%d] ", len);
            for (uint32_t i = 0; i < len; ++i) {
                PRINTF("%02X ", rpmsg_buffer[i]);
            }
            PRINTF("\r\n");
            */
            ASSERT(APP_RPMSG_Send(rpmsg_buffer, len) == 0);
        } else {
            PANIC_("RPMSG receive error: { status: %d }", status);
        }
    }

    APP_RPMSG_Deinit();
}

int main(void) {
    /* Initialize board specified hardware. */
    hardware_init();

    PRINTF("\r\n\r\n");
    APP_INFO("Program start");
    
    /* Create tasks. */
    xTaskCreate(
        APP_Task_Rpmsg, "RPMSG task",
        APP_TASK_STACK_SIZE, NULL, tskIDLE_PRIORITY + 2, NULL
    );

    /* Start FreeRTOS scheduler. */
    vTaskStartScheduler();

    /* Should never reach this point. */
    PANIC_("End of main()");
    return 0;
}
