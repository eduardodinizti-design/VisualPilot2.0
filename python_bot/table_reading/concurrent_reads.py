"""At most two workers on one board; ordered results and snapshot-local context."""
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
import os

def ordered_board_reads(function, items, *, enabled=True):
    if not enabled or os.environ.get('VISUALPILOT_PARALLEL_BOARD','1')=='0':
        return [function(item) for item in items]
    with ThreadPoolExecutor(max_workers=2,thread_name_prefix='board-reader') as pool:
        futures=[pool.submit(copy_context().run,function,item) for item in items]
        return [future.result() for future in futures]
