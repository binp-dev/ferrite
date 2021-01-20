#include <stdint.h>
#include <stdbool.h>
#include <string.h>

#include "board.h"
#include "app_debug.h"

#include "FreeRTOS.h"
#include "task.h"
#include "semphr.h"

#include "app.h"
#include "app_ecspi.h"
#include "app_gpt.h"
#include "app_rpmsg.h"
#include "app_time.h"
#include "app_log.h"
#include "app_gpio.h"

#include "../../common/proto.h"


#define APP_TASK_STACK_SIZE    256
#define APP_RPMSG_BUF_SIZE     256

static SemaphoreHandle_t wf_send_sem = NULL;
static SemaphoreHandle_t wf_ready_sem = NULL;

#define APP_WF_BUF_SIZE        APP_RPMSG_BUF_SIZE
#define APP_WF_OFFSET          1
#define APP_WF_POINT_SIZE      3

static uint8_t wf_buffers[2][APP_WF_BUF_SIZE] = {{0}, {0}};
static volatile uint8_t wf_current = 0;

#define APP_SPI_TX_SIZE 4
#if APP_WF_POINT_SIZE > APP_SPI_TX_SIZE - 1
#error "Waveform point is too big to be put in SPI message"
#endif

#define PB_BUF_SIZE 0x100
static char pb_buf[PB_BUF_SIZE];
static void APP_Print_Bytes(const uint8_t *buffer, const uint32_t len) {
    for (uint32_t i = 0; i < len; ++i) {
        snprintf(pb_buf + 3 * i, 4, "%02X ", buffer[i]);
    }
    PRINTF("%s", pb_buf);
}

static void APP_Task_EcspiTransfer(void *param);

static void APP_Task_Rpmsg(void *param) {
    APP_INFO("RPMSG task start");

    if (APP_RPMSG_Init() != 0) {
        PANIC_("RPMSG init error");
    }

#ifdef APP_DEBUG_IO_RPMSG
    APP_Debug_IO_RPMSG_Enable();
#endif // APP_DEBUG_IO_RPMSG

    uint8_t ssid;
    uint32_t slen = 0;
    int32_t sst = APP_RPMSG_Receive(&ssid, &slen, 1, APP_FOREVER_MS);
    if (sst == 0 && slen == 1 && ssid == PSCA_START) {
        APP_INFO("RPMSG received start signal");
    } else {
        PANIC_("RPMSG receive start signal error: { status: %ld, len: %ld, sid: %d }", sst, slen, (int)ssid);
    }

    xTaskCreate(
        APP_Task_EcspiTransfer, "ECSPI task",
        APP_TASK_STACK_SIZE, NULL, tskIDLE_PRIORITY + 2, NULL
    );

    APP_INFO("Start GPT");
    APP_GPT_Init(APP_GPT_SEC/10, wf_send_sem);

    APP_INFO("Enter RPMSG read loop");
    while(true) {
        uint32_t len = 0;
        uint8_t *buffer = wf_buffers[!wf_current];
        // FIXME: Avoid buffer switching while receiving data.
        int32_t status = APP_RPMSG_Receive(buffer, &len, APP_RPMSG_BUF_SIZE, APP_FOREVER_MS);
        APP_INFO("RPMSG receive status: %ld", status);
        if (status == 0) {
            APP_INFO("RPMSG mesage received: { len: %ld, sid: %d }", len, (int)buffer[0]);
            ASSERT(len == APP_WF_BUF_SIZE);
            ASSERT(buffer[0] == PSCA_WF_DATA);
            xSemaphoreGive(wf_ready_sem);
        } else {
            PANIC_("RPMSG receive error");
        }
    }

    APP_RPMSG_Deinit();
}

static void APP_Task_EcspiTransfer(void *param) {
    uint8_t *buf = NULL;
    size_t pos = 0;

    uint8_t spi_tx[APP_SPI_TX_SIZE] = {0xFF};
    uint8_t spi_rx[APP_SPI_TX_SIZE];

    APP_INFO("ECSPI task start");

    while (true) {
        if (buf == NULL || pos + APP_WF_POINT_SIZE > APP_WF_BUF_SIZE) {
            APP_INFO("RPMSG send waveform request");

            uint8_t sid = PSCM_WF_REQ;
            uint8_t tmp_buf[2] = {sid, 0};
            APP_RPMSG_Send(tmp_buf, 2);

            ASSERT(xSemaphoreTake(wf_ready_sem, portMAX_DELAY) == pdTRUE);
            
            wf_current = !wf_current;
            buf = wf_buffers[wf_current];
            pos = APP_WF_OFFSET;
        }

        APP_INFO("Waiting for timer");
        ASSERT(xSemaphoreTake(wf_send_sem, portMAX_DELAY) == pdTRUE);
        APP_INFO("Sending");

        // FIXME: Use driver
        spi_tx[0] = 0xE0;
        memcpy(
            spi_tx + APP_SPI_TX_SIZE - APP_WF_POINT_SIZE,
            buf + pos,
            APP_WF_POINT_SIZE
        );
        pos += APP_WF_POINT_SIZE;

        if (APP_ECSPI_Transfer(spi_tx, spi_rx, APP_SPI_TX_SIZE, APP_FOREVER_MS) != 0) {
            PANIC_("Cannot send ECSPI message");
        }
        PRINTF("SPI Write: TX: [");
        //APP_Print_Bytes(spi_tx, APP_SPI_TX_SIZE);
        PRINTF("], RX: [");
        //APP_Print_Bytes(spi_rx, APP_SPI_TX_SIZE);
        PRINTF("]\r\n");

        // FIXME: Use driver
        spi_tx[0] = 0xC0;
        memset(
            spi_tx + 1,
            0x00,
            APP_SPI_TX_SIZE - 1
        );

        if (APP_ECSPI_Transfer(spi_tx, spi_rx, APP_SPI_TX_SIZE, APP_FOREVER_MS) != 0) {
            PANIC_("Cannot send ECSPI message");
        }
        PRINTF("SPI Read: TX: [");
        //APP_Print_Bytes(spi_tx, APP_SPI_TX_SIZE);
        PRINTF("], RX: [");
        //APP_Print_Bytes(spi_rx, APP_SPI_TX_SIZE);
        PRINTF("]\r\n");

        if (buf != NULL) {
            // TODO: What 
        }
    }
}

int main(void) {
    /* Initialize board specified hardware. */
    hardware_init();

    PRINTF("\r\n\r\n");
    APP_INFO("Program start");

    wf_send_sem = xSemaphoreCreateBinary();
    wf_ready_sem = xSemaphoreCreateBinary();

    /* Initialize SPI */
    ASSERT(APP_ECSPI_Init(25000000) == 0);

    /* Create tasks. */
    xTaskCreate(
        APP_Task_Rpmsg, "RPMSG task",
        APP_TASK_STACK_SIZE, NULL, tskIDLE_PRIORITY + 1, NULL
    );

    /* Start FreeRTOS scheduler. */
    vTaskStartScheduler();

    /* Should never reach this point. */
    PANIC_("End of main()");
    return 0;
}
