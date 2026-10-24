"""Deployment recipe tests never contact a VM or create paid resources."""
from pathlib import Path
import os
import shutil
import subprocess
import sys

import pytest
import yaml

ROOT=Path(__file__).resolve().parents[1]


def prepare(path,ip='203.0.113.10'):
    return subprocess.run([sys.executable,str(ROOT/'infra/yandex/prepare_env.py'),'--public-ip',ip,'--output',str(path)],capture_output=True,text=True)


def test_production_env_is_private_stable_and_has_no_default_password(tmp_path):
    path=tmp_path/'config/production.env'
    first=prepare(path)
    assert first.returncode==0,first.stderr
    content=path.read_text()
    assert 'APP_URL=https://203.0.113.10\n' in content
    assert 'SECURE_COOKIES=true\n' in content and 'APP_ENV=production\n' in content
    password=next(line.split('=',1)[1] for line in content.splitlines() if line.startswith('APP_DB_PASSWORD='))
    assert len(password)>=40 and password not in first.stdout+first.stderr
    assert 'LANGFUSE_PUBLIC_KEY=\n' in content and 'LANGFUSE_SECRET_KEY=\n' in content
    assert path.stat().st_mode&0o777==0o600
    assert prepare(path).returncode==0 and path.read_text()==content
    assert prepare(path,ip='203.0.113.11').returncode!=0 and path.read_text()==content


def test_invalid_ip_and_unpinned_ssh_fail_before_any_remote_action(tmp_path):
    path=tmp_path/'bad.env'
    assert prepare(path,ip='not-an-ip').returncode!=0 and not path.exists()
    result=subprocess.run(['bash',str(ROOT/'scripts/deploy_yandex_vm.sh'),'--host','203.0.113.10','--revision','a'*40,'--identity-file',str(tmp_path/'missing-key'),'--known-hosts',str(tmp_path/'missing-hosts')],capture_output=True,text=True)
    assert result.returncode!=0
    assert 'Traceback' not in result.stderr


def test_compose_exposes_only_proxy_and_requires_real_app_database_secret(tmp_path):
    spec=yaml.safe_load((ROOT/'compose.production.yml').read_text())
    assert set(spec['services'])=={'app','app-db','proxy','certbot'}
    assert not spec['services']['app'].get('ports') and not spec['services']['app-db'].get('ports')
    assert set(spec['services']['proxy']['ports'])=={'80:80','443:443'}
    assert spec['services']['certbot']['profiles']==['ops']
    assert '@sha256:' in spec['services']['proxy']['image']
    assert '@sha256:' in spec['services']['certbot']['image']
    assert '${APP_DB_PASSWORD:?' in spec['services']['app-db']['environment']['POSTGRES_PASSWORD']
    if shutil.which('docker'):
        path=tmp_path/'production.env';assert prepare(path).returncode==0
        result=subprocess.run(['docker','compose','--env-file',str(path),'-f',str(ROOT/'compose.production.yml'),'config','--quiet'],capture_output=True,text=True)
        assert result.returncode==0,result.stderr


def test_cloud_init_requires_operator_public_key_and_configures_renewal_timer():
    data=yaml.safe_load((ROOT/'infra/yandex/cloud-init.yaml').read_text())
    assert data['ssh_pwauth'] is False and data['disable_root'] is True
    assert any('REPLACE_WITH_ED25519_PUBLIC_KEY' in str(user) for user in data['users'])
    written={row['path']:row for row in data['write_files']}
    assert 'DPkg::Lock::Timeout "600";' in written['/etc/apt/apt.conf.d/99-agentpay-lock-timeout']['content']
    timer=written['/etc/systemd/system/agentpay-cert-renew.timer']['content']
    assert 'OnCalendar=' in timer and 'Persistent=true' in timer
    assert not any('PASSWORD=' in row.get('content','') for row in data['write_files'])


def test_shell_recipe_is_parseable_and_never_uses_unverified_ssh():
    for script in ('scripts/deploy_yandex_vm.sh','infra/yandex/backup.sh','infra/yandex/renew-cert.sh'):
        result=subprocess.run(['bash','-n',str(ROOT/script)],capture_output=True,text=True)
        assert result.returncode==0,result.stderr
    text=(ROOT/'scripts/deploy_yandex_vm.sh').read_text()
    assert '-o StrictHostKeyChecking=yes' in text and 'hashlib.file_digest' in text
    assert 'options=(-F /dev/null ' in text
    assert 'git get-tar-commit-id' in text and 'before stopping' in text
    assert 'filter=\'data\'' in text


