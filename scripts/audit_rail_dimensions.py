"""Measure the active mesh in Gazebo coordinates, including GLB node transforms."""
import contextlib
import io
import json
import numpy as np
from inspect_rail_mesh import load

def measure():
    with contextlib.redirect_stdout(io.StringIO()):
        doc,_,positions = load()
    clouds=[]
    def walk(index,parent):
        node=doc['nodes'][index]
        transform=parent @ np.array(node.get('matrix',np.eye(4).T.flatten())).reshape(4,4).T
        if 'mesh' in node:
            for primitive in doc['meshes'][node['mesh']]['primitives']:
                p=positions(primitive['attributes']['POSITION'])
                clouds.append((np.column_stack((p,np.ones(len(p)))) @ transform.T)[:,:3])
        for child in node.get('children',[]): walk(child,transform)
    for root in doc['scenes'][doc.get('scene',0)]['nodes']: walk(root,np.eye(4))
    p=np.vstack(clouds)
    # Active SDF visual pose: Rx(pi/2), translation z=0.185822.
    p=np.column_stack((p[:,0],-p[:,2],p[:,1]+.185822))
    top=p[:,2].max()
    crown=p[p[:,2]>top-.005]
    left=crown[crown[:,1]<0,1]; right=crown[crown[:,1]>0,1]
    report={'world_bounds_min':p.min(axis=0).tolist(),'world_bounds_max':p.max(axis=0).tolist(),
       'rail_top_z_m':float(top),'crown_band_depth_m':.005,
       'negative_rail_y_range_m':[float(left.min()),float(left.max())],
       'positive_rail_y_range_m':[float(right.min()),float(right.max())],
       'crown_inner_gap_m':float(right.min()-left.max()),
       'crown_centre_spacing_m':float((right.min()+right.max()-left.min()-left.max())/2)}
    return report

if __name__=='__main__': print(json.dumps(measure(),indent=2))
