"""Per-stage timing and resource aggregation over session records.

Pure functions, no I/O. A "record" is one line of a session `leituras.jsonl`
(see coletar_sessao.py). `row_from_record` flattens the per-stage numbers the
pipeline already measured; `summarize` reduces many rows to median/p95 per
stage plus a memory budget. The idle-zero rule matches ObservationMetrics:
reader stages with zero attempts are dropped so idle cycles do not dilute the
real reading cost, and OCR stages only count when some reader ran.
"""
import math
import statistics

# Capture -> detection -> OCR setup/work -> hero/buttons/board -> totals -> resources.
STAGE_ORDER = ('capture', 'detection', 'ocr_setup', 'ocr_wall', 'card_reading',
               'button_reading', 'board_reading', 'analyze_total', 'cycle', 'cpu')


def _numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) \
        and math.isfinite(value) and value >= 0


def row_from_record(record):
    """Flatten one session record into {stage: ms, ..., 'rss_mb': mb}.

    Only finite, non-negative values are kept. Stages absent from the record
    (e.g. a failed capture with no analysis) are simply omitted."""
    if not isinstance(record, dict):
        return {}
    row = {}
    capture = record.get('capture')
    if isinstance(capture, dict):
        row['capture'] = capture.get('duration_ms')
    report = record.get('report') if isinstance(record.get('report'), dict) else {}
    timings = report.get('timings_ms', {}) if isinstance(report.get('timings_ms'), dict) else {}
    for key in ('detection', 'ocr_setup', 'card_reading', 'button_reading', 'board_reading'):
        if key in timings:
            row[key] = timings[key]
    ocr_work = report.get('ocr_work', {}) if isinstance(report.get('ocr_work'), dict) else {}
    if 'wall_ms' in ocr_work:
        row['ocr_wall'] = ocr_work['wall_ms']
    attempts = report.get('attempts', {}) if isinstance(report.get('attempts'), dict) else {}
    for key in ('card_reading', 'button_reading', 'board_reading'):
        if attempts.get(key, 0) == 0:
            row.pop(key, None)
    if not any(attempts.values()):
        row.pop('ocr_setup', None)
        row.pop('ocr_wall', None)
    if 'duration_ms' in report:
        row['analyze_total'] = report['duration_ms']
    row['cycle'] = record.get('duration_ms')
    row['cpu'] = record.get('cpu_ms')
    row['rss_mb'] = record.get('rss_mb')
    return {k: float(v) for k, v in row.items() if _numeric(v)}


def _p95(values):
    return values[math.ceil(.95 * len(values)) - 1]


def summarize(rows):
    """Reduce flat rows to {stages:{name:{n,median_ms,p95_ms}}, memory, stage_order}."""
    rows = list(rows)
    stages = {}
    for key in sorted({k for r in rows for k in r if k != 'rss_mb'}):
        values = sorted(r[key] for r in rows if key in r)
        if values:
            stages[key] = {'n': len(values), 'median_ms': round(statistics.median(values), 1),
                           'p95_ms': round(_p95(values), 1)}
    memory = None
    rss = sorted(r['rss_mb'] for r in rows if 'rss_mb' in r)
    if rss:
        memory = {'n': len(rss), 'median_mb': round(statistics.median(rss), 1), 'peak_mb': round(rss[-1], 1)}
    order = [k for k in STAGE_ORDER if k in stages] + [k for k in stages if k not in STAGE_ORDER]
    return {'stages': stages, 'memory': memory, 'stage_order': order}


def format_table(profile):
    """Human-readable per-stage table (pt-BR), fixed stage order."""
    stages = profile.get('stages', {})
    order = profile.get('stage_order') or list(stages)
    lines = ['Etapa                n    mediana(ms)   p95(ms)',
             '-------------------- ---- ------------ ---------']
    for key in order:
        s = stages.get(key)
        if not s:
            continue
        lines.append(f"{key:<20} {s['n']:>4} {s['median_ms']:>12} {s['p95_ms']:>9}")
    memory = profile.get('memory')
    if memory:
        lines.append('')
        lines.append(f"Memoria RSS: mediana {memory['median_mb']} MiB | pico {memory['peak_mb']} MiB (n={memory['n']})")
    return '\n'.join(lines)
