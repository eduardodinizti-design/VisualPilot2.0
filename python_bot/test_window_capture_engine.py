"""Contract tests with explicit fake backend. No native Windows claims."""
from contextlib import nullcontext
import ctypes
import unittest
from unittest.mock import patch, MagicMock
import numpy as np
from window_capture_engine import WindowCaptureEngine, CaptureError, _NativeBackend

class Backend:
    def __init__(self):
        self.windows = {1: dict(hwnd=1, pid=44, process_created=100, executable=r'C:\PPPoker\PPPoker.exe',
                               title='MTT NLH', client_rect=(0,0,16,24), screen_origin=(-1280,0))}
        self.after = None
        self.captured = []
        self.fail = None
    def physical_pixels(self): return nullcontext()
    def handles(self): return list(self.windows)
    def state(self, hwnd):
        if self.fail: raise self.fail
        if hwnd not in self.windows: raise CaptureError('WINDOW_INVALID_HWND')
        return self.windows[hwnd].copy()
    def pixels(self, hwnd, w, h):
        self.captured.append((hwnd,w,h))
        if self.after: self.after(self.windows[hwnd])
        return np.full((h,w,3), 50, np.uint8)

class CaptureContracts(unittest.TestCase):
    def setUp(self):
        self.backend=Backend();self.engine=WindowCaptureEngine(_backend=self.backend)
    def test_client_dimensions_negative_origin_and_title_not_required(self):
        frame,meta=self.engine.capture_frame()
        self.assertEqual(frame.shape,(24,16,3));self.assertEqual(meta['screen_origin'],(-1280,0))
        self.assertEqual(self.backend.captured,[(1,16,24)])
    def test_large_unity_surface_not_rejected(self):
        self.backend.windows[1]['client_rect']=(0,0,2560,1440)
        self.assertEqual(self.engine.capture_frame()[1]['status'],'SUCCESS')
    def test_unauthorized_process(self):
        for executable in ['chrome.exe','unknown.exe','python.exe','random.exe']:
            self.backend.windows[1]['executable']=executable
            frame,meta=self.engine.capture_frame(hwnd=1)
            self.assertIsNone(frame);self.assertEqual(meta['status'],'EXECUTABLE_NOT_ALLOWED')
        self.assertFalse(self.backend.captured)
    def test_query_failure(self):
        self.backend.fail=CaptureError('PROCESS_QUERY_FAILED')
        self.assertEqual(self.engine.capture_frame(hwnd=1)[1]['status'],'PROCESS_QUERY_FAILED')
        self.assertFalse(self.backend.captured)
    def test_ambiguous_and_explicit_selection(self):
        self.backend.windows[2]=dict(self.backend.windows[1],hwnd=2)
        self.assertEqual(self.engine.capture_frame()[1]['status'],'WINDOW_AMBIGUOUS')
        self.assertFalse(self.backend.captured)
        self.assertEqual(self.engine.capture_frame(hwnd=2)[1]['hwnd'],2)
    def test_explicit_invalid_does_not_select_other(self):
        self.assertEqual(self.engine.capture_frame(hwnd=99)[1]['status'],'WINDOW_INVALID_HWND')
        self.assertFalse(self.backend.captured)
    def test_identity_and_geometry_changes(self):
        changes={'pid':99,'process_created':999,'executable':r'D:\PPPoker.exe',
                 'screen_origin':(800,200),'client_rect':(0,0,17,24)}
        for key,value in changes.items():
            with self.subTest(key=key):
                b=Backend();b.after=lambda s,k=key,v=value:s.update({k:v})
                frame,meta=WindowCaptureEngine(_backend=b).capture_frame()
                self.assertIsNone(frame);self.assertEqual(meta['status'],'WINDOW_CHANGED_DURING_CAPTURE')
    def test_minimized(self):
        self.backend.fail=CaptureError('WINDOW_MINIMIZED')
        self.assertEqual(self.engine.capture_frame(hwnd=1)[1]['status'],'WINDOW_MINIMIZED')
    def test_dpi_failure_prevents_capture(self):
        self.backend.physical_pixels=MagicMock(side_effect=CaptureError('DPI_CONTEXT_FAILED'))
        self.assertEqual(self.engine.capture_frame()[1]['status'],'DPI_CONTEXT_FAILED')
        self.assertFalse(self.backend.captured)
    def test_blank_frame_not_success(self):
        self.backend.pixels=lambda hwnd,w,h:np.zeros((h,w,3),np.uint8)
        self.assertEqual(self.engine.capture_frame()[1]['status'],'BLACK_FRAME_UNVERIFIED')

