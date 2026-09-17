"""Inspect GLB geometry without installing a mesh viewer."""
import json
import struct
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]

def load():
    data = (ROOT/'simulation/gazebo/models/railway_straight_realistic/meshes/straight_track.glb').read_bytes()
    size,kind = struct.unpack_from('<II',data,12)
    doc = json.loads(data[20:20+size])
    offset = 20+size
    binary = data[offset+8:]
    def positions(index):
        a = doc['accessors'][index]
        v = doc['bufferViews'][a['bufferView']]
        return np.ndarray((a['count'],3),dtype='<f4',buffer=binary,
            offset=v.get('byteOffset',0)+a.get('byteOffset',0),
            strides=(v.get('byteStride',12),4)).copy()
    print('nodes',json.dumps(doc.get('nodes')))
    for mesh in doc['meshes']:
        for primitive in mesh['primitives']:
            p = positions(primitive['attributes']['POSITION'])
            print(mesh.get('name'), 'material',primitive.get('material'),
                  'bounds',p.min(axis=0),p.max(axis=0), 'count',len(p))
            print('highest y levels',np.unique(np.round(p[:,1],5))[-15:])
    return doc,binary,positions

if __name__ == '__main__':
    load()
