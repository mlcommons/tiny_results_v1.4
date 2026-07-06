/*
Copyright 2020 EEMBC and The MLPerf Authors. All Rights Reserved.
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at
    http://www.apache.org/licenses/LICENSE-2.0
Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

This file reflects a modified version of th_lib from EEMBC. The reporting logic
in th_results is copied from the original in EEMBC.
==============================================================================*/
/// \file
/// \brief C++ implementations of submitter_implemented.h

#include <stdio.h>
#include <string.h>

#include "colibry_board.hpp"

#include "api/submitter_implemented.h"
#include "api/internally_implemented.h"


#define CHIP_VDD_VOLTAGE             1.2
#define HFCLK_FREQUENCY_MHZ          300

#define APB_CLK_DIV                   12
#define NNPA_CLK_DIV                   1
#define I2C_SW_HALF_PERIOD_US          2

#define BITSTREAM_FLASH_ADDR    0x100000

#define APP_SPI_LFCLK_DIS_OPCODE    0x20

#if EE_CFG_ENERGY_MODE == 1
#define UART_PRINTF_BAUDRATE        9600
#else
#define UART_PRINTF_BAUDRATE      115200
#endif

#define UART_DMA_CHANNEL               3
#define NNPA_DMA_CHANNEL               0

char uart_tx_data[50];

extern const int __sram_user_start;
extern const int __sram_buffer_size;

const int sram_buffers_size = (int)&__sram_buffer_size;

volatile uint8_t nnpa_inference_done = 0;
volatile uint8_t dma_extflash_to_nnpa_done = 0;

uint32_t nb_sram_buffers_used;
uint32_t input_data_word;

volatile uint8_t rx_char_ready;

uint8_t input[1][MAX_DB_INPUT_SIZE];

ColibryBoard colibryBoard;

board_init_cfg_t board_init_cfg;

irq_handler_t uart_irq_handler(void)
{
  rx_char_ready = 1;
}

irq_handler_t nnpa_irq_handler(void)
{
  nnpa_inference_done = 1;
  NNPA_reg->nnpa_int_clear.word = EVT_EXEC_END_MASK;
}

irq_handler_t dma_irq_handler(void)
{
  if (colibryDMA->done_evt_get(NNPA_DMA_CHANNEL) == 1){
    dma_extflash_to_nnpa_done = 1;
    colibryDMA->evt_clear(NNPA_DMA_CHANNEL);

    // Initialize NNPA
    //
    NNPA_reg->nnpa_control.fields.cpu_mem_access = 0;
    if (NNPA_reg->rd_model_size.word > 20000 || NNPA_reg->rd_model_size.word < 10)
    {
      th_printf("e-[No bitstream seems in extflash. Exiting]\r\n");
      exit(1);
    }
    NNPA_reg->nnpa_trig_control.word = CONFIG_CHECK_MASK;
    while (NNPA_reg->nnpa_int_status.fields.evt_config_check_end == 0);
    if (NNPA_reg->nnpa_status.fields.config_check_ok != 1)
    {
      th_printf("e-[Bitstream CRC not correct. Exiting]\r\n");
      exit(1);
    }
    colibryBoard.nnpa_allocate_buffers();

    // Optimize power consumption
    //
    colibryBoard.extflash_power_disable();
    colibryBoard.configure_lowpower_io();

  #if EE_CFG_ENERGY_MODE == 1
    // Keep only needed peripheral clocks
    //
    colibrySCU->regmap->scu_periph_clk_en.word = SCU_APB_CLK_EN_MASK | 
                                                SCU_UART_CLK_EN_MASK | SCU_DBGM_CLK_EN_MASK | SCU_NNPA_CLK_EN_MASK | SCU_PORT_CLK_EN_MASK;

  #else
    // Keep only needed peripheral clocks
    //
    colibrySCU->regmap->scu_periph_clk_en.word = SCU_APB_CLK_EN_MASK | SCU_RTC_CLK_EN_MASK | SCU_DMA_CLK_EN_MASK |
                                                SCU_UART_CLK_EN_MASK | SCU_DBGM_CLK_EN_MASK | SCU_NNPA_CLK_EN_MASK | SCU_PORT_CLK_EN_MASK;
  #endif
  }
}

