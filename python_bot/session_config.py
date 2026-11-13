"""Session config + eligibility selector for the grind (decision only, no clicks).

This is the glue between `grade_reader` (reads the lobby) and
`POLITICA_SELECAO_E_BANKROLL.md` (the rules). It holds the session config (the
pre-established grade and the limits) and decides, for one grade card, whether it
is ELIGIBLE or BLOCKED and why. It never registers and never authorises spend:
`execution_allowed` is always False here, and a missing financial field blocks
the card rather than being treated as zero (per the registration spec).
"""
import math
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SessionConfig:
    """The operator's pre-grind choices. Financial fields are None until the user
    sets them; None means BLOCKED, never zero or an invented value."""
    enabled: bool = False
    clubs_authorized: tuple = ('Karekas', 'Veneza')
    allowed_modalities: tuple = ('freezeout', 'mko', 'pko')   # rebuy only if also pko
    currency: Optional[str] = None
    max_entry_buyin: Optional[float] = None       # teto por inscrição (moeda do clube)
    daily_budget: Optional[float] = None          # orçamento diário de inscrição
    bankroll_bi: Optional[float] = None           # banca atual em buy-ins (regra §2.1)
    min_bi_by_format: dict = field(                # mínimo de BI por formato (variância)
        default_factory=lambda: {'freezeout': 75, 'deep': 75, 'mko': 120, 'pko': 150})
    turbo_multiplier: float = 1.5                  # turbo/hyper exige +50% de BI
    max_tournaments_day: Optional[int] = None
    max_simultaneous: int = 4
    registration_cutoff: Optional[str] = None     # 'HH:MM' local; não registrar depois
    grade_preset: tuple = ()                      # nomes autorizados; vazio = sem pré-grade
    rebuy_pko_only: bool = True
    rebuy_trigger_bb: int = 40

    @classmethod
    def from_dict(cls, d):
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: (tuple(v) if isinstance(v, list) else v)
                      for k, v in (d or {}).items() if k in known})

    def financial_ready(self):
        return (self.currency is not None and self.max_entry_buyin is not None
                and self.daily_budget is not None and self.bankroll_bi is not None)

    def format_min_bi(self, modality, name=''):
        """Minimum bankroll (in buy-ins) to play this format, turbo-scaled by the
        card name, or None when the format has no rule here."""
        base = self.min_bi_by_format.get(modality)
        if base is None:
            return None
        if re.search(r'HYPER|TURBO', name or '', re.I):
            base = base * self.turbo_multiplier
        return base


@dataclass
class SessionState:
    """What the session has already committed today. A commitment is a seat that
    counts against the limits: registered, active, or a pending reserve."""
    committed: list = field(default_factory=list)   # PENDING reserves only: [{'name','buyin'}]
    confirmed_spend: float = 0.0                     # custos já CONFIRMADOS hoje (liquidados)

    def committed_cost(self):
        """Total daily commitment = confirmed spend + pending reserves. A seat is
        in exactly one of the two (confirm() moves it), so nothing is counted twice."""
        return self.confirmed_spend + sum(c.get('buyin') or 0 for c in self.committed)

    def is_committed(self, name):
        return any(c.get('name') == name for c in self.committed)

    def confirm(self, name):
        """Move a pending reserve to confirmed spend (registration succeeded), so a
        registered seat is never counted both as a reserve and as confirmed spend."""
        for c in list(self.committed):
            if c.get('name') == name:
                self.confirmed_spend += c.get('buyin') or 0
                self.committed.remove(c)
                return True
        return False


def _parse_hhmm(s):
    """(hour, minute) for a valid 'HH:MM' string, else None (unknown time)."""
    try:
        h, m = int(s[:2]), int(s[3:5])
    except (TypeError, ValueError, IndexError):
        return None
    return (h, m) if 0 <= h <= 23 and 0 <= m <= 59 else None


