"""Diagnostic UE2 full-hierarchy animation sampling; no game execution."""
import bisect
import math
import struct


def floats(words, count):
    if len(words) != count:
        raise ValueError('Invalid animation vector width')
    result = struct.unpack('<'+'f'*count, struct.pack('<'+'I'*count, *words))
    if not all(math.isfinite(v) for v in result):
        raise ValueError('Non-finite animation value')
    return result


def quaternion(value):
    length = math.sqrt(sum(x*x for x in value))
    if not .5 < length < 1.5:
        raise ValueError('Invalid animation quaternion length')
    return tuple(x/length for x in value)


def multiply(a, b):
    x,y,z,w = a; X,Y,Z,W = b
    return (w*X+x*W+y*Z-z*Y, w*Y-x*Z+y*W+z*X,
            w*Z+x*Y-y*X+z*W, w*W-x*X-y*Y-z*Z)


def rotate(q, position):
    inverse = (-q[0],-q[1],-q[2],q[3])
    return multiply(multiply(q,(*position,0.)),inverse)[:3]


def slerp(a, b, fraction):
    dot = sum(x*y for x,y in zip(a,b))
    if dot < 0:
        b = tuple(-x for x in b);dot = -dot
    dot = min(1.,dot)
    if dot > .9995:
        return quaternion(tuple(x+(y-x)*fraction for x,y in zip(a,b)))
    angle = math.acos(dot)
    u = math.sin((1-fraction)*angle)/math.sin(angle)
    v = math.sin(fraction*angle)/math.sin(angle)
    return tuple(u*x+v*y for x,y in zip(a,b))


def hierarchy(bones):
    if not 0 < len(bones) <= 512:
        raise ValueError('Skeleton preview requires 1..512 bones')
    parents = []
    for i,bone in enumerate(bones):
        parent = bone['parent']
        if (i==0 and parent not in (0,0xffffffff)) or (i>0 and not 0 <= parent < i):
            raise ValueError('Unsupported skeleton hierarchy')
        parents.append(parent)
    return parents


def world_pose(parents, positions, rotations):
    points, orientations = [], []
    for i,(parent,p,q) in enumerate(zip(parents,positions,rotations)):
        # UE2 axis convention: root and child orientations have opposite
        # conjugation in local-to-world transforms.
        if i:
            q = (-q[0],-q[1],-q[2],q[3])
            offset = rotate(orientations[parent],p)
            p = tuple(a+b for a,b in zip(points[parent],offset))
            q = multiply(orientations[parent],q)
        points.append(p);orientations.append(q)
    return points


def reference_skeleton(document):
    bones = document['body']['bones'];parents = hierarchy(bones)
    positions,rotations = [],[]
    for bone in bones:
        pose = floats(bone['pose_bits'],11)
        rotations.append(quaternion(pose[:4]));positions.append(pose[4:7])
    return world_pose(parents,positions,rotations), parents, [b['name'] for b in bones]


def prepare_animation(document, index):
    body = document['body']
    result = {'index':index}
    try:
        parents = hierarchy(body['bones'])
        if len(body['moves']) != len(body['sequences']):
            raise ValueError('Animation sequence/move counts differ')
        if not 0 <= index < len(body['sequences']):
            raise ValueError('No animation sequence selected')
        sequence,move = body['sequences'][index],body['moves'][index]
        frames = sequence['frames'];rate = floats([sequence['rate_bits']],1)[0]
        if not 0 < frames <= 1000000 or not 0 < rate <= 1000:
            raise ValueError('Invalid animation frame count or rate')
        duration = floats([move['header'][3]],1)[0]
        if duration <= 0 or move['header'][4] != 0:
            raise ValueError('Partial hierarchy or invalid track duration is unsupported')
        if move['bone_indices'] not in ([],list(range(len(parents)))) or len(move['tracks']) != len(parents):
            raise ValueError('Non-identity animation track mapping is unsupported')
        tracks = [];key_count = 0
        for track in move['tracks']:
            key_count += len(track['rotation_bits'])+len(track['position_bits'])+len(track['time_bits'])
            if key_count > 1000000:
                raise ValueError('Animation preview exceeds one million keys')
            positions = [floats(p,3) for p in track['position_bits']]
            rotations = [quaternion(floats(q,4)) for q in track['rotation_bits']]
            times = [floats([t],1)[0]*frames/duration for t in track['time_bits']]
            if not positions or not rotations:
                raise ValueError('Animation needs reference-pose fallback for missing keys')
            if times and (any(len(keys) not in (1,len(times)) for keys in (positions,rotations))
                          or times[0] != 0 or times[-1] > frames
                          or any(a>=b for a,b in zip(times,times[1:]))):
                raise ValueError('Invalid animation key times or counts')
            tracks.append(dict(positions=positions,rotations=rotations,times=times))
        # Conservative fixed camera bounds: all root translations plus maximum
        # lengths along each parent chain. Rotation cannot enlarge those radii.
        radii = [0.]
        for i in range(1,len(parents)):
            length = max(math.sqrt(sum(x*x for x in p)) for p in tracks[i]['positions'])
            radii.append(radii[parents[i]]+length)
        root = tracks[0]['positions'];radius = max(radii)
        low = [min(p[i] for p in root)-radius for i in range(3)]
        high = [max(p[i] for p in root)+radius for i in range(3)]
        result.update(parents=parents,tracks=tracks,frames=frames,rate=rate,
                      names=[b['name'] for b in body['bones']],name=sequence['name'],
                      center=[(a+b)/2 for a,b in zip(low,high)],
                      scale=max(max(b-a for a,b in zip(low,high))/2,1e-6))
    except (ValueError,KeyError,IndexError,struct.error) as error:
        result['error'] = str(error)
    return result


def sample(keys, times, frame, frames, loop, rotation=False):
    if len(keys)==1:return keys[0]
    if times:
        a = max(0,min(len(times)-1,bisect.bisect_right(times,frame)-1))
        start = times[a]
        end = times[a+1] if a+1<len(times) else frames
    else:
        value = frame*len(keys)/frames
        a = min(len(keys)-1,int(value));start = a*frames/len(keys)
        end = (a+1)*frames/len(keys)
    b = a+1
    if b==len(keys):
        if not loop:return keys[a]
        b = 0
    fraction = max(0.,min(1.,(frame-start)/(end-start))) if end>start else 0.
    if rotation:return slerp(keys[a],keys[b],fraction)
    return tuple(x+(y-x)*fraction for x,y in zip(keys[a],keys[b]))


def animation_pose(prepared, seconds, loop=False):
    frames = prepared['frames'];frame = max(0.,seconds*prepared['rate'])
    frame = frame%frames if loop else min(frame,frames-1e-6)
    positions,rotations = [],[]
    for track in prepared['tracks']:
        positions.append(sample(track['positions'],track['times'],frame,frames,loop))
        rotations.append(sample(track['rotations'],track['times'],frame,frames,loop,True))
    return world_pose(prepared['parents'],positions,rotations)


def skeleton_geometry(points, parents, names, center=None, scale=None):
    if center is None:
        low = [min(p[i] for p in points) for i in range(3)]
        high = [max(p[i] for p in points) for i in range(3)]
        center = [(a+b)/2 for a,b in zip(low,high)]
        scale = max(max(b-a for a,b in zip(low,high))/2,1e-6)
    return dict(points=[tuple((p[i]-center[i])/scale for i in range(3)) for p in points],
                edges=[(parent,i) for i,parent in enumerate(parents) if i],polygons=[],
                bone_names=names)
