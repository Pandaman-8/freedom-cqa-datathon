import test from 'node:test';
import assert from 'node:assert/strict';
import {answerText, assessmentChanged, aiStatusText} from '../../main/resources/static/js/presentation.js';
import {parse, clone} from '../../main/resources/static/js/json.js';
test('same score must not hide changed explanation or evidence',()=>{
  const score=parse('{"overall_score":0.123456789012345678901}');
  const answers=[{criterion_id:'C01',answer:'no',value:null,explanation:'reason',evidence:[{message_id:'m0001',quote:'exact'}]}];
  const e={original_score:score,final_score:clone(score),original_answers:answers,final_answers:clone(answers)};
  assert.equal(assessmentChanged(e),false);
  e.final_answers[0].explanation='Reviewer reason';assert.equal(assessmentChanged(e),true);
  e.final_answers=clone(answers);e.final_answers[0].evidence[0].quote='changed';assert.equal(assessmentChanged(e),true);
});
test('Russian labels preserve no, NA, zero and exact decimal distinctions',()=>{
  assert.equal(answerText({answer:'no',value:null}),'Нет');
  assert.equal(answerText({answer:'na',value:null}),'N/A — не применимо');
  assert.equal(answerText(parse('{"answer":"scale","value":0}')),'0');
  assert.equal(answerText(parse('{"answer":"scale","value":0.1234567890123456789}')),'0.1234567890123456789');
});
test('Java liveness is never described as model readiness',()=>{
  assert.match(aiStatusText({ml_configured:false}),/не настроен/);
  assert.match(aiStatusText({ml_configured:true,ml_reachable:false}),/Нет связи/);
  assert.match(aiStatusText({ml_configured:true,ml_reachable:true,ml_ready:false}),/не готов/);
  assert.match(aiStatusText({ml_configured:true,ml_reachable:true,ml_ready:true}),/данным проверяется отдельно/);
});
