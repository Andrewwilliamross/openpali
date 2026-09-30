import { useEffect, useRef, useState } from 'react';
import maplibregl, {type Map as MapInstance} from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { apiPath, stages } from './lib/api';
export function ParcelMap({release,selected,select,filter}:{release:string;selected:string|null;select:(apn:string)=>void;filter:string}){
 const host=useRef<HTMLDivElement>(null),map=useRef<MapInstance|null>(null),choose=useRef(select);choose.current=select;
 const [error,setError]=useState(''),[ready,setReady]=useState(false);
 useEffect(()=>{if(!host.current)return;
  let m:MapInstance;try{m=new maplibregl.Map({container:host.current,center:[-118.53,34.049],zoom:14,pitch:0,attributionControl:false,style:{version:8,sources:{basemap:{type:'raster',tiles:['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],tileSize:256,attribution:'© OpenStreetMap contributors'}},layers:[{id:'base',type:'raster',source:'basemap',paint:{'raster-opacity':0.42,'raster-saturation':-1}}]}});}catch(e){setError(String(e));return;}
  map.current=m;m.addControl(new maplibregl.NavigationControl({showCompass:false}),'bottom-right');m.addControl(new maplibregl.AttributionControl({compact:true}));
  m.on('load',()=>{m.addSource('parcels',{type:'geojson',data:apiPath(release,'artifacts/parcels.geojson'),promoteId:'apn'});
   const color=['match',['get','stage'],...Object.entries(stages).flatMap(([key,v])=>[key,v.color]),'#a0a59a'] as unknown as maplibregl.ExpressionSpecification;
   m.addLayer({id:'parcels',type:'fill',source:'parcels',paint:{'fill-color':color,'fill-opacity':0.62}});
   m.addLayer({id:'outlines',type:'line',source:'parcels',paint:{'line-color':'#565f56','line-width':0.5,'line-opacity':0.5}});
   m.addLayer({id:'selected',type:'line',source:'parcels',filter:['==','apn',''],paint:{'line-color':'#132e28','line-width':3}});
   m.on('click','parcels',e=>{const apn=e.features?.[0]?.properties?.apn;if(apn)choose.current(String(apn));});
   m.on('mouseenter','parcels',()=>{m.getCanvas().style.cursor='pointer'});m.on('mouseleave','parcels',()=>{m.getCanvas().style.cursor=''});setReady(true);
  });m.on('error',e=>{if(e.error.message.includes('parcels'))setError('Parcel map could not load. Search remains available.');});
  return()=>{setReady(false);m.remove();map.current=null;};
 },[release]);
 useEffect(()=>{const m=map.current;if(!ready||!m)return;m.setFilter('selected',['==','apn',selected||'']);m.setFilter('parcels',filter?['==','stage',filter]:null);},[selected,filter,ready]);
 return <div className="map-shell"><div ref={host} className="map" aria-label="Interactive parcel map"/>{error&&<div className="map-message" role="alert">{error}</div>}<div className="map-caption">PARCEL EVIDENCE <span>Agency milestones · capture dates on property records</span></div></div>;
}
