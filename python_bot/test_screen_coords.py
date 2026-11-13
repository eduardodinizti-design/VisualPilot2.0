"""Testes do transform frame->tela (passo 2)."""
import unittest

from screen_coords import dpi_scale, frame_to_screen, rect_frame_to_screen

# Geometria REAL medida na máquina do Eduardo (HWND 1508766):
WIN = (-1280, 0, 3840, 1440)     # rect lógico (discover_pppoker)
FRAME = (5760, 2160)             # frame físico (image_shape -> W,H)


class TransformTest(unittest.TestCase):
    def test_dpi_scale_is_1_5(self):
        self.assertEqual(dpi_scale(WIN, FRAME), (1.5, 1.5))

    def test_raise_button_maps_to_cursor_coord(self):
        # Botão Raise do run ao vivo (frame 3308,1360) -> (925, 907) na tela.
        sx, sy = frame_to_screen((3308, 1360), window_rect=WIN, frame_size=FRAME)
        self.assertAlmostEqual(sx, 925.333, places=2)   # -1280 + 3308*2/3
        self.assertAlmostEqual(sy, 906.667, places=2)   # 1360*2/3

    def test_corners(self):
        # Canto (0,0) do frame -> origem lógica da janela.
        self.assertEqual(frame_to_screen((0, 0), window_rect=WIN, frame_size=FRAME),
                         (-1280.0, 0.0))
        # Canto oposto do frame -> canto oposto da janela.
        self.assertEqual(frame_to_screen((5760, 2160), window_rect=WIN, frame_size=FRAME),
                         (-1280 + 3840.0, 1440.0))

    def test_negative_origin_ok(self):
        sx, sy = frame_to_screen((2880, 1080), window_rect=(-1920, 0, 1920, 1080),
                                 frame_size=(2880, 1620))
        self.assertEqual((sx, sy), (0.0, 720.0))

    def test_rect_transform_scales_size(self):
        r = rect_frame_to_screen((3270, 1338, 76, 44), window_rect=WIN, frame_size=FRAME)
        self.assertAlmostEqual(r[2], 76 / 1.5, places=3)   # largura escalada por 1/1.5
        self.assertAlmostEqual(r[3], 44 / 1.5, places=3)


if __name__ == '__main__':
    unittest.main()
