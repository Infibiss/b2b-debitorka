#!/usr/bin/env python3
"""Render cloud-init from an explicitly supplied PUBLIC SSH key, without cloud API calls."""
import argparse
import base64
import json
from pathlib import Path
import re
import sys

import yaml


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ssh-public-key',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:
        key=args.ssh_public_key.read_text().strip()
        if '\n' in key or not re.fullmatch(r'ssh-ed25519 [A-Za-z0-9+/]+={0,2}(?: [^\r\n]+)?',key):raise ValueError('Expected one Ed25519 public key')
        binary=base64.b64decode(key.split()[1],validate=True)
        if len(binary)!=51 or not binary.startswith(b'\x00\x00\x00\x0bssh-ed25519'):raise ValueError('Invalid Ed25519 public key')
        data=yaml.safe_load(Path(__file__).with_name('cloud-init.yaml').read_text())
        data['users'][1]['ssh_authorized_keys']=[key]
        # YC expands $NAME in metadata files. Transport all scripts/configs as
        # base64 so remote shell variables survive unchanged. Cloud-init decodes.
        for row in data['write_files']:
            row['content']=base64.b64encode(row['content'].encode()).decode()
            row['encoding']='b64'
        text='#cloud-config\n'+yaml.safe_dump(data,sort_keys=False)
        with args.output.open('x') as handle:handle.write(text)
    except (ValueError,OSError):
        print('Cloud-init rendering refused. Supply a valid public .pub key and a new output path.',file=sys.stderr);return 1
    print('Cloud-init rendered; no cloud resources were created.')
    return 0

if __name__=='__main__':raise SystemExit(main())