class GDIContracts(unittest.TestCase):
    def backend(self):
        n=_NativeBackend.__new__(_NativeBackend);n.np=np;n.u=MagicMock();n.g=MagicMock()
        n.u.GetDC.return_value=10;n.u.ReleaseDC.return_value=1
        n.g.CreateCompatibleDC.return_value=20;n.g.CreateCompatibleBitmap.return_value=30
        n.g.SelectObject.return_value=40;n.g.BitBlt.return_value=1
        n.g.DeleteObject.return_value=1;n.g.DeleteDC.return_value=1
        def pixels(dc,bmp,start,lines,buffer,header,usage):
            ctypes.memset(buffer,71,16*24*4)
            return lines
        n.g.GetDIBits.side_effect=pixels
        return n
    def test_success_uses_client_dc_and_releases_only_owned_dc(self):
        n=self.backend();frame=n.pixels(1,16,24)
        self.assertEqual(frame.shape,(24,16,3));self.assertTrue((frame==71).all())
        n.u.GetDC.assert_called_once_with(1)
        n.g.BitBlt.assert_called_once_with(20,0,0,16,24,10,0,0,0x00CC0020)
        self.assertEqual(n.g.SelectObject.call_args_list[-1].args,(20,40))
        n.g.DeleteObject.assert_called_once_with(30);n.g.DeleteDC.assert_called_once_with(20)
        n.u.ReleaseDC.assert_called_once_with(1,10)
    def test_bitblt_exception_restores_bitmap_and_frees_all(self):
        n=self.backend();n.g.BitBlt.side_effect=RuntimeError('injected failure')
        with self.assertRaises(RuntimeError):n.pixels(1,16,24)
        self.assertEqual(n.g.SelectObject.call_args_list[-1].args,(20,40))
        n.g.DeleteObject.assert_called_once_with(30);n.g.DeleteDC.assert_called_once_with(20)
        n.u.ReleaseDC.assert_called_once_with(1,10)
    def test_partial_acquisition_failure(self):
        n=self.backend();n.g.CreateCompatibleBitmap.side_effect=RuntimeError('allocation failed')
        with self.assertRaises(RuntimeError):n.pixels(1,16,24)
        n.g.DeleteObject.assert_not_called();n.g.DeleteDC.assert_called_once_with(20)
        n.u.ReleaseDC.assert_called_once_with(1,10)
    def test_cleanup_failure_blocks_return(self):
        n=self.backend();n.g.DeleteObject.return_value=0;n.g.DeleteObject.__name__='DeleteObject'
        with self.assertRaises(CaptureError) as raised:n.pixels(1,16,24)
        self.assertEqual(raised.exception.status,'GDI_CLEANUP_FAILED')
        n.u.ReleaseDC.assert_called_once_with(1,10)
    def test_native_process_query_exception_does_not_default_name(self):
        n=self.backend();n.u.IsWindow.return_value=True;n.u.IsWindowVisible.return_value=True
        n.u.IsIconic.return_value=False
        def pid(hwnd,p):p._obj.value=123;return 1
        n.u.GetWindowThreadProcessId.side_effect=pid;n.psutil=MagicMock()
        n.psutil.Process.side_effect=PermissionError('denied')
        with self.assertRaises(CaptureError) as raised:n.state(1)
        self.assertEqual(raised.exception.status,'PROCESS_QUERY_FAILED')

if __name__=='__main__':unittest.main()
