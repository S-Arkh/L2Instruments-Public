"""Linear blend skinning using serialized bind poses and full animation tracks."""
from animation_decode import (floats,quaternion,hierarchy,multiply,rotate,
                              prepare_animation,sample)
from mesh_decode import prepare_mesh,vector


def world_transforms(parents,positions,rotations):
    points=[];orientations=[]
    for i,(parent,p,q) in enumerate(zip(parents,positions,rotations)):
        if i:
            q=(-q[0],-q[1],-q[2],q[3])
            offset=rotate(orientations[parent],p)
            p=tuple(a+b for a,b in zip(points[parent],offset))
            q=multiply(orientations[parent],q)
        points.append(p);orientations.append(q)
    return points,orientations


def prepare_skin(document,index):
    try:
        mesh=document['mesh'];body=mesh['body'];animation=document['animation']
        prepared=prepare_animation(animation,index)
        if 'error' in prepared:raise ValueError(prepared['error'])
        bones=body['bones'];parents=hierarchy(bones)
        names=[n.casefold() for n in prepared['names']]
        mesh_names=[b['name'].casefold() for b in bones]
        if len(set(names))!=len(names) or len(set(mesh_names))!=len(mesh_names):
            raise ValueError('Ambiguous duplicate bone names')
        if any(n not in names for n in mesh_names):
            raise ValueError('Animation is missing a mesh bone track')
        # UE2 binds tracks by bone name and composes them using the mesh's
        # hierarchy; auxiliary animation-only bones do not deform the mesh.
        prepared['tracks']=[prepared['tracks'][names.index(n)] for n in mesh_names]
        prepared['parents']=parents;prepared['names']=[b['name'] for b in bones]
        if len(body['points_bits'])>20000 or len(body['influences'])>500000:
            raise ValueError('Skinning preview exceeds 20000 points / 500000 influences')
        poses=[floats(b['pose_bits'],11) for b in bones]
        bind_positions,bind_rotations=world_transforms(parents,[p[4:7] for p in poses],
                                                      [quaternion(p[:4]) for p in poses])
        points=[vector(p) for p in body['points_bits']]
        weights=[[] for _ in points]
        for influence in body['influences']:
            point,bone=influence['point'],influence['bone']
            weight=floats([influence['weight_bits']],1)[0]
            if not 0<=point<len(points) or not 0<=bone<len(bones) or not 0<=weight<=1:
                raise ValueError('Invalid skin influence')
            if weight:
                q=bind_rotations[bone];inverse=(-q[0],-q[1],-q[2],q[3])
                offset=rotate(inverse,tuple(a-b for a,b in zip(points[point],bind_positions[bone])))
                weights[point].append((bone,weight,offset))
        for row in weights:
            total=sum(w for _,w,_ in row)
            if not .98<=total<=1.02:raise ValueError('Missing or non-unit skin weights')
            for i,(bone,w,offset) in enumerate(row):row[i]=(bone,w/total,offset)
        geometry=prepare_mesh(mesh,'skeletal_mesh')
        # Fixed reference-mesh framing plus the root translation range. Bone
        # chains may contain helper offsets far outside the visible geometry;
        # using their summed lengths makes the rendered model unnecessarily tiny.
        root_positions=prepared['tracks'][0]['positions']
        low=[geometry['bounds'][0][i]+min(p[i] for p in root_positions)-bind_positions[0][i]
             for i in range(3)]
        high=[geometry['bounds'][1][i]+max(p[i] for p in root_positions)-bind_positions[0][i]
              for i in range(3)]
        prepared.update(kind='skinning',weights=weights,polygons=geometry['polygons'],
                        edges=geometry['edges'],vertices=len(points),
                        center=[(a+b)/2 for a,b in zip(low,high)],
                        scale=max(max(b-a for a,b in zip(low,high))/2,1e-6),
                        textures=document.get('surface',{}).get('textures',{}),
                        uv=document.get('surface',{}).get('uv',[]),
                        face_materials=document.get('surface',{}).get('face_materials',[]),
                        warnings=['Координаты mesh-local; размещение объекта MeshOrigin/RotOrigin не применяется']
                                 +document.get('surface',{}).get('warnings',[]))
        if 'uv_base' in document.get('surface',{}):
            prepared['uv_base']=document['surface']['uv_base']
        for field in ('uv_input','fragment_inputs','fragment_uv'):
            if field in document.get('surface',{}):
                prepared[field]=document['surface'][field]
        return prepared
    except (ValueError,KeyError,IndexError,TypeError) as error:return {'error':str(error)}


def skin_geometry(prepared,seconds,loop=False):
    frames=prepared['frames'];frame=max(0.,seconds*prepared['rate'])
    frame=frame%frames if loop else min(frame,frames-1e-6)
    positions=[];rotations=[]
    for track in prepared['tracks']:
        positions.append(sample(track['positions'],track['times'],frame,frames,loop))
        rotations.append(sample(track['rotations'],track['times'],frame,frames,loop,True))
    positions,rotations=world_transforms(prepared['parents'],positions,rotations)
    points=[]
    for row in prepared['weights']:
        point=[0.,0.,0.]
        for bone,weight,offset in row:
            rotated=rotate(rotations[bone],offset)
            for axis in range(3):point[axis]+=(positions[bone][axis]+rotated[axis])*weight
        points.append(tuple((point[i]-prepared['center'][i])/prepared['scale'] for i in range(3)))
    geometry=dict(points=points,polygons=prepared['polygons'],edges=prepared['edges'])
    if prepared['textures']:
        geometry.update(uv=prepared['uv'],face_materials=prepared['face_materials'])
        for field in ('uv_input','fragment_inputs','fragment_uv'):
            if field in prepared:geometry[field]=prepared[field]
    return geometry
