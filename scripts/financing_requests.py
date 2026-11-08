"""Operator queue for financing applications.

python -m scripts.financing_requests list
python -m scripts.financing_requests update --request UUID --status in_review --partner "Банк"
python -m scripts.financing_requests update --request UUID --status funded --funded-amount 30000000 --repay-amount 33000000 --funded-on 2026-12-01

Amounts are kopeks. The application reaches the partner only by the operator's
action, under the client's recorded consent.
"""
import argparse
from datetime import date, datetime, timezone

from server.database import Config, database
from server.financing import STATUS_LABELS

TRANSITIONS = {
    'requested': {'in_review', 'declined'},
    'in_review': {'offer', 'declined'},
    'offer': {'funded', 'declined'},
    'funded': {'repaid'},
}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Financing application queue')
    commands = parser.add_subparsers(dest='command', required=True)
    listing = commands.add_parser('list')
    listing.add_argument('--status', choices=tuple(STATUS_LABELS))
    update = commands.add_parser('update')
    update.add_argument('--request', required=True)
    update.add_argument('--status', required=True, choices=tuple(STATUS_LABELS))
    update.add_argument('--partner', default='')
    update.add_argument('--note', default='')
    update.add_argument('--funded-amount', type=int)
    update.add_argument('--repay-amount', type=int)
    update.add_argument('--funded-on', type=date.fromisoformat)
    args = parser.parse_args(argv)
    config = Config.from_environment()
    if args.command == 'list':
        with database(config) as connection:
            rows = connection.execute('SELECT id,status,product_id,debtor_name,amount,partner,created_at FROM financing_requests ORDER BY created_at').fetchall()
        for row in rows:
            if not args.status or row['status'] == args.status:
                print(row['id'], row['status'], row['product_id'], row['debtor_name'], row['amount'], row['partner'], row['created_at'], sep=' | ')
        return 0
    if args.status == 'funded' and not (args.funded_amount and args.repay_amount and args.funded_on):
        parser.error('funded requires --funded-amount, --repay-amount and --funded-on')
    with database(config, write=True) as connection:
        row = connection.execute('SELECT status FROM financing_requests WHERE id=?', (args.request,)).fetchone()
        if not row:
            parser.error('request not found')
        if args.status not in TRANSITIONS.get(row['status'], set()):
            parser.error(f"cannot move from {row['status']} to {args.status}")
        connection.execute('''UPDATE financing_requests SET status=?,partner=COALESCE(NULLIF(?,''),partner),partner_note=COALESCE(NULLIF(?,''),partner_note),
            funded_amount=COALESCE(?,funded_amount),repay_amount=COALESCE(?,repay_amount),funded_on=COALESCE(?,funded_on),updated_at=? WHERE id=?''',
                           (args.status, args.partner, args.note, args.funded_amount, args.repay_amount, str(args.funded_on) if args.funded_on else None, datetime.now(timezone.utc).isoformat(), args.request))
    print('updated')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
