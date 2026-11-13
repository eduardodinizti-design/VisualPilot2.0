"""Study supplied snapshots against an NVT package. Never captures or clicks."""
import argparse
import json
from preflop_study import RangeBook, study_tables, exported_example


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ranges', required=True)
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument('--cenario', help='JSON with a tables list; explicit simulation evidence only')
    source.add_argument('--exemplo', help='Validated open_raise node ID; creates a fictional observation from its table')
    p.add_argument('--cartas', nargs=2, help='Physical hero cards for --exemplo, e.g. Ah Kd')
    args = p.parse_args(argv)
    try:
        book = RangeBook(args.ranges)
        if args.exemplo:
            scenes = [exported_example(book, args.exemplo, args.cartas)]
        else:
            with open(args.cenario, encoding='utf8') as stream:
                scenes = json.load(stream)['tables']
        result = study_tables(scenes, book)
        print(json.dumps(dict(scope='OFFLINE_SIMULATION', tables=result), ensure_ascii=False, indent=2))
        return 0 if all(r['status']=='STUDY_ONLY' for r in result) else 2
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps(dict(status='ABSTAIN', reason=str(exc), execution_allowed=False)))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
