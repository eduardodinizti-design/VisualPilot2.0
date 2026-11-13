"""PPPoker window discovery for VisualPilot (discovery/identity only).

Scope is deliberately PPPoker-only (see the handoff: do not pull multi-room
support into the recognizer). This layer answers one question: which live
top-level windows belong to PPPoker, with their identity and geometry. It does
not capture cards, move windows, open accounts or send input.

It deliberately does NOT try to tell a table from a lobby at the window level.
On real setups one PPPoker window is a large canvas (e.g. 3840x1440) holding a
table, the lobby and side panels at once, and a GPU (Unity) window does not
render through PrintWindow, so a whole-window felt-colour test is both wrong and
unreliable. Separating the blue table region from the lobby is VisualPilot's own
detector job, downstream and already validated. Discovery just hands the HWNDs
to observe; the pipeline rejects the lobby regions.

Identity still comes from VisualPilot binding each HWND to pid + process_created
at capture time; the pid here is informational.
"""
import argparse

from .windows import enum_windows

PPPOKER_PROCESS = 'PPPoker.exe'
MIN_SIZE = 150


def _as_dict(w):
    return dict(hwnd=w.hwnd, pid=w.pid, process=w.process, title=w.title,
                rect=list(w.rect), x=w.x, y=w.y, w=w.w, h=w.h, minimized=w.minimized)


def discover_pppoker(windows=None):
    """Return {'windows': [...]} — the live, visible PPPoker windows to observe.

    `windows` is an optional pre-enumerated list of WindowInfo (injected in
    tests); otherwise the live top-level windows are enumerated."""
    windows = windows if windows is not None else enum_windows()
    found = [_as_dict(w) for w in windows
             if w.process.lower() == PPPOKER_PROCESS.lower()
             and not w.minimized and w.w >= MIN_SIZE and w.h >= MIN_SIZE]
    return {'windows': found}


def pppoker_table_hwnds(windows=None, max_tables=6):
    """Live PPPoker window HWNDs to observe, capped at max_tables."""
    return [w['hwnd'] for w in discover_pppoker(windows)['windows'][:max_tables]]


def main(argv=None):
    parser = argparse.ArgumentParser(description='Lista as janelas PPPoker abertas (sem cliques, sem captura de cartas).')
    parser.add_argument('--json', action='store_true', help='Saida em JSON')
    args = parser.parse_args(argv)
    found = discover_pppoker()
    if args.json:
        import json
        print(json.dumps(found, ensure_ascii=False, indent=2))
        return 0
    windows = found['windows']
    if not windows:
        print('Nenhuma janela PPPoker encontrada. Abra o PPPoker e tente novamente.')
        return 2
    for w in windows:
        print(f"PPPoker | HWND {w['hwnd']} | PID {w['pid']} | {w['w']}x{w['h']} em ({w['x']},{w['y']}) | {w['title']}")
    print(f"\n{len(windows)} janela(s) PPPoker. A mesa (feltro azul) e o lobby sao separados na leitura.")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
