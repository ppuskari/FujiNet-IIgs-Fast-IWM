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
            'Accept a D3EP endpoint WRITEBLOCK from FASTPROBE and use it '
            'instead of hidden persisted FujiNet NetStream configuration.'
        )
    )
    parser.add_argument('--project-root', default='.')
    parser.add_argument('--firmware-root', required=True)
    args = parser.parse_args()

    project = Path(args.project_root).resolve()
    root = Path(args.firmware_root).resolve()
    base = project / 'tools' / 'patch_fujinet_fastiwm_p02d2_softreturn.py'
    llcpp = root / 'lib' / 'bus' / 'iwm' / 'iwm_ll.cpp'
    buscpp = root / 'lib' / 'bus' / 'iwm' / 'iwm.cpp'
    if not base.is_file() or not llcpp.is_file() or not buscpp.is_file():
        raise SystemExit('Missing P0.2D2 transform or IWM sources.')

    ltext = llcpp.read_text(encoding='utf-8')
    btext = buscpp.read_text(encoding='utf-8')
    if 'FASTIWM D3 ENDPOINT SET' in btext:
        print('FujiNet P0.2D3 endpoint overlay already applied.')
        return
    if 'FASTIWM D2 PROVIDER START' not in btext:
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
    if 'FASTIWM D2 PROVIDER START' not in btext:
        raise SystemExit('P0.2D2 firmware transform did not apply.')

    btext = replace_once(
        btext,
        '''static uint32_t fast_iwm_provider_batches_sent = 0;

static void fast_iwm_provider_close(bool disable)
''',
        '''static uint32_t fast_iwm_provider_batches_sent = 0;
// Match the regular 22-mono streamer application. FASTPROBE sends an
// explicit D3EP override before START, so these are a deterministic fallback
// rather than a dependency on persisted FujiNet web/SD configuration.
static std::string fast_iwm_provider_host = "192.168.5.235";
static uint16_t fast_iwm_provider_port = 22510;

static void fast_iwm_provider_close(bool disable)
''',
        'provider endpoint state',
    )

    btext = replace_once(
        btext,
        '''    const std::string host = Config.get_network_netstream_host();
    int port = Config.get_network_netstream_port();
    if (port <= 0)
      port = 22510;
    if (host.empty())
''',
        '''    const std::string host = fast_iwm_provider_host;
    const int port = static_cast<int>(fast_iwm_provider_port);
    if (host.empty() || port <= 0)
''',
        'persisted provider endpoint lookup',
    )

    endpoint_command = r'''  if (cmd.frame.sp_command == SP_CMD_WRITEBLOCK)
  {
    const uint32_t block = static_cast<uint32_t>(cmd.frame.block_rw.num);
    if (block == 0x7fa556)
    {
      std::array<uint8_t, 512> endpoint{};
      transaction_accept(TRANS_STATE::WILL_GET);
      if (!transaction_get(endpoint.data(), endpoint.size()))
      {
        transaction_error(SP_ERR::IOERROR);
        Debug_printf("\r\nFASTIWM D3 ENDPOINT RECEIVE FAILED");
        goto done;
      }

      const uint8_t host_len = endpoint[5];
      const uint16_t port = static_cast<uint16_t>(endpoint[6]) |
          (static_cast<uint16_t>(endpoint[7]) << 8);
      bool valid = endpoint[0] == 'D' && endpoint[1] == '3' &&
          endpoint[2] == 'E' && endpoint[3] == 'P' && endpoint[4] == 1 &&
          host_len > 0 && host_len <= 63 && port > 0;
      for (uint8_t i = 0; valid && i < host_len; ++i)
        valid = endpoint[8 + i] >= 0x21 && endpoint[8 + i] <= 0x7e;
      if (!valid)
      {
        transaction_error(SP_ERR::IOERROR);
        Debug_printf("\r\nFASTIWM D3 ENDPOINT INVALID len=%u port=%u",
                     static_cast<unsigned int>(host_len),
                     static_cast<unsigned int>(port));
        goto done;
      }

      fast_iwm_provider_close(true);
      fast_iwm_provider_host.assign(
          reinterpret_cast<const char *>(endpoint.data() + 8), host_len);
      fast_iwm_provider_port = port;
      fast_iwm_provider_error = 0;
      transaction_success();
      Debug_printf("\r\nFASTIWM D3 ENDPOINT SET host=%s port=%u source=IIgs",
                   fast_iwm_provider_host.c_str(),
                   static_cast<unsigned int>(fast_iwm_provider_port));
      goto done;
    }
  }

'''
    btext = replace_once(
        btext,
        '  if (cmd.frame.sp_command == SP_CMD_READBLOCK)\n',
        endpoint_command + '  if (cmd.frame.sp_command == SP_CMD_READBLOCK)\n',
        'provider command dispatch',
    )

    btext = btext.replace('FASTIWM D2 ', 'FASTIWM D3 ')

    required = (
        'FASTIWM D3 ENDPOINT SET',
        'block == 0x7fa556',
        'transaction_accept(TRANS_STATE::WILL_GET)',
        'transaction_get(endpoint.data(), endpoint.size())',
        'fast_iwm_provider_host = "192.168.5.235"',
        'fast_iwm_provider_port = 22510',
        'const std::string host = fast_iwm_provider_host',
        'FASTIWM D3 PROVIDER START',
        'FASTIWM D3 PROVIDER CONNECTED',
        'pdMS_TO_TICKS(100)',
    )
    joined = ltext + '\n' + btext
    for marker in required:
        if marker not in joined:
            raise SystemExit(f'Missing P0.2D3 firmware marker: {marker}')
    if 'Config.get_network_netstream_host()' in btext:
        raise SystemExit('P0.2D3 still depends on persisted NetStream host.')
    if 'FASTIWM D2 ' in btext:
        raise SystemExit('Obsolete D2 firmware diagnostic remains.')

    llcpp.write_text(ltext, encoding='utf-8', newline='\n')
    buscpp.write_text(btext, encoding='utf-8', newline='\n')
    print('Applied FujiNet P0.2D3 app-configured provider endpoint overlay.')


if __name__ == '__main__':
    main()
