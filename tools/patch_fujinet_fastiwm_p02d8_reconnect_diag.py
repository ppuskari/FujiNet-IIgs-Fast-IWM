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
            'Keep transient provider reconnects non-terminal, preserve queued '
            'PCM, and report D8 reconnect/duplicate-control telemetry.'
        )
    )
    parser.add_argument('--project-root', default='.')
    parser.add_argument('--firmware-root', required=True)
    args = parser.parse_args()

    project = Path(args.project_root).resolve()
    root = Path(args.firmware_root).resolve()
    base = project / 'tools' / 'patch_fujinet_fastiwm_p02d7_isr_guard.py'
    buscpp = root / 'lib' / 'bus' / 'iwm' / 'iwm.cpp'
    llcpp = root / 'lib' / 'bus' / 'iwm' / 'iwm_ll.cpp'
    if not base.is_file() or not buscpp.is_file() or not llcpp.is_file():
        raise SystemExit('Missing P0.2D7 transform or IWM sources.')

    btext = buscpp.read_text(encoding='utf-8')
    if 'FASTIWM D8 ENDPOINT SET' in btext:
        print('FujiNet P0.2D8 reconnect overlay already applied.')
        return
    if 'FASTIWM D7 ENDPOINT SET' not in btext:
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
        btext = buscpp.read_text(encoding='utf-8')
    if 'FASTIWM D7 ENDPOINT SET' not in btext:
        raise SystemExit('P0.2D7 firmware transform did not apply.')

    btext = replace_once(
        btext,
        '''static uint16_t fast_iwm_provider_port = 22510;

static void fast_iwm_provider_close(bool disable)
''',
        '''static uint16_t fast_iwm_provider_port = 22510;
static uint32_t fast_iwm_provider_disconnects = 0;
static uint32_t fast_iwm_provider_reconnects = 0;
static uint32_t fast_iwm_provider_control_retries = 0;
static bool fast_iwm_provider_had_connection = false;

static void fast_iwm_provider_close(bool disable)
''',
        'provider telemetry state',
    )

    btext = replace_once(
        btext,
        '''  if (!fast_iwm_provider_client.connected())
  {
    fast_iwm_provider_client.stop();
    fast_iwm_provider_connected = false;
    fast_iwm_provider_state = 1;
    fast_iwm_provider_error = 4;
    fast_iwm_provider_next_connect = fnSystem.millis() + 1000UL;
    return;
  }
''',
        '''  if (!fast_iwm_provider_client.connected())
  {
    fast_iwm_provider_client.stop();
    fast_iwm_provider_connected = false;
    fast_iwm_provider_state = 1;
    fast_iwm_provider_error = 4;
    fast_iwm_provider_disconnects++;
    fast_iwm_provider_next_connect = fnSystem.millis() + 250UL;
    Debug_printf("\\r\\nFASTIWM D8 PROVIDER LOST disconnects=%lu fifo=%u retry_ms=250",
                 (unsigned long)fast_iwm_provider_disconnects,
                 (unsigned int)fast_iwm_provider_count);
    return;
  }
''',
        'provider disconnect handling',
    )

    btext = replace_once(
        btext,
        '''    if (!fast_iwm_provider_client.connect(host.c_str(),
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
    Debug_printf("\\r\\nFASTIWM D7 PROVIDER CONNECTED host=%s port=%d",
                 host.c_str(), port);
''',
        '''    if (!fast_iwm_provider_client.connect(host.c_str(),
                                          static_cast<uint16_t>(port), 500))
    {
      // P0.2D8: connection refusal during a station handoff is transient.
      // Keep the existing PCM FIFO and let the host's large DOC ring play on.
      fast_iwm_provider_state = 1;
      fast_iwm_provider_error = 3;
      fast_iwm_provider_next_connect = now + 250UL;
      return;
    }
    fast_iwm_provider_client.setNoDelay(true);
    fast_iwm_provider_connected = true;
    if (fast_iwm_provider_had_connection)
      fast_iwm_provider_reconnects++;
    fast_iwm_provider_had_connection = true;
    fast_iwm_provider_state = 2;
    fast_iwm_provider_error = 0;
    Debug_printf("\\r\\nFASTIWM D8 PROVIDER CONNECTED host=%s port=%d reconnects=%lu fifo=%u",
                 host.c_str(), port,
                 (unsigned long)fast_iwm_provider_reconnects,
                 (unsigned int)fast_iwm_provider_count);
''',
        'provider connect handling',
    )

    btext = replace_once(
        btext,
        '''          fast_iwm_provider_error = 0;
          fast_iwm_provider_next_connect = 0;
          fast_iwm_provider_last_activity = fnSystem.millis();
''',
        '''          fast_iwm_provider_error = 0;
          fast_iwm_provider_next_connect = 0;
          fast_iwm_provider_disconnects = 0;
          fast_iwm_provider_reconnects = 0;
          fast_iwm_provider_control_retries = 0;
          fast_iwm_provider_had_connection = false;
          fast_iwm_provider_last_activity = fnSystem.millis();
''',
        'provider session initialization',
    )

    btext = replace_once(
        btext,
        '''        if (fast_iwm_provider_connected && fast_iwm_provider_count >= 16384)
        {
          fast_iwm_probe_armed = true;
''',
        '''        if (fast_iwm_provider_connected && fast_iwm_provider_count >= 16384)
        {
          if (fast_iwm_probe_armed && !fast_iwm_probe_burst_started &&
              !fast_iwm_probe_request && fast_iwm_probe_burst_remaining == 32)
          {
            fast_iwm_provider_control_retries++;
            Debug_printf("\\r\\nFASTIWM D8 CONTROL RETRY arm=%lu fifo=%u",
                         (unsigned long)fast_iwm_provider_control_retries,
                         (unsigned int)fast_iwm_provider_count);
          }
          fast_iwm_probe_armed = true;
''',
        'duplicate ARM telemetry',
    )

    btext = replace_once(
        btext,
        '''  memcpy(reply.data() + 18, &fast_iwm_provider_batches_sent, 4);
  return reply;
''',
        '''  memcpy(reply.data() + 18, &fast_iwm_provider_batches_sent, 4);
  memcpy(reply.data() + 22, &fast_iwm_provider_disconnects, 4);
  memcpy(reply.data() + 26, &fast_iwm_provider_reconnects, 4);
  const uint16_t control_retries = static_cast<uint16_t>(
      std::min(fast_iwm_provider_control_retries,
               static_cast<uint32_t>(0xffff)));
  memcpy(reply.data() + 30, &control_retries, 2);
  return reply;
''',
        'provider status telemetry',
    )

    btext = replace_once(
        btext,
        '''        Debug_printf("\\r\\nFASTIWM D7 HEAP batch=%lu free=%u min=%u largest=%u duplicate_ready=%lu isr_deferred=%lu",
                     (unsigned long)fast_iwm_provider_batches_sent,
                     (unsigned int)heap_caps_get_free_size(MALLOC_CAP_8BIT),
                     (unsigned int)heap_caps_get_minimum_free_size(MALLOC_CAP_8BIT),
                     (unsigned int)heap_caps_get_largest_free_block(MALLOC_CAP_8BIT),
                     (unsigned long)fast_iwm_probe_duplicate_ready_count,
                     (unsigned long)fast_iwm_probe_isr_deferred_events);
''',
        '''        Debug_printf("\\r\\nFASTIWM D8 HEAP batch=%lu free=%u min=%u largest=%u duplicate_ready=%lu isr_deferred=%lu disconnects=%lu reconnects=%lu control_retries=%lu",
                     (unsigned long)fast_iwm_provider_batches_sent,
                     (unsigned int)heap_caps_get_free_size(MALLOC_CAP_8BIT),
                     (unsigned int)heap_caps_get_minimum_free_size(MALLOC_CAP_8BIT),
                     (unsigned int)heap_caps_get_largest_free_block(MALLOC_CAP_8BIT),
                     (unsigned long)fast_iwm_probe_duplicate_ready_count,
                     (unsigned long)fast_iwm_probe_isr_deferred_events,
                     (unsigned long)fast_iwm_provider_disconnects,
                     (unsigned long)fast_iwm_provider_reconnects,
                     (unsigned long)fast_iwm_provider_control_retries);
''',
        'D7 heap telemetry',
    )

    btext = btext.replace('FASTIWM D7 ', 'FASTIWM D8 ')

    required = (
        'FASTIWM D8 ENDPOINT SET',
        'FASTIWM D8 PROVIDER LOST',
        'FASTIWM D8 PROVIDER CONNECTED',
        'FASTIWM D8 CONTROL RETRY',
        'FASTIWM D8 HEAP',
        'fast_iwm_provider_disconnects',
        'fast_iwm_provider_reconnects',
        'fast_iwm_provider_control_retries',
        'fast_iwm_provider_next_connect = now + 250UL',
    )
    for marker in required:
        if marker not in btext:
            raise SystemExit(f'Missing P0.2D8 firmware marker: {marker}')
    if 'FASTIWM D7 ' in btext:
        raise SystemExit('Obsolete D7 firmware diagnostic remains.')

    lltext = llcpp.read_text(encoding='utf-8')
    if 'fast_iwm_probe_burst_started && (_phases == 0b1011)' not in lltext:
        raise SystemExit('P0.2D8 lost the D7 duplicate-READY ISR guard.')

    buscpp.write_text(btext, encoding='utf-8', newline='\n')
    print('Applied FujiNet P0.2D8 reconnect/control telemetry overlay.')


if __name__ == '__main__':
    main()