def evaluate_card(card, config, state=None, *, club=None, now_hhmm=None):
    """Decide eligibility for one grade card (from grade_reader.read_grade).

    Returns {decision: 'ELIGIBLE'|'BLOCKED', reasons: [...], name, buyin, modality,
    execution_allowed: False}. ELIGIBLE means only 'passes the policy filter';
    the actual registration still needs the supervised flow and confirmation.
    """
    state = state or SessionState()
    reasons = []
    name = card.get('name')
    buyin = card.get('buyin')
    modality = card.get('modality')
    status = card.get('status') or {}

    if not config.financial_ready():
        reasons.append('MISSING_FINANCIAL_CONFIG')           # moeda/teto/orçamento em branco = BLOQUEADO

    if config.clubs_authorized and (club is None or club not in config.clubs_authorized):
        reasons.append('CLUB_NOT_AUTHORIZED')   # unknown club is not authorized either
    if config.grade_preset and name not in config.grade_preset:
        reasons.append('NOT_IN_PRESET_GRADE')

    if modality == 'unknown':
        reasons.append('MODALITY_UNKNOWN_NEEDS_CONFIRMATION')
    elif modality in ('rebuy', 'addon'):
        # Rebuy/add-on formats are only allowed when they are also PKO (user rule);
        # a plain rebuy/add-on is not. A PKO-with-rebuy classifies as 'pko' upstream.
        reasons.append('REBUY_ONLY_IN_PKO' if config.rebuy_pko_only else 'MODALITY_NOT_ALLOWED')
    elif modality not in config.allowed_modalities:
        reasons.append('MODALITY_NOT_ALLOWED')
    else:
        # Bankroll rule by format (policy §2.1): e.g. PKO needs >=150 buy-ins,
        # turbo/hyper +50%. Only checked for an allowed format with a known bankroll.
        min_bi = config.format_min_bi(modality, name)
        if min_bi is not None and config.bankroll_bi is not None and config.bankroll_bi < min_bi:
            reasons.append('INSUFFICIENT_BANKROLL_FOR_FORMAT')

    if buyin is None or not isinstance(buyin, (int, float)) or not math.isfinite(buyin) or buyin < 0:
        reasons.append('BUYIN_UNKNOWN')          # NaN/inf/negative never pass a cap check
    elif config.max_entry_buyin is not None and buyin > config.max_entry_buyin:
        reasons.append('BUYIN_ABOVE_CAP')

    if status.get('state') != 'reg_open':
        reasons.append('REGISTRATION_NOT_OPEN')
    if config.registration_cutoff:
        cutoff, now = _parse_hhmm(config.registration_cutoff), _parse_hhmm(now_hhmm)
        if cutoff is None or now is None:
            reasons.append('REGISTRATION_TIME_UNKNOWN')   # a cutoff with no valid clock fails safe
        elif now > cutoff:
            reasons.append('PAST_REGISTRATION_CUTOFF')

    if name and state.is_committed(name):
        reasons.append('ALREADY_COMMITTED')
    if config.max_tournaments_day is not None and len(state.committed) >= config.max_tournaments_day:
        reasons.append('DAILY_TOURNAMENT_LIMIT_REACHED')
    if len(state.committed) >= config.max_simultaneous:
        reasons.append('MAX_SIMULTANEOUS_REACHED')
    if (config.daily_budget is not None and buyin is not None
            and state.committed_cost() + buyin > config.daily_budget):
        reasons.append('DAILY_BUDGET_EXCEEDED')

    return dict(decision='ELIGIBLE' if not reasons else 'BLOCKED', reasons=reasons,
                name=name, buyin=buyin, modality=modality, execution_allowed=False)


def select_from_grade(cards, config, state=None, *, club=None, now_hhmm=None):
    """Evaluate every card; return (eligible, blocked) lists of decisions."""
    decisions = [evaluate_card(c, config, state, club=club, now_hhmm=now_hhmm) for c in cards]
    return ([d for d in decisions if d['decision'] == 'ELIGIBLE'],
            [d for d in decisions if d['decision'] == 'BLOCKED'])
