"""Deployment recipe tests never contact a VM or create paid resources."""
from pathlib import Path
import os
import shutil
import subprocess
import sys

import pytest
import yaml
from scripts.private_files import is_private

ROOT=Path(__file__).resolve().parents[1]


def bash(*arguments):
    if os.name=='nt':
        # Native MSYS/Git Bash accepts Windows paths. WSL's bash.exe does not
        # share the host path or Python runtime and must not be chosen by PATH.
        candidates=[os.getenv('TEST_BASH',''),
                    str(Path(os.getenv('ProgramFiles','C:/Program Files'))/'Git/bin/bash.exe'),
                    'C:/msys64/usr/bin/bash.exe']
        executable=next((value for value in candidates if value and Path(value).is_file()),None)
        if not executable:
            raise RuntimeError('Install native Git Bash/MSYS2 or set TEST_BASH')
    else:
        executable=os.getenv('TEST_BASH') or shutil.which('bash')
        if not executable:
            raise RuntimeError('Install bash or set TEST_BASH')
    return [executable,*[str(value).replace('\\','/') if isinstance(value,Path) else value for value in arguments]]


def prepare(path,ip='203.0.113.10',public_url=None):
    args=[sys.executable,str(ROOT/'infra/yandex/prepare_env.py'),'--public-ip',ip,'--output',str(path)]
    if public_url is not None:args+=['--public-url',public_url]
    return subprocess.run(args,capture_output=True,text=True)


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
    assert is_private(path)
    assert prepare(path).returncode==0 and path.read_text()==content
    assert prepare(path,ip='203.0.113.11').returncode!=0 and path.read_text()==content


def test_invalid_ip_and_unpinned_ssh_fail_before_any_remote_action(tmp_path):
    path=tmp_path/'bad.env'
    assert prepare(path,ip='not-an-ip').returncode!=0 and not path.exists()
    result=subprocess.run(bash('-s','--','--host','203.0.113.10','--revision','a'*40,'--identity-file',tmp_path/'missing-key','--known-hosts',tmp_path/'missing-hosts'),
                          input=(ROOT/'scripts/deploy_yandex_vm.sh').read_text(encoding='utf-8').encode('utf-8'),capture_output=True)
    assert result.returncode!=0
    assert b'SSH identity and verified known_hosts files are required.' in result.stderr


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
        # Feed UTF-8/LF source through stdin so a Windows CRLF checkout does not
        # change the Linux shell program being syntax-checked.
        result=subprocess.run(bash('-n'),input=(ROOT/script).read_text(encoding='utf-8').encode('utf-8'),capture_output=True)
        assert result.returncode==0,result.stderr
    text=(ROOT/'scripts/deploy_yandex_vm.sh').read_text()
    assert '-o StrictHostKeyChecking=yes' in text and 'hashlib.file_digest' in text
    assert 'options=(-F /dev/null ' in text
    assert 'git get-tar-commit-id' in text and 'before stopping' in text
    assert 'filter=\'data\'' in text
    assert 'bash -s --' not in text
    assert 'cat > "$remote_script"' in text
    assert '"$checksum" "$host" "$public_url" < /dev/null' in text


@pytest.mark.parametrize('url',[
    'http://mandato.ru','https://mandato.ru/','https://mandato.ru/path',
    'https://mandato.ru?token=secret','https://mandato.ru#fragment',
    'https://user@mandato.ru','https://mandato.ru:443','https://MANDATO.ru',
    'https://other domain.ru','https://-bad.ru','https://203.0.113.11',
    'https://mandato.ru;touch /tmp/no','https://mandato.ru\n',
])
def test_custom_public_origin_rejects_unsafe_or_ambiguous_urls(tmp_path,url):
    path=tmp_path/'production.env'
    result=prepare(path,public_url=url)
    assert result.returncode!=0 and not path.exists()
    assert url not in result.stdout+result.stderr


def test_custom_domain_requires_existing_matching_config_and_never_rewrites(tmp_path):
    path=tmp_path/'production.env'
    assert prepare(path,public_url='https://mandato.ru').returncode!=0
    assert not path.exists()
    assert prepare(path).returncode==0
    original=path.read_text()
    assert prepare(path,public_url='https://mandato.ru').returncode!=0
    assert path.read_text()==original
    configured=original.replace('APP_URL=https://203.0.113.10','APP_URL=https://mandato.ru')
    path.write_text(configured)
    assert prepare(path,public_url='https://mandato.ru').returncode==0
    assert path.read_text()==configured
    assert prepare(path).returncode!=0 and path.read_text()==configured
    assert prepare(path,ip='203.0.113.11',public_url='https://mandato.ru').returncode!=0
    assert path.read_text()==configured


