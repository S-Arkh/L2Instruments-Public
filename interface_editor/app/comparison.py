"""Property alignment and comparison without modifying either selected object."""
import math

ORANGE = '#ffbf69'
RED = '#ff8a80'


def equal_value(left, right):
    if isinstance(left, float) and isinstance(right, float):
        if math.isnan(left) and math.isnan(right):
            return True
        if left == 0 and right == 0:
            return math.copysign(1, left) == math.copysign(1, right)
    return left == right


def align_properties(left, right):
    """Union of active field names, stable left order then right-only fields."""
    maps = [{p['name']: p for p in side} for side in (left, right)]
    names = list(dict.fromkeys(p['name'] for side in (left, right) for p in side if p.get('active', True)))
    rows = []
    for name in names:
        fields = [m.get(name) for m in maps]
        active = [p if p and p.get('active', True) else None for p in fields]
        status = 'missing' if None in active else (
            'different' if active[0].get('type', active[0]['kind']) != active[1].get('type', active[1]['kind'])
            or not equal_value(active[0]['value'], active[1]['value']) else 'equal')
        rows.append(dict(name=name, fields=active, status=status,
                         reasons=['Неактивно при текущих флагах' if p else 'Нет поля у этого типа объекта' for p in fields]))
    return rows
