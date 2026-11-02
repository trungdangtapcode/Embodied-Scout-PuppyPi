import fs from 'node:fs/promises';
import path from 'node:path';
import {chromium,expect} from '@playwright/test';
const [sessionFile]=process.argv.slice(2);
const state=JSON.parse(await fs.readFile(sessionFile,'utf8'));
const token=await fs.readFile(state.token_file,'utf8');
const output=state.run;
const browser=await chromium.launch({headless:true});
const report={scope:'Chromium touch-phone emulation on host through actual public Cloudflare HTTPS; no real phone radio, ROS or physical robot',ai:false,errors:[]};
let context;
try {
 context=await browser.newContext({viewport:{width:844,height:390},isMobile:true,hasTouch:true});
 const page=await context.newPage();page.on('pageerror',e=>report.errors.push(e.message));
 await page.addInitScript(()=>{
  window.phonePaints=[];window.phoneInputs=[];
  addEventListener('puppypi-camera-painted',e=>window.phonePaints.push(e.detail));
  document.addEventListener('pointerdown',e=>{
   const label=e.target.closest('button')?.getAttribute('aria-label');
   if(['Turn left','Turn right'].includes(label))window.phoneInputs.push({label,at_ms:performance.timeOrigin+performance.now()});
  },true);
 });
 report.anonymous_status=(await page.request.get(state.public_url+'/api/state')).status();
 await page.goto(state.public_url,{timeout:45000});
 await page.getByLabel('Pairing code').fill(token);
 await page.getByRole('button',{name:'Open Field Console'}).click();
 await expect(page.getByAltText('Robot camera view')).toBeVisible({timeout:15000});
 await page.getByRole('button',{name:'Control',exact:true}).click();
 await page.getByRole('button',{name:'Arm controls',exact:true}).click();
 await expect(page.getByRole('button',{name:'Turn left',exact:true})).toBeEnabled({timeout:10000});
 const cdp=await context.newCDPSession(page);
 report.clock_reference=await (await page.request.get(state.public_url+'/api/timing')).json();
 report.measure_start_ms=await page.evaluate(()=>performance.timeOrigin+performance.now());
 for(let i=0;i<24;i++){
  const label=i%2?'Turn right':'Turn left';
  const button=page.getByRole('button',{name:label,exact:true});
  await expect(button).toBeEnabled();
  await button.scrollIntoViewIfNeeded();
  const box=await button.boundingBox();
  if(!box)throw Error('Control button not visible');
  try {
   await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:box.x+box.width/2,y:box.y+box.height/2}]});
   await page.waitForTimeout(300);
  } finally {await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]})}
  await page.waitForTimeout(1100);
 }
 const elapsed=await page.evaluate(start=>performance.timeOrigin+performance.now()-start,report.measure_start_ms);
 if(elapsed<60000)await page.waitForTimeout(60000-elapsed);
 report.measure_end_ms=await page.evaluate(()=>performance.timeOrigin+performance.now());
 await page.getByRole('button',{name:'STOP',exact:true}).click();
 await expect.poll(async()=>{report.final_state=await (await page.request.get(state.public_url+'/api/state')).json();return report.final_state.control.armed}).toBe(false);
 report.frames=await page.evaluate(()=>window.phonePaints);
 report.inputs=await page.evaluate(()=>window.phoneInputs);
 report.secure_cookie=(await context.cookies()).find(c=>c.name==='puppypi_session')?.secure;
 report.rtt_ms=[];
 for(let i=0;i<8;i++)report.rtt_ms.push(await page.evaluate(async()=>{const t=performance.now();await fetch('/api/timing',{cache:'no-store'}).then(r=>r.json());return performance.now()-t}));
 await page.screenshot({path:path.join(output,'phone-control-measurement.png')});
 report.completed=report.errors.length===0 && report.inputs.length===24 && report.anonymous_status===401;
 if(!report.completed)throw Error('Remote-only acceptance incomplete');
 console.log(JSON.stringify({completed:true,inputs:report.inputs.length,frames:report.frames.length}));
} catch(error){report.failure=String(error);throw error}
finally {
 if(context){await context.request.post(state.public_url+'/api/stop').catch(()=>{});await context.close()}
 await fs.writeFile(path.join(output,'browser-measurement.json'),JSON.stringify(report,null,2));await browser.close();
}
