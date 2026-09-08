"""Send a Tcl command to MAGICAL HAPPY RALLY's dedicated emulator."""
import os
import sys
import urllib.error
import urllib.request

if len(sys.argv) < 2:
    raise SystemExit('Usage: python tools/emu.py "machine_info config_name"')
port = int(os.environ.get('OPENMSX_PORT', '18796'))
request = urllib.request.Request(f'http://127.0.0.1:{port}',
                                 data=' '.join(sys.argv[1:]).encode('utf-8'), method='POST')
try:
    with urllib.request.urlopen(request, timeout=30) as response:
        print(response.read().decode('utf-8'))
except urllib.error.HTTPError as error:
    print(error.read().decode('utf-8'), file=sys.stderr)
    raise SystemExit(1)
except urllib.error.URLError as error:
    raise SystemExit(f'MAGICAL HAPPY RALLY emulator is unavailable on port {port}: {error.reason}')
