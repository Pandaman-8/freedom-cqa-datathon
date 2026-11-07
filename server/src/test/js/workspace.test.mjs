import test from 'node:test';
import assert from 'node:assert/strict';
import {parse, stringify, decimal, integer, equalDecimal} from '../../main/resources/static/js/json.js';
import {Latest, Drafts} from '../../main/resources/static/js/state.js';
import {request, ApiError} from '../../main/resources/static/js/api.js';
import {safeAudio, exactEvidence} from '../../main/resources/static/js/ui.js';

test('Java integers/decimals survive parse/edit/send exactly, including nested arbitrary keys', () => {
  const text='{"version":9007199254740993,"weight":0.123456789012345678901,"levels":[0,1e-20],"__proto__":{"safe":true},"text":"Қазақша\\n\\\"x\\\""}';
  assert.equal(stringify(parse(text)),text);
  assert.equal(integer(parse(text).version),'9007199254740993');
  assert.equal({}.safe,undefined);
});
test('invalid JSON and silent numeric rounding are rejected', () => {
  for(const text of ['{"x":1,"x":2}','[1,]','{"x":}','01','NaN','1 2','{"x":"bad\n"}','{"x":1,}']) assert.throws(()=>parse(text));
  for(const value of ['1,2','','+1','01','Infinity']) assert.throws(()=>decimal(value));
  for(const value of ['0','1.1','-1','01']) assert.throws(()=>integer(value));
  assert.throws(()=>stringify(0.1));assert.throws(()=>stringify(Number.MAX_SAFE_INTEGER+1));
});
test('stale generation is invalid even when transport ignores abort', () => {
  const latest=new Latest(), first=latest.next(), second=latest.next();
  assert.equal(first.signal.aborted,true);assert.equal(first.current(),false);assert.equal(second.current(),true);
  latest.cancel();assert.equal(second.current(),false);
});
test('drafts stay separated by exact context and keep decimal values', () => {
  const drafts=new Drafts();const a=drafts.get('conversation A / v1',()=>({value:decimal('0.10000000000000001')}));
  drafts.touch('conversation A / v1');drafts.get('conversation B / v2',()=>({value:null}));
  assert.equal(drafts.count(),1);assert.equal(drafts.get('conversation A / v1',()=>null),a);
  assert.equal(String(a.value.value),'0.10000000000000001');drafts.clean('conversation A / v1');assert.equal(drafts.count(),0);
});
test('audio schemes/user-info rejected; evidence uses ID and exact Unicode/whitespace', () => {
  for(const url of ['javascript:alert(1)','data:audio/wav,x','file:///tmp/x','//host/x','https://name:secret@example.invalid/x']) assert.equal(safeAudio(url),null);
  assert.equal(safeAudio('https://example.invalid/synthetic.wav'),'https://example.invalid/synthetic.wav');
  const conversation={messages:[{id:'m0001',text:'e\u0301\n  Қ'}]};
  assert.equal(exactEvidence(conversation,[{message_id:'m0001',quote:'\n  Қ'}]),true);
  assert.equal(exactEvidence(conversation,[{message_id:'m0002',quote:'\n  Қ'}]),false);
  assert.equal(exactEvidence(conversation,[{message_id:'m0001',quote:'é'}]),false);
});
test('API preserves numeric lexemes and never exposes proxy bodies or replays mutations', async () => {
  const original=globalThis.fetch;let calls=0;
  try {
    globalThis.fetch=async(path,options)=>{calls++;assert.equal(path,'/api/checklists/test');assert.equal(options.body,'{"weight":0.1234567890123456789}');return new Response('{"version":9007199254740993}');};
    assert.equal(String((await request('/api/checklists/test',{method:'POST',body:{weight:decimal('0.1234567890123456789')}})).version),'9007199254740993');
    globalThis.fetch=async()=>{calls++;return new Response('SYNTHETIC_SECRET',{status:500});};
    await assert.rejects(request('/api/evaluations/manual',{method:'POST',body:{}}),e=>e instanceof ApiError&&!e.message.includes('SYNTHETIC_SECRET'));
    assert.equal(calls,2);
    globalThis.fetch=async()=>{calls++;throw new TypeError('SYNTHETIC_SECRET');};
    await assert.rejects(request('/api/evaluations/manual',{method:'POST',body:{}}),e=>e.unknown&&!e.message.includes('SYNTHETIC_SECRET'));
    assert.equal(calls,3);
  }finally{globalThis.fetch=original;}
});
test('bounded fetch abort reports unknown mutation, without a retry', async () => {
  const original=globalThis.fetch;let calls=0;
  try {
    globalThis.fetch=(_,options)=>new Promise((resolve,reject)=>{calls++;options.signal.addEventListener('abort',()=>reject(new Error('abort')));});
    await assert.rejects(request('/api/evaluations/manual',{method:'POST',body:{},timeout:5}),e=>e.unknown);
    assert.equal(calls,1);
  }finally{globalThis.fetch=original;}
});

test('discrete levels compare numerically without decimal rounding', () => {
  assert.equal(equalDecimal(decimal('7'),decimal('7.000')),true);
  assert.equal(equalDecimal(decimal('1e-30'),decimal('0.000000000000000000000000000001')),true);
  assert.equal(equalDecimal(decimal('0.10000000000000001'),decimal('0.1')),false);
  assert.equal(equalDecimal(decimal('-0'),decimal('0.00')),true);
});
