import json
from pathlib import Path
import pytest
from infra.yandex import pull_cd as cd

SHA='a'*40
REPO='Infibiss/b2b-debitorka'
def run(**changes):
    return dict(id=10,workflow_id=11,path='.github/workflows/ci.yml',head_sha=SHA,head_branch='main',event='push',status='completed',conclusion='success',head_repository={'full_name':REPO},**changes)

@pytest.mark.parametrize('field,value', [('head_sha','b'*40),('event','pull_request'),('head_branch','feature'),('conclusion','failure'),('status','in_progress'),('workflow_id',12),('path','.github/workflows/other.yml'),('head_repository',{'full_name':'evil/fork'})])
def test_provenance(field,value):
    good=run();assert cd.approved(good,SHA,11)
    good[field]=value;assert not cd.approved(good,SHA,11)

def test_bad_shas_and_workflow_metadata():
    for sha in ['main','a'*39,'a'*40+';x','A'*40,'../secret']:
        with pytest.raises(ValueError):cd.validate_sha(sha)
    assert cd.validate_sha(SHA)==SHA

def test_no_ci_current_and_failed_are_noop(tmp_path,monkeypatch):
    ctl=cd.Controller(tmp_path,'https://mandato.ru','158.160.164.25',Path('/trusted/release.sh'))
    monkeypatch.setattr(ctl,'head',lambda:SHA)
    monkeypatch.setattr(ctl,'current',lambda:SHA)
    monkeypatch.setattr(ctl,'eligible',lambda sha:pytest.fail('current release must not query CI'))
    assert ctl.tick()=='current'
    monkeypatch.setattr(ctl,'current',lambda:'b'*40)
    ctl.save({'failed_sha':SHA})
    assert ctl.tick()=='failed_revision'
    ctl.save({})
    monkeypatch.setattr(ctl,'eligible',lambda sha:False)
    monkeypatch.setattr(ctl,'deploy',lambda sha:pytest.fail('unverified must not deploy'))
    assert ctl.tick()=='awaiting_ci'


def test_changed_head_and_success(tmp_path,monkeypatch):
    ctl=cd.Controller(tmp_path,'https://mandato.ru','158.160.164.25',Path('/trusted/release.sh'))
    monkeypatch.setattr(ctl,'current',lambda:'b'*40)
    monkeypatch.setattr(ctl,'eligible',lambda sha:True)
    heads=iter([SHA,'c'*40]);monkeypatch.setattr(ctl,'head',lambda:next(heads))
    monkeypatch.setattr(ctl,'deploy',lambda sha:pytest.fail('superseded revision'))
    assert ctl.tick()=='superseded'
    monkeypatch.setattr(ctl,'head',lambda:SHA)
    deployed=[];monkeypatch.setattr(ctl,'deploy',lambda sha:deployed.append(sha))
    assert ctl.tick()=='deployed' and deployed==[SHA]
    assert ctl.load()['last_success']==SHA


def test_failure_is_latched_and_state_private(tmp_path,monkeypatch):
    ctl=cd.Controller(tmp_path,'https://mandato.ru','158.160.164.25',Path('/trusted/release.sh'))
    monkeypatch.setattr(ctl,'head',lambda:SHA)
    monkeypatch.setattr(ctl,'current',lambda:'b'*40)
    monkeypatch.setattr(ctl,'eligible',lambda sha:True)
    def fail(sha):raise RuntimeError('build failed')
    monkeypatch.setattr(ctl,'deploy',fail)
    with pytest.raises(RuntimeError):ctl.tick()
    assert ctl.tick()=='failed_revision'
    if __import__('os').name!='nt':assert ctl.state.stat().st_mode & 0o777==0o600


def test_guard_rechecks_ci_and_head(tmp_path,monkeypatch):
    ctl=cd.Controller(tmp_path,'https://mandato.ru','158.160.164.25',Path('/trusted/release.sh'))
    monkeypatch.setattr(ctl,'head',lambda:'b'*40)
    monkeypatch.setattr(ctl,'eligible',lambda sha:True)
    assert not ctl.guard(SHA)
    monkeypatch.setattr(ctl,'head',lambda:SHA)
    monkeypatch.setattr(ctl,'eligible',lambda sha:False)
    assert not ctl.guard(SHA)


