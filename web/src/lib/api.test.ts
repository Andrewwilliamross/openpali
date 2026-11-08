import {describe,it,expect} from 'vitest';
import {apiPath,money,stages} from './api';
describe('public presentation boundaries',()=>{
 it('never labels missing price as zero',()=>{expect(money(null)).toBe('Not recorded');expect(money(2095000)).toBe('$2,095,000')});
 it('distinguishes reported construction completion from occupancy',()=>{expect(stages.construction_complete.label).not.toMatch(/occupancy/i);expect(stages.unknown.label).not.toMatch(/uncleared|vacant|undamaged/i)});
 it('pins requests to one release',()=>{expect(apiPath('evidence-a','properties/123')).toBe('/v1/evidence/releases/evidence-a/properties/123')});
});
describe('request failures',()=>{
 it('surfaces problem-details titles and keeps the body for lifecycle conflicts',async()=>{
  const body={type:'https://openpali.org/problems/illegal-transition',title:"acquisition_task: cannot move from 'queued' to 'needs_review'",status:409,current:'queued',allowed_next:['in_progress']};
  const original=globalThis.fetch;globalThis.fetch=(async()=>new Response(JSON.stringify(body),{status:409}))as typeof fetch;
  try{const {post,ApiError}=await import('./api');const error=await post('/x',{}).catch((e:unknown)=>e) as InstanceType<typeof ApiError>;
   expect(error).toBeInstanceOf(ApiError);expect(error.message).toBe(body.title);expect(error.body.allowed_next).toEqual(['in_progress']);}
  finally{globalThis.fetch=original;}
 });
});
