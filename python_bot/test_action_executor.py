"""Testes do executor de ação (passo 3) — dry-run, gate, uma-por-mão, travas."""
import unittest

from action_executor import ActionExecutor
from action_coordinator import DryRunInput

WIN = (-1280, 0, 3840, 1440)
FRAME = (5760, 2160)
ORIGIN = (1920, 74)


def _buttons(actions=('FOLD', 'CALL', 'RAISE'), amounts=None):
    amounts = amounts or {}
    return dict(status='EXPERIMENTAL_BUTTON_ROW', hero_turn_confirmed=False,
                actions_allowed=False,
                buttons=[dict(box=[100 + i * 120, 1200, 100, 44], action=a,
                              label=a.title(), amount=amounts.get(a), unit='bb' if amounts.get(a) else None)
                         for i, a in enumerate(actions)])


def _result(rec, **advice):
    return dict(advice=dict(status='ADVICE', recommended=rec, **advice))


def _calloff(rec, eq, req):
    return _result(rec, spot='call_off_vs_3bet_shove', equity=eq, required_equity_icm=req)


class _Control:
    def __init__(self, running=True):
        self.running = running

    def execution_allowed(self):
        return self.running


def _ok(intent, now):
    return dict(ok=True)


class PlanGateTest(unittest.TestCase):
    def test_refuses_raise_multistep(self):
        ex = ActionExecutor(window_rect=WIN)
        p = ex.plan(_result('raise'), _buttons(), origin=ORIGIN, frame_size=FRAME)
        self.assertFalse(p['ok'])
        self.assertIn('ACAO_MULTI_ETAPA_NAO_ARMADA:RAISE', p['reason'])

    def test_allows_fold_with_screen_rect(self):
        ex = ActionExecutor(window_rect=WIN)
        p = ex.plan(_result('fold'), _buttons(), origin=ORIGIN, frame_size=FRAME)
        self.assertTrue(p['ok'])
        self.assertEqual(p['plan']['action'], 'FOLD')
        self.assertIn('screen_rect', p['plan'])          # coord de tela pronta


class ExecuteTest(unittest.TestCase):
    def _exec(self, ex, inp, rec='fold', hand='h1'):
        return ex.execute(_result(rec), _buttons(), origin=ORIGIN, frame_size=FRAME,
                          input_adapter=inp, validator=_ok, hand_id=hand)

    def test_dry_run_clicks_and_dedups_same_decision(self):
        ex = ActionExecutor(window_rect=WIN, armed=False)
        inp = DryRunInput()
        out = self._exec(ex, inp)
        self.assertTrue(out['acted'])
        self.assertTrue(out['dry_run'])
        self.assertEqual(len(inp.clicks), 1)             # registrou (dry-run)
        # mesma DECISAO (mesma mao/acao/valor) -> nao reaperta (mesmo em dry-run)
        out2 = self._exec(ex, DryRunInput())
        self.assertFalse(out2['acted'])
        self.assertIn('JA_AGIU_NESTA_DECISAO', out2['reason'])

    def test_armed_but_paused_does_not_click(self):
        ex = ActionExecutor(window_rect=WIN, armed=True, bot_control=_Control(False))
        inp = DryRunInput()
        out = self._exec(ex, inp)
        self.assertFalse(out['acted'])
        self.assertEqual(out['reason'], 'BOT_PAUSADO')
        self.assertEqual(len(inp.clicks), 0)             # nada enviado

    def test_armed_running_clicks(self):
        ex = ActionExecutor(window_rect=WIN, armed=True, bot_control=_Control(True))
        inp = DryRunInput()
        out = self._exec(ex, inp)
        self.assertTrue(out['acted'])
        self.assertFalse(out['dry_run'])
        self.assertEqual(len(inp.clicks), 1)

    def test_refuses_raise_no_click(self):
        ex = ActionExecutor(window_rect=WIN, armed=True, bot_control=_Control(True))
        inp = DryRunInput()
        out = self._exec(ex, inp, rec='raise')
        self.assertFalse(out['acted'])
        self.assertIn('ACAO_MULTI_ETAPA', out['reason'])
        self.assertEqual(len(inp.clicks), 0)

    def test_abstains_when_advice_abstain(self):
        ex = ActionExecutor(window_rect=WIN)
        out = ex.execute(dict(advice=dict(status='ABSTAIN', reason='X')), _buttons(),
                         origin=ORIGIN, frame_size=FRAME, input_adapter=DryRunInput(),
                         validator=_ok, hand_id='h')
        self.assertFalse(out['acted'])


