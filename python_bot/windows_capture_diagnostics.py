"""Capture-only diagnostics. Never selects a substitute for an explicit HWND."""
import argparse
import json
from pathlib import Path
import time
from window_capture_engine import WindowCaptureEngine


def run_diagnostics(target_hwnd=None, output_dir='logs/diagnostics', *, _engine=None):
    engine = _engine or WindowCaptureEngine()
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    frame, metadata = engine.capture_frame(hwnd=target_hwnd)
    report = dict(metadata, requested_hwnd=target_hwnd, capture_success=frame is not None,
                  actions_allowed=False, candidates=metadata.get('candidates', engine.last_diagnostics))
    stamp = str(time.time_ns())
    files = {}
    if frame is not None:
        try:
            import cv2
            ok, encoded = cv2.imencode('.png', frame)
            if not ok: raise RuntimeError('PNG encoding failed')
            image = directory / f'capture-{stamp}.png'
            files[str(Path(directory.name)/image.name)] = encoded.tobytes()
            report['image_path'] = str(image)
        except Exception as exc:
            report['image_save_error'] = str(exc)
    target = directory / f'capture-{stamp}.json'
    files[str(Path(directory.name)/target.name)] = json.dumps(report, ensure_ascii=False, indent=2).encode('utf-8')
    from diagnostic_storage import store_bundle
    store_bundle(directory.parent, files)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print('Diagnostic:', target)
    return report

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--hwnd', type=lambda s: int(s, 0))
    parser.add_argument('--output-dir', default='logs/diagnostics')
    args = parser.parse_args()
    run_diagnostics(args.hwnd, args.output_dir)
