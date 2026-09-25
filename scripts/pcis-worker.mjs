/** Bounded deterministic worker. Usage: node scripts/pcis-worker.mjs jobs.json out-dir
 * jobs = [{permit:'25010-10000-03188', apn:'...'}]. A human-reviewed APN link
 * is retained as supplied, not inferred from the inspection page.
 * Install Playwright in the local environment before running; no remote browser
 * sessions, accounts, cookies or proxy bypasses are used.
 */
import { mkdir, readFile, writeFile, appendFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { createHash } from 'node:crypto';
import { extractPcis } from './pcis-extract.mjs';

export function permitUrl(permit) {
 if(!/^\d{5}-\d{5}-\d{5}$/.test(permit)) throw new Error('Invalid permit identifier');
 const [id1,id2,id3]=permit.split('-');
 return `https://www.ladbsservices2.lacity.org/OnlineServices/PermitReport/PcisPermitDetail?id1=${id1}&id2=${id2}&id3=${id3}`;
}
export async function runWorker(browser,jobs,out){
 if(!Array.isArray(jobs)||jobs.length>25||!jobs.length)throw new Error('Worker requires 1–25 explicit jobs');
 for(const job of jobs){permitUrl(job.permit);if(!/^\d{10}$/.test(job.apn))throw new Error('Invalid APN link');}
 await mkdir(resolve(out,'objects'),{recursive:true});
 const context=await browser.newContext();const page=await context.newPage();
 try{
  for(const job of jobs){
   const requested_at=new Date().toISOString();let status='failed',record;
   try{
    const response=await page.goto(permitUrl(job.permit),{waitUntil:'domcontentloaded',timeout:45000});
    if([401,403,429].includes(response?.status())){
     record={job,requested_at,status:'access_denied',http_status:response.status(),next_action:'review browser access; no automatic retries or bypass'};
     await appendFile(resolve(out,'runs.jsonl'),JSON.stringify(record)+'\n');break;
    }
    await page.locator('dt').first().waitFor({timeout:20000});
    const result=await extractPcis(page,job.permit);const body=JSON.stringify(result);
    const sha256=createHash('sha256').update(body).digest('hex');await writeFile(resolve(out,'objects',sha256),body);
    record={job,requested_at,status:'complete',sha256,observed_at:result.observed_at,link_status:'requires_verified_APN_link'};
   }catch(error){
    const html=await page.content();const sha256=createHash('sha256').update(html).digest('hex');
    await writeFile(resolve(out,'objects',sha256),html);
    record={job,requested_at,status,error:String(error),failure_html_sha256:sha256,next_action:'review retained page and update deterministic parser; agent fallback requires review'};
   }
   await appendFile(resolve(out,'runs.jsonl'),JSON.stringify(record)+'\n');
   await new Promise(r=>setTimeout(r,1500));
  }
 }finally{await context.close();}
}
if(process.argv[1]&&import.meta.url===new URL(`file://${resolve(process.argv[1])}`).href){
 const [jobsPath,out]=process.argv.slice(2);if(!jobsPath||!out)throw new Error('Provide jobs.json and output directory');
 const {chromium}=await import('playwright');const browser=await chromium.launch({headless:true});
 try{await runWorker(browser,JSON.parse(await readFile(jobsPath,'utf8')),out);}finally{await browser.close();}
}