def test_origin_validation_does_not_provision_domain_config(tmp_path):
    path=tmp_path/'not-created/production.env'
    result=subprocess.run([sys.executable,str(ROOT/'infra/yandex/prepare_env.py'),
        '--public-ip','203.0.113.10','--public-url','https://mandato.ru',
        '--output',str(path),'--validate-only'],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert not path.parent.exists()


def test_optional_cd_public_origin_is_passed_as_one_argument_without_enabling_deploy():
    spec=yaml.safe_load((ROOT/'.github/workflows/deploy-yandex.yml').read_text())
    job=spec['jobs']['deploy']
    assert "vars.YANDEX_VM_DEPLOY_ENABLED == 'true'" in job['if']
    step=job['steps'][-1]
    assert step['env']['DEPLOY_PUBLIC_URL']=='${{ vars.YANDEX_VM_PUBLIC_URL }}'
    assert 'target_args+=(--public-url "$DEPLOY_PUBLIC_URL")' in step['run']
    assert '"${target_args[@]}"' in step['run']
    result=subprocess.run(bash('-n'),input=step['run'].encode(),capture_output=True)
    assert result.returncode==0,result.stderr


def test_domain_preflight_refuses_missing_nginx_without_mutating_files(tmp_path):
    script=(ROOT/'scripts/deploy_yandex_vm.sh').read_text()
    start=script.index('custom_domain=false')
    end=script.index('compose=(',start)
    path=tmp_path/'nginx-site.conf'
    env={**os.environ,'config':path.as_posix(),'public_ip':'203.0.113.10','public_url':'https://mandato.ru'}
    result=subprocess.run(bash('-c','set -euo pipefail\n'+script[start:end]),env=env,capture_output=True,text=True)
    assert result.returncode!=0 and 'configuration is missing' in result.stderr
    assert not path.exists()


@pytest.mark.parametrize('custom_domain,certificate,expected',[
    ('true',True,'existing domain configuration'),
    ('false',True,'HTTPS 203.0.113.10'),
    ('false',False,'bootstrap configuration'),
])
def test_nginx_domain_branch_preserves_existing_config_while_ip_path_stays_compatible(tmp_path,custom_domain,certificate,expected):
    script=(ROOT/'scripts/deploy_yandex_vm.sh').read_text()
    start=script.index('certificate_present=false')
    end=script.index('"${compose[@]}" up -d --wait',start)
    config=tmp_path/'nginx-site.conf';config.write_text('existing domain configuration')
    templates=tmp_path/'infra/yandex';templates.mkdir(parents=True)
    (templates/'nginx-https.conf.template').write_text('HTTPS PUBLIC_IP')
    (templates/'nginx-bootstrap.conf').write_text('bootstrap configuration')
    env={**os.environ,'custom_domain':custom_domain,'config':config.as_posix(),'public_ip':'203.0.113.10'}
    snippet='set -euo pipefail\ncompose=('+('true' if certificate else 'false')+')\n'+script[start:end]
    result=subprocess.run(bash('-c',snippet),cwd=tmp_path,env=env,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert config.read_text()==expected
    # Missing domain config must fail before build/stop, and health must target the origin.
    assert script.index('Custom-domain nginx configuration is missing')<script.index('"${compose[@]}" build app')
    assert '"$public_url/api/health"' in script


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
    stub=tools/'gh.py'
    stub.write_text('import os,sys\nfrom pathlib import Path\nprint("101" if sys.argv[2].endswith("/ci.yml") else Path(os.environ["GH_FIXTURE"]).read_text())\n',encoding='utf-8')
    commit='a'*40;repo='example/agentpay'
    valid={'id':12,'workflow_id':101,'head_sha':commit,'head_branch':'main','event':'push','status':'completed','conclusion':'success','head_repository':{'full_name':repo}}
    env={**os.environ,'RELEASE_SHA':commit,'GITHUB_REPOSITORY':repo,'RUNNER_TEMP':tmp_path.as_posix(),'SOURCE_RUN_ID':'','SOURCE_WORKFLOW_ID':'',
         'TEST_PYTHON':Path(sys.executable).as_posix(),'TEST_GH_STUB':stub.as_posix()}
    # Exercise the exact production gate, using local functions for its two
    # executables instead of a POSIX shebang pointing at Windows python.exe.
    gate='python3() { "$TEST_PYTHON" "$@"; }\ngh() { "$TEST_PYTHON" "$TEST_GH_STUB" "$@"; }\n'+gate
    fixture=tmp_path/'runs.json';env['GH_FIXTURE']=fixture.as_posix()
    for changes,allowed in [({},True),({'event':'pull_request'},False),({'head_branch':'feature'},False),({'head_repository':{'full_name':'fork/agentpay'}},False),({'head_sha':'b'*40},False),({'workflow_id':102},False),({'conclusion':'failure'},False)]:
        fixture.write_text(json.dumps({'workflow_runs':[{**valid,**changes}]}))
        result=subprocess.run(bash('-c',gate),env=env,capture_output=True,text=True)
        assert (result.returncode==0)==allowed,result.stdout+result.stderr
    fixture.write_text(json.dumps({'workflow_runs':[valid]}));env['SOURCE_RUN_ID']='13';env['SOURCE_WORKFLOW_ID']='101'
    assert subprocess.run(bash('-c',gate),env=env,capture_output=True).returncode!=0
    env['SOURCE_RUN_ID']='12';env['SOURCE_WORKFLOW_ID']='102'
    assert subprocess.run(bash('-c',gate),env=env,capture_output=True).returncode!=0
    env['SOURCE_WORKFLOW_ID']='101'
    assert subprocess.run(bash('-c',gate),env=env,capture_output=True).returncode==0


def test_prepare_refuses_existing_non_private_config_without_rewriting_it(tmp_path):
    path=tmp_path/'production.env'
    assert prepare(path).returncode==0
    original=path.read_bytes()
    if os.name=='nt':
        assert subprocess.run(['icacls',str(path),'/grant','*S-1-1-0:R'],capture_output=True).returncode==0
    else:
        path.chmod(0o644)
    assert not is_private(path)
    assert prepare(path).returncode!=0
    assert path.read_bytes()==original


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
