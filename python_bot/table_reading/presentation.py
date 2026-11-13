"""Explain detector decisions without claiming rejected regions are lobbies."""
REASONS = {
    'TOUCHES_FRAME_EDGE': 'regiao encosta na borda da captura',
    'OVERLAPPING_WINDOW': 'sobreposicao com janela informada',
    'UNSUPPORTED_GREEN_LAYOUT': 'layout verde ainda nao suportado',
    'FULL_BOUNDARY_NOT_ESTABLISHED': 'limites completos da mesa nao confirmados',
    'LAYOUT_PROPORTIONS_UNSUPPORTED': 'proporcoes fora do layout suportado',
    'HORIZONTAL_VISIBILITY_GAP': 'descontinuidade visual horizontal',
    'INSUFFICIENT_LAYOUT_EVIDENCE': 'evidencia visual insuficiente do layout',
    'TABLE_LIMIT_EXCEEDED': 'limite de mesas excedido',
}

def describe_regions(report):
    rows=report.get('tables',[])
    accepted=sum(row.get('status')=='COMPLETE_CANDIDATE' for row in rows)
    lines=[f'Mesas aceitas para leitura: {accepted} | Regioes rejeitadas: {len(rows)-accepted}']
    for row in rows:
        index=row['table_index'];box=row['local_box'];status=row.get('status','UNKNOWN')
        if status!='COMPLETE_CANDIDATE':
            reasons=row.get('reasons') or ['REASON_NOT_REPORTED']
            explanation='; '.join(f'{code}: {REASONS.get(code,"motivo sem traducao")}' for code in reasons)
            lines.append(f'REGIAO REJEITADA {index} | caixa {box} | {status} | {explanation} | OCR nao executado')
        else:
            cards=' / '.join(c or 'NAO IDENTIFICADO' for c in row['hero_cards'])
            lines.append(f'MESA ACEITA (regiao {index}) | caixa {box} | Hero: {cards} | {row["reading_status"]}')
            if 'board' in row:
                board=row['board']
                lines.append('BOARD: '+(' / '.join(board['cards']) or 'NAO CONFIRMADO')+' | '+str(board.get('street') or 'FASE NAO CONFIRMADA')+' | '+board['status'])
            if 'action_buttons' in row:
                result=row['action_buttons']
                labels=[f"{b.get('label') or 'NAO IDENTIFICADO'} [{b['status']}]" for b in result['buttons']]
                lines.append('BOTOES: '+(' | '.join(labels) if labels else result['status'])+' | vez do Hero nao confirmada')
    return lines
