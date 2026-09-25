"""Dated geometric measurements from an archived metric LiDAR crop.

Ground-normalized heights are geometric observations, not building classifications.
Requires classified ground, projected meter coordinates, and sufficient nearby
returns. Never substitutes file creation time for capture time.
"""
from pathlib import Path
import argparse
import hashlib
import json
import laspy
import numpy as np
from scipy.spatial import cKDTree


def measure(path:Path,captured_at:str,expected_sha:str, crs_override:str|None=None, crs_evidence:str|None=None):
    from datetime import date
    date.fromisoformat(captured_at)
    body=path.read_bytes()
    if hashlib.sha256(body).hexdigest()!=expected_sha: raise ValueError('LiDAR hash mismatch')
    las=laspy.read(path)
    crs=las.header.parse_crs()
    if crs is None and crs_override and crs_evidence:
        from pyproj import CRS
        crs=CRS.from_user_input(crs_override)
    if crs is None or not crs.is_projected or any(a.unit_name not in ('metre','meter') for a in crs.axis_info[:2]):
        raise ValueError('LiDAR must have an explicit projected metric CRS')
    xyz=np.column_stack((las.x,las.y,las.z)); classes=np.asarray(las.classification)
    ground=xyz[classes==2]; surface=xyz[~np.isin(classes,[2,7,18])]
    if len(ground)<20 or len(surface)<20: raise ValueError('insufficient classified ground/surface support')
    distance,index=cKDTree(ground[:,:2]).query(surface[:,:2],k=1)
    good=distance<=2.0
    height=surface[good,2]-ground[index[good],2]
    coverage=float(good.mean())
    return dict(schema_version='lidar-height-v1',captured_at=captured_at,sha256=expected_sha,
                crs=str(crs), crs_evidence=crs_evidence or 'embedded LAS metadata',
                method='surface minus nearest classified ground elevation within 2 m',
                ground_points=len(ground),surface_points=len(surface),normalized_points=int(good.sum()),
                ground_support_fraction=coverage,quality='usable' if coverage>=0.9 else 'limited_ground_support',
                height_quantiles_m={str(q):round(float(np.quantile(height,q)),3) for q in (.1,.5,.9,.95)} if len(height) else {},
                limitations=['5 m context crop is not a building footprint',
                             'vegetation and debris can be elevated returns',
                             'single historical acquisition cannot establish change or current construction'])


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('path',type=Path);parser.add_argument('--captured-at',required=True);parser.add_argument('--sha256',required=True);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--crs');parser.add_argument('--crs-evidence');args=parser.parse_args();result=measure(args.path,args.captured_at,args.sha256,args.crs,args.crs_evidence);args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__': main()
