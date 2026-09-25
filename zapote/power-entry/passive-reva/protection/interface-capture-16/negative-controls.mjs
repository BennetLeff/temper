// Transport-only harness: mutate isolated drawings, ask KiCad to export,
// then invoke the Rust auditor. No circuit calculations live here.
import fs from 'node:fs';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
const auditor=process.argv[2];
if(!auditor) throw Error('usage: node negative-controls.mjs /absolute/path/to/auditor');
const cases=[
  {name:'clamp-sense-shorted-to-input',sheet:'clamp',from:'(label "SNS"',to:'(label "AUX_RAW"'},
  {name:'hot-run-data-fixed-high',sheet:'reset',from:'(label "ARM_AUTHORIZED"',to:'(label "HOT_LOGIC5"'}
];
const results=[];
for(const c of cases){
 const dir=path.resolve('negative-controls',c.name);fs.mkdirSync(dir,{recursive:true});
 for(const file of ['clamp.net','reset.net','clamp-expected.tsv','reset-expected.tsv'])fs.copyFileSync(file,path.join(dir,file));
 const good=fs.readFileSync(c.sheet+'.kicad_sch','utf8');
 if(!good.includes(c.from))throw Error('mutation target missing');
 // Only first occurrence: on reset this is the D1 input, not Q2 output.
 fs.writeFileSync(path.join(dir,c.sheet+'.kicad_sch'),good.replace(c.from,c.to));
 const exp=spawnSync('kicad-cli',['sch','export','netlist','--format','kicadsexpr','-o',path.join(dir,c.sheet+'.net'),path.join(dir,c.sheet+'.kicad_sch')],{encoding:'utf8'});
 fs.writeFileSync(path.join(dir,'export.log'),exp.stdout+exp.stderr);
 if(exp.status!==0)throw Error('KiCad failed before audit');
 const check=spawnSync(auditor,[dir],{encoding:'utf8'});
 fs.writeFileSync(path.join(dir,'rejection.log'),check.stdout+check.stderr);
 if(check.status!==1||!check.stderr.includes('AUDIT FAILED:'))throw Error('mutation was not rejected by auditor');
 results.push({case:c.name,export_exit:exp.status,audit_exit:check.status,rejection:check.stderr.trim()});
}
fs.writeFileSync('negative-controls.json',JSON.stringify(results,null,2)+'\n');
console.log(JSON.stringify(results,null,2));
