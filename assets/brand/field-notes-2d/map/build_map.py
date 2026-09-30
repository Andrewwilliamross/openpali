#!/usr/bin/env python3
"""Build a neutral, source-linked parcel plan from retained County geometry.

Standard library only. No recovery, owner, or address attributes enter the output.
Run from any directory: python3 assets/brand/field-notes-2d/map/build_map.py
"""
from pathlib import Path
import collections, datetime, hashlib, html, json, math, sys

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'source'
BOUNDS = [-118.52345, 34.04920, -118.51950, 34.05170]
CLOSE = '--close' in sys.argv
if CLOSE:
    BOUNDS = [-118.52230, 34.05015, -118.51980, 34.05170]
OUTPUT = ROOT / 'close' if CLOSE else ROOT
OUTPUT.mkdir(exist_ok=True)
VIEWBOX = [0, 0, 1100, 720]
FRAME = {'x': 44, 'y': 92, 'width': 738, 'height': 544}
R = 6378137.0
BLUE = '#1557ff'

def project(point):
    lon, lat = point[:2]
    return R * math.radians(lon), R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))

SW = project(BOUNDS[:2]); NE = project(BOUNDS[2:])
SCALE = min(FRAME['width'] / (NE[0]-SW[0]), FRAME['height'] / (NE[1]-SW[1]))
DRAW_W = (NE[0]-SW[0])*SCALE; DRAW_H = (NE[1]-SW[1])*SCALE
OX = FRAME['x']+(FRAME['width']-DRAW_W)/2; OY = FRAME['y']+(FRAME['height']-DRAW_H)/2

def xy(point):
    x,y=project(point)
    return [round(OX+(x-SW[0])*SCALE,2),round(OY+(NE[1]-y)*SCALE,2)]

def intersect_box(points):
    xs=[p[0] for p in points];ys=[p[1] for p in points]
    if not (max(xs)>=BOUNDS[0] and min(xs)<=BOUNDS[2] and max(ys)>=BOUNDS[1] and min(ys)<=BOUNDS[3]):
        return False
    if any(BOUNDS[0]<=x<=BOUNDS[2] and BOUNDS[1]<=y<=BOUNDS[3] for x,y in points):
        return True
    if any(line_clip(a,b) for a,b in zip(points,points[1:])):
        return True
    # A polygon may enclose the entire display window without crossing its edges.
    x,y=BOUNDS[:2];inside=False
    for a,b in zip(points,points[1:]):
        if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:inside=not inside
    return inside

def line_clip(a,b):
    """Liang–Barsky clip in WGS84 coordinates; preserves source segment direction."""
    dx=b[0]-a[0];dy=b[1]-a[1];lo=0;hi=1
    for p,q in [(-dx,a[0]-BOUNDS[0]),(dx,BOUNDS[2]-a[0]),(-dy,a[1]-BOUNDS[1]),(dy,BOUNDS[3]-a[1])]:
        if abs(p)<1e-15:
            if q<0:return None
        else:
            t=q/p
            if p<0:lo=max(lo,t)
            else:hi=min(hi,t)
            if lo>hi:return None
    return [[a[0]+lo*dx,a[1]+lo*dy],[a[0]+hi*dx,a[1]+hi*dy]]

def clip_line(points):
    out=[]
    for a,b in zip(points,points[1:]):
        piece=line_clip(a,b)
        if not piece:continue
        if out and distance(out[-1][-1],piece[0])<1e-10:out[-1].append(piece[1])
        else:out.append(piece)
    return out

def distance(a,b):return math.hypot(a[0]-b[0],a[1]-b[1])

def merge_lines(lines):
    lines=[list(p) for p in lines]
    changed=True
    while changed:
        changed=False
        for i in range(len(lines)):
            for j in range(i+1,len(lines)):
                a,b=lines[i],lines[j]
                if distance(a[-1],b[0])<1e-7:c=a+b[1:]
                elif distance(a[-1],b[-1])<1e-7:c=a+list(reversed(b))[1:]
                elif distance(a[0],b[-1])<1e-7:c=b+a[1:]
                elif distance(a[0],b[0])<1e-7:c=list(reversed(b))+a[1:]
                else:continue
                lines[i]=c;del lines[j];changed=True;break
            if changed:break
    return lines

