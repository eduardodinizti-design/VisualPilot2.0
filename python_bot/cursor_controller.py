"""Coordenador de intenção do cursor — máquina de estados (Fase 3B).

Implementa o fluxo §8 da spec `ORIENTAÇÃO PARA MOVIMENTO NATURAL`:

  AWAITING_INTENT → VALIDATING → MOVING → REVALIDATING → CLICKING → VERIFYING
                  → DONE | CANCELLED | UNKNOWN_RESULT

Garantias centrais (segurança funcional §12):
- **Gate**: sem `BotControl` RUNNING, nada é enviado (mesmo gate do F2).
- **Revalidação NA CHEGADA** antes do mouse-down: recaptura e confere janela/
  geometria/alvo/estado/atualidade. Corrige o anti-padrão do executor manual
  (validar imagem → mover demorado → clicar sem revalidar). Alvo invalidado NÃO
  recebe clique.
- **Cancelável**: durante o movimento, intervenção do usuário, mudança de foco,
  invalidação do alvo ou prazo vencido → CANCELA (não clica, não puxa o cursor
  de volta — não disputa com o mouse do usuário).
- **Clique ÚNICO**: uma intenção gera no máximo um clique; `id` consumido não
  reexecuta. Soltura garantida pelo adaptador.
- **Exclusão mútua**: o cursor é compartilhado → um lock serializa as intenções
  de mesas diferentes; a fila NÃO guarda intenção vencida (revalida o prazo após
  adquirir o lock).
- **Resultado desconhecido ≠ sucesso**: sem verificação do efeito, termina em
  UNKNOWN_RESULT e NÃO repete o clique automaticamente.

NUNCA aponte para o PPPoker nesta fase: use um app de teste.
"""
import threading
import time
from dataclasses import dataclass, field

from cursor_trajectory import TrajectoryGenerator, safe_point, within_virtual_desktop

STATES = ('AWAITING_INTENT', 'VALIDATING', 'MOVING', 'REVALIDATING',
          'CLICKING', 'VERIFYING', 'DONE', 'CANCELLED', 'UNKNOWN_RESULT')

# Cursor compartilhado do Windows: um único lock de processo serializa as
# trajetórias. NÃO executar trajetórias concorrentes para mesas diferentes.
_CURSOR_LOCK = threading.Lock()


@dataclass
class Intent:
    """Uma intenção de clique identificada e com prazo. `target_rect` já em
    coordenadas FÍSICAS de tela (o chamador transforma a geometria local)."""
    id: str
    action: str
    source_key: str                 # identidade mesa/janela (pid+hwnd)
    target_rect: tuple              # (x, y, w, h) físico
    deadline: float                 # relógio monotônico; prazo de validade
    hand: object = None             # identidade da mão quando exigida
    snapshot_id: object = None      # snapshot que originou a intenção
    expected: dict = field(default_factory=dict)   # o que deve continuar válido


def center_of(rect, *, margin_frac=0.25):
    cx, cy, _ = safe_point(rect, margin_frac=margin_frac)
    return (cx, cy)


def make_intervention_check(input_adapter, *, tol_px=6.0):
    """cancel_check padrão: se o cursor REAL divergir do esperado além de tol_px,
    é intervenção do usuário → cancela (não disputa o mouse)."""
    def check(intent, now, expected_pos):
        try:
            ax, ay = input_adapter.cursor_pos()
        except Exception:                      # noqa: BLE001
            return None
        if abs(ax - expected_pos[0]) > tol_px or abs(ay - expected_pos[1]) > tol_px:
            return 'USER_INTERVENTION'
        return None
    return check


