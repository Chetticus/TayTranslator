// Lightweight interaction checks without a browser dependency; not visual QA.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

function setup(){
 const elements=new Map(),downloads=[];
 class Element{
  constructor(){this.children=[];this.value='';this.handlers={};this.textContent=''}
  set id(value){this._id=value;elements.set(value,this)}
  get id(){return this._id}
  append(...children){this.children.push(...children)}
  replaceChildren(...children){this.children=children}
  addEventListener(name,handler){this.handlers[name]=handler}
  click(){if(this.download)downloads.push(this.download);if(this.onclick)this.onclick()}
 }
 const doc={getElementById(id){if(!elements.has(id)){const el=new Element();el.id=id}return elements.get(id)},createElement(){return new Element()}};
 const score={output:'test translation',status:'ok',meaning_1_to_5:null,fluency_1_to_5:null,critical_error:null,notes:''};
 const rows=[1,2].map(n=>({case_hash:String(n),case:{id:String(n),text:'sentence '+n,direction:'vi2tay'},reviewer:'',dialect:'',reference_translation:'',A:{...score},B:{...score}}));
 rows[1].B={...score,output:null,status:'no_exact'};
 doc.getElementById('data').textContent=JSON.stringify(rows);
 let blob;
 const context=vm.createContext({document:doc,window:{addEventListener(){}},Blob,URL:{createObjectURL(value){blob=value;return 'blob:test'},revokeObjectURL(){}},setTimeout(fn){fn()},confirm(){return true}});
 const html=fs.readFileSync(path.join(__dirname,'../templates/benchmark_review.html'),'utf8');
 const code=html.match(/<script>\s*([\s\S]*?)<\/script>/)[1];
 vm.runInContext(code,context);
 return {get:id=>doc.getElementById(id),downloads,rows,blob:()=>blob};
}

test('navigation retains scores and disables unavailable output ratings',()=>{
 const ui=setup();assert.equal(ui.get('source').textContent,'sentence 1');
 const score=ui.get('A-meaning_1_to_5');score.value='5';score.handlers.change();
 ui.get('next').click();assert.equal(ui.get('B-meaning_1_to_5').disabled,true);
 ui.get('prev').click();assert.equal(ui.get('A-meaning_1_to_5').value,'5');
});

test('export requires identity, includes saved scores and supports resume',async()=>{
 const ui=setup();ui.get('download').click();assert.equal(ui.downloads.length,0);
 for(const [field,value] of [['reviewer','test-01'],['dialect','test dialect']]){ui.get(field).value=value;ui.get(field).handlers.input()}
 ui.get('A-meaning_1_to_5').value='4';ui.get('A-meaning_1_to_5').handlers.change();ui.get('download').click();
 assert.equal(ui.downloads[0],'tay-review-test-01.jsonl');
 const saved=await ui.blob().text();assert.equal(JSON.parse(saved.split('\n')[0]).A.meaning_1_to_5,4);
 const resumed=setup();await resumed.get('import').onchange({target:{files:[{size:saved.length,text:async()=>saved}],value:'file'}});
 assert.equal(resumed.get('reviewer').value,'test-01');assert.equal(resumed.get('A-meaning_1_to_5').value,'4');
});

test('import rejects altered outputs without changing the current case',async()=>{
 const ui=setup();ui.rows[0].A.output='tampered';const saved=ui.rows.map(JSON.stringify).join('\n');
 await ui.get('import').onchange({target:{files:[{size:saved.length,text:async()=>saved}],value:'file'}});
 assert.match(ui.get('message').textContent,/Không thể tải/);assert.equal(ui.get('source').textContent,'sentence 1');
});
