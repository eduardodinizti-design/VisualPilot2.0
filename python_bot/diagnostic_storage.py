"""Bounded diagnostic writes; only recognized bundles may be rotated."""
from contextlib import contextmanager
from pathlib import Path
import os

DEFAULT_BUDGET = 100 * 1024 * 1024

@contextmanager
def _lock(root):
    root.mkdir(parents=True, exist_ok=True)
    with (root / '.diagnostic-storage.lock').open('a+b') as handle:
        handle.seek(0)
        if os.name == 'nt':
            import msvcrt
            if handle.read(1) == b'':
                handle.write(b'0'); handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _files(root):
    # Never follow symlinks, including Windows directory junctions.
    for base, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if not (Path(base)/d).is_symlink()
                   and not getattr(Path(base)/d, 'is_junction', lambda: False)()]
        for name in names:
            p = Path(base)/name
            if not p.is_symlink(): yield p


def store_bundle(root, files, budget=DEFAULT_BUDGET):
    """Paths relative to root; .keep protects a reading or capture pair.

    Unknown files count toward the cap but are never deleted. Refuse writes if
    protected/unknown data leaves insufficient space. All cooperating writers
    share the OS lock. This does not constrain unrelated external writers.
    """
    root = Path(root).absolute()
    paths = [root / p for p in files]
    for path in paths:
        if not path.resolve().is_relative_to(root.resolve()) or '..' in path.parts:
            raise ValueError('Unsafe diagnostic path')
        if path.exists(): raise FileExistsError(path)
    incoming = sum(len(v) for v in files.values())
    if incoming > budget: raise RuntimeError('Diagnostico maior que o limite global; nada removido.')
    with _lock(root):
        if any(p.exists() for p in paths): raise FileExistsError('Diagnostic already exists')
        existing = list(_files(root))
        used = sum(p.stat().st_size for p in existing)
        bundles = []
        for directory in (root/'leitura').glob('leitura-*'):
            if directory.is_dir() and not directory.is_symlink() and not getattr(directory, 'is_junction', lambda: False)() and not (directory/'.keep').exists():
                members = list(_files(directory))
                if (directory/'resultado.json').is_file() and not any(p.name=='.keep' for p in members):
                    bundles.append((members, directory))
        for report in (root/'diagnostics').glob('capture-*.json'):
            if not report.is_symlink() and not report.with_suffix('.keep').exists():
                bundles.append(([p for p in (report, report.with_suffix('.png')) if p.is_file() and not p.is_symlink()], None))
        bundles.sort(key=lambda b: min(p.stat().st_mtime_ns for p in b[0]))
        reclaimable = sum(sum(p.stat().st_size for p in members) for members,_ in bundles)
        if used + incoming - reclaimable > budget:
            raise RuntimeError('Limite global: arquivos protegidos ou externos impedem salvar. Nada removido.')
        for members, directory in bundles:
            if used + incoming <= budget: break
            for p in members:
                size=p.stat().st_size; p.unlink(); used-=size
            if directory:
                for base, dirs, _ in os.walk(directory, topdown=False):
                    for d in dirs: (Path(base)/d).rmdir()
                directory.rmdir()
        written=[]
        try:
            for relative, data in files.items():
                path=root/relative; path.parent.mkdir(parents=True,exist_ok=True)
                with path.open('xb') as handle: handle.write(data)
                written.append(path)
        except Exception:
            for path in written: path.unlink(missing_ok=True)
            raise
    return paths
