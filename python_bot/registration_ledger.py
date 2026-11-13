"""Ledger de reservas de inscrição — persistente, atômico, com dedup (Fase 3A).

Implementa as garantias §5/§6/§9 da spec `ESTRATÉGIA DE INSCRIÇ.txt`:

- Reserva de custo+vaga é ATÔMICA (uma transação de escrita serializada) e
  PERSISTENTE (SQLite em arquivo). Reiniciar o programa NÃO apaga reservas.
- Dois ciclos/processos NÃO podem reservar a mesma oferta duas vezes nem passar
  do limite numa corrida: `BEGIN IMMEDIATE` serializa a verificação+inserção e um
  índice único parcial sobre a identidade em estados ativos é o segundo cinto.
- Dinheiro é SEMPRE Decimal exato em centavos. Nunca float, nunca arredondar para
  encaixar numa oferta.
- A IDENTIDADE do torneio é um token interno composto (clube+nome+modalidade+
  buy-in+início), rotulado como interno — NUNCA apresentado como um ID lido da
  tela. Nome sozinho não estabelece identidade (§4).

Este módulo NÃO clica, não lê tela e não autoriza gasto. É só o livro-razão.
"""
import hashlib
import json
import sqlite3
import time
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

CENT = Decimal('0.01')

# Estados que CONTAM como compromisso de vaga+custo (§6): inscrito/ativo, reserva
# pendente, inscrição com resultado desconhecido. Um deles ocupa capacidade.
ACTIVE_STATES = (
    'RESERVED', 'AWAITING_CONFIRMATION', 'CONFIRMATION_SENT',
    'CONFIRMED', 'UNKNOWN_RESULT',
)
# Estados terminais que LIBERAM a vaga/custo (prova de não-envio ou recusa limpa).
RELEASED_STATES = ('CANCELLED_BEFORE_SEND', 'REJECTED_NO_CHARGE')

_ACTIVE_SQL = ','.join('?' * len(ACTIVE_STATES))


class LedgerError(Exception):
    """Falha de pré-condição do ledger (identidade/custo/moeda ausente etc.)."""


def to_money(x):
    """Decimal exato em centavos, ou None quando ausente/ilegível/inválido.

    None NUNCA vira zero (§3). NaN/inf/negativo não são dinheiro válido.
    """
    if x is None:
        return None
    try:
        d = x if isinstance(x, Decimal) else Decimal(str(x))
    except (InvalidOperation, ValueError):
        return None
    if not d.is_finite() or d < 0:
        return None
    return d.quantize(CENT, rounding=ROUND_HALF_UP)


def sum_parcels(parcels, total=None):
    """Soma de parcelas (entrada+taxa+bounty) como Decimal, conferida contra o
    total exibido quando houver (§5).

    Retorna (soma, ok). `ok` é False se alguma parcela for ilegível ou se a soma
    divergir do total informado — o chamador deve BLOQUEAR, não adivinhar. Não
    soma o total às parcelas de novo.
    """
    vals = [to_money(p) for p in (parcels or [])]
    if not vals or any(v is None for v in vals):
        return (None, False)
    s = sum(vals, Decimal(0)).quantize(CENT, rounding=ROUND_HALF_UP)
    if total is not None:
        t = to_money(total)
        if t is None or t != s:
            return (s, False)
    return (s, True)


def make_identity(*, name, club=None, modality=None, buyin=None, start_time=None):
    """Token de identidade VERIFICÁVEL do evento + a lista de campos usados.

    Retorna (identity_hash, basis). `identity_hash` é None quando a identidade não
    pode ser estabelecida: §4 diz que o nome sozinho não distingue dois torneios,
    então exigimos nome + pelo menos um campo concreto (buy-in OU horário de
    início). O hash é um token INTERNO de auditoria — não é um ID lido da tela.
    """
    money = to_money(buyin)
    fields = {
        'name': (name or '').strip() or None,
        'club': (club or '').strip() or None,
        'modality': (modality or '').strip() or None,
        'buyin': (str(money) if money is not None else None),
        'start_time': (start_time or '').strip() or None,
    }
    basis = [k for k, v in fields.items() if v]
    distinguishing = [k for k in ('buyin', 'start_time') if fields[k]]
    if not fields['name'] or not distinguishing:
        return (None, basis)
    key = json.dumps({k: fields[k] for k in sorted(fields)}, ensure_ascii=False)
    return (hashlib.sha256(key.encode('utf-8')).hexdigest()[:16], basis)


