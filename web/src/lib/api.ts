export type Evidence = {source_id:string;url:string;observed_at?:string;captured_at?:string;sha256?:string};
export type Summary = {apn:string;address:string;stage:string;damage:string;cohorts:string[]};
export type Task = {task_id:string;apn:string;kind:string;reason:string;next_sources:string[];priority:number;address?:string};
export type Property = Summary & {
 parcel:Record<string,unknown>;geometry:{type:string;coordinates:unknown}|null; cleanup:Record<string,unknown>|null;
 assessor:null|{detail:Record<string,unknown>;assessments:Record<string,unknown>[];transfers:Record<string,unknown>[];profile:Record<string,unknown>};
 permit_records:Record<string,unknown>[];inspection_requests:Record<string,unknown>[];permits:{permit:string;details:Record<string,string>;sections:{heading:string;rows:string[][];tag:string}[];evidence:Evidence}[];
 visuals:{kind:string;captured_at:string;points:number;measurements:{ground_support_fraction:number;quality:string;height_quantiles_m:Record<string,number>};preview:string;asset:string;limitation:string;evidence:Evidence}[];
 utilities:{kind:string;radius_m:number;features:{attributes:Record<string,unknown>}[];limitation:string;evidence:Evidence}[];
 evidence:Evidence[];listings:{source:string;source_url:string;asking_price:number;status:string;observed_at:string;limitation:string;events:{date:string;kind:string;asking_price?:number}[]}[];market_events:{date:string|null;raw_date:string;price:number|null;screening:string;reasons:string[];description:string}[];
 market_support:{status:string;reason:string;requirements:string[];screened_candidates:number};
 neighborhood:{measures?:Record<string,{parcel_count:number;destroyed_count:number;destruction_share:number|null;construction_evidence_count:number;unknown_damage_count:number}>;limitation?:string};tasks:Task[];
};
export type Release = {release_id:string;counts:Record<string,number>;coverage:{cohort:string;limitation:string};sources:(Evidence&{count:number;shape:string;limitation:string})[];unmatched_evidence:unknown[];local_workspace:boolean;permit_timing?:{issued_with_valid_dates:number;not_yet_issued:number;median_observed_days_to_issue:number|null;interpretation:string}};
/** Ordered like the recovery ladder (openpali.domain.lifecycles.RECOVERY_STAGE); a pipeline test guards the order. */
export const stages:Record<string,{label:string;color:string}>={unknown:{label:'No recovery milestone established',color:'#a0a59a'},cleanup:{label:'Cleanup reported complete',color:'#b6aa79'},application:{label:'Rebuild application',color:'#dfb668'},design:{label:'Plans approved',color:'#8d9db1'},permit:{label:'Permit issued',color:'#5a8fac'},construction:{label:'Construction reported',color:'#448577'},construction_complete:{label:'Construction reported complete',color:'#224b3d'},occupancy:{label:'Occupancy certificate recorded',color:'#173f34'}};
export function apiPath(release:string,tail:string){return `/v1/evidence/releases/${encodeURIComponent(release)}/${tail}`;}
/** Server-declared task lifecycle (GET /v1/evidence/lifecycles). */
export type TaskStatus='open'|'queued'|'in_progress'|'needs_review';
export type TaskHistory={items:{payload:{status:TaskStatus}}[];status:TaskStatus;allowed_next:TaskStatus[];writable:boolean};
/** One async resource, one state: no "loading AND error" or "data from the previous parcel". */
export type Remote<T>={status:'loading'}|{status:'ready';data:T}|{status:'failed';error:string};
export class ApiError extends Error{constructor(message:string,readonly status:number,readonly body:Record<string,unknown>){super(message);this.name='ApiError';}}
async function fail(r:Response):Promise<never>{const b=await r.json().catch(()=>({}));const text=(v:unknown)=>typeof v==='string'?v:'';throw new ApiError([text(b.title),text(b.detail)].filter(Boolean).join(': ')||`Request failed (${r.status})`,r.status,b);}
export const errorMessage=(e:unknown)=>e instanceof Error?e.message:String(e);
export const isAbort=(e:unknown)=>e instanceof Error&&e.name==='AbortError';
export async function get<T>(path:string,signal?:AbortSignal):Promise<T>{const r=await fetch(path,{signal});if(!r.ok)return fail(r);return r.json();}
export async function post<T>(path:string,value:unknown):Promise<T>{const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-OpenPali-Workspace':'local-draft'},body:JSON.stringify(value)});if(!r.ok)return fail(r);return r.json();}
export const money=(value:unknown)=>typeof value==='number'?new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:0}).format(value):'Not recorded';
export const display=(value:unknown)=>value===null||value===undefined||value===''?'Not recorded':typeof value==='object'?JSON.stringify(value):String(value);
