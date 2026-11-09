"""Deployment contract: safe Compose defaults without a dotenv file or shell overrides."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


def test_compose_starts_with_safe_defaults_without_env_file(tmp_path):
    docker = shutil.which('docker')
    if not docker:
        pytest.skip('Docker CLI is not installed')
    root = Path(__file__).resolve().parents[1]
    # An isolated config directory proves no project .env can be loaded.
    config = tmp_path / 'docker-compose.yml'
    config.write_text((root / 'docker-compose.yml').read_text())
    clean_env = dict(os.environ)
    for line in (root / '.env.example').read_text().splitlines():
        if line and not line.startswith('#') and '=' in line:
            clean_env.pop(line.split('=', 1)[0], None)
    for name in ('COMPOSE_ENV_FILES', 'COMPOSE_FILE', 'COMPOSE_PROFILES', 'COMPOSE_PROJECT_NAME'):
        clean_env.pop(name, None)
    clean_env['COMPOSE_DISABLE_ENV_FILE'] = '1'
    result = subprocess.run([docker, 'compose', '-f', str(config), 'config', '--format', 'json'],
                            cwd=tmp_path, env=clean_env, text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr
    services = json.loads(result.stdout)['services']
    for role, port in [('sensor', '2222'), ('web', '8080')]:
        assert services[role]['ports'][0]['host_ip'] == '127.0.0.1'
        assert services[role]['ports'][0]['published'] == port
        assert not services[role].get('env_file')
    assert services['sensor']['environment']['SENTINEL_LOG_PASSWORDS'] == 'true'