def test_cloud_init_renderer_rejects_private_key_and_preserves_existing_output(tmp_path):
    public=tmp_path/'operator.pub';output=tmp_path/'cloud-init.yaml'
    public.write_text('-----BEGIN OPENSSH PRIVATE KEY-----\n')
    command=[sys.executable,str(ROOT/'infra/yandex/render_cloud_init.py'),'--ssh-public-key',str(public),'--output',str(output)]
    rejected=subprocess.run(command,capture_output=True,text=True)
    assert rejected.returncode!=0 and not output.exists()
    import base64
    payload=b'\x00\x00\x00\x0bssh-ed25519'+b'\x00\x00\x00\x20'+b'x'*32
    public.write_text('ssh-ed25519 '+base64.b64encode(payload).decode()+' operator: test # value')
    accepted=subprocess.run(command,capture_output=True,text=True)
    assert accepted.returncode==0,accepted.stderr
    assert 'REPLACE_WITH_ED25519_PUBLIC_KEY' not in output.read_text()
    rendered=yaml.safe_load(output.read_text())
    assert rendered['users'][1]['ssh_authorized_keys']==[public.read_text()]
    original=output.read_bytes()
    assert subprocess.run(command,capture_output=True).returncode!=0 and output.read_bytes()==original


def test_cd_allows_only_successful_exact_ci_push_to_main(tmp_path):
    import json
    spec=yaml.safe_load((ROOT/'.github/workflows/deploy-yandex.yml').read_text())
    triggers=spec.get('on',spec.get(True))
    assert triggers['workflow_run']['types']==['completed']
    gate=spec['jobs']['deploy']['steps'][0]['run']
    tools=tmp_path/'tools';tools.mkdir()
    stub=tools/'gh';stub.write_text('#!'+sys.executable+'\nimport os,sys\nfrom pathlib import Path\nprint("101" if sys.argv[2].endswith("/ci.yml") else Path(os.environ["GH_FIXTURE"]).read_text())\n');stub.chmod(0o755)
    commit='a'*40;repo='example/agentpay'
    valid={'id':12,'workflow_id':101,'head_sha':commit,'head_branch':'main','event':'push','status':'completed','conclusion':'success','head_repository':{'full_name':repo}}
    env={**os.environ,'PATH':str(tools)+os.pathsep+os.environ['PATH'],'RELEASE_SHA':commit,'GITHUB_REPOSITORY':repo,'RUNNER_TEMP':str(tmp_path),'SOURCE_RUN_ID':'','SOURCE_WORKFLOW_ID':''}
    fixture=tmp_path/'runs.json';env['GH_FIXTURE']=str(fixture)
    for changes,allowed in [({},True),({'event':'pull_request'},False),({'head_branch':'feature'},False),({'head_repository':{'full_name':'fork/agentpay'}},False),({'head_sha':'b'*40},False),({'workflow_id':102},False),({'conclusion':'failure'},False)]:
        fixture.write_text(json.dumps({'workflow_runs':[{**valid,**changes}]}))
        result=subprocess.run(['bash','-c',gate],env=env,capture_output=True,text=True)
        assert (result.returncode==0)==allowed,result.stdout+result.stderr
    fixture.write_text(json.dumps({'workflow_runs':[valid]}));env['SOURCE_RUN_ID']='13';env['SOURCE_WORKFLOW_ID']='101'
    assert subprocess.run(['bash','-c',gate],env=env,capture_output=True).returncode!=0
    env['SOURCE_RUN_ID']='12';env['SOURCE_WORKFLOW_ID']='102'
    assert subprocess.run(['bash','-c',gate],env=env,capture_output=True).returncode!=0
    env['SOURCE_WORKFLOW_ID']='101'
    assert subprocess.run(['bash','-c',gate],env=env,capture_output=True).returncode==0


def test_ci_has_no_render_hook_and_small_vm_swap_is_private():
    ci=yaml.safe_load((ROOT/'.github/workflows/ci.yml').read_text())
    assert set(ci['jobs'])=={'verify'}
    assert 'RENDER_DEPLOY' not in (ROOT/'.github/workflows/ci.yml').read_text()
    cloud=yaml.safe_load((ROOT/'infra/yandex/cloud-init.yaml').read_text())
    scripts={row['path']:row['content'] for row in cloud['write_files']}
    swap=scripts['/usr/local/sbin/agentpay-swap-init']
    assert 'chmod 600' in swap and '2G' in swap and 'swapon' in swap


def test_rendered_metadata_preserves_shell_variables_without_cli_expansion(tmp_path):
    import base64
    payload=b'\x00\x00\x00\x0bssh-ed25519'+b'\x00\x00\x00\x20'+b'x'*32
    public=tmp_path/'operator.pub';public.write_text('ssh-ed25519 '+base64.b64encode(payload).decode())
    output=tmp_path/'cloud-init.yaml'
    subprocess.run([sys.executable,str(ROOT/'infra/yandex/render_cloud_init.py'),'--ssh-public-key',str(public),'--output',str(output)],check=True,capture_output=True)
    rendered=output.read_text()
    # YC metadata-from-file expands $NAME before transmitting user-data.
    # Encode script contents; no shell variable may remain in the transport YAML.
    assert '$' not in rendered
    original=yaml.safe_load((ROOT/'infra/yandex/cloud-init.yaml').read_text())
    data=yaml.safe_load(rendered)
    expected={row['path']:row['content'] for row in original['write_files']}
    for row in data['write_files']:
        assert row['encoding']=='b64'
        assert base64.b64decode(row['content']).decode()==expected[row['path']]
