"""Pure string simulation. No host filesystem, process execution or networking."""
import re
import shlex


class FakeShell:
    def __init__(self, username):
        self.username = re.sub(r'[^a-zA-Z0-9_.-]', '_', username)[:64] or 'guest'
        self.home = '/root' if self.username == 'root' else '/home/' + self.username

    @property
    def prompt(self):
        return f'{self.username}@srv01:~' + ('# ' if self.username == 'root' else '$ ')

    def execute(self, command):
        try:
            args = shlex.split(command)
        except ValueError:
            return 'sh: syntax error\n', False
        if not args:
            return '', False
        # This is intentionally not a shell parser: operators are never interpreted.
        if any(char in command for char in (';', '|', '&', '`', '$', '<', '>')):
            return 'sh: unsupported command\n', False
        name = args[0]
        if name in ('exit', 'logout'):
            return 'logout\n', True
        if name == 'pwd':
            return self.home + '\n', False
        if name == 'whoami':
            return self.username + '\n', False
        if name == 'id':
            uid = 0 if self.username == 'root' else 1000
            return f'uid={uid}({self.username}) gid={uid}({self.username}) groups={uid}({self.username})\n', False
        if name == 'uname':
            return ('Linux srv01 6.12.0 #1 SMP aarch64 GNU/Linux\n' if len(args) > 1 else 'Linux\n'), False
        if name == 'ls':
            return 'backups  notes.txt\n', False
        if name == 'ps':
            return '  PID TTY          TIME CMD\n    1 ?        00:00:01 systemd\n  410 pts/0    00:00:00 bash\n', False
        if name == 'cat':
            files = {'/etc/passwd': 'root:x:0:0:root:/root:/bin/bash\n',
                     '/etc/os-release': 'PRETTY_NAME="Debian GNU/Linux 13 (trixie)"\n',
                     'notes.txt': 'Backup scheduled at 02:00 UTC.\n',
                     '/etc/hostname': 'srv01\n'}
            return ''.join(files.get(p, 'cat: No such file or directory\n') for p in args[1:]), False
        return 'sh: command not found\n', False
