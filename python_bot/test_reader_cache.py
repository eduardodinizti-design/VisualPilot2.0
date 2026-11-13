"""Cache de HUD/bounty: relê só a cada N frames e em mudança de ocupação, com merge
que mantém o valor bom (contra latência e animação). Leitores fake (sem OCR)."""
import unittest

from reader_cache import ReaderCache


class HudCacheTests(unittest.TestCase):
    def test_reads_once_then_caches(self):
        calls = []

        def fn(crop, seats):
            calls.append(list(seats))
            return {s: {'stats': {'vpip': 20}, 'confidence': 'high'} for s in seats}

        c = ReaderCache(hud_every=100, hud_fn=fn)
        occ = ['bot_left', 'left_up']
        for _ in range(5):
            r = c.huds(None, 't', occ)
        self.assertEqual(len(calls), 1)                  # leu 1x, reusou o cache
        self.assertEqual(set(r), set(occ))

    def test_refreshes_every_n(self):
        calls = []

        def fn(crop, seats):
            calls.append(1)
            return {s: {'x': 1} for s in seats}

        c = ReaderCache(hud_every=3, hud_fn=fn)
        for _ in range(7):
            c.huds(None, 't', ['a'])
        self.assertEqual(len(calls), 3)                  # n=0,3,6 -> 3 leituras em 7 frames

    def test_occupancy_change_invalidates_seat(self):
        calls = []

        def fn(crop, seats):
            calls.append(list(seats))
            return {s: {'v': 1} for s in seats}

        c = ReaderCache(hud_every=100, hud_fn=fn)
        c.huds(None, 't', ['a', 'b'])
        c.huds(None, 't', ['a', 'b'])                    # cache
        c.huds(None, 't', ['a', 'c'])                    # b saiu, c entrou -> relê (c faltando)
        self.assertEqual(len(calls), 2)
        c.huds(None, 't', ['a', 'c'])                    # tudo cacheado -> sem releitura
        self.assertEqual(len(calls), 2)

    def test_hero_skipped(self):
        c = ReaderCache(hud_fn=lambda crop, seats: {s: {} for s in seats})
        r = c.huds(None, 't', ['hero', 'a'])
        self.assertNotIn('hero', r)


class BountyCacheTests(unittest.TestCase):
    def test_keeps_good_value_on_abstention(self):
        seq = [{'a': 135}, {'a': None}]

        def fn(crop, seats):
            return seq.pop(0) if seq else {}

        c = ReaderCache(bounty_every=1, bounty_fn=fn)      # relê todo frame
        self.assertEqual(c.bounties(None, 't', ['a']), {'a': 135})
        self.assertEqual(c.bounties(None, 't', ['a']), {'a': 135})  # None não zera o cache


if __name__ == '__main__':
    unittest.main()
