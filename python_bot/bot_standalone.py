"""Compatibility entry: use the canonical console reader, without GUI/debug."""
from pathlib import Path
import sys

def main():
    here = Path(__file__).resolve().parent
    for candidate in (here, *here.parents):
        if (candidate / 'ler_mesas.py').is_file() and (candidate / 'table_reading' / 'pipeline.py').is_file():
            sys.path.insert(0, str(candidate))
            from ler_mesas import main as reader_main
            print('Leitor oficial:', candidate / 'ler_mesas.py')
            args = sys.argv[1:]
            if not args:
                print('Use --hwnd NUMERO --continuo --botoes --board. Ctrl+C encerra.')
                return reader_main(['--help'])
            return reader_main(args)
    raise SystemExit('Checkout incompleto: use a raiz da branch fix/strict-client-capture com ler_mesas.py e table_reading/.')

if __name__ == '__main__':
    raise SystemExit(main())
