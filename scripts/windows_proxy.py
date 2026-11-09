"""Native Windows TCP entry point. No Docker socket, credentials or SSH parsing.

Run via start-windows-proxy.ps1. Backend must be localhost and PROXY-enabled.
"""
import argparse
import asyncio
import contextlib
import ipaddress


class Proxy:
    def __init__(self, backend_port=2223, max_connections=64, session_seconds=300):
        self.backend_port = backend_port
        self.max_connections = max_connections
        self.session_seconds = session_seconds
        self.active = 0

    async def handle(self, reader, writer):
        if self.active >= self.max_connections:
            writer.close()
            return
        self.active += 1
        backend_writer = None
        tasks = []
        try:
            async with asyncio.timeout(self.session_seconds):
                source = writer.get_extra_info('peername')
                destination = writer.get_extra_info('sockname')
                family = 'TCP4' if ipaddress.ip_address(source[0]).version == 4 else 'TCP6'
                backend_reader, backend_writer = await asyncio.wait_for(
                    asyncio.open_connection('127.0.0.1', self.backend_port, limit=65536), 5)
                # Always generate our own header before forwarding ANY client bytes.
                backend_writer.write(f'PROXY {family} {source[0]} {destination[0]} {source[1]} {destination[1]}\r\n'.encode('ascii'))
                await backend_writer.drain()
                tasks = [asyncio.create_task(self.copy(reader, backend_writer)),
                         asyncio.create_task(self.copy(backend_reader, writer))]
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
        except (OSError, TimeoutError, ValueError):
            pass
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            for stream in (writer, backend_writer):
                if stream is not None:
                    stream.close()
                    with contextlib.suppress(OSError, TimeoutError):
                        await asyncio.wait_for(stream.wait_closed(), 2)
            self.active -= 1

    @staticmethod
    async def copy(reader, writer):
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()


async def main(port):
    proxy = Proxy()
    server = await asyncio.start_server(proxy.handle, '0.0.0.0', port, backlog=64, limit=65536)
    async with server:
        await server.serve_forever()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=2222, choices=range(1, 65536), metavar='PORT')
    args = parser.parse_args()
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main(args.port))