def point_along(points,t):
    pp=[xy(p) for p in points];lengths=[distance(a,b) for a,b in zip(pp,pp[1:])];target=sum(lengths)*t
    for i,length in enumerate(lengths):
        if target<=length or i==len(lengths)-1:
            f=target/length if length else 0
            p=[pp[i][j]+f*(pp[i+1][j]-pp[i][j]) for j in (0,1)]
            geo=[points[i][j]+f*(points[i+1][j]-points[i][j]) for j in (0,1)]
            angle=math.degrees(math.atan2(pp[i+1][1]-pp[i][1],pp[i+1][0]-pp[i][0]))
            if angle>90:angle-=180
            if angle<-90:angle+=180
            return [round(v,2) for v in p],round(angle,2),geo
        target-=length

def path(points,closed=False):
    ps=[xy(p) for p in points]
    return 'M'+'L'.join(f'{x:g},{y:g}' for x,y in ps)+('Z' if closed else '')

raw=json.loads((SOURCE/'parcels-general-esri.json').read_text())
parcels=[]
for f in raw['features']:
    rings=f['geometry']['rings']
    if not intersect_box(sum(rings,[])):continue
    if len(rings)!=1:raise ValueError('Unexpected multipart parcel: preserve ring topology before exporting')
    parcels.append({'type':'Feature','id':f['attributes']['OBJECTID'],'properties':{'source_object_id':f['attributes']['OBJECTID']},'geometry':{'type':'Polygon','coordinates':rings}})
assert len(parcels)<=150, len(parcels)
roads_raw=json.loads((SOURCE/'streets-context.geojson').read_text())
roads=[];named=collections.defaultdict(list)
for f in roads_raw['features']:
    g=f['geometry'];lines=[g['coordinates']] if g['type']=='LineString' else g['coordinates']
    clips=sum((clip_line(points) for points in lines),[])
    if not clips:continue
    props=f['properties'];roads.append({'type':'Feature','id':props['OBJECTID'],'properties':{k:props.get(k) for k in ('OBJECTID','FullName','Source','SourceID','UpdateDate')},'geometry':g})
    if props.get('FullName'):named[props['FullName']]+=clips
named={name:merge_lines(lines) for name,lines in named.items()}
labels=[];longest={}
for name in ('Fiske St','Galloway St','Hartzell St','Albright St','Bestor Blvd'):
    if name not in named:continue
    line=max(named[name],key=lambda p:sum(distance(xy(a),xy(b)) for a,b in zip(p,p[1:])))
    longest[name]=line
    fraction={'Fiske St':.43,'Galloway St':.52,'Hartzell St':.52,'Albright St':.66,'Bestor Blvd':.53}.get(name,.5)
    pos,angle,geo=point_along(line,fraction)
    labels.append({'text':name,'position_svg':pos,'rotation_degrees':angle,'anchor_wgs84':geo,'verification':'FullName attribute in County CAMS source geometry'})

