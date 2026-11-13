"""Native GDI smoke test on our own Tk window, NOT PPPoker/Unity validation."""
import platform
import unittest
from unittest.mock import patch

@unittest.skipUnless(platform.system()=='Windows','Native Windows required')
class NativeGDISmoke(unittest.TestCase):
    def test_capture_client_pixels_and_resize(self):
        import ctypes
        from ctypes import wintypes as W
        import tkinter as tk
        import psutil
        import os
        import ntpath
        import window_capture_engine as module
        root=tk.Tk()
        root.geometry('320x240+100+100')
        root.configure(bg='#00ff00')
        root.update()
        user=ctypes.WinDLL('user32',use_last_error=True)
        user.GetAncestor.argtypes=[W.HWND,W.UINT];user.GetAncestor.restype=W.HWND
        hwnd=int(user.GetAncestor(root.winfo_id(),2))
        # Explicit test-only allowlist: production does NOT authorize Python windows.
        name=ntpath.basename(psutil.Process(os.getpid()).exe()).casefold()
        try:
            with patch.object(module,'ALLOWED_EXECUTABLES',frozenset({name})):
                engine=module.WindowCaptureEngine()
                frame,meta=engine.capture_frame(hwnd)
                self.assertEqual(meta['status'],'SUCCESS',meta)
                self.assertEqual(frame.shape[:2],(meta['client_rect'][3],meta['client_rect'][2]))
                self.assertTrue((frame[frame.shape[0]//2,frame.shape[1]//2]==[0,255,0]).all())
                original=frame.shape
                root.geometry('400x280+200+150');root.configure(bg='#0000ff');root.update()
                new,meta=engine.capture_frame(hwnd)
                self.assertEqual(meta['status'],'SUCCESS',meta)
                self.assertNotEqual(original,new.shape)
                self.assertTrue((new[new.shape[0]//2,new.shape[1]//2]==[255,0,0]).all())
                user.GetGuiResources.argtypes=[W.HANDLE,W.DWORD];user.GetGuiResources.restype=W.DWORD
                kernel=ctypes.WinDLL('kernel32');kernel.GetCurrentProcess.restype=W.HANDLE
                handle=kernel.GetCurrentProcess();before=user.GetGuiResources(handle,0)
                for _ in range(40):
                    _,meta=engine.capture_frame(hwnd)
                    self.assertEqual(meta['status'],'SUCCESS',meta)
                self.assertLessEqual(user.GetGuiResources(handle,0),before+1)
        finally:root.destroy()

if __name__=='__main__':unittest.main()
