"""Estabilizador temporal de posições (observação; sem captura, sem clique).

O leitor de mesa (`read_table_state`) é stateless: deriva as posições a cada
frame de `dealer_seat` + assentos ocupados. Como os rótulos (`SB, BB, ... ,BTN`)
dependem da CONTAGEM de ocupados e do assento do dealer, um único frame com a
ocupação na borda do threshold, ou o botão detectado um assento adiante, desloca
todos os rótulos do meio — o mesmo assento pisca entre, p.ex., HJ e UTG+2 na
MESMA mão. Durante uma mão o botão e a disposição são FIXOS, então reler do zero
a cada frame é a causa do flicker.

Este estabilizador mantém estado por mesa: trava o assento do dealer (com
debounce — só troca quando um novo dealer persiste, o que é o sinal real de mão
nova) e acumula a ocupação por MAIORIA numa janela recente. As posições são
derivadas do dealer travado + ocupação estável. Resultado: dentro da mão as
posições não oscilam; quando o botão realmente anda, o debounce confirma e o
epoch reinicia.
"""
from collections import deque, Counter

from table_reading.dealer_button import derive_positions

DEBOUNCE = 2          # frames que um novo dealer precisa persistir p/ trocar o epoch
WINDOW = 6            # janela de frames p/ a maioria de ocupação


class _TableState:
    def __init__(self, window):
        self.locked_dealer = None
        self.occ = deque(maxlen=window)      # conjuntos de ocupados recentes
        self.pending = None                  # candidato a novo dealer
        self.pending_n = 0
        self.hand = None                     # identidade da mão do epoch atual


class PositionStabilizer:
    def __init__(self, *, window=WINDOW, debounce=DEBOUNCE):
        self.window = window
        self.debounce = debounce
        self._tables = {}

    def _table(self, key):
        st = self._tables.get(key)
        if st is None:
            st = self._tables[key] = _TableState(self.window)
        return st

    def update(self, *, table_key, dealer_seat, occupied_seats, hand_key=None):
        """Processa um frame e devolve (dealer_estavel, posicoes_estaveis).

        `hand_key` (identidade da mão, quando legível) é o sinal AUTORITATIVO de
        troca: dentro de uma mesma mão as posições são fixas (blips de dealer são
        ignorados, segurando o travado); uma MÃO NOVA invalida tudo na hora e adota
        o observado — nunca herda a posição da mão anterior. Sem `hand_key`, um
        conflito de dealer não confirmado fica PENDENTE e NÃO emite a posição antiga
        (devolve {}, o consumidor abstém) até estabilizar (debounce) ou reverter.
        Devolve {} enquanto não houver dealer travado.
        """
        st = self._table(table_key)
        occ = frozenset(occupied_seats)

        prev_hand = st.hand
        is_new_hand = (hand_key is not None and prev_hand is not None and hand_key != prev_hand)
        same_hand = (hand_key is not None and prev_hand is not None and hand_key == prev_hand)
        if hand_key is not None:
            st.hand = hand_key
        if is_new_hand:                                 # mão nova confirmada: invalida já
            st.locked_dealer = dealer_seat
            st.occ.clear()
            st.pending, st.pending_n = None, 0

        st.occ.append(occ)

        pending_conflict = False
        if st.locked_dealer is None:
            if dealer_seat is not None:
                st.locked_dealer = dealer_seat
                st.pending, st.pending_n = None, 0
        elif dealer_seat is not None and dealer_seat != st.locked_dealer:
            # Conflito de dealer. Dentro da MESMA mão (confirmada) é misread -> ignora
            # e segura o travado. Senão, debounce; enquanto não confirma, fica pendente.
            if same_hand:
                st.pending, st.pending_n = None, 0
            else:
                if dealer_seat == st.pending:
                    st.pending_n += 1
                else:
                    st.pending, st.pending_n = dealer_seat, 1
                if st.pending_n >= self.debounce:
                    st.locked_dealer = dealer_seat      # epoch novo
                    st.occ.clear()
                    st.occ.append(occ)
                    st.pending, st.pending_n = None, 0
                else:
                    pending_conflict = True
        else:
            st.pending, st.pending_n = None, 0          # bateu com o travado (ou None)

        if st.locked_dealer is None:
            return None, {}
        # Conflito não resolvido e sem confirmação de mão: não emitir a posição antiga.
        if pending_conflict:
            return st.locked_dealer, {}

        # Ocupação por maioria na janela (assento conta se ocupado em >= metade dos
        # frames recentes); o dealer sempre entra.
        counts = Counter()
        for o in st.occ:
            counts.update(o)
        thr = (len(st.occ) + 1) // 2
        stable_occ = {s for s, c in counts.items() if c >= thr}
        stable_occ.add(st.locked_dealer)

        positions = derive_positions(st.locked_dealer, stable_occ)
        return st.locked_dealer, positions

    def reset(self, table_key=None):
        """Esquece o estado (uma mesa, ou todas). Útil ao perder a mesa de vista."""
        if table_key is None:
            self._tables.clear()
        else:
            self._tables.pop(table_key, None)
