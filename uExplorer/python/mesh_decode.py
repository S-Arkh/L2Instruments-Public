"""Bounded diagnostic geometry, independent of package serialization."""
import math
import struct

MAX_VERTICES = 100000
MAX_FACES = 50000
MAX_EDGES = 150000


def vector(words):
    if len(words) != 3:
        raise ValueError('Invalid position width')
    values = struct.unpack('<3f', struct.pack('<3I', *words))
    if not all(math.isfinite(v) for v in values):
        raise ValueError('Non-finite geometry position')
    return values


def partial_model_warning(document):
    status=document.get('status')
    profile=document.get('profile')
    if status=='unverified':
        shape=(f'{profile[0]}/{profile[1]}' if isinstance(profile,(list,tuple)) and len(profile)==2
               else 'неизвестного профиля')
        remaining=document.get('remaining_bytes',0)
        return (f'Непроверенная форма Model {shape}: '
                +('доступен только ограниченный просмотр исходных байтов; '
                  if document.get('interpretation')=='opaque' else
                  'геометрия разобрана по предположительной схеме; ')
                +(f'нераспознанных байтов: {remaining}; ' if remaining else '')
                +'реконструкция, мировое размещение и игровая коллизия не подтверждены')
    observed_profiles=([133,40],[127,39],[128,39],[130,40],[132,40])
    if status=='decoded' and profile in observed_profiles:
        invalid=len(document.get('invalid_unused_vertices',[]))
        hulls=len(document.get('invalid_unlinked_hull_planes',[]))
        return (f'Сохранённая структура Model {profile[0]}/{profile[1]}; '
                +('проверен только вариант с пустыми дополнительными массивами; '
                  if profile!=[133,40] else '')
                +'мировое размещение и игровая '
                'коллизия не подтверждены'
                +(f'; неверных записей вне диапазонов узлов: {invalid}' if invalid else '')
                +(f'; неверных плоскостей в hull без связи с узлами: {hulls}' if hulls else '')
                +('. Использование этих записей игрой не установлено' if invalid or hulls else ''))
    if status!='partial':
        return None
    remaining=document.get('remaining_bytes',0)
    invalid=len(document.get('invalid_unused_vertices',[]))
    return (f'Model 133/40: частичный разбор геометрии; {remaining} байт не расшифрованы'
            +(f'; неверных записей вне диапазонов узлов: {invalid}' if invalid else '')+'. '
            'Реконструкция, размещение объекта и игровое поведение коллизий не подтверждены')


