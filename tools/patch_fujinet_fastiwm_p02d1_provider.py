from pathlib import Path
import argparse
import subprocess
import sys


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'Expected {label} pattern not found.')
    return text.replace(old, new, 1)


def replace_section(text: str, start: str, end: str, new: str, label: str) -> str:
    try:
        first = text.index(start)
        last = text.index(end, first)
    except ValueError as exc:
        raise SystemExit(f'Expected {label} section not found.') from exc
    return text[:first] + new + text[last:]


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            'Connect FujiNet to the configured raw-U8 TCP stream provider '
            'and serve ready-checked 16 KiB batches over the proven 2-us link.'
        )
    )
    parser.add_argument('--project-root', default='.')
    parser.add_argument('--firmware-root', required=True)
    args = parser.parse_args()

    project = Path(args.project_root).resolve()
    root = Path(args.firmware_root).resolve()
    base = project / 'tools' / 'patch_fujinet_fastiwm_p02d0_pcm.py'
    llcpp = root / 'lib' / 'bus' / 'iwm' / 'iwm_ll.cpp'
    buscpp = root / 'lib' / 'bus' / 'iwm' / 'iwm.cpp'
    if not base.is_file() or not llcpp.is_file() or not buscpp.is_file():
        raise SystemExit('Missing P0.2D0 transform or IWM sources.')

    ltext = llcpp.read_text(encoding='utf-8')
    btext = buscpp.read_text(encoding='utf-8')
    if 'FASTIWM D1 PROVIDER START' in btext:
        print('FujiNet P0.2D1 provider overlay already applied.')
        return
    if 'FASTIWM D0 PCM BURST ARMED' not in btext:
        subprocess.run(
            [
                sys.executable,
                str(base),
                '--project-root',
                str(project),
                '--firmware-root',
                str(root),
            ],
            check=True,
        )
        ltext = llcpp.read_text(encoding='utf-8')
        btext = buscpp.read_text(encoding='utf-8')
    if 'FASTIWM D0 PCM BURST ARMED' not in btext:
        raise SystemExit('P0.2D0 firmware transform did not apply.')

    ltext = replace_once(
        ltext,
        '''volatile bool fast_iwm_probe_burst_started = false;
#endif
''',
        '''volatile bool fast_iwm_probe_burst_started = false;
extern uint8_t fast_iwm_provider_pcm[512];
#endif
''',
        'provider PCM extern',
    )

    new_sender = '''error_is_true IRAM_ATTR iwm_sp_ll::iwm_send_fast_probe_spi()
{
  // D1 fits an exact 512-byte PCM packet into the 604-byte logical buffer:
  // 12 sync + marker + 586 encoded + 2 guard + zero terminator.
  memset(packet_buffer, 0, sizeof(packet_buffer));
  int p = 0;
  for (int i = 0; i < 12; i++)
    packet_buffer[p++] = 0xff;
  packet_buffer[p++] = 0xd5;
  packet_buffer[p++] = 0xaa;
  packet_buffer[p++] = 0x96;

  uint16_t pcm_index = 0;
  for (uint8_t group = 0; group < 73; group++)
  {
    uint8_t packed_msb = 0;
    for (uint8_t lane = 0; lane < 7; lane++)
    {
      const uint8_t pcm = fast_iwm_provider_pcm[pcm_index++];
      packet_buffer[p++] = 0x80 | (pcm & 0x7f);
      packed_msb |= static_cast<uint8_t>(((pcm >> 7) & 1U) << lane);
    }
    packet_buffer[p++] = 0x80 | packed_msb;
  }

  const uint8_t final_pcm = fast_iwm_provider_pcm[511];
  packet_buffer[p++] = 0x80 | (final_pcm & 0x7f);
  packet_buffer[p++] = 0x80 | ((final_pcm >> 7) & 1U);
  packet_buffer[p++] = 0xff;
  packet_buffer[p++] = 0xff;
  packet_buffer[p] = 0x00;

  if (p != 603)
    RETURN_ERROR_AS_TRUE();

  set_output_to_spi();
  int spi_len = encode_spi_packet();
  spi_transaction_t trans;
  memset(&trans, 0, sizeof(spi_transaction_t));
  trans.tx_buffer = spi_buffer;
  trans.length = spi_len * 8;

  esp_err_t acquire_ret = spi_device_acquire_bus(spifast, portMAX_DELAY);
  if (acquire_ret != ESP_OK)
    RETURN_ERROR_AS_TRUE();

  portDISABLE_INTERRUPTS();
  enable_output();
  esp_err_t ret = spi_device_polling_transmit(spifast, &trans);
  disable_output();
  portENABLE_INTERRUPTS();
  spi_device_release_bus(spifast);

  if (ret != ESP_OK)
    RETURN_ERROR_AS_TRUE();
  RETURN_SUCCESS_AS_FALSE();
}
'''
    ltext = replace_section(
        ltext,
        'error_is_true IRAM_ATTR iwm_sp_ll::iwm_send_fast_probe_spi()\n',
        '#endif\n\n#define IWM_NEXT_BIT()',
        new_sender,
        'D0 fast sender',
    )

    btext = replace_once(
        btext,
        '#include "fnSystem.h"\n',
        '''#include "fnSystem.h"
#include "fnConfig.h"
#include "fnTcpClient.h"
#include "fnWiFi.h"
#include "esp_heap_caps.h"
''',
        'provider includes',
    )

    old_probe_state_end = '''static uint32_t fast_iwm_probe_tx_count = 0;
static unsigned long fast_iwm_probe_arm_deadline = 0;
static unsigned long fast_iwm_probe_fallback_due = 0;
#endif
'''
    new_probe_state_end = '''static uint32_t fast_iwm_probe_tx_count = 0;
static unsigned long fast_iwm_probe_arm_deadline = 0;
static unsigned long fast_iwm_probe_fallback_due = 0;

uint8_t fast_iwm_provider_pcm[512];
static fnTcpClient fast_iwm_provider_client;
// Allocate four complete 16 KiB batches lazily in PSRAM.  Keeping this out of
// internal DRAM is mandatory: Wi-Fi initializes before the IIgs starts a
// provider session and needs its internal RX/control buffers intact.
static constexpr size_t fast_iwm_provider_fifo_size = 65536;
static uint8_t *fast_iwm_provider_fifo = nullptr;
static size_t fast_iwm_provider_head = 0;
static size_t fast_iwm_provider_tail = 0;
static size_t fast_iwm_provider_count = 0;
static bool fast_iwm_provider_enabled = false;
static bool fast_iwm_provider_connected = false;
static uint8_t fast_iwm_provider_state = 0;
static uint8_t fast_iwm_provider_error = 0;
static unsigned long fast_iwm_provider_next_connect = 0;
static unsigned long fast_iwm_provider_last_activity = 0;
static uint32_t fast_iwm_provider_bytes_received = 0;
static uint32_t fast_iwm_provider_packets_sent = 0;
static uint32_t fast_iwm_provider_batches_sent = 0;

static void fast_iwm_provider_close(bool disable)
{
  fast_iwm_provider_client.stop();
  fast_iwm_provider_connected = false;
  fast_iwm_provider_state = disable ? 0 : 1;
  if (disable)
    fast_iwm_provider_enabled = false;
  fast_iwm_provider_head = 0;
  fast_iwm_provider_tail = 0;
  fast_iwm_provider_count = 0;
}

static void fast_iwm_provider_pump()
{
  if (!fast_iwm_provider_connected)
    return;
  if (!fast_iwm_provider_client.connected())
  {
    fast_iwm_provider_client.stop();
    fast_iwm_provider_connected = false;
    fast_iwm_provider_state = 1;
    fast_iwm_provider_error = 4;
    fast_iwm_provider_next_connect = fnSystem.millis() + 1000UL;
    return;
  }

  if (fast_iwm_provider_fifo == nullptr)
    return;
  const size_t fifo_free =
      fast_iwm_provider_fifo_size - fast_iwm_provider_count;
  if (!fifo_free)
    return;
  size_t available = fast_iwm_provider_client.available();
  if (!available)
    return;
  size_t contiguous = fast_iwm_provider_fifo_size - fast_iwm_provider_head;
  size_t take = std::min(available, fifo_free);
  take = std::min(take, contiguous);
  take = std::min(take, static_cast<size_t>(8192));
  const int received = fast_iwm_provider_client.read(
      fast_iwm_provider_fifo + fast_iwm_provider_head, take);
  if (received > 0)
  {
    fast_iwm_provider_head =
        (fast_iwm_provider_head + static_cast<size_t>(received)) %
        fast_iwm_provider_fifo_size;
    fast_iwm_provider_count += static_cast<size_t>(received);
    fast_iwm_provider_bytes_received += static_cast<uint32_t>(received);
  }
}

static void fast_iwm_provider_service()
{
  if (!fast_iwm_provider_enabled)
    return;

  const unsigned long now = fnSystem.millis();
  if (!fast_iwm_provider_connected)
  {
    if (static_cast<int32_t>(now - fast_iwm_provider_next_connect) < 0)
      return;
    if (!fnWiFi.connected())
    {
      fast_iwm_provider_state = 1;
      fast_iwm_provider_error = 2;
      fast_iwm_provider_next_connect = now + 1000UL;
      return;
    }

    const std::string host = Config.get_network_netstream_host();
    int port = Config.get_network_netstream_port();
    if (port <= 0)
      port = 22510;
    if (host.empty())
    {
      fast_iwm_provider_state = 3;
      fast_iwm_provider_error = 1;
      fast_iwm_provider_next_connect = now + 1000UL;
      return;
    }

    fast_iwm_provider_state = 1;
    if (!fast_iwm_provider_client.connect(host.c_str(),
                                          static_cast<uint16_t>(port), 500))
    {
      fast_iwm_provider_state = 3;
      fast_iwm_provider_error = 3;
      fast_iwm_provider_next_connect = now + 1000UL;
      return;
    }
    fast_iwm_provider_client.setNoDelay(true);
    fast_iwm_provider_connected = true;
    fast_iwm_provider_state = 2;
    fast_iwm_provider_error = 0;
    Debug_printf("\\r\\nFASTIWM D1 PROVIDER CONNECTED host=%s port=%d",
                 host.c_str(), port);
  }

  fast_iwm_provider_pump();
}

static bool fast_iwm_provider_pop_packet()
{
  if (fast_iwm_provider_fifo == nullptr)
    return false;
  if (fast_iwm_provider_count < sizeof(fast_iwm_provider_pcm))
    return false;
  for (size_t copied = 0; copied < sizeof(fast_iwm_provider_pcm);)
  {
    size_t contiguous = fast_iwm_provider_fifo_size - fast_iwm_provider_tail;
    size_t take = std::min(sizeof(fast_iwm_provider_pcm) - copied, contiguous);
    memcpy(fast_iwm_provider_pcm + copied,
           fast_iwm_provider_fifo + fast_iwm_provider_tail, take);
    fast_iwm_provider_tail =
        (fast_iwm_provider_tail + take) % fast_iwm_provider_fifo_size;
    fast_iwm_provider_count -= take;
    copied += take;
  }
  return true;
}

static std::array<uint8_t, 512> fast_iwm_provider_status()
{
  std::array<uint8_t, 512> reply{};
  reply[0] = 'D'; reply[1] = '1'; reply[2] = 'F'; reply[3] = 'S';
  reply[4] = 1;
  reply[5] = fast_iwm_provider_state;
  reply[6] = fast_iwm_provider_error;
  reply[7] = fast_iwm_provider_connected ? 1 : 0;
  const uint16_t fifo = static_cast<uint16_t>(
      std::min(fast_iwm_provider_count, static_cast<size_t>(0xffff)));
  reply[8] = static_cast<uint8_t>(fifo);
  reply[9] = static_cast<uint8_t>(fifo >> 8);
  memcpy(reply.data() + 10, &fast_iwm_provider_bytes_received, 4);
  memcpy(reply.data() + 14, &fast_iwm_provider_packets_sent, 4);
  memcpy(reply.data() + 18, &fast_iwm_provider_batches_sent, 4);
  return reply;
}
#endif
'''
    btext = replace_once(
        btext,
        old_probe_state_end,
        new_probe_state_end,
        'provider state and service',
    )

    new_commands = '''#ifdef IIGS_FAST_IWM_PROBE
  static bool fast_iwm_probe_c3_banner_printed = false;
  static uint32_t fast_iwm_probe_c3_read_count = 0;
  if (!fast_iwm_probe_c3_banner_printed)
  {
    fast_iwm_probe_c3_banner_printed = true;
    Debug_printf("\\r\\nFASTIWM D1 PROVIDER BRIDGE ACTIVE start=7fa559 status=7fa558 arm=7fa55a stop=7fa557");
  }

  if (cmd.frame.sp_command == SP_CMD_READBLOCK)
  {
    const uint32_t block = static_cast<uint32_t>(cmd.frame.block_rw.num);
    fast_iwm_probe_c3_read_count++;
    if (block >= 0x7fa557 && block <= 0x7fa55a)
    {
      if (block == 0x7fa559)
      {
        fast_iwm_provider_close(false);
        if (fast_iwm_provider_fifo == nullptr)
          fast_iwm_provider_fifo = static_cast<uint8_t *>(heap_caps_malloc(
              fast_iwm_provider_fifo_size,
              MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
        if (fast_iwm_provider_fifo == nullptr)
        {
          fast_iwm_provider_enabled = false;
          fast_iwm_provider_state = 3;
          fast_iwm_provider_error = 8;
          Debug_printf("\\r\\nFASTIWM D1 PROVIDER PSRAM ALLOC FAILED bytes=%u",
                       (unsigned int)fast_iwm_provider_fifo_size);
        }
        else
        {
          fast_iwm_provider_enabled = true;
          fast_iwm_provider_state = 1;
          fast_iwm_provider_error = 0;
          fast_iwm_provider_next_connect = 0;
          fast_iwm_provider_last_activity = fnSystem.millis();
          Debug_printf("\\r\\nFASTIWM D1 PROVIDER START count=%lu fifo=PSRAM:%u",
                       (unsigned long)fast_iwm_probe_c3_read_count,
                       (unsigned int)fast_iwm_provider_fifo_size);
        }
      }
      else if (block == 0x7fa558)
      {
        fast_iwm_provider_last_activity = fnSystem.millis();
        fast_iwm_provider_service();
      }
      else if (block == 0x7fa557)
      {
        fast_iwm_provider_close(true);
        fast_iwm_probe_armed = false;
        fast_iwm_probe_request = false;
        fast_iwm_probe_burst_remaining = 0;
        fast_iwm_probe_burst_started = false;
        Debug_printf("\\r\\nFASTIWM D1 PROVIDER STOP packets=%lu batches=%lu",
                     (unsigned long)fast_iwm_provider_packets_sent,
                     (unsigned long)fast_iwm_provider_batches_sent);
      }
      else
      {
        fast_iwm_provider_service();
        if (fast_iwm_provider_connected && fast_iwm_provider_count >= 16384)
        {
          fast_iwm_probe_armed = true;
          fast_iwm_probe_reset_grace = 0;
          fast_iwm_probe_request = false;
          fast_iwm_probe_burst_index = 0;
          fast_iwm_probe_burst_remaining = 32;
          fast_iwm_probe_waiting_for_ready_low = false;
          fast_iwm_probe_burst_started = false;
          fast_iwm_probe_arm_count++;
          fast_iwm_probe_arm_deadline = fnSystem.millis() + 10000UL;
          fast_iwm_provider_last_activity = fnSystem.millis();
          Debug_printf("\\r\\nFASTIWM D1 READY ARMED count=%lu fifo=%u trigger=1011",
                       (unsigned long)fast_iwm_probe_arm_count,
                       (unsigned int)fast_iwm_provider_count);
          Debug_printf("\\r\\nFASTIWM D1 PROVIDER BATCH ARMED packets=32 pcm=16384");
        }
        else
        {
          fast_iwm_probe_armed = false;
          fast_iwm_provider_error = 5;
        }
      }

      const auto reply = fast_iwm_provider_status();
      transaction_accept(TRANS_STATE::NO_GET);
      transaction_send(reply.data(), reply.size());
      goto done;
    }
  }
#endif

'''
    function_start = btext.index('void systemBus::iwm_process')
    probe_start = btext.index('#ifdef IIGS_FAST_IWM_PROBE', function_start)
    normal_anchor = btext.index(
        '  // SmartPort doesn\'t allow sending payload with STATUS commands,',
        probe_start,
    )
    btext = btext[:probe_start] + new_commands + btext[normal_anchor:]

    service_start = btext.index('void IRAM_ATTR systemBus::service()')
    probe_start = btext.index('#ifdef IIGS_FAST_IWM_PROBE', service_start)
    probe_end = btext.index('#endif\n\n#ifndef DEV_RELAY_SLIP', probe_start)
    new_service = '''#ifdef IIGS_FAST_IWM_PROBE
  fast_iwm_provider_service();

  if (fast_iwm_probe_burst_started &&
      fast_iwm_probe_waiting_for_ready_low &&
      (smartport.iwm_phase_vector() == 0b1010))
  {
    fast_iwm_probe_waiting_for_ready_low = false;
    fast_iwm_probe_armed = true;
    fast_iwm_probe_arm_deadline = fnSystem.millis() + 10000UL;
  }

  if (fast_iwm_probe_armed &&
      (smartport.iwm_phase_vector() == 0b1011))
  {
    fast_iwm_probe_armed = false;
    fast_iwm_probe_arm_deadline = 0;
    fast_iwm_probe_request = true;
    fast_iwm_probe_burst_started = true;
    fast_iwm_probe_req_count++;
  }

  if (fast_iwm_probe_armed && fast_iwm_probe_arm_deadline &&
      (static_cast<int32_t>(fnSystem.millis() - fast_iwm_probe_arm_deadline) >= 0))
  {
    fast_iwm_probe_armed = false;
    fast_iwm_probe_request = false;
    fast_iwm_probe_burst_remaining = 0;
    fast_iwm_probe_waiting_for_ready_low = false;
    fast_iwm_probe_burst_started = false;
    fast_iwm_probe_arm_deadline = 0;
    Debug_printf("\\r\\nFASTIWM D1 ARM EXPIRED phase=%02x",
                 (unsigned int)smartport.iwm_phase_vector());
  }

  if (fast_iwm_probe_request)
  {
    if (!fast_iwm_provider_pop_packet())
    {
      fast_iwm_probe_request = false;
      fast_iwm_probe_armed = false;
      fast_iwm_probe_burst_remaining = 0;
      fast_iwm_probe_burst_started = false;
      fast_iwm_provider_error = 6;
      Debug_printf("\\r\\nFASTIWM D1 PROVIDER UNDERRUN fifo=%u",
                   (unsigned int)fast_iwm_provider_count);
      return;
    }

    fast_iwm_probe_request = false;
    const uint8_t packet_index = fast_iwm_probe_burst_index;
    fast_iwm_probe_tx_count++;
    if (packet_index == 0)
    {
      Debug_printf("\\r\\nFASTIWM D1 READY TRIGGER count=%lu phase=%02x fifo=%u",
                   (unsigned long)fast_iwm_probe_req_count,
                   (unsigned int)smartport.iwm_phase_vector(),
                   (unsigned int)fast_iwm_provider_count);
      Debug_printf("\\r\\nFASTIWM TX START packet=0 count=%lu",
                   (unsigned long)fast_iwm_probe_tx_count);
    }

    smartport.iwm_ack_set();
    error_is_true fast_err = smartport.iwm_send_fast_probe_spi();
    smartport.iwm_ack_set();
    if (fast_err)
    {
      fast_iwm_probe_armed = false;
      fast_iwm_probe_burst_remaining = 0;
      fast_iwm_probe_waiting_for_ready_low = false;
      fast_iwm_probe_burst_started = false;
      fast_iwm_provider_error = 7;
      Debug_printf("\\r\\nFASTIWM TX DONE packet=%u count=%lu err=1",
                   (unsigned int)packet_index,
                   (unsigned long)fast_iwm_probe_tx_count);
      return;
    }

    fast_iwm_provider_packets_sent++;
    if (fast_iwm_probe_burst_remaining)
      fast_iwm_probe_burst_remaining--;
    if (!fast_iwm_probe_burst_remaining)
    {
      fast_iwm_probe_armed = false;
      fast_iwm_probe_waiting_for_ready_low = false;
      fast_iwm_probe_burst_started = false;
      fast_iwm_probe_arm_deadline = 0;
      fast_iwm_provider_batches_sent++;
      Debug_printf("\\r\\nFASTIWM TX DONE packet=31 count=%lu err=0",
                   (unsigned long)fast_iwm_probe_tx_count);
      Debug_printf("\\r\\nFASTIWM D1 PROVIDER BATCH DONE batch=%lu packets=%lu fifo=%u err=0",
                   (unsigned long)fast_iwm_provider_batches_sent,
                   (unsigned long)fast_iwm_provider_packets_sent,
                   (unsigned int)fast_iwm_provider_count);
      return;
    }

    fast_iwm_probe_burst_index++;
    if (smartport.iwm_phase_vector() == 0b1010)
    {
      fast_iwm_probe_waiting_for_ready_low = false;
      fast_iwm_probe_armed = true;
      fast_iwm_probe_arm_deadline = fnSystem.millis() + 10000UL;
    }
    else
    {
      fast_iwm_probe_waiting_for_ready_low = true;
    }
    return;
  }
#endif'''
    btext = btext[:probe_start] + new_service + btext[probe_end + len('#endif'):]

    required = (
        '#include "fnTcpClient.h"',
        'FASTIWM D1 PROVIDER START',
        'FASTIWM D1 PROVIDER PSRAM ALLOC FAILED',
        'FASTIWM D1 PROVIDER CONNECTED',
        'FASTIWM D1 PROVIDER BATCH ARMED packets=32 pcm=16384',
        'FASTIWM D1 PROVIDER BATCH DONE',
        'FASTIWM TX START packet=0',
        'FASTIWM TX DONE packet=31',
        'fast_iwm_provider_fifo',
        'MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT',
        'Config.get_network_netstream_host()',
        'Config.get_network_netstream_port()',
        'fast_iwm_provider_pcm[512]',
        'group < 73',
        'p != 603',
        'fastcfg.clock_speed_hz = 2 * MHZ',
    )
    joined = ltext + '\n' + btext
    for marker in required:
        if marker not in joined:
            raise SystemExit(f'Missing P0.2D1 firmware marker: {marker}')
    for forbidden in (
        'FASTIWM D0 PCM BURST ARMED',
        'FASTIWM D0 PCM BURST DONE',
        '(sample_number % 255UL) + 1UL',
        'fast_iwm_probe_burst_remaining = 240',
    ):
        if forbidden in joined:
            raise SystemExit(f'Obsolete D0 firmware path remains: {forbidden}')

    llcpp.write_text(ltext, encoding='utf-8', newline='\n')
    buscpp.write_text(btext, encoding='utf-8', newline='\n')
    print('Applied FujiNet P0.2D1 TCP-provider bridge and 16 KiB batch transmitter.')


if __name__ == '__main__':
    main()
