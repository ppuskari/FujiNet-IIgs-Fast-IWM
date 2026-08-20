from pathlib import Path
import argparse
import subprocess
import sys

AUTO_DELAY_MS = 20


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'Expected {label} pattern not found.')
    return text.replace(old, new, 1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Apply P0.2C2 then replace manual 1011 trigger with delayed autonomous TX.'
    )
    parser.add_argument('--project-root', default='.')
    parser.add_argument('--firmware-root', required=True)
    args = parser.parse_args()

    project = Path(args.project_root).resolve()
    root = Path(args.firmware_root).resolve()
    c2_patch = project / 'tools' / 'patch_fujinet_fastiwm_p02c2.py'
    buscpp = root / 'lib' / 'bus' / 'iwm' / 'iwm.cpp'

    subprocess.run(
        [sys.executable, str(c2_patch),
         '--project-root', str(project),
         '--firmware-root', str(root)],
        check=True,
    )

    text = buscpp.read_text(encoding='utf-8')
    if 'P0.2C3 AUTOSEND' in text:
        print('FujiNet P0.2C3 autosend overlay already applied.')
        return

    old_state = '''extern volatile uint32_t fast_iwm_probe_req_count;
extern volatile uint8_t fast_iwm_probe_reset_grace;
extern volatile uint32_t fast_iwm_probe_reset_hold_count;
static uint32_t fast_iwm_probe_arm_count = 0;
static uint32_t fast_iwm_probe_tx_count = 0;
'''
    new_state = f'''extern volatile uint32_t fast_iwm_probe_req_count;
extern volatile uint8_t fast_iwm_probe_reset_grace;
extern volatile uint32_t fast_iwm_probe_reset_hold_count;
static uint32_t fast_iwm_probe_arm_count = 0;
static uint32_t fast_iwm_probe_tx_count = 0;
static bool fast_iwm_probe_autosend_pending = false; // P0.2C3 AUTOSEND
static uint32_t fast_iwm_probe_autosend_due_ms = 0;
static uint32_t fast_iwm_probe_autosend_count = 0;
'''
    text = replace_once(text, old_state, new_state, 'P0.2C2 state block')

    old_arm = '''    fast_iwm_probe_armed = true;
    fast_iwm_probe_reset_grace = 1;
    fast_iwm_probe_request = false;
    fast_iwm_probe_arm_count++;

    Debug_printf("\\r\\nFASTIWM ARM block=7fa55a count=%lu",
                 (unsigned long)fast_iwm_probe_arm_count);

    // Return a normal 512-byte 4-us block so the ROM SmartPort call that
    // performed negotiation completes exactly like the proven B3 baseline.
    std::array<uint8_t, 512> fast_arm_reply;
    fast_arm_reply.fill(0xa5);
    transaction_accept(TRANS_STATE::NO_GET);
    transaction_send(fast_arm_reply.data(), fast_arm_reply.size());
    goto done;
'''

    new_arm = f'''    // P0.2C3: the magic normal SmartPort READBLOCK is the only trigger.
    // Do not depend on a later manually generated PH0..PH3 transition.
    fast_iwm_probe_armed = false;
    fast_iwm_probe_reset_grace = 0;
    fast_iwm_probe_request = false;
    fast_iwm_probe_autosend_pending = false;
    fast_iwm_probe_arm_count++;

    Debug_printf("\\r\\nFASTIWM C3 ARM block=7fa55a count=%lu",
                 (unsigned long)fast_iwm_probe_arm_count);

    // First complete the ordinary 4-us reply through the proven ROM path.
    std::array<uint8_t, 512> fast_arm_reply;
    fast_arm_reply.fill(0xa5);
    transaction_accept(TRANS_STATE::NO_GET);
    transaction_send(fast_arm_reply.data(), fast_arm_reply.size());

    // Start the delay only AFTER the normal block reply has completed. This
    // gives the IIgs time to return from ROM SmartPort and enter its direct
    // IWM Read-Data polling loop before the one-shot 2-us waveform begins.
    fast_iwm_probe_autosend_due_ms = fnSystem.millis() + {AUTO_DELAY_MS};
    fast_iwm_probe_autosend_pending = true;
    Debug_printf("\\r\\nFASTIWM C3 AUTO SCHEDULE delay={AUTO_DELAY_MS}ms");
    goto done;
'''
    text = replace_once(text, old_arm, new_arm, 'P0.2C2 magic arm block')

    service_anchor = '''#ifdef IIGS_FAST_IWM_PROBE
  if (fast_iwm_probe_request)
  {
'''
    service_insert = '''#ifdef IIGS_FAST_IWM_PROBE
  if (fast_iwm_probe_autosend_pending)
  {
    uint32_t fast_now = fnSystem.millis();
    if ((int32_t)(fast_now - fast_iwm_probe_autosend_due_ms) >= 0)
    {
      fast_iwm_probe_autosend_pending = false;
      fast_iwm_probe_autosend_count++;
      fast_iwm_probe_tx_count++;

      Debug_printf("\\r\\nFASTIWM C3 AUTO TX START auto=%lu tx=%lu phase=%02x",
                   (unsigned long)fast_iwm_probe_autosend_count,
                   (unsigned long)fast_iwm_probe_tx_count,
                   (unsigned int)smartport.iwm_phase_vector());

      smartport.iwm_ack_set();
      error_is_true fast_err = smartport.iwm_send_fast_probe_spi();
      smartport.iwm_ack_set();

      Debug_printf("\\r\\nFASTIWM C3 AUTO TX DONE auto=%lu tx=%lu err=%d",
                   (unsigned long)fast_iwm_probe_autosend_count,
                   (unsigned long)fast_iwm_probe_tx_count,
                   fast_err ? 1 : 0);
      return;
    }
  }

  // Retain the older request path only as a diagnostic fallback. P0.2C3 host
  // does not generate a manual 1010 -> 1011 request after the arm call.
  if (fast_iwm_probe_request)
  {
'''
    text = replace_once(text, service_anchor, service_insert, 'P0.2C service block')

    required = (
        'P0.2C3 AUTOSEND',
        'FASTIWM C3 ARM block=7fa55a',
        'FASTIWM C3 AUTO SCHEDULE',
        'FASTIWM C3 AUTO TX START',
        'FASTIWM C3 AUTO TX DONE',
        f'fnSystem.millis() + {AUTO_DELAY_MS}',
        'iwm_send_fast_probe_spi()',
    )
    for item in required:
        if item not in text:
            raise SystemExit(f'Missing P0.2C3 firmware marker: {item}')

    buscpp.write_text(text, encoding='utf-8', newline='\n')
    print('Applied FujiNet P0.2C3 delayed autonomous-send overlay.')
    print(f'Autosend delay starts after normal arm reply: {AUTO_DELAY_MS} ms.')
    print('P0.2C3 no longer requires a post-arm phase trigger from the IIgs.')


if __name__ == '__main__':
    main()
