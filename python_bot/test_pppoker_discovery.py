"""PPPoker window discovery: PPPoker-only, visible, min size.

Unit test with injected windows (no live capture). Discovery enumerates PPPoker
windows; separating the blue table region from the lobby is the pipeline's job
downstream, not this layer's."""
import unittest

from table_discovery.windows import WindowInfo
from table_discovery import pppoker


def win(hwnd, process='PPPoker.exe', title='PPPoker', w=800, h=600, x=0, y=0, minimized=False):
    return WindowInfo(hwnd=hwnd, title=title, class_name='UnityWndClass', pid=1000 + hwnd,
                      process=process, rect=(x, y, x + w, y + h), minimized=minimized, maximized=False)


class DiscoveryTests(unittest.TestCase):
    def test_returns_visible_pppoker_windows(self):
        found = pppoker.discover_pppoker([win(1), win(2)])['windows']
        self.assertEqual([w['hwnd'] for w in found], [1, 2])

    def test_non_pppoker_processes_ignored(self):
        found = pppoker.discover_pppoker([win(1), win(5, process='chrome.exe'),
                                          win(6, process='XPoker.exe')])['windows']
        self.assertEqual([w['hwnd'] for w in found], [1])

    def test_minimized_and_tiny_windows_excluded(self):
        windows = [win(1), win(2, minimized=True), win(3, w=120, h=120)]
        found = pppoker.discover_pppoker(windows)['windows']
        self.assertEqual([w['hwnd'] for w in found], [1])

    def test_hwnds_helper_caps_and_lists(self):
        windows = [win(h) for h in range(1, 9)]
        self.assertEqual(pppoker.pppoker_table_hwnds(windows, max_tables=6), [1, 2, 3, 4, 5, 6])

    def test_rect_and_identity_fields_present(self):
        w = pppoker.discover_pppoker([win(3, w=1024, h=768, x=-1920, y=0)])['windows'][0]
        self.assertEqual((w['x'], w['y'], w['w'], w['h']), (-1920, 0, 1024, 768))
        self.assertEqual(w['pid'], 1003)  # negative-origin multi-monitor case is legitimate


if __name__ == '__main__':
    unittest.main()