class IdentityAndEligibilityTest(unittest.TestCase):
    """#5/#6-exec do feedback: identidade desconhecida bloqueia o armado; status
    ADVICE sozinho não autoriza auto-CALL de call-off numa borda ruidosa."""

    def _run(self, result, inp, *, armed, hand, table='A'):
        ex = ActionExecutor(window_rect=WIN, armed=armed, bot_control=_Control(True))
        return ex.execute(result, _buttons(), origin=ORIGIN, frame_size=FRAME,
                          input_adapter=inp, validator=_ok, hand_id=hand, table_key=table)

    def test_unknown_identity_blocks_armed(self):
        inp = DryRunInput()
        out = self._run(_result('fold'), inp, armed=True, hand=None)
        self.assertFalse(out['acted'])
        self.assertEqual(out['reason'], 'IDENTIDADE_DESCONHECIDA_BLOQUEIA')
        self.assertEqual(len(inp.clicks), 0)

    def test_unknown_identity_ok_in_dry_run(self):
        inp = DryRunInput()
        out = self._run(_result('fold'), inp, armed=False, hand=None)
        self.assertTrue(out['acted'])                    # dry-run só estuda

    def test_calloff_near_boundary_not_eligible_armed(self):
        inp = DryRunInput()
        out = self._run(_calloff('call', eq=0.42, req=0.40), inp, armed=True, hand='h1')
        self.assertFalse(out['acted'])
        self.assertIn('NAO_ELEGIVEL:CALLOFF_NA_FRONTEIRA', out['reason'])
        self.assertEqual(len(inp.clicks), 0)

    def test_calloff_with_margin_is_eligible_armed(self):
        inp = DryRunInput()
        out = self._run(_calloff('call', eq=0.52, req=0.40), inp, armed=True, hand='h1')
        self.assertTrue(out['acted'])
        self.assertEqual(len(inp.clicks), 1)

    def test_fold_always_eligible_armed(self):
        inp = DryRunInput()
        out = self._run(_result('fold'), inp, armed=True, hand='h1')
        self.assertTrue(out['acted'])

    def test_call_validated_is_eligible_armed(self):
        inp = DryRunInput()
        out = self._run(_result('call', validated=True), inp, armed=True, hand='h1')
        self.assertTrue(out['acted'])
        self.assertEqual(len(inp.clicks), 1)

    def test_call_unvalidated_not_eligible_armed(self):
        # updates.txt: Call com validated=False NAO pode auto-clicar.
        inp = DryRunInput()
        out = self._run(_result('call'), inp, armed=True, hand='h1')
        self.assertFalse(out['acted'])
        self.assertIn('NAO_ELEGIVEL:NAO_VALIDADO', out['reason'])
        self.assertEqual(len(inp.clicks), 0)

    def test_call_unvalidated_ok_in_dry_run(self):
        inp = DryRunInput()
        out = self._run(_result('call'), inp, armed=False, hand='h1')
        self.assertTrue(out['acted'])                    # dry-run só estuda, não gated

    def test_legit_second_decision_same_hand_allowed(self):
        ex = ActionExecutor(window_rect=WIN, armed=False)
        a = ex.execute(_result('fold'), _buttons(), origin=ORIGIN, frame_size=FRAME,
                       input_adapter=DryRunInput(), validator=_ok, hand_id='h1', table_key='A')
        b = ex.execute(_result('call'), _buttons(), origin=ORIGIN, frame_size=FRAME,
                       input_adapter=DryRunInput(), validator=_ok, hand_id='h1', table_key='A')
        self.assertTrue(a['acted'])
        self.assertTrue(b['acted'])                      # ação diferente = decisão nova

    def test_call_value_change_is_new_decision(self):
        ex = ActionExecutor(window_rect=WIN, armed=False)
        b50 = _buttons(amounts={'CALL': 50})
        b100 = _buttons(amounts={'CALL': 100})
        a = ex.execute(_result('call'), b50, origin=ORIGIN, frame_size=FRAME,
                       input_adapter=DryRunInput(), validator=_ok, hand_id='h1', table_key='A')
        b = ex.execute(_result('call'), b100, origin=ORIGIN, frame_size=FRAME,
                       input_adapter=DryRunInput(), validator=_ok, hand_id='h1', table_key='A')
        self.assertTrue(a['acted'])
        self.assertTrue(b['acted'])                      # valor diferente = decisão nova


if __name__ == '__main__':
    unittest.main()
