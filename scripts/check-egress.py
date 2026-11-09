"""Run in sensor container; every explicitly supplied target must be unreachable."""
import socket
import sys

if len(sys.argv) < 2:
    sys.exit('Usage: python - HOST:PORT [HOST:PORT ...]; use known listening LAN and host services')
failed = False
for target in sys.argv[1:]:
    host, port = target.rsplit(':', 1)
    try:
        with socket.create_connection((host, int(port)), timeout=3):
            pass
    except OSError:
        print(f'UNREACHABLE {target} (verify the target was listening from the host)')
    else:
        failed = True
        print(f'FAIL: sensor reached {target}')
sys.exit(1 if failed else 0)
