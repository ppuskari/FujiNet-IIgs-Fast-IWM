from pathlib import Path
import argparse
import subprocess
import sys


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'Expected {label} pattern not found.')
    return text.replace(old, new, 1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            'Apply the proven P0.2C14 2-us transmitter, then add the P0.2C19 '
            '32-packet READY-low/READY-high burst protocol.'
        )
    )
    parser.add_argument('--project-root', default='.')
    parser.add_argument('--firmware-root', required=True)
    args = parser.parse_args()

    project = Path(args.project_root).resolve()
    root = Path(args.firmware_root).resolve()
    base = project / 'tools' / 'patch_fujinet_fastiwm_p02c14_pulse.py'
    llcpp = root / 'lib' / 'bus' / 'iwm' / 'iwm_ll.cpp'
    buscpp = root / 'lib' / 'bus' / 'iwm' / 'iwm.cpp'
    if not base.is_file() or not llcpp.is_file() or not buscpp.is_file():
        raise SystemExit('Missing P0.2C14 transform or IWM sources.')

    ltext = llcpp.read_text(encoding='utf-8')
    btext = buscpp.read_text(encoding='utf-8')
    if 'FASTIWM C19 BURST ARMED' in btext:
        print('FujiNet P0.2C19 burst overlay already applied.')
        return
    if 'FASTIWM C14 TX SHAPE' not in ltext:
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
    if 'FASTIWM C14 TX SHAPE' not in ltext:
        raise SystemExit('P0.2C14 firmware transform did not apply.')

    ltext = replace_once(
        ltext,
        '''volatile uint8_t fast_iwm_probe_reset_grace = 0; // P0.2C2 arm-hold
volatile uint32_t fast_iwm_probe_reset_hold_count = 0;
''',
        '''volatile uint8_t fast_iwm_probe_reset_grace = 0; // P0.2C2 arm-hold
volatile uint32_t fast_iwm_probe_reset_hold_count = 0;
volatile uint8_t fast_iwm_probe_burst_index = 0;
volatile uint8_t fast_iwm_probe_burst_remaining = 0;
volatile bool fast_iwm_probe_waiting_for_ready_low = false;
volatile bool fast_iwm_probe_burst_started = false;
''',
        'low-level burst state',
    )

    old_isr = '''  if (fast_iwm_probe_armed && (_phases == 0b1011))
  {
    fast_iwm_probe_armed = false;
    fast_iwm_probe_reset_grace = 0;
    fast_iwm_probe_request = true;
    fast_iwm_probe_req_count++;
    return;
  }

  // P0.2C10: ROM cleanup can emit more than one reset after the arm
  // response. Preserve an armed one-shot across every reset; normal service
  // context expires it after five seconds if the host never raises READY.
  if (_phases == 0b0101)
  {
    if (fast_iwm_probe_armed)
    {
      fast_iwm_probe_reset_hold_count++;
      smartport.iwm_ack_set();
      return;
    }

    fast_iwm_probe_reset_grace = 0;
    fast_iwm_probe_request = false;
    smartport.iwm_ack_set();
  }
'''
    new_isr = '''  // C19 inter-packet handshake: the host drops PH0 to 1010 after each
  // packet. Re-arm on that low edge before accepting the next 1011 READY.
  if (fast_iwm_probe_burst_started &&
      fast_iwm_probe_waiting_for_ready_low && (_phases == 0b1010))
  {
    fast_iwm_probe_waiting_for_ready_low = false;
    fast_iwm_probe_armed = true;
  }

  if (fast_iwm_probe_armed && (_phases == 0b1011))
  {
    fast_iwm_probe_armed = false;
    fast_iwm_probe_reset_grace = 0;
    fast_iwm_probe_request = true;
    fast_iwm_probe_burst_started = true;
    fast_iwm_probe_req_count++;
    return;
  }

  // ROM cleanup resets after the original 4-us arm must be preserved.
  // Once the private burst has begun, reset is an explicit abort.
  if (_phases == 0b0101)
  {
    if (fast_iwm_probe_armed && !fast_iwm_probe_burst_started)
    {
      fast_iwm_probe_reset_hold_count++;
      smartport.iwm_ack_set();
      return;
    }

    fast_iwm_probe_armed = false;
    fast_iwm_probe_reset_grace = 0;
    fast_iwm_probe_request = false;
    fast_iwm_probe_burst_remaining = 0;
    fast_iwm_probe_waiting_for_ready_low = false;
    fast_iwm_probe_burst_started = false;
    smartport.iwm_ack_set();
  }
'''
    ltext = replace_once(ltext, old_isr, new_isr, 'C14 READY/reset ISR')

    ltext = replace_once(
        ltext,
        '    packet_buffer[p++] = 0x80 | (i & 0x7f);\n',
        '    packet_buffer[p++] = 0x80 | ((i + fast_iwm_probe_burst_index) & 0x7f);\n',
        'C14 deterministic payload',
    )

    ltext = replace_once(
        ltext,
        '''  // C14 controlled A/B: retain the encoder-native one-sample pulse.
  // At the private 2-MHz SPI clock this is a 0.5-us pulse while falling
  // transitions remain separated by the required 2-us IWM bit cell.
  Debug_printf("\\r\\nFASTIWM C14 TX SHAPE len=%d cell=2us pulse=0.5us", spi_len);
  Debug_printf(
      "\\r\\nFASTIWM C14 TX ROUTE phase=%02x en35=%u d1=%u d2=%u hdsel=%u",
      (unsigned int)_phases,
      IWM_BIT(SP_EN35) ? 1U : 0U,
      IWM_BIT(SP_DRIVE1) ? 1U : 0U,
      IWM_BIT(SP_DRIVE2) ? 1U : 0U,
      IWM_BIT(SP_HDSEL) ? 1U : 0U);
''',
        '''  // C19 keeps C14's proven encoder-native 0.5-us pulse in a 2-us
  // cell. Per-packet serial output is deliberately absent from the timed
  // burst; the arm/first-trigger/final-summary messages bracket the run.
''',
        'C14 per-packet shape/route diagnostics',
    )
    ltext = replace_once(
        ltext,
        '''  Debug_printf("\\r\\nFASTIWM C5 BUS ACQUIRE START");
  esp_err_t acquire_ret = spi_device_acquire_bus(spifast, portMAX_DELAY);
  Debug_printf("\\r\\nFASTIWM C5 BUS ACQUIRE DONE ret=%d", (int)acquire_ret);
''',
        '''  esp_err_t acquire_ret = spi_device_acquire_bus(spifast, portMAX_DELAY);
''',
        'C14 per-packet bus acquire diagnostics',
    )
    ltext = replace_once(
        ltext,
        '''  spi_device_release_bus(spifast);
  Debug_printf("\\r\\nFASTIWM C5 BUS RELEASE ret=%d", (int)ret);
''',
        '''  spi_device_release_bus(spifast);
''',
        'C14 per-packet bus release diagnostics',
    )

    btext = replace_once(
        btext,
        '''extern volatile uint8_t fast_iwm_probe_reset_grace;
extern volatile uint32_t fast_iwm_probe_reset_hold_count;
''',
        '''extern volatile uint8_t fast_iwm_probe_reset_grace;
extern volatile uint32_t fast_iwm_probe_reset_hold_count;
extern volatile uint8_t fast_iwm_probe_burst_index;
extern volatile uint8_t fast_iwm_probe_burst_remaining;
extern volatile bool fast_iwm_probe_waiting_for_ready_low;
extern volatile bool fast_iwm_probe_burst_started;
''',
        'service burst externs',
    )

    btext = replace_once(
        btext,
        '''      fast_iwm_probe_armed = true;
      fast_iwm_probe_reset_grace = 0;
      fast_iwm_probe_request = false;
      fast_iwm_probe_arm_count++;
      fast_iwm_probe_arm_deadline = fnSystem.millis() + 10000UL;
      fast_iwm_probe_fallback_due = fnSystem.millis() + 3000UL;
''',
        '''      fast_iwm_probe_armed = true;
      fast_iwm_probe_reset_grace = 0;
      fast_iwm_probe_request = false;
      fast_iwm_probe_burst_index = 0;
      fast_iwm_probe_burst_remaining = 32;
      fast_iwm_probe_waiting_for_ready_low = false;
      fast_iwm_probe_burst_started = false;
      fast_iwm_probe_arm_count++;
      fast_iwm_probe_arm_deadline = fnSystem.millis() + 10000UL;
      fast_iwm_probe_fallback_due = 0;
''',
        'C14 arm state',
    )
    btext = replace_once(
        btext,
        '''      Debug_printf("\\r\\nFASTIWM C14 READY ARMED count=%lu trigger=1011",
                   (unsigned long)fast_iwm_probe_arm_count);
''',
        '''      Debug_printf("\\r\\nFASTIWM C19 READY ARMED count=%lu trigger=1011",
                   (unsigned long)fast_iwm_probe_arm_count);
      Debug_printf("\\r\\nFASTIWM C19 BURST ARMED packets=32 bytes=16384");
''',
        'C14 arm diagnostic',
    )

    service_start = btext.index('void IRAM_ATTR systemBus::service()')
    probe_start = btext.index('#ifdef IIGS_FAST_IWM_PROBE', service_start)
    probe_end = btext.index('#endif\n\n#ifndef DEV_RELAY_SLIP', probe_start)
    old_service = btext[probe_start:probe_end + len('#endif')]
    new_service = '''#ifdef IIGS_FAST_IWM_PROBE
  // Catch a READY-low edge even if the GPIO ISR was missed. The host holds
  // 1010 throughout its 512-byte validator, providing a deterministic
  // re-arm window before the next 1011 edge.
  if (fast_iwm_probe_burst_started &&
      fast_iwm_probe_waiting_for_ready_low &&
      (smartport.iwm_phase_vector() == 0b1010))
  {
    fast_iwm_probe_waiting_for_ready_low = false;
    fast_iwm_probe_armed = true;
    fast_iwm_probe_arm_deadline = fnSystem.millis() + 10000UL;
  }

  // Polling backs up the edge ISR without introducing a transmit timer.
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
    fast_iwm_probe_reset_grace = 0;
    fast_iwm_probe_arm_deadline = 0;
    Debug_printf("\\r\\nFASTIWM C19 ARM EXPIRED phase=%02x held_resets=%lu",
                 (unsigned int)smartport.iwm_phase_vector(),
                 (unsigned long)fast_iwm_probe_reset_hold_count);
  }

  if (fast_iwm_probe_request)
  {
    fast_iwm_probe_request = false;
    const uint8_t packet_index = fast_iwm_probe_burst_index;
    fast_iwm_probe_tx_count++;

    if (packet_index == 0)
    {
      Debug_printf("\\r\\nFASTIWM C19 READY TRIGGER count=%lu phase=%02x",
                   (unsigned long)fast_iwm_probe_req_count,
                   (unsigned int)smartport.iwm_phase_vector());
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
      Debug_printf("\\r\\nFASTIWM TX DONE packet=%u count=%lu err=1",
                   (unsigned int)packet_index,
                   (unsigned long)fast_iwm_probe_tx_count);
      return;
    }

    if (fast_iwm_probe_burst_remaining)
      fast_iwm_probe_burst_remaining--;

    if (!fast_iwm_probe_burst_remaining)
    {
      fast_iwm_probe_armed = false;
      fast_iwm_probe_waiting_for_ready_low = false;
      fast_iwm_probe_burst_started = false;
      fast_iwm_probe_arm_deadline = 0;
      Debug_printf("\\r\\nFASTIWM TX DONE packet=31 count=%lu err=0",
                   (unsigned long)fast_iwm_probe_tx_count);
      Debug_printf("\\r\\nFASTIWM C19 BURST DONE packets=32 bytes=16384");
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
        'FASTIWM C19 READY ARMED',
        'FASTIWM C19 READY TRIGGER',
        'FASTIWM TX START',
        'FASTIWM TX DONE',
        'FASTIWM C19 BURST ARMED packets=32 bytes=16384',
        'FASTIWM C19 BURST DONE packets=32 bytes=16384',
        'fast_iwm_probe_burst_index',
        'fast_iwm_probe_burst_remaining',
        'fast_iwm_probe_waiting_for_ready_low',
        'fast_iwm_probe_burst_started',
        '((i + fast_iwm_probe_burst_index) & 0x7f)',
        'fastcfg.clock_speed_hz = 2 * MHZ',
    )
    joined = ltext + '\n' + btext
    for marker in required:
        if marker not in joined:
            raise SystemExit(f'Missing P0.2C19 firmware marker: {marker}')
    for forbidden in (
        'FASTIWM C14 READY ARMED',
        'FASTIWM C14 READY TRIGGER',
        'FASTIWM C14 READY FALLBACK',
        'spi_buffer[i] |= (spi_buffer[i] >> 1)',
    ):
        if forbidden in joined:
            raise SystemExit(f'Obsolete firmware path remains: {forbidden}')

    llcpp.write_text(ltext, encoding='utf-8', newline='\n')
    buscpp.write_text(btext, encoding='utf-8', newline='\n')
    print('Applied FujiNet P0.2C19 32-packet burst transmitter overlay.')


if __name__ == '__main__':
    main()
