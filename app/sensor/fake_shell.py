"""Pure string simulation. No host filesystem, process execution or networking."""
import re
import shlex


class UnsupportedSyntax(Exception):
    pass


def split_commands(command):
    """Recognize bounded semicolon sequences; never evaluate shell expressions."""
    if len(command) > 4096:
        raise UnsupportedSyntax
    parts = []
    start = 0
    quote = None
    escaped = False
    for index, char in enumerate(command):
        if escaped:
            escaped = False
            continue
        if char == '\\' and quote != "'":
            escaped = True
            continue
        if quote == "'":
            if char == quote:
                quote = None
            continue
        if char in ('$', '`'):
            raise UnsupportedSyntax
        if quote == '"':
            if char == quote:
                quote = None
            continue
        if char in ("'", '"'):
            quote = char
        elif char in ('|', '&', '<', '>'):
            raise UnsupportedSyntax
        elif char == ';':
            part = command[start:index].strip()
            if not part:
                raise ValueError('Empty command')
            parts.append(part)
            start = index + 1
    if quote or escaped:
        raise ValueError('Incomplete quoting')
    if command[start:].strip():
        parts.append(command[start:].strip())
    if len(parts) > 32:
        raise UnsupportedSyntax
    # Parse every segment before emitting output or changing simulated session state.
    return [shlex.split(part) for part in parts]


class FakeShell:
    def __init__(self, username):
        self.username = re.sub(r'[^a-zA-Z0-9_.-]', '_', username)[:64] or 'guest'
        self.home = '/root' if self.username == 'root' else '/home/' + self.username

    @property
    def prompt(self):
        return f'{self.username}@srv01:~' + ('# ' if self.username == 'root' else '$ ')

    def execute(self, command):
        try:
            commands = split_commands(command)
        except UnsupportedSyntax:
            return 'sh: unsupported command\n', False
        except ValueError:
            return 'sh: syntax error\n', False
        if len(commands) > 1 and any(not args or args[0] != 'echo' for args in commands):
            return 'sh: unsupported command\n', False
        output = []
        done = False
        for args in commands:
            text, done = self.execute_args(args)
            output.append(text)
            if done:
                break
        return ''.join(output), done

    def execute_args(self, args):
        if not args:
            return '', False
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
        if name == 'echo':
            return ' '.join(args[1:]) + '\n', False
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