def test_backoff_without_request(tmp_path,monkeypatch):
    ctl=cd.Controller(tmp_path,'https://mandato.ru','158.160.164.25',Path('/trusted/release.sh'))
    ctl.save({'next_check':__import__('time').time()+600})
    monkeypatch.setattr(ctl,'head',lambda:pytest.fail('backoff must not request'))
    assert ctl.tick()=='backoff'


def test_api_provenance_workflow_identity(monkeypatch,tmp_path):
    ctl=cd.Controller(tmp_path,'https://mandato.ru','158.160.164.25',Path('/trusted/release.sh'))
    def api(path):
        if '?' in path:return {'workflow_runs':[run()]}
        return {'id':11,'path':'.github/workflows/ci.yml','state':'active'}
    monkeypatch.setattr(cd,'request',api)
    assert ctl.eligible(SHA)
    monkeypatch.setattr(cd,'request',lambda path:{'id':11,'path':'other.yml','state':'active'})
    assert not ctl.eligible(SHA)


def test_dry_run_never_deploys_or_latches(tmp_path,monkeypatch):
    ctl=cd.Controller(tmp_path,'https://mandato.ru','158.160.164.25',Path('/trusted/release.sh'))
    ctl.dry_run=True
    monkeypatch.setattr(ctl,'head',lambda:SHA)
    monkeypatch.setattr(ctl,'current',lambda:None)
    monkeypatch.setattr(ctl,'eligible',lambda sha:True)
    monkeypatch.setattr(ctl,'deploy',lambda sha:pytest.fail('dry run'))
    assert ctl.tick()=='eligible_dry_run' and not ctl.state.exists()


def test_release_guard_runs_before_app_stop():
    source=(Path(__file__).resolve().parents[1]/'infra/yandex/deploy_release.sh').read_text()
    assert source.index('"${compose[@]}" build app')<source.index('--guard "$release"')<source.index('"${compose[@]}" stop')


def test_service_has_no_runner_or_secret_and_timer_is_opt_in():
    root=Path(__file__).resolve().parents[1]/'infra/yandex'
    service=(root/'agentpay-cd.service').read_text()
    installer=(root/'install_pull_cd.sh').read_text()
    assert 'User=agentpay' in service and 'ProtectSystem=strict' in service
    assert 'OnCalendar=*:0/5' in (root/'agentpay-cd.timer').read_text()
    assert 'enable --now' not in installer and 'registration-token' not in installer


def test_low_disk_never_downloads_or_builds(tmp_path,monkeypatch):
    from types import SimpleNamespace
    ctl=cd.Controller(tmp_path,'https://mandato.ru','158.160.164.25',Path('/trusted/release.sh'))
    monkeypatch.setattr(cd.shutil,'disk_usage',lambda path:SimpleNamespace(free=1))
    monkeypatch.setattr(cd.subprocess,'run',lambda *a,**kw:pytest.fail('low disk must not start a command'))
    with pytest.raises(RuntimeError,match='disk space'):ctl.deploy(SHA)


@pytest.mark.parametrize('phase,resume',[('backup',True),('activating',False)])
def test_release_failure_recovery_is_phase_aware(tmp_path,phase,resume):
    import subprocess
    root=Path(__file__).resolve().parents[1]
    source=(root/'infra/yandex/deploy_release.sh').read_text()
    start=source.index('# BEGIN RECOVERY')
    end=source.index('# END RECOVERY')
    log=tmp_path/'log';marker=tmp_path/'needs-operator'
    program=source[start:end]+f'\nold_stopped=true\nphase={phase}\nexit 7\n'
    setup='set -euo pipefail\ncompose_stub() { echo "$*" >> "$TEST_LOG"; }\ncompose=(compose_stub)\nrelease='+SHA+'\n'
    result=subprocess.run(['bash','-c',setup+program],env={**__import__('os').environ,'TEST_LOG':str(log),'AGENTPAY_OPERATOR_MARKER':str(marker)},capture_output=True)
    assert result.returncode==7
    assert log.exists()==resume
    assert marker.exists()!=resume
