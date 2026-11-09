"""Bound all SSH transport traffic, including packets outside shell channels.

AsyncSSH.listen fixes its connection factory internally. Construct the pinned
public SSHServerConnection implementation as an asyncio protocol to override its
otherwise no-op write-backpressure callback. Real protocol tests guard this
version-coupled integration.
"""
import asyncssh


class BoundedSSHConnection(asyncssh.SSHServerConnection):
    def __init__(self, loop, options):
        super().__init__(loop, options)
        self.sentinel_owner = None
        self.received_bytes = 0
        self.limit_reported = False

    def connection_made(self, transport):
        transport.set_write_buffer_limits(high=65536, low=16384)
        super().connection_made(transport)

    def limit(self, kind):
        if not self.limit_reported:
            self.limit_reported = True
            if self.sentinel_owner:
                self.sentinel_owner.event('limit', limit=kind)
        self.abort()

    def pause_writing(self):
        # Replies to global requests bypass SSH channel flow control entirely.
        self.limit('transport_output')

    def data_received(self, data):
        if self.limit_reported:
            return
        self.received_bytes += len(data)
        if self.received_bytes > 4 * 1024**2:
            self.limit('transport_input')
            return
        super().data_received(data)