(OUTPUT/'parcels.geojson').write_text(json.dumps({'type':'FeatureCollection','display_extent_wgs84':BOUNDS,'features':parcels},separators=(',',':'))+'\n')
(OUTPUT/'streets.geojson').write_text(json.dumps({'type':'FeatureCollection','display_extent_wgs84':BOUNDS,'features':roads},separators=(',',':'))+'\n')
area_description = 'around Galloway and Hartzell Streets at Bestor Boulevard' if CLOSE else 'around Fiske, Galloway and Hartzell Streets, between Albright Street and Bestor Boulevard'
svg=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1100 720" role="img" aria-labelledby="map-title map-description">',
'<title id="map-title">Alphabet Streets, Pacific Palisades</title>',
f'<desc id="map-description">Actual Los Angeles County parcel boundaries and named street centerlines {area_description}. Neutral geometry, with no property conditions or rebuilding claims. Right margin reserved for separate illustrations.</desc>',
'<metadata>Sources: Los Angeles County Office of the Assessor; Countywide Address Management System (CAMS). Retrieved 2026-09-27. WGS84 geographic coordinates projected to Web Mercator for this plan. Provider terms: https://egis-lacounty.hub.arcgis.com/pages/terms-of-use . See provenance.json.</metadata>',
f'<defs><clipPath id="map-extent-clip"><rect x="{OX:.2f}" y="{OY:.2f}" width="{DRAW_W:.2f}" height="{DRAW_H:.2f}"/></clipPath></defs>',
'<g id="paper"><rect width="1100" height="720" fill="#fff"/></g>',
'<g id="map-heading" fill="#1557ff" font-family="Arial,sans-serif"><text x="44" y="40" font-size="11" letter-spacing="2">PACIFIC PALISADES</text><text x="44" y="64" font-size="19" letter-spacing="-.3">Alphabet Streets / a closer look</text></g>',
f'<g id="actual-parcels" clip-path="url(#map-extent-clip)" fill="none" stroke="{BLUE}" stroke-width="1.15" stroke-linejoin="round" opacity=".65">']
for f in parcels:svg.append(f'<path id="parcel-{f["id"]}" data-source-object-id="{f["id"]}" d="{path(f["geometry"]["coordinates"][0],True)}"/>')
svg+=['</g>',f'<g id="actual-street-centerlines" clip-path="url(#map-extent-clip)" fill="none" stroke="{BLUE}" stroke-width=".7" stroke-dasharray="3 5" opacity=".28">']
for f in roads:
    lines=[f['geometry']['coordinates']] if f['geometry']['type']=='LineString' else f['geometry']['coordinates']
    svg.append(f'<path id="street-{f["id"]}" data-street-name="{html.escape(f["properties"].get("FullName") or "",quote=True)}" d="'+''.join(path(p) for p in lines)+'"/>')
svg+=['</g>','<g id="verified-street-labels" fill="#1557ff" font-family="Arial,sans-serif" font-size="10" letter-spacing="1.3" text-anchor="middle" dominant-baseline="middle" paint-order="stroke" stroke="white" stroke-width="5" stroke-linejoin="round">']
for l in labels:
    x,y=l['position_svg'];svg.append(f'<text x="{x}" y="{y}" transform="rotate({l["rotation_degrees"]} {x} {y})">{html.escape(l["text"].upper())}</text>')
svg+=['</g>',
'<g id="orientation" fill="#1557ff" stroke="#1557ff"><path d="M766 49V24m0 0-4 9m4-9 4 9" fill="none" stroke-width="1"/><text x="766" y="17" font-family="Arial,sans-serif" text-anchor="middle" font-size="8" stroke="none">N</text></g>',
'<g id="source-caption" font-family="Arial,sans-serif" fill="#5e76a2"><text x="44" y="677" font-size="9">Parcel boundaries: LA County Assessor · street names and centerlines: LA County CAMS</text><text x="44" y="694" font-size="8">Geographic context only. No addresses, building designs, or property conditions are shown.</text></g>',
'<g id="illustrative-margin" data-purpose="Reserved blank margin. Put explicitly illustrative construction detail here; do not merge it with actual parcel geometry."/>',
'<g id="character-layer" data-purpose="Reserved for decorative pelican animation. Keep source geometry stationary."/>','</svg>']
(OUTPUT/'alphabet-streets.svg').write_text('\n'.join(svg)+'\n')
# A geometry-only option retains the exact same scene coordinates and group IDs.
linework=[s for s in svg]
for group in ('paper','map-heading','orientation','source-caption'):
    import re
    joined='\n'.join(linework)
    joined=re.sub(r'<g id="'+group+r'".*?</g>','',joined,flags=re.S)
    linework=[joined]
(OUTPUT/'alphabet-streets-linework.svg').write_text('\n'.join(linework)+'\n')

