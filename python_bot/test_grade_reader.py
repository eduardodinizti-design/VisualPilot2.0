"""Lobby grade reader: field parsing and modality classification.

Pure parsers over synthetic OCR text (lab-safe). The badge detection and the
field OCR are validated live on a real Karekas lobby gabarito; these pin the
parsing and naming so a real read is interpreted consistently."""
import unittest

import grade_reader as gr


class ModalityTests(unittest.TestCase):
    def test_keywords_and_bounty(self):
        self.assertEqual(gr.classify_modality('KOMBAT MISTERY'), 'mko')
        self.assertEqual(gr.classify_modality('BOX MYSTERY MKO'), 'mko')
        self.assertEqual(gr.classify_modality('HYPER PKO 10K'), 'pko')
        self.assertEqual(gr.classify_modality('BOUNTY HUNTER'), 'pko')
        self.assertEqual(gr.classify_modality('MINI FREEZE'), 'freezeout')
        self.assertEqual(gr.classify_modality('SUPER DEEP'), 'deep')
        self.assertEqual(gr.classify_modality('SUPER ADD-ON'), 'addon')
        self.assertEqual(gr.classify_modality('CRAZY REBUY'), 'rebuy')

    def test_unknown_is_flagged_not_guessed(self):
        self.assertEqual(gr.classify_modality('MICRO LUDIKA'), 'unknown')
        self.assertEqual(gr.classify_modality(''), 'unknown')

    def test_mystery_beats_rebuy_keyword_order(self):
        # A mystery rebuy is still treated as the bounty format (mko) first.
        self.assertEqual(gr.classify_modality('MYSTERY REBUY'), 'mko')


class FieldParseTests(unittest.TestCase):
    def test_buyin(self):
        self.assertEqual(gr.parse_buyin('Buy-in: 10'), 10)
        self.assertEqual(gr.parse_buyin('Buyin:50'), 50)
        self.assertIsNone(gr.parse_buyin('Buy-in:'))

    def test_buyin_keeps_cents_and_sums_composite(self):
        # Cents must not be dropped (a cap check needs the real cost) and a
        # composite buy-in (entry + fee + bounty) is summed, not truncated.
        self.assertEqual(gr.parse_buyin('Buy-in: 50,50'), 50.5)
        self.assertEqual(gr.parse_buyin('Buy-in: 0,50'), 0.5)
        self.assertEqual(gr.parse_buyin('28.34 + 14.16 + 7.50'), 50.0)

    def test_players(self):
        self.assertEqual(gr.parse_players('96/263'), (96, 263))
        self.assertEqual(gr.parse_players('& 58/75 @12min'), (58, 75))
        self.assertEqual(gr.parse_players('14'), (None, None))

    def test_players_icon_noise_recovered_or_dropped(self):
        # Icon glues a '2' onto '71/105'; strip it back to 71.
        self.assertEqual(gr.parse_players('271/105'), (71, 105))
        # Impossible and unrecoverable -> drop registered, keep max.
        self.assertEqual(gr.parse_players('999/80'), (None, 80))

    def test_level_minutes(self):
        self.assertEqual(gr.parse_level_minutes('96/263 10 min'), 10)
        self.assertIsNone(gr.parse_level_minutes('no time here'))

    def test_status_reg_open(self):
        s = gr.parse_status('Registro encerra em 56 min')
        self.assertEqual((s['state'], s['closes_in_min']), ('reg_open', 56))

    def test_status_not_started(self):
        s = gr.parse_status('Horario de inicio: 11/08 23:00')
        self.assertEqual(s['state'], 'not_started')
        self.assertEqual(s['starts_at'], '11/08 23:00')

    def test_status_unknown(self):
        s = gr.parse_status('{ something unreadable')
        self.assertEqual(s['state'], 'unknown')

    def test_status_strict_no_false_positive_on_stack_or_level(self):
        # O cartão Karekas atual NÃO imprime status; a banda cai na linha de STACK
        # (números) ou pega o 'N min' do NÍVEL. Nada disso pode virar reg_open —
        # tem de ficar unknown (fail-safe; achado ao vivo 09/11).
        for raw in ('{� =25,000', '1 ==2,592+2,592', '{@ =2500',
                    '@ 54/78 12 min', 'fe&19 min'):
            self.assertEqual(gr.parse_status(raw)['state'], 'unknown', raw)


if __name__ == '__main__':
    unittest.main()
