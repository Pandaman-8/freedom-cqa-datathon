import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const css=readFileSync(new URL('../../main/resources/static/styles.css',import.meta.url),'utf8');
const token=name=>css.match(new RegExp('--'+name+':\\s*(#[0-9a-fA-F]{6})'))[1];
function luminance(hex){return hex.slice(1).match(/../g).map(n=>parseInt(n,16)/255).map(n=>n<=.04045?n/12.92:((n+.055)/1.055)**2.4).reduce((sum,n,i)=>sum+n*[.2126,.7152,.0722][i],0);}
const contrast=(a,b)=>{const x=luminance(a),y=luminance(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);};
test('Freedom Lens normal text and primary action colours meet WCAG AA',()=>{
  for(const surface of ['surface','background','surface-accent']) for(const ink of ['text-primary','text-secondary','status-success'])
    assert.ok(contrast(token(ink),token(surface))>=4.5,ink+' on '+surface);
  for(const surface of ['brand-primary','brand-primary-hover']) assert.ok(contrast(token('brand-dark'),token(surface))>=4.5,'dark primary action on '+surface);
  assert.ok(contrast(token('status-error'),'#fff3f1')>=4.5,'error text');
  assert.ok(contrast('#7b8e81',token('surface'))>=3,'input boundary');
});