stops=[]
for key,name,t in [('pause-source','Galloway St' if CLOSE else 'Fiske St',.76),('pause-notebook','Hartzell St',.75)]:
    pos,angle,geo=point_along(longest[name],t)
    stops.append({'id':key,'foot_position_svg':pos,'coordinate_wgs84':geo,'aligned_street':name,'meaning':'Decorative animation stop; not a route or observation of a real person.'})
geometry={'viewBox':VIEWBOX,'extent_wgs84':BOUNDS,'projection':'EPSG:3857 / Web Mercator','plot_rect_svg':{'x':round(OX,2),'y':round(OY,2),'width':round(DRAW_W,2),'height':round(DRAW_H,2)},'transform':{'mercator_origin_west':SW[0],'mercator_origin_north':NE[1],'scale_svg_units_per_projected_metre':SCALE},'parcel_count':len(parcels),'street_feature_count':len(roads),'labels':labels,'bird_stops':stops,'blank_margin_svg':{'x':825,'y':100,'width':240,'height':520},'suggested_illustrative_detail_svg':{'x':830,'y':390,'width':230,'height':205},'parcel_paths':[{'source_object_id':f['id'],'d':path(f['geometry']['coordinates'][0],True)} for f in parcels]}
(OUTPUT/'geometry.json').write_text(json.dumps(geometry,indent=2)+'\n')
provenance={'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'geography':'Alphabet Streets, Pacific Palisades, Los Angeles, California','extent_wgs84':BOUNDS,'viewBox':VIEWBOX,'parcel_count':len(parcels),'street_feature_count':len(roads),'coordinate_retention':'Full source WGS84 rings/lines retained in GeoJSON and raw responses. SVG coordinates rounded to 0.01 units; no vertex simplification. Rendering clipped to extent.','selection':'All geometry intersecting the chosen geographic window from the general County parcel service. No damage or recovery filter.','parcel_source':'https://cache.gis.lacounty.gov/cache/rest/services/LACounty_Cache/LACounty_Parcel/FeatureServer/0','parcel_catalog':'https://www.arcgis.com/home/item.html?id=5b277305f006459586a70165065d0fd6','street_source':'https://services.arcgis.com/RmCCgQtiZLDCtblq/arcgis/rest/services/eGIS_Addressing_ROAD_LINES/FeatureServer/0','street_catalog':'https://www.arcgis.com/home/item.html?id=0a72e51eab7949678aff0670bf5d108b','attribution':'Los Angeles County Office of the Assessor; Los Angeles County Countywide Address Management System (CAMS). Accessed September 27, 2026.','terms_url':'https://egis-lacounty.hub.arcgis.com/pages/terms-of-use','terms_review':'Provider terms read in browser on 2026-09-27. License allows copying, publication, distribution, transmission, adaptation, and commercial/personal use subject to County terms. Does not grant ownership or imply County endorsement. County provides data as-is without completeness or accuracy warranties. This is not a public-domain or CC0 claim.','street_item_license_field':'None; County-wide terms apply to County published mapping data.','confidence':{'geometric_provenance':'Direct official County sources, retained response hashes.','street_names':'Source FullName attributes, with topology from the same source.','engineering_use':'Provider identifies parcel data as informational, potentially unsuitable for legal, engineering, or surveying uses.','current_conditions':'No inference; no building footprints, construction activity, damage, or occupancy is encoded.'},'excluded_fields':'No owner, address, APN, value, permit, damage, recovery or construction-status attributes are exported. Source OBJECTID is kept for lineage.','coastline':'Not included: this is an inland close-up. Adding a shoreline within this extent would misrepresent geography.','illustration_boundary':'Character and construction-detail inset are separate reserved groups; they must be labeled illustrative and cannot alter actual parcel geometry.','source_files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(SOURCE.iterdir()) if p.is_file()}}
(OUTPUT/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
print(json.dumps({k:geometry[k] for k in ('extent_wgs84','plot_rect_svg','parcel_count','street_feature_count','bird_stops','blank_margin_svg')},indent=2))
