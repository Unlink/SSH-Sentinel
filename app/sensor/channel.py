"""Bound SSH metadata requests which bypass the shell data receive window.

AsyncSSH has no public environment-request policy callback. The single protected
env handler override is covered by real-protocol regression tests against our pin.
"""
import asyncio

import asyncssh
from asyncssh.constants import MSG_CHANNEL_REQUEST


class HoneypotChannel(asyncssh.SSHServerChannel):
    def __init__(self, owner):
        self.owner = owner
        self.request_count = 0
        self.env_reported = False
        super().__init__(owner.conn, asyncio.get_running_loop(), True, False, False,
                         0, owner.settings.max_line, 'utf-8', 'replace', 65536, 32768)

    def process_packet(self, pkttype, pktid, packet):
        if pkttype == MSG_CHANNEL_REQUEST:
            self.request_count += 1
            if self.request_count > 128:
                if self.request_count == 129:
                    self.owner.event('limit', limit='channel_requests')
                self.owner.conn.abort()
                return True
        return super().process_packet(pkttype, pktid, packet)

    def _process_env_request(self, packet):
        packet.get_string()  # Consume, but never retain client environment values.
        packet.get_string()
        packet.check_end()
        if not self.env_reported:
            self.owner.event('denied', request='environment')
            self.env_reported = True
        return False