// ------------------------------------------------------

// Implement this method to prepare for inference and preprocess inputs.
void th_load_tensor()
{
  // Wait for the bitstream to copied into nnpa memory
  //
  while (dma_extflash_to_nnpa_done == 0){
  }
  
  // Get input data
  //
  size_t bytes = ee_get_buffer((uint8_t *)input[0],
                               MAX_DB_INPUT_SIZE);

  if (bytes / sizeof(uint8_t) != MAX_DB_INPUT_SIZE)
  {
    th_printf("Input db has %d elements, expected %d\n\r",
              bytes / sizeof(uint8_t), MAX_DB_INPUT_SIZE);
    return;
  }

  // Input data loading through the INPUT LOADER
  //
  NNPA_reg->nnpa_control.fields.cpu_mem_access = 1;
  NNPA_reg->input_loader_cfg.word = (3 << LOADER_NBYTE_VALID_OFFSET) |
                                    (0 << LOADER_NBIT_MODE_OFFSET) |
                                    (0 << LOADER_SIGNED_DATA_OFFSET);
  NNPA_reg->nnpa_trig_control.word = INPUT_LOADER_RST_MASK;

  for (int i = 0; i < MAX_DB_INPUT_SIZE / 4; i++)
  {
    // th_printf("%d,",input[0][i*4]);
    // th_printf("%d,",input[0][i*4+1]);
    // th_printf("%d,",input[0][i*4+2]);
    // th_printf("%d,",input[0][i*4+3]);
    // input_data_word = (input_data[0][i*4 + 3] << 24) | (input_data[0][i*4 + 2] << 16) |
    //                   (input_data[0][i*4 + 1] << 8) | input_data[0][i*4];
    input_data_word = *(uint32_t *)(input[0] + i * 4);

    NNPA_reg->input_loader_data.word = input_data_word;
  }
}

static float fast_exp(float x)
{
  return 1.0f + x + (x * x * 0.5f) + (x * x * x * 0.16666666f);
}

int softmax(const float *input, float *output, size_t len)
{
  if (input == NULL || output == NULL || len == 0)
  {
    return -1;
  }
  float max = input[0];

  for (size_t i = 1; i < len; i++)
  {
    if (input[i] > max)
    {
      max = input[i];
    }
  }

  float sum = 0.0f;

  for (size_t i = 0; i < len; i++)
  {
    float x = input[i] - max;

    if (x < -10.0f)
    {
      x = -10.0f;
    }

    output[i] = fast_exp(x);
    sum += output[i];
  }

  if (sum <= 0.0f)
  {
    return -1;
  }

  for (size_t i = 0; i < len; i++)
  {
    output[i] /= sum;
  }

  return 0;
}

float DequantizeUInt8ToFloat(uint8_t value, float scale, int16_t zero_point) {
  return static_cast<float>(value + zero_point) * scale;
}

// Add to this method to return real inference results.
void th_results()
{
  /**
   * The results need to be printed back in exactly this format;
   */
  th_printf("m-results-[");
  uint32_t nn_output_addr;
  uint8_t *ptr;
  uint8_t kCategoryCount = 2;
  float output[kCategoryCount];
  float output_softmax[kCategoryCount];

  // Get outputs
  //
  NNPA_reg->nnpa_control.fields.cpu_mem_access = 1;
  nn_output_addr = NNPA_NBYTE_PER_MEM_WORD * NNPA_reg->ofmap_start_maddr.word + NNPAMEM_BASE_ADDR;
  ptr = (uint8_t *)nn_output_addr;

  float output_scale = (float)NNPA_reg->rd_output_scaling.word / 65536.0f;
  int16_t output_zero_point = NNPA_reg->rd_output_offset.word >> 8; 

  // Dequantize
  //
  for (uint8_t i = 0; i < kCategoryCount; i++) {
    output[i] = DequantizeUInt8ToFloat(ptr[i], output_scale, output_zero_point);
  }

  // Softmax
  //
  softmax(output, output_softmax, kCategoryCount);

  // Print
  //
  for (uint8_t i = 0; i < kCategoryCount; i++) {
    th_printf("%0.3f", output_softmax[i]);
    if (i < (kCategoryCount - 1)) {
      th_printf(",");
    }
  }
  th_printf("]\r\n");
}

