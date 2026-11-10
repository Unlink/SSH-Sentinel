# Virtual SSH forwarding capture

The user selected the proposed initial implementation: accept a virtual direct-tcpip channel and capture what the client requests. Never resolve destinations, dial target sockets, relay traffic or fabricate HTTP/SMTP/TLS success. Existing remote TCP/Unix forwarding, SFTP/SCP/agent/X11 restrictions and sensor egress firewall stay in force.

## Approach and bounds
Return a custom AsyncSSH SSHTCPSession with a byte-mode channel (8 KiB receive window, 4 KiB max packet). No network helper is called. Record forward_open with channel UUID, requested destination and client-claimed origin fields; the event source IP remains the authenticated transport peer. On completion record forward_close with reason, received bytes, first 2048 bytes as base64 plus readable UTF-8 preview, and a sample-truncated flag. End on EOF, disconnect, 10-second absolute timeout or 16 KiB input. Allow 2 concurrent channels and 8 lifetime opens per SSH connection, with a 32-request budget including rejected admission requests; abort transport after lifetime admission budget is exceeded to prevent metadata/log floods. Bound host names at 1024 characters; ports must be in range. Session duration and 4 MiB transport cap still apply.

## GUI and compatibility
Import both event types. Show forwarding count and "Forwarding simulated" outcome in the grouped session history, retaining "Shell opened" precedence. In detail show the target and captured fields with HTML escaping and explicitly state no destination connection was made. Add new types to filters. JSON/CSV keep their current format. Previously denied-forward events are historical and unchanged.

## Validation
Real SSH client opens a target while a controlled TCP listener and resolver spy prove no outbound connection or DNS lookup occurs. Test binary/fragmented preview capture and truncation, EOF/disconnect/timeout cleanup, per-channel input caps, simultaneous and lifetime channel caps, claimed origin not changing source IP, invalid destinations and continued shell access. Exercise ingestion, filters and escaped GUI for new events. Full tests and independent security-focused review precede deployment through the guarded Windows helper.