def prepare_mesh(document, operation, source='render'):
    """Return centered, uniformly scaled geometry; never repair bad indices."""
    if operation == 'skeletal_mesh' and source == 'skeleton':
        from animation_decode import reference_skeleton, skeleton_geometry
        points,parents,names = reference_skeleton(document)
        result = skeleton_geometry(points,parents,names)
        result['bounds'] = tuple(tuple(f(p[i] for p in points) for i in range(3)) for f in (min,max))
        return result
    points, polygons = [], []
    body = document.get('body', document)
    if operation == 'static_mesh':
        rows = body['vertices']
        if len(rows) > MAX_VERTICES:
            raise ValueError('Geometry preview exceeds 100000 vertices')
        points = [vector(row['position_bits']) for row in rows]
        if source == 'collision':
            polygons = [face['vertices'] for face in body['collision_faces']]
        else:
            indices = body['indices']
            for section in body['sections']:
                start, count = section['first_index'], section['face_count']
                if start < 0 or count < 0 or start+count*3 > len(indices):
                    raise ValueError('Invalid geometry section range')
                if len(polygons)+count > MAX_FACES:
                    raise ValueError('Geometry preview exceeds 50000 faces')
                polygons.extend(indices[i:i+3] for i in range(start, start+count*3, 3))
    elif operation == 'skeletal_mesh':
        if len(body['points_bits']) > MAX_VERTICES:
            raise ValueError('Geometry preview exceeds 100000 vertices')
        points = [vector(row) for row in body['points_bits']]
        wedges = body['mesh_wedges']
        if len(body['triangles']) > MAX_FACES:
            raise ValueError('Geometry preview exceeds 50000 faces')
        for face in body['triangles']:
            if any(i < 0 or i >= len(wedges) for i in face['wedges']):
                raise ValueError('Invalid skeletal wedge index')
            polygons.append([wedges[i]['vertex'] for i in face['wedges']])
    elif operation == 'polys':
        for poly in body['polygons']:
            rows = poly['vertices_bits']
            if len(points)+len(rows) > MAX_VERTICES:
                raise ValueError('Geometry preview exceeds 100000 vertices')
            start = len(points)
            points.extend(vector(row) for row in rows)
            polygons.append(list(range(start, len(points))))
    elif operation == 'model':
        if len(body['points']) > MAX_VERTICES:
            raise ValueError('Geometry preview exceeds 100000 vertices')
        points = [vector(row) for row in body['points']]
        pool = body['vertices']
        for node in body['nodes']:
            start, count = node['vertex_pool'], node['vertex_count']
            if start < 0 or count < 0 or start+count > len(pool):
                raise ValueError('Invalid BSP vertex range')
            if count:
                polygons.append([pool[i][0] for i in range(start, start+count)])
    else:
        raise ValueError('Graphical geometry preview is not available for this class')
    if len(polygons) > MAX_FACES:
        raise ValueError('Geometry preview exceeds 50000 faces')
    if not points or not polygons:
        raise ValueError('No drawable geometry in this stream')
    edges = set()
    for face in polygons:
        if len(face) < 3 or any(not isinstance(i, int) or i < 0 or i >= len(points) for i in face):
            raise ValueError('Invalid geometry polygon')
        for a, b in zip(face, face[1:]+face[:1]):
            if a != b:
                edges.add((min(a,b), max(a,b)))
        if len(edges) > MAX_EDGES:
            raise ValueError('Geometry preview exceeds 150000 edges')
    source_point_count=len(points)
    if operation=='model':
        # Frame the faces actually drawn, without altering the saved Model.
        # Retain strict validation of all saved point coordinates above.
        visible=sorted({index for face in polygons for index in face})
        remap={index:offset for offset,index in enumerate(visible)}
        points=[points[index] for index in visible]
        polygons=[[remap[index] for index in face] for face in polygons]
        edges={(remap[a],remap[b]) for a,b in edges}
    low = tuple(min(p[i] for p in points) for i in range(3))
    high = tuple(max(p[i] for p in points) for i in range(3))
    center = tuple((a+b)/2 for a,b in zip(low, high))
    extent = max(b-a for a,b in zip(low, high))
    scale = extent/2 if extent else 1.
    normalized = [tuple((p[i]-center[i])/scale for i in range(3)) for p in points]
    result=dict(points=normalized, polygons=polygons, edges=sorted(edges),
                bounds=(low, high), center=center, scale=scale, source=source)
    if operation=='polys':
        result['warnings']=[
            'Сохранённые полигоны Polys: соответствие узлам Model, мировое размещение '
            'и игровая коллизия не подтверждены']
    if operation=='model':
        warning=partial_model_warning(body)
        if warning:result['warnings']=[warning]
        result['source_point_count']=source_point_count
        result['frame_point_count']=len(points)
        excluded=source_point_count-len(points)
        if excluded:
            result.setdefault('warnings',[]).append(
                f'Точки вне отображаемых граней: {excluded}; они остаются в данных, '
                'их использование игрой не установлено')
    return result


def mesh_preview(document, operation, source='render'):
    if operation=='model' and isinstance(document,dict):
        body=document.get('body',document)
        if isinstance(body,dict) and body.get('interpretation')=='opaque':
            return {'error':'Геометрия не распознана', 'warnings':[partial_model_warning(body)]}
    try:
        return prepare_mesh(document, operation, source)
    except (ValueError, KeyError, IndexError, struct.error) as error:
        result={'error': str(error)}
        if operation=='model' and isinstance(document,dict):
            body=document.get('body',document)
            if isinstance(body,dict):
                warning=partial_model_warning(body)
                if warning:result['warnings']=[warning]
        return result


def project(points, yaw, pitch):
    """Orthographic camera, Z up. Return screen-right, screen-up, depth."""
    cy, sy, cp, sp = math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch)
    result = []
    for x,y,z in points:
        right, forward = cy*x-sy*y, sy*x+cy*y
        result.append((right, cp*z-sp*forward, cp*forward+sp*z))
    return result