class RegistrationLedger:
    """Livro-razão de reservas em SQLite. Use um arquivo para persistir entre
    execuções; `:memory:` só para testes de uma sessão."""

    def __init__(self, db_path=':memory:', *, clock=time.monotonic, wall=time.time):
        self._clock = clock
        self._wall = wall
        # isolation_level=None => sem autocommit implícito; controlamos BEGIN/COMMIT.
        self.db = sqlite3.connect(db_path, isolation_level=None, timeout=30)
        self.db.execute('PRAGMA busy_timeout=30000')
        if db_path != ':memory:':
            self.db.execute('PRAGMA journal_mode=WAL')
        self._init_schema()

    def _init_schema(self):
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS reservations(
              token           TEXT PRIMARY KEY,
              identity        TEXT NOT NULL,
              name            TEXT,
              club            TEXT,
              modality        TEXT,
              cost            TEXT NOT NULL,     -- Decimal em centavos, como texto
              currency        TEXT NOT NULL,
              state           TEXT NOT NULL,
              round_id        TEXT,
              operator        TEXT,
              start_time      TEXT,
              created_wall    REAL,
              created_mono    REAL,
              updated_wall    REAL,
              reason          TEXT,
              evidence_ref    TEXT
            );
            -- Um único compromisso ativo por identidade: impede dupla reserva/
            -- cobrança da mesma oferta mesmo em corrida entre processos (§6).
            CREATE UNIQUE INDEX IF NOT EXISTS ux_active_identity
              ON reservations(identity)
              WHERE state IN ('RESERVED','AWAITING_CONFIRMATION',
                              'CONFIRMATION_SENT','CONFIRMED','UNKNOWN_RESULT');
            """
        )

    # ---- escrita ---------------------------------------------------------
    def reserve(self, *, identity, cost, currency, name=None, club=None,
                modality=None, start_time=None, round_id=None, operator=None,
                token=None, max_active=None):
        """Reserva custo+vaga atomicamente. Retorna um dict com `ok`.

        ok=False + reason='ALREADY_RESERVED' quando já existe compromisso ativo
        para a identidade (dedup). `max_active` (opcional) impõe o LIMITE DE VAGAS
        DENTRO da transação (BEGIN IMMEDIATE serializa escritores), então duas
        corridas não ultrapassam o limite — ok=False + reason='CAPACITY_FULL'
        quando já há max_active compromissos ativos. Levanta LedgerError se
        identidade/custo/moeda faltarem (ausência nunca vira zero).
        """
        if not identity:
            raise LedgerError('IDENTITY_NOT_VERIFIABLE')
        money = to_money(cost)
        if money is None:
            raise LedgerError('COST_UNKNOWN')
        if not currency:
            raise LedgerError('CURRENCY_UNKNOWN')
        token = token or ('rsv-' + hashlib.sha256(
            (identity + str(time.time_ns())).encode()).hexdigest()[:12])
        try:
            self.db.execute('BEGIN IMMEDIATE')
            row = self.db.execute(
                'SELECT token,state FROM reservations '
                'WHERE identity=? AND state IN (%s)' % _ACTIVE_SQL,
                (identity, *ACTIVE_STATES)).fetchone()
            if row:
                self.db.execute('ROLLBACK')
                return dict(ok=False, reason='ALREADY_RESERVED',
                            token=row[0], state=row[1])
            if max_active is not None:
                # Limite de vagas ATÔMICO: conta ativos na MESMA transação.
                active = self.db.execute(
                    'SELECT COUNT(*) FROM reservations WHERE state IN (%s)'
                    % _ACTIVE_SQL, ACTIVE_STATES).fetchone()[0]
                if active >= max_active:
                    self.db.execute('ROLLBACK')
                    return dict(ok=False, reason='CAPACITY_FULL', active=active)
            now_w, now_m = self._wall(), self._clock()
            self.db.execute(
                'INSERT INTO reservations(token,identity,name,club,modality,cost,'
                'currency,state,round_id,operator,start_time,created_wall,'
                'created_mono,updated_wall) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (token, identity, name, club, modality, str(money), currency,
                 'RESERVED', round_id, operator, start_time, now_w, now_m, now_w))
            self.db.execute('COMMIT')
            return dict(ok=True, token=token, state='RESERVED', cost=str(money))
        except sqlite3.IntegrityError:
            # Índice único parcial disparado por um COMMIT concorrente entre o
            # SELECT e o INSERT: a outra corrida ganhou a vaga.
            try:
                self.db.execute('ROLLBACK')
            except sqlite3.OperationalError:
                pass
            row = self.db.execute(
                'SELECT token,state FROM reservations '
                'WHERE identity=? AND state IN (%s)' % _ACTIVE_SQL,
                (identity, *ACTIVE_STATES)).fetchone()
            return dict(ok=False, reason='ALREADY_RESERVED',
                        token=(row[0] if row else None),
                        state=(row[1] if row else None))

    def set_state(self, token, new_state, *, reason=None, evidence_ref=None):
        """Transição validada de um token. Levanta LedgerError em transição
        inválida ou token inexistente."""
        cur = self.db.execute(
            'SELECT state FROM reservations WHERE token=?', (token,)).fetchone()
        if cur is None:
            raise LedgerError('UNKNOWN_TOKEN')
        if new_state not in _ALLOWED_TRANSITIONS.get(cur[0], ()):
            raise LedgerError('INVALID_TRANSITION:%s->%s' % (cur[0], new_state))
        self.db.execute('BEGIN IMMEDIATE')
        self.db.execute(
            'UPDATE reservations SET state=?,reason=?,evidence_ref=?,updated_wall=? '
            'WHERE token=?',
            (new_state, reason, evidence_ref, self._wall(), token))
        self.db.execute('COMMIT')
        return dict(ok=True, token=token, state=new_state)

    def confirm(self, token, *, evidence_ref=None):
        """Converte reserva em inscrição confirmada (mantém o compromisso de vaga,
        sem contar o custo duas vezes — o estado CONFIRMED já é contado como gasto
        confirmado em `committed`)."""
        return self.set_state(token, 'CONFIRMED', reason='RECONCILED',
                              evidence_ref=evidence_ref)

    def release(self, token, *, reason, evidence_ref=None):
        """Libera a reserva (§9): só para falha COMPROVADA antes do envio ou recusa
        explícita sem cobrança. Em dúvida, use mark_unknown()."""
        cur = self.db.execute(
            'SELECT state FROM reservations WHERE token=?', (token,)).fetchone()
        if cur is None:
            raise LedgerError('UNKNOWN_TOKEN')
        target = 'CANCELLED_BEFORE_SEND' if cur[0] in (
            'RESERVED', 'AWAITING_CONFIRMATION') else 'REJECTED_NO_CHARGE'
        return self.set_state(token, target, reason=reason,
                              evidence_ref=evidence_ref)

    def mark_unknown(self, token, *, reason, evidence_ref=None):
        """Resultado desconhecido (§9): timeout, exceção após o envio, cliente
        fechado, confirmação ilegível. MANTÉM custo+vaga reservados, não reenvia."""
        return self.set_state(token, 'UNKNOWN_RESULT', reason=reason,
                              evidence_ref=evidence_ref)

    # ---- leitura ---------------------------------------------------------
    def get(self, token):
        row = self.db.execute(
            'SELECT token,identity,name,cost,currency,state,round_id,reason '
            'FROM reservations WHERE token=?', (token,)).fetchone()
        if row is None:
            return None
        return dict(token=row[0], identity=row[1], name=row[2], cost=Decimal(row[3]),
                    currency=row[4], state=row[5], round_id=row[6], reason=row[7])

    def active_for_identity(self, identity):
        row = self.db.execute(
            'SELECT token,state FROM reservations '
            'WHERE identity=? AND state IN (%s)' % _ACTIVE_SQL,
            (identity, *ACTIVE_STATES)).fetchone()
        return dict(token=row[0], state=row[1]) if row else None

    def committed(self):
        """(confirmado, pendente, nº de compromissos ativos) em Decimal (§5/§6).

        Confirmado = estados CONFIRMED; pendente = demais estados ativos. Uma vaga
        está em exatamente um dos dois — nada é contado duas vezes.
        """
        rows = self.db.execute(
            'SELECT state,cost FROM reservations WHERE state IN (%s)' % _ACTIVE_SQL,
            ACTIVE_STATES).fetchall()
        confirmed = sum((Decimal(c) for s, c in rows if s == 'CONFIRMED'), Decimal(0))
        pending = sum((Decimal(c) for s, c in rows if s != 'CONFIRMED'), Decimal(0))
        return (confirmed.quantize(CENT), pending.quantize(CENT), len(rows))

    def active_count(self):
        return self.committed()[2]

    def available_budget(self, session_budget):
        """Orçamento disponível = orçamento da sessão − confirmados − pendentes
        (§5). None quando o orçamento não foi informado (ausência ≠ zero)."""
        sb = to_money(session_budget)
        if sb is None:
            return None
        conf, pend, _ = self.committed()
        return (sb - conf - pend).quantize(CENT)

    def close(self):
        self.db.close()


# Transições permitidas da máquina de persistência (espelha §7/§9).
_ALLOWED_TRANSITIONS = {
    'RESERVED': ('AWAITING_CONFIRMATION', 'CANCELLED_BEFORE_SEND',
                 'REJECTED_NO_CHARGE', 'UNKNOWN_RESULT'),
    'AWAITING_CONFIRMATION': ('CONFIRMATION_SENT', 'CANCELLED_BEFORE_SEND',
                              'REJECTED_NO_CHARGE', 'UNKNOWN_RESULT'),
    # Depois do envio NÃO se libera por suposição: só CONFIRMED (reconciliado) ou
    # UNKNOWN_RESULT (mantém a reserva). Pausa após o envio não desfaz inscrição.
    'CONFIRMATION_SENT': ('CONFIRMED', 'UNKNOWN_RESULT'),
    'UNKNOWN_RESULT': ('CONFIRMED',),   # conciliação posterior pode resolver
    'CONFIRMED': (),
    'CANCELLED_BEFORE_SEND': (),
    'REJECTED_NO_CHARGE': (),
}
