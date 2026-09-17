"""Bounded, credential-free diagnostics for the public school service."""
import json
import platform
import socket
import ssl
import time
import urllib.request

import scrape_hrbeu as radar


def main():
    host = 'job.hrbeu.edu.cn'
    print('Platform:', platform.system(), flush=True)
    try:
        addresses = sorted({(r[0], r[4][0]) for r in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)})
    except OSError as exc:
        print('DNS failed:', type(exc).__name__, str(exc), flush=True)
        return
    print('DNS:', addresses, flush=True)
    for family, address in addresses[:4]:
        start = time.monotonic()
        stage = 'TCP'
        try:
            with socket.socket(family, socket.SOCK_STREAM) as sock:
                sock.settimeout(8)
                sock.connect((address, 443))
                print(address, 'TCP OK', round(time.monotonic()-start, 2), flush=True)
                stage = 'TLS'
                with ssl.create_default_context().wrap_socket(sock, server_hostname=host) as secured:
                    print(address, 'TLS OK', secured.version(), flush=True)
        except OSError as exc:
            print(address, stage, 'FAIL', type(exc).__name__, str(exc), round(time.monotonic()-start, 2), flush=True)
    # Test the same IPv4 path as production, without retrieving whole event lists.
    import os
    os.environ['HRBEU_FORCE_IPV4'] = '1'
    radar.enable_ipv4_only_if_requested()
    for source in radar.SOURCES:
        try:
            start = time.monotonic()
            result = radar.post_json(source.endpoint, {'pageNo': 1, 'pageSize': 1}, timeout=10, retries=1)
            print(source.kind, 'API', result.get('state'), 'seconds', round(time.monotonic()-start, 2), flush=True)
        except Exception as exc:
            print(source.kind, 'API FAIL', type(exc).__name__, str(exc), flush=True)


if __name__ == '__main__':
    main()