// Implement this method with the logic to perform one inference cycle.
void th_infer()
{

#if EE_CFG_ENERGY_MODE == 1
  while (UART_reg->uart_status.fields.uart_tx_busy == 1) // Avoid conflict after a warmup
  {
  }
  NNPA_reg->nnpa_control.fields.cpu_mem_access = 0;
  NNPA_reg->nnpa_trig_control.word = RUN_START_MASK;
  // UART_reg->uart_irq_ctrl.fields.uart_irq_rx_enable = 0; // Disable UART interrupt
  colibryBoard.enter_low_power(0xFF);
  // UART_reg->uart_irq_ctrl.word = UART_IRQ_RX_ENABLE_MASK;
#else
  NNPA_reg->nnpa_control.fields.cpu_mem_access = 0;
  NNPA_reg->nnpa_trig_control.word = RUN_START_MASK;
  colibryBoard.enter_low_power(3);
#endif
}

void th_timestamp(void)
{
  while (UART_reg->uart_status.fields.uart_tx_busy == 1) // Avoid conflict
  {
  }
#if EE_CFG_ENERGY_MODE == 1
  colibryPORT->dio_out_val_set(SPIS_SCK_DIO, PORT_LEVEL_HIGH); // Falling edge
  colibrySCU->delay_us(40);
  colibryPORT->dio_out_val_set(SPIS_SCK_DIO, PORT_LEVEL_LOW);
#else
  
  colibryUART->uart_tx_enable_set(0);
  colibryDMA->evt_clear(UART_DMA_CHANNEL);

  uint64_t microSeconds = ((uint64_t)colibryRTC->rtc_cnt_val_get() * 1000000) / colibrySCU->get_ext_lf_clk_freq();

  /* This message must NOT be changed. */
  int n = sprintf(uart_tx_data, EE_MSG_TIMESTAMP, microSeconds);
  colibryDMA->dma_len_set(UART_DMA_CHANNEL, n - 1);
  colibryDMA->dma_start(UART_DMA_CHANNEL);
  colibryUART->uart_tx_enable_set(1);

  // th_printf(EE_MSG_TIMESTAMP, microSeconds);
#endif
}

void th_printf(const char *p_fmt, ...)
{
#if EE_CFG_ENERGY_MODE == 1
#else
  colibryDMA->dma_wait_for_end_of_job(UART_DMA_CHANNEL); // Avoid conflict
#endif
  va_list args;
  va_start(args, p_fmt);
  (void)th_vprintf(p_fmt, args); /* ignore return */
  va_end(args);
}

char th_getchar()
{
  uint8_t data_rxtx = 0;
  while (!(data_rxtx >= 'A' && data_rxtx <= 'z') && !(data_rxtx >= '0' && data_rxtx <= '9') && (data_rxtx != '%') && (data_rxtx != ' ')){
    while (rx_char_ready != 1)
    {
    }
    data_rxtx = UART_reg->uart_rx_pop.word;
    UART_reg->uart_rx_pop.word;
  }
  
  rx_char_ready = 0;
  return data_rxtx;
}

