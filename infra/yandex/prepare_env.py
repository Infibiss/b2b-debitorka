#!/usr/bin/env python3
"""Generate one private VM config without printing secrets or rotating a live DB password."""
import argparse
import ipaddress
import os
from pathlib import Path
import secrets
import sys

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
from scripts.private_files import create_private, is_private


def prepare(public_ip,output):
    ip=ipaddress.ip_address(public_ip)
    if ip.version!=4:raise ValueError('Use the VM public IPv4 address')
    output=Path(output).expanduser().absolute()
    if output.is_symlink():raise ValueError('Config must not be a symbolic link')
    url='https://'+str(ip)
    if output.exists():
        values=dict(line.split('=',1) for line in output.read_text().splitlines() if line and not line.startswith('#') and '=' in line)
        if not is_private(output):raise ValueError('Existing config must have private owner-only permissions')
        if values.get('APP_URL')!=url:raise ValueError('Existing APP_URL differs. Review IP, TLS certificate and session origin before changing it')
        if values.get('APP_ENV')!='production' or values.get('SECURE_COOKIES')!='true' or len(values.get('APP_DB_PASSWORD',''))<40:raise ValueError('Existing production config is incomplete; review it without rotating the live database password')
        return output
    output.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    password=secrets.token_hex(32)
    content=f'''# Generated on the VM; do not commit, paste into logs, or rotate APP_DB_PASSWORD on a populated volume.
AGENTPAY_ENV_FILE={output}
AGENTPAY_CONFIG_DIR={output.parent}
APP_PUBLIC_IP={ip}
APP_URL={url}
APP_ENV=production
SECURE_COOKIES=true
APP_TIMEZONE=Europe/Moscow
APP_DB_PASSWORD={password}
YANDEX_API_KEY=
YANDEX_MODEL=
YANDEX_AGENT_TENANT_IDS=
YANDEX_OCR_ENABLED=false
YANDEX_VOICE_ENABLED=false
WORKFLOW_WORKER_ENABLED=true
SMTP_HOST=
SMTP_FROM=
SMTP_TENANT_ID=
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_BASE_URL=
'''
    descriptor=create_private(output)
    with os.fdopen(descriptor,'w',encoding='utf-8',newline='\n') as handle:
        handle.write(content);handle.flush();os.fsync(handle.fileno())
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--public-ip',required=True)
    parser.add_argument('--output',type=Path,default=Path('/etc/agentpay/production.env'))
    args=parser.parse_args()
    try:prepare(args.public_ip,args.output)
    except (ValueError,OSError):
        print('Private config preparation refused. Check IPv4, file permissions and existing APP_URL; existing files were preserved.',file=sys.stderr);return 1
    print('Private production configuration ready; secret values were not displayed.')
    return 0

if __name__=='__main__':raise SystemExit(main())