class CursorController:
    def __init__(self, *, trajectory=None, input_adapter, validator,
                 verifier=None, bot_control=None, cancel_check=None,
                 clock=time.monotonic, sleep=time.sleep, step_s=0.012,
                 lock=None, lock_timeout=2.0, arrival_tol=8.0):
        self._traj = trajectory or TrajectoryGenerator(clock=clock)
        self._input = input_adapter
        self._validate_fn = validator          # recaptura+confere (inicial e na chegada)
        self._verifier = verifier              # observa o efeito; None => desconhecido
        self._bot = bot_control
        self._cancel_check = cancel_check
        self._clock = clock
        self._sleep = sleep
        self._step_s = float(step_s)
        self._lock = lock or _CURSOR_LOCK
        self._lock_timeout = float(lock_timeout)
        self._arrival_tol = float(arrival_tol)
        self._consumed = set()

    def _invalid_target(self, target):
        """Motivo se o alvo é inválido (geometria ruim ou fora da tela), senão
        None. Rejeita antes de mover (§2)."""
        try:
            x, y, w, h = target
        except Exception:                      # noqa: BLE001
            return 'TARGET_GEOMETRY_INVALID'
        if not (w > 0 and h > 0):
            return 'TARGET_GEOMETRY_INVALID'
        try:
            bounds = self._input.virtual_bounds()
        except Exception:                      # noqa: BLE001
            bounds = None                      # sem bounds, confere só a geometria
        if bounds is not None:
            cx, cy = center_of(target)
            if not within_virtual_desktop((cx, cy), bounds):
                return 'TARGET_OFF_SCREEN'
        return None

    # ---- gates ----------------------------------------------------------
    def _armed(self):
        if self._bot is None:
            return True
        return bool(getattr(self._bot, 'execution_allowed', lambda: False)())

    def _expired(self, intent):
        return self._clock() >= intent.deadline

    # ---- API ------------------------------------------------------------
    def execute(self, intent):
        """Processa UMA intenção pela máquina de estados. Retorna
        {state, reasons, log, intent_id}. Nunca mais de um clique."""
        log = []

        def term(state, reasons=()):
            log.append(dict(state=state, reasons=list(reasons)))
            return dict(state=state, reasons=list(reasons), log=log,
                        intent_id=intent.id)

        if intent.id in self._consumed:
            return term('CANCELLED', ['INTENT_ALREADY_CONSUMED'])
        if not self._armed():
            return term('CANCELLED', ['BOT_NOT_RUNNING'])
        if self._expired(intent):
            return term('CANCELLED', ['INTENT_EXPIRED'])

        if not self._lock.acquire(timeout=self._lock_timeout):
            return term('CANCELLED', ['CURSOR_BUSY'])          # não enfileira vencida
        try:
            # Fila não guarda intenção vencida: revalida prazo/arme após o lock.
            if self._expired(intent):
                return term('CANCELLED', ['INTENT_EXPIRED'])
            if not self._armed():
                return term('CANCELLED', ['BOT_NOT_RUNNING'])
            # Anti-duplo AUTORITATIVO sob o lock: o check pré-lock é só fast-path;
            # duas threads poderiam passar por ele antes de qualquer consumo.
            if intent.id in self._consumed:
                return term('CANCELLED', ['INTENT_ALREADY_CONSUMED'])

            # VALIDATING (inicial)
            v = self._validate_fn(intent, self._clock())
            if not v.get('ok'):
                return term('CANCELLED', ['INITIAL_VALIDATION_FAILED', *v.get('reasons', [])])
            target = v.get('target_rect') or intent.target_rect
            bad = self._invalid_target(target)       # §2: rejeita alvo inválido/fora da tela
            if bad:
                return term('CANCELLED', [bad])

            # MOVING (cancelável)
            cancel = self._move(intent, target)
            if cancel is not None:
                return term('CANCELLED', cancel)

            # REVALIDATING (na chegada, ANTES do mouse-down)
            reasons = []
            r = self._validate_fn(intent, self._clock())
            if not r.get('ok'):
                reasons = ['ARRIVAL_REVALIDATION_FAILED', *r.get('reasons', [])]
            elif r.get('target_rect') and r['target_rect'] != target:
                reasons = ['TARGET_MOVED_ON_ARRIVAL']
            elif r.get('identity') is not None and r['identity'] != intent.source_key:
                # Mesa/mão/janela trocou — mesmo se o botão estiver na mesma coord.
                reasons = ['IDENTITY_CHANGED_ON_ARRIVAL']
            if self._expired(intent):
                reasons.append('INTENT_EXPIRED')
            if not self._armed():
                reasons.append('BOT_NOT_RUNNING')
            if reasons:
                return term('CANCELLED', reasons)

            # Confere a posição REAL do cursor antes do mouse-down (não clicar se
            # não chegou de fato ao alvo). §2
            cx, cy = center_of(target)
            try:
                ax, ay = self._input.cursor_pos()
            except Exception:                      # noqa: BLE001
                return term('CANCELLED', ['CURSOR_POS_UNAVAILABLE'])
            if abs(ax - cx) > self._arrival_tol or abs(ay - cy) > self._arrival_tol:
                return term('CANCELLED', ['CURSOR_NOT_AT_TARGET'])

            # CLICKING (único) — consome a intenção ANTES de clicar (anti-duplo)
            self._consumed.add(intent.id)
            click = self._input.click_once(cx, cy)
            log.append(dict(state='CLICKING', click=click))
            # Confere SEPARADAMENTE movimento, mouse-down e mouse-up (§1): se o
            # Windows rejeitar um evento, não declarar sucesso.
            moved = click.get('moved') or {}
            if moved.get('accepted', 1) < 1:
                return term('UNKNOWN_RESULT', ['MOVE_NOT_ACCEPTED'])
            if click.get('down_accepted', 1) < 1:
                return term('UNKNOWN_RESULT', ['DOWN_NOT_ACCEPTED'])
            if not click.get('released'):
                return term('UNKNOWN_RESULT', ['RELEASE_UNCONFIRMED'])

            # VERIFYING
            if self._verifier is None:
                return term('UNKNOWN_RESULT', ['NO_VERIFIER'])
            ver = self._verifier(intent, self._clock()) or {}
            if ver.get('confirmed'):
                return term('DONE')
            return term('UNKNOWN_RESULT', ['EFFECT_UNCONFIRMED'])
        finally:
            self._lock.release()

    # ---- movimento ------------------------------------------------------
    def _move(self, intent, target):
        """Executa a trajetória min-jerk cancelável. None se chegou OK; lista de
        motivos se cancelou (sem clique)."""
        try:
            start = self._input.cursor_pos()
        except Exception:                      # noqa: BLE001
            # §1: falha ao ler a posição do cursor CANCELA; não assumir alternativa.
            return ['CURSOR_POS_UNAVAILABLE']
        end = center_of(target)
        plan = self._traj.plan(start, end)
        commanded = start                       # último ponto que o BOT comandou
        while not plan.done():
            now = self._clock()
            if self._expired(intent):
                return ['INTENT_EXPIRED']
            if not self._armed():
                return ['BOT_NOT_RUNNING']
            # Detecção de intervenção: o cursor REAL deve estar perto de onde o
            # bot o deixou (commanded), NÃO do próximo ponto — senão o próprio
            # passo do movimento dispararia falso cancelamento.
            if self._cancel_check is not None:
                why = self._cancel_check(intent, now, commanded)
                if why:
                    return [why]               # intervenção/foco/alvo invalidado
            pos = plan.position(now)
            self._input.move_to(pos[0], pos[1])
            commanded = pos
            self._sleep(self._step_s)
        self._input.move_to(end[0], end[1])     # ponto final exato
        return None
