"""Author the atlas's static SVG fallback from a small geometric coastal model.
All topography is imagined artwork. It is not derived from parcel or recovery data.
"""
from pathlib import Path
import math
from html import escape

W,H=3.55,5.05
ANGLE=math.radians(76-.58*71)
SHIFT=-(W+2*W*math.cos(ANGLE))/2

def shore(u):return .25+.28*math.sin(u*.65)+.18*math.sin(u*1.38+.8)
def elevation(u,z):
 d=shore(u)-z
 if d<0:return .038
 ridge=.77+.12*math.sin(u*.57)+.1*math.cos(u*1.5+z*.7)
 def g(x,c,w):return math.exp(-((x-c)/w)**2)
 canyon=.64*g(u,2.5+.35*(z+1),.34)+.58*g(u,6.15-.27*(z+1),.35)+.59*g(u,8.9+.38*math.sin(z),.3)
 within=u-math.floor(u/W)*W;edge=min(within,W-within);t=max(0,min(1,(edge-.025)/.235));seam=t*t*(3-2*t)
 return .041+(.089+(1-math.exp(-d*1.4))*ridge*(1-min(.83,canyon)))*seam
def unit(v):
 n=math.sqrt(sum(a*a for a in v));return [a/n for a in v]
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
forward=unit([-9.1,-12.3,-14.4]);right=unit(cross(forward,[0,1,0]));up=cross(right,forward)
def world(index,p):
 x,y,z=p
 if index==1:x,y=W+x*math.cos(ANGLE)-y*math.sin(ANGLE),x*math.sin(ANGLE)+y*math.cos(ANGLE)
 elif index==2:
  x,y=x*math.cos(-ANGLE)-y*math.sin(-ANGLE),x*math.sin(-ANGLE)+y*math.cos(-ANGLE)
  x+=W+W*math.cos(ANGLE);y+=W*math.sin(ANGLE)
 x+=SHIFT;y+=.17
 x,z=x*math.cos(-.14)+z*math.sin(-.14),-x*math.sin(-.14)+z*math.cos(-.14)
 return [x,y,z]
def project(p):
 point=[p[0],p[1]-.9,p[2]]
 return 600+dot(point,right)*84,305-dot(point,up)*84
faces=[];lines=[];labels=[]
def poly(index,points,color):
 pts=[world(index,p) for p in points]
 depth=sum(dot(p,forward) for p in pts)/len(pts)
 points=' '.join(f'{a:.1f},{b:.1f}' for a,b in map(project,pts))
 faces.append((depth,f'<polygon points="{points}" fill="{color}" stroke="{color}" stroke-width=".35"/>'))
def line(index,points,color,width=.8,opacity=.7):
 pts=' '.join(f'{a:.1f},{b:.1f}' for a,b in (project(world(index,p)) for p in points))
 lines.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="{width}" opacity="{opacity}"/>')
for index in range(3):
 poly(index,[(0,0,-H/2),(W,0,-H/2),(W,0,H/2),(0,0,H/2)],'#fcfcf8')
 poly(index,[(0,0,H/2),(W,0,H/2),(W,-.06,H/2),(0,-.06,H/2)],'#dfe5d9')
 water=[(0,.04,1.52),(W,.04,1.52)]+[(W*i/28,.04,shore(index*W+W*i/28)) for i in range(28,-1,-1)]
 poly(index,water,['#1557ff','#1d53e9','#2b69ff'][index])
 nx,nz=23,26
 grid=[]
 for j in range(nz+1):
  row=[]
  for i in range(nx+1):
   x=W*i/nx;u=index*W+x;z=-1.78+(shore(u)+1.78)*j/nz;row.append((x,elevation(u,z),z))
  grid.append(row)
 for j in range(nz):
  for i in range(nx):
   for tri in [(grid[j][i],grid[j+1][i],grid[j][i+1]),(grid[j][i+1],grid[j+1][i],grid[j+1][i+1])]:
    a,b,c=[world(index,p) for p in tri]
    normal=unit(cross([b[k]-a[k] for k in range(3)],[c[k]-a[k] for k in range(3)]))
    brightness=.82+.18*max(0,dot(normal,unit([-5,12,7])))
    color='#'+''.join(f'{min(255,round(v*brightness)):02x}' for v in [249,250,241])
    poly(index,tri,color)
 for i in range(nx):
  a,b=grid[-1][i],grid[-1][i+1]
  poly(index,[a,(a[0],.04,a[2]),(b[0],.04,b[2]),b],'#d9e1d2')
 for t in []:
  points=[]
  for i in range(61):
   x=W*i/60;u=index*W+x;z=-1.78+(shore(u)+1.78)*t;points.append((x,elevation(u,z)+.025,z))
  line(index,points,'#aebfaa',.65,.52)
 for offset in [.18,.34,.56,.83]:
  points=[]
  for i in range(45):
   x=W*i/44;z=shore(index*W+x)+offset
   if z<1.48:points.append((x,.052,z))
  line(index,points,'#c4ddff',.9,.5)
 line(index,[(.03,.033,-H/2+.06),(.03,.033,H/2-.06)],'#aab8a4',.8,.75)
 # Affine projection keeps the printed label aligned to the paper surface.
 origin=project(world(index,(.21,.036,1.88)));ex=project(world(index,(1.21,.036,1.88)));ey=project(world(index,(.21,.036,2.88)))
 a,b=(ex[0]-origin[0])/100,(ex[1]-origin[1])/100;c,d=(ey[0]-origin[0])/100,(ey[1]-origin[1])/100
 labels.append(f'<g transform="matrix({a:.4f} {b:.4f} {c:.4f} {d:.4f} {origin[0]:.2f} {origin[1]:.2f})"><text fill="#1557ff" font-family="Arial,sans-serif" font-size="8" letter-spacing="1.1">0{index+1} / {("SOURCE","OBSERVATION","RELEASE")[index]}</text><text y="25" fill="#233d3d" font-family="Georgia,serif" font-size="23">{("Event date","Observed date","Published date")[index]}</text></g>')
faces.sort(key=lambda item:item[0],reverse=True)
svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 650" role="img" aria-labelledby="title"><title id="title">An imagined coastal landscape on a folded paper atlas</title><defs><filter id="shadow"><feGaussianBlur stdDeviation="17"/></filter></defs><ellipse cx="630" cy="444" rx="354" ry="45" fill="#657568" opacity=".12" filter="url(#shadow)"/>'
svg+=''.join(s for _,s in faces)+''.join(lines)+''.join(labels)+'</svg>'
Path(__file__).with_name('poster.svg').write_text(svg)
print('Wrote poster.svg:',len(svg),'bytes')
