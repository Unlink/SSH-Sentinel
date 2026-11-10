"""Bounded virtual direct-tcpip channels. Never resolve or connect to a target."""
import asyncio
import base64
import time
from uuid import uuid4

import asyncssh

MAX_CHANNELS = 8
MAX_CONCURRENT = 2
MAX_REQUESTS = 32
INPUT_BYTES = 16384
SAMPLE_BYTES = 2048
CHANNEL_SECONDS = 10


class VirtualForwarding(asyncssh.SSHTCPSession):
    def __init__(self, owner, destination_host, destination_port, origin_host, origin_port):
        self.owner = owner
        self.id = str(uuid4())
        self.target = {'destination_host': destination_host, 'destination_port': destination_port,
                       'claimed_origin_host': origin_host, 'claimed_origin_port': origin_port}
        self.channel = None
        self.timer = None
        self.closed = False
        self.received_bytes = 0
        self.sample = bytearray()
        self.started = time.monotonic()
        owner.forward_active.add(self)

    def connection_made(self, channel):
        self.channel = channel
        self.owner.event('forward_open', channel_id=self.id, simulated=True, **self.target)
        self.timer = asyncio.get_running_loop().call_later(CHANNEL_SECONDS, self.finish, 'timeout')

    def data_received(self, data, datatype):
        if self.closed:
            return
        self.received_bytes += len(data)
        self.sample.extend(data[:max(0, SAMPLE_BYTES-len(self.sample))])
        if self.received_bytes >= INPUT_BYTES:
            self.finish('input_limit')

    def finish(self, reason):
        if self.closed:
            return
        self.closed = True
        self.owner.forward_active.discard(self)
        if self.timer:
            self.timer.cancel()
        if self.channel is not None:
            self.owner.event('forward_close', channel_id=self.id, simulated=True,
                             reason=reason, received_bytes=self.received_bytes,
                             sample_base64=base64.b64encode(self.sample).decode('ascii'),
                             sample_text=bytes(self.sample).decode('utf-8', errors='replace'),
                             sample_truncated=self.received_bytes > len(self.sample),
                             duration=round(time.monotonic()-self.started, 3))
            self.channel.close()
        self.sample.clear()

    def eof_received(self):
        self.finish('eof')
        return False

    def connection_lost(self, exc):
        self.finish('disconnect')