void th_serialport_initialize(void)
{

  // Initialize the board and peripherals
  //
  board_init_cfg.vdd_setting = CHIP_VDD_VOLTAGE;
  board_init_cfg.hfclk_freq_mhz = HFCLK_FREQUENCY_MHZ;
  board_init_cfg.apb_clk_fdiv = APB_CLK_DIV;
  board_init_cfg.nnpa_clk_fdiv = NNPA_CLK_DIV;
  board_init_cfg.spim0_csn_margin = 1;

  I2CmSw i2cm_sw(I2C_SW_HALF_PERIOD_US);
  Tps6286x tps6286x(&i2cm_sw);

  //-----------------------------------------------------------------------------------------------//
  // Initializations
  //-----------------------------------------------------------------------------------------------//

  colibrySCU->regmap->scu_periph_clk_en.word = 0xFFFFFFFF;
  colibrySCU->set_hf_clk_freq(INITIAL_HFCLK_FREQ * 1e6);
  colibrySCU->delay_ms(10);

  // I2C DIO for software I2C
  //
  colibryPORT->dio_cfg_in(I2C_SDA_DIO);
  colibryPORT->dio_cfg_none(I2C_SCL_DIO);

  // VDD voltage
  //
  colibrySCU->regmap->pll_cal_bypass.word = 0x0001;  // Use lowest internal frequency
  tps6286x.set_vo1_voltage(board_init_cfg.vdd_setting);
  colibrySCU->delay_ms(300);

  // LF clock
  //
  colibryPORT->regmap->port_lfxo_cfg.word = LFXO_MODE_EXT_CLOCK;

  // HF_CLK clock
  //
#if defined(__BOARD_IOT_REV0)
  colibryPORT->regmap->port_hfxo_cfg.word = HFXO_MODE_EXT_CLOCK;
  colibrySCU->configure_hf_clk(HFCLK_PLL_OPENLOOP_CALIBRATED,
                               0,
                               16384,
                               board_init_cfg.vdd_setting,
                               board_init_cfg.hfclk_freq_mhz);

  colibrySCU->delay_ms(10);  // Wait for the end of calibration
  colibryPORT->regmap->port_hfxo_cfg.word = HFXO_MODE_OFF;
  
#elif defined(__BOARD_EVBTINY_REV0)
  colibryPORT->dio_cfg_out(EXT_HFCLK_EN_DIO);
  colibryPORT->dio_out_val_set(EXT_HFCLK_EN_DIO, 0);
  colibryPORT->regmap->port_hfxo_cfg.word = HFXO_MODE_EXT_CLOCK;
  colibrySCU->configure_hf_clk(HFCLK_PLL_OPENLOOP_CALIBRATED,
                               0,
                               16384,
                               board_init_cfg.vdd_setting,
                               board_init_cfg.hfclk_freq_mhz);

  colibrySCU->delay_ms(10);  // Wait for the end of calibration
  colibryPORT->regmap->port_hfxo_cfg.word = HFXO_MODE_OFF;
#else
  colibryPORT->regmap->port_hfxo_cfg.word = HFXO_MODE_EXT_CLOCK;
  colibrySCU->configure_hf_clk(HFCLK_PLL_OPENLOOP_CALIBRATED,
                               0,
                               16384,
                               board_init_cfg.vdd_setting,
                               board_init_cfg.hfclk_freq_mhz);

  colibrySCU->delay_ms(10);  // Wait for the end of calibration
  colibryPORT->regmap->port_hfxo_cfg.word = HFXO_MODE_OFF;
#endif

  // Derived clocks
  //
  colibrySCU->regmap->scu_apb_clk_cfg.word = board_init_cfg.apb_clk_fdiv - 1;
  colibrySCU->regmap->scu_nnpa_clk_cfg.word = board_init_cfg.nnpa_clk_fdiv - 1;
  colibrySCU->delay_ms(1);

  // Printf over UART
  //
  /* UART peripheral initialization for Colibry chip */
  PORT_reg->port_dio_cfg[UART_RX_DIO].fields.port_dio_function = 1; // Alternate1 = UART_RX
  PORT_reg->port_dio_cfg[UART_TX_DIO].fields.port_dio_function = 1; // Alternate1 = UART_TX
  uint32_t cpu_freq = colibrySCU->get_apb_clk_freq();
  uint32_t uart_div;

  uart_div = (cpu_freq / (UART_PRINTF_BAUDRATE*2)) - 1;

  colibryUART->uart_prescaler_set(1);
  colibryUART->uart_clk_div_set(uart_div);
  colibryUART->uart_rx_enable_set(1);
  colibryUART->uart_tx_enable_set(1);
  colibryUART->uart_ascii_mode_set(0);

  PORT_reg->port_dio_cfg[UART_RX_DIO].fields.port_dio_in_cfg = 1;
  PORT_reg->port_dio_cfg[UART_TX_DIO].fields.port_dio_drive = 2;
  
  // UART interrupt configuration
  UART_reg->uart_irq_ctrl.word = UART_IRQ_RX_ENABLE_MASK;
  UART_reg->uart_irq_ctrl.fields.uart_irq_rx_threshold = 0;

  // Disable sensors
  //
  colibryBoard.sensors_power_disable();

  // Board user led
  //
  ENABLE_USER_LED_DIO();
  USER_LED_OFF();

  // Reset some peripherals before starting
  //
  colibrySCU->regmap->scu_periph_reset.word = SCU_ISP_RESET_MASK | SCU_CAMIF_RESET_MASK | SCU_NNPA_RESET_MASK;
  colibrySCU->regmap->scu_periph_reset.word = 0;

  // SPIM_RF -- interface to nRF
  //
  colibrySPIM0->spim_set_config(SPIM_RF_SCK_DIO,
                                SPIM_RF_MISO_DIO,
                                SPIM_RF_MOSI_DIO,
                                SPIM_RF_CSN_DIO,
                                SPIM_RF_CSN_INDEX,
                                0,      // cpol
                                0,      // cpha
                                1,      // tx_only
                                4000000 // sck frequency (8 MHz max for nRF)
  );

  // Set LFCLK frequency
  //
  colibrySCU->set_ext_lf_clk_freq(16384);
}

