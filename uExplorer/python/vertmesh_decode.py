"""Bounded packed/float UE2 vertex animation in mesh-local coordinates."""
from array import array
import math
import struct
from animation_decode import floats

MAX_SAMPLES = 1000000
MAX_VERTICES = 20000
MAX_FACES = 50000


def unpack_vertex(word):
    if not isinstance(word, int) or not 0 <= word <= 0xffffffff:
        raise ValueError('Invalid packed vertex')
    def signed(value, width):
        return value-(1 << width) if value & (1 << (width-1)) else value
    return (signed(word & 2047, 11), signed((word >> 11) & 2047, 11),
            signed((word >> 22) & 1023, 10))


def prepare_vertmesh(document, index):
    try:
        body = document['body']
        vertices, total = body['vertex_count'], body['frame_count']
        if not isinstance(vertices, int) or not 0 < vertices <= MAX_VERTICES:
            raise ValueError('Vertex animation preview requires 1..20000 vertices')
        if not isinstance(total, int) or total <= 0:
            raise ValueError('Invalid vertex frame count')
        if vertices != body['animated_vertex_count']:
            raise ValueError('Unsupported animated vertex count')
        floating = 'vertices_bits' in body
        storage = body['vertices_bits'] if floating else body['packed_original_vertices']
        if len(storage) != vertices*total:
            raise ValueError('Invalid vertex frame storage')
        # Initial verified format: unit mesh transform. Never silently ignore
        # an origin, scale or rotation when presenting diagnostic geometry.
        transform = body['transforms']
        if len(transform) != 9 or floats(transform[:3],3) != (1.,1.,1.) or any(transform[3:]):
            raise ValueError('Non-identity vertex mesh transforms are not yet supported')
        if not isinstance(index, int) or not 0 <= index <= len(body['sequences']):
            raise ValueError('No vertex animation sequence selected')
        stored = index == len(body['sequences'])
        sequence = (dict(name='Сохранённые кадры (диагностика, 30 кадров/с)',start=0,
                         frames=total,rate_bits=0x41f00000) if stored else body['sequences'][index])
        start, frames = sequence['start'], sequence['frames']
        if (not isinstance(start,int) or not isinstance(frames,int) or
                start < 0 or frames <= 0 or start+frames > total):
            raise ValueError('Invalid vertex animation sequence range')
        if frames*vertices > MAX_SAMPLES:
            raise ValueError('Vertex animation preview exceeds 1000000 samples')
        rate = floats([sequence['rate_bits']],1)[0]
        if not 0 < rate <= 1000:
            raise ValueError('Invalid vertex animation rate')
        wedges = body['wedges']
        if len(wedges) > 100000 or not 0 < len(body['faces']) <= MAX_FACES:
            raise ValueError('Vertex animation topology exceeds preview limits')
        for wedge in wedges:
            if not isinstance(wedge['vertex'],int) or not 0 <= wedge['vertex'] < vertices:
                raise ValueError('Invalid vertex animation wedge')
        polygons, edges = [], set()
        for face in body['faces']:
            if len(face) != 4 or any(not isinstance(i,int) or not 0 <= i < len(wedges) for i in face[:3]):
                raise ValueError('Invalid vertex animation face')
            polygon = [wedges[i]['vertex'] for i in face[:3]]
            polygons.append(polygon)
            edges.update((min(a,b),max(a,b)) for a,b in zip(polygon,polygon[1:]+polygon[:1]) if a != b)
        coordinates = array('f')
        low, high = [math.inf]*3, [-math.inf]*3
        for i in range(start*vertices,(start+frames)*vertices):
            point = floats(storage[i],3) if floating else unpack_vertex(storage[i])
            coordinates.extend(point)
            for axis, value in enumerate(point):
                low[axis] = min(low[axis],value)
                high[axis] = max(high[axis],value)
        center = tuple((a+b)/2 for a,b in zip(low,high))
        scale = max(b-a for a,b in zip(low,high))/2 or 1.
        return dict(kind='vert_mesh', name=sequence['name'], frames=frames, rate=rate,
                    storage='float' if floating else 'packed',
                    diagnostic_frames=stored,
                    vertices=vertices, coordinates=coordinates, polygons=polygons,
                    edges=sorted(edges), center=center, scale=scale, bounds=(low,high))
    except (ValueError, KeyError, IndexError, TypeError, struct.error) as error:
        return {'error': str(error)}


def vertex_geometry(prepared, seconds, repeat=False):
    frame = max(0.,seconds)*prepared['rate']
    frame = frame % prepared['frames'] if repeat else min(frame,prepared['frames']-1)
    first = int(frame)
    second = (first+1) % prepared['frames'] if repeat else min(first+1,prepared['frames']-1)
    fraction = frame-first
    count, data = prepared['vertices'], prepared['coordinates']
    points = []
    for vertex in range(count):
        a, b = (first*count+vertex)*3, (second*count+vertex)*3
        points.append(tuple((data[a+i]+(data[b+i]-data[a+i])*fraction-prepared['center'][i])/
                            prepared['scale'] for i in range(3)))
    return dict(points=points, polygons=prepared['polygons'], edges=prepared['edges'],
                bounds=prepared['bounds'], center=prepared['center'], scale=prepared['scale'])
