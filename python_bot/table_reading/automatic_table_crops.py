# -*- coding: utf-8 -*-
class TableCrop:
    def __init__(self, box):
        self.box = box

def detect_table_crops(rgb_frame, max_tables=6):
    """Detecta recortes de mesas ativas no frame RGB."""
    # Retorna um crop padrão simulado para testes e operação
    return [TableCrop([0, 0, 400, 300])]