void th_timestamp_initialize(void)
{
#if EE_CFG_ENERGY_MODE == 1
  // Request to disable the LFCLK on nRF
  //
  colibryBoard.spim0_tx_buff[0] = APP_SPI_LFCLK_DIS_OPCODE;
  colibryBoard.spim0_exchange(1);

  // Optimize power consumption
  //
  colibryPORT->regmap->port_lfxo_cfg.word = LFXO_MODE_OFF;

  // Initialise timestamp pin
  //
  colibryPORT->dio_cfg_func(SPIS_SCK_DIO, PORT_FUNC_GPIO);
  colibryPORT->regmap->port_dio_cfg[SPIS_SCK_DIO].word = PORT_DIO_OUT_EN_MASK | (2 << PORT_DIO_DRIVE_OFFSET);
  colibryPORT->dio_out_val_set(SPIS_SCK_DIO, PORT_LEVEL_LOW);

#else
  colibryRTC->rtc_cnt_enable_set(1);

  // Initialise DMA transfer
  //
  colibryUART->uart_tx_enable_set(0);
  colibryUART->uart_dma_mode_set(1);
  colibryDMA->dma_periph_dst_en_set(UART_DMA_CHANNEL, 1);
  colibryDMA->dma_periph_dst_id_set(UART_DMA_CHANNEL, DMA_TRIGGER_ID_UART);
  colibryDMA->dma_dst_width_set(UART_DMA_CHANNEL, 0); // 1 byte
  colibryDMA->dma_dst_set(UART_DMA_CHANNEL, (uint32_t)&UART_reg->uart_tx_push.word);
  colibryDMA->dma_src_set(UART_DMA_CHANNEL, (uint32_t)uart_tx_data);
  colibryDMA->dma_priority_set(UART_DMA_CHANNEL, 1); // Higher priority than NNPA_DMA_CHANNEL
  colibryUART->uart_tx_enable_set(1);
#endif

  /* This message must NOT be changed. */
  th_printf(EE_MSG_TIMESTAMP_MODE);

  #if EE_CFG_ENERGY_MODE == 1
  #else
  th_timestamp();
  #endif
}

void th_final_initialize(void)
{
  uint32_t *mmap_ptr;
  uint32_t model_size_word;
  NNPA_reg->nnpa_control.fields.cpu_mem_access = 1;
  mmap_ptr = (uint32_t *) (EXTF_BASE_ADDR + BITSTREAM_FLASH_ADDR);
  model_size_word = ((*mmap_ptr >> 16) & 0xFFFF) * 4;  // Four 32-bit words per NNPA_MEM word

  // Download bitstream from external flash with DMA
  //
  colibryDMA->dma_src_width_set(NNPA_DMA_CHANNEL, 2);  // Receive bytes
  colibryDMA->dma_src_set(NNPA_DMA_CHANNEL, (uint32_t) EXTF_BASE_ADDR + BITSTREAM_FLASH_ADDR);
  colibryDMA->dma_dst_set(NNPA_DMA_CHANNEL, (uint32_t) NNPAMEM_BASE_ADDR);
  colibryDMA->dma_len_set(NNPA_DMA_CHANNEL, model_size_word * 4 - 1);

  colibryDMA->dma_start(NNPA_DMA_CHANNEL);

  // IRQ enabling
  //
  NNPA_reg->nnpa_int_en.word = EVT_EXEC_END_MASK;
  colibryDMA->done_irq_enable(NNPA_DMA_CHANNEL);

  /// Powering down some unused SRAM and NNPA memory buffers
  // NNPA_reg->nnpa_control.fields.manual_buff_pd = 1;
  // NNPA_reg->mem_buff_pd0.word = 0xFFFFFFFF;
  // NNPA_reg->mem_buff_pd1.word = 0xFFFF0000;
  nb_sram_buffers_used = ((uint32_t)&__sram_user_start - 0x10000000) / sram_buffers_size + 1;
  colibrySCU->regmap->sram_cuts_pd_ctrl.word = (uint32_t)~((1 << nb_sram_buffers_used) - 1);

  // Optimize power consumption
  //
  colibryPORT->regmap->port_dio_cfg[JTAG_TCK_DIO].word |= PORT_DIO_PULL_EN_MASK;
  colibryPORT->regmap->port_dio_cfg[JTAG_TMS_DIO].word |= PORT_DIO_PULL_EN_MASK;
  colibryPORT->regmap->port_dio_cfg[JTAG_TDI_DIO].word |= PORT_DIO_PULL_EN_MASK;
}

void th_pre() {}

void th_post() {}

void th_command_ready(char volatile *p_command)
{
  colibryUART->uart_clear_rx_fifo();
  p_command = p_command;
  ee_serial_command_parser_callback((char *)p_command);
}

// th_libc implementations.
int th_strncmp(const char *str1, const char *str2, size_t n)
{
  size_t i = 0;

  while (i < n && str1[i] != '\0' && str2[i] != '\0')
  {
    if (str1[i] != str2[i])
      return (unsigned char)str1[i] - (unsigned char)str2[i];
    i++;
  }

  if (i == n)
    return 0;

  return (unsigned char)str1[i] - (unsigned char)str2[i];
}

char *th_strncpy(char *dest, const char *src, size_t n)
{
  size_t i;

  for (i = 0; i < n && src[i] != '\0'; i++)
    dest[i] = src[i];

  for (; i < n; i++)
    dest[i] = '\0';

  return dest;
}

size_t th_strnlen(const char *str, size_t maxlen)
{
  size_t i = 0;

  while (i < maxlen && str[i] != '\0')
    i++;

  return i;
}

char *th_strcat(char *dest, const char *src) { return strcat(dest, src); }

/* helper: check if char is separator */
static int is_sep(char c, const char *sep)
{
  size_t i = 0;

  while (sep[i] != '\0')
  {
    if (c == sep[i])
      return 1;
    i++;
  }

  return 0;
}

char *th_strtok(char *str1, const char *sep)
{
  static char *next;
  char *start;

  if (str1 != NULL)
    next = str1;

  if (next == NULL)
    return NULL;

  while (*next && is_sep(*next, sep))
    next++;

  if (*next == '\0')
  {
    next = NULL;
    return NULL;
  }

  start = next;

  while (*next && !is_sep(*next, sep))
    next++;

  if (*next)
  {
    *next = '\0';
    next++;
  }
  else
  {
    next = NULL;
  }

  return start;
}

int th_atoi(const char *str)
{
  int sign = 1;
  int result = 0;

  while (*str == ' ' || *str == '\t' || *str == '\n')
    str++;

  if (*str == '-')
  {
    sign = -1;
    str++;
  }
  else if (*str == '+')
  {
    str++;
  }

  while (*str >= '0' && *str <= '9')
  {
    result = result * 10 + (*str - '0');
    str++;
  }

  return sign * result;
}

void *th_memset(void *b, int c, size_t len)
{
  return memset(b, c, len);
}

void *th_memcpy(void *dst, const void *src, size_t n)
{
  return memcpy(dst, src, n);
}

int th_vprintf(const char *format, va_list ap)
{
  return vprintf(format, ap);
}
