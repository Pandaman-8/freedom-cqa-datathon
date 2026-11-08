import {request, pathId} from './api.js';
import {decimal, integer} from './json.js';

export const BATCH_KEY='cqa:batch:v1', BATCH_LOCK='cqa:batch-runner';
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const states=new Set(['sending','pending','unknown','unresolved','not_found','succeeded','failed','conflict']);
const terminal=new Set(['succeeded','failed','conflict','blocked']);
const preflight=new Set(['INVALID_INPUT','INPUT_TOO_LARGE','UNSUPPORTED_CONTRACT','NOT_FOUND','VERSION_CONFLICT','PAYLOAD_TOO_LARGE','EVALUATOR_UNCONFIGURED','PRIVACY_POLICY_UNCONFIGURED']);
const codes=new Set([...preflight,'REQUEST_ID_CONFLICT','EVALUATOR_INVALID_OUTPUT','EVALUATOR_PROVIDER_ERROR','EVALUATOR_TIMEOUT','EVALUATOR_BUSY','EVALUATOR_AUTH','EVALUATOR_RATE_LIMITED']);
const admissionCodes=new Set(['EXTERNAL_INFERENCE_DISABLED','JAVA_POLICY_MODE_INVALID','JAVA_SELECTION_DENIED','APPROVAL_INVALID','APPROVAL_EXPIRED','APPROVAL_CHANGED','DATASET_HASH_MISMATCH','CHECKLIST_OUTSIDE_SCOPE','RUBRIC_CONFIRMATION_REQUIRED','PYTHON_ADMISSION_UNSUPPORTED','PYTHON_ADMISSION_DENIED','PYTHON_POLICY_MISMATCH','PYTHON_GRANT_MISMATCH','PYTHON_DESTINATION_MISMATCH']);
const safeCode=value=>codes.has(value)?value:null;
const safeAdmissionCode=value=>codes.has(value)||admissionCodes.has(value)?value:'PRIVACY_POLICY_UNCONFIGURED';
const text=value=>typeof value==='string'&&value.length>0;
export const lastAttempt=item=>item.attempts.at(-1);
export const itemState=item=>lastAttempt(item)&&!terminal.has(lastAttempt(item).state)?lastAttempt(item).state:
  item.blocked_code?'blocked':lastAttempt(item)?.state||'queued';
const uncertain=state=>!terminal.has(state)&&state!=='queued';

export async function batchLock(action) {
  if(!globalThis.navigator?.locks?.request)throw new Error('Для batch нужен браузер с Web Locks на localhost/HTTPS. Отправка заблокирована.');
  return navigator.locks.request(BATCH_LOCK,{ifAvailable:true},lock=>{
    if(!lock)throw new Error('Batch уже выполняется в другой вкладке. Повторите чтение после его остановки.');
    return action();
  });
}

// Browser-local manifest only. Never store transcripts, rubric, answers, raw errors or credentials.
export function readManifest(storage) {
  const raw=storage.getItem(BATCH_KEY);if(raw===null)return null;
  try {
    if(raw.length>2*1024*1024)throw new Error();
    const m=JSON.parse(raw);
    if(m.format!==1||!uuid.test(m.id)||!text(m.group)||!text(m.checklist_key)||typeof m.checklist_version!=='string'||
       integer(m.checklist_version)!==m.checklist_version||!Array.isArray(m.items)||!m.items.length||typeof m.paused!=='boolean')throw new Error();
    const ids=new Set(),requests=new Set();
    for(const item of m.items){
      if(!text(item.conversation_id)||ids.has(item.conversation_id)||!Array.isArray(item.attempts))throw new Error();
      if(item.blocked_code!==undefined&&item.blocked_code!==null&&safeAdmissionCode(item.blocked_code)!==item.blocked_code)throw new Error();
      ids.add(item.conversation_id);
      for(const a of item.attempts){
        if(!uuid.test(a.request_id)||requests.has(a.request_id)||!states.has(a.state)||typeof a.rejected!=='boolean'||
           !(a.code===null||codes.has(a.code))||!(a.evaluation_id===null||uuid.test(a.evaluation_id))||
           (a.state==='succeeded'&&!a.evaluation_id))throw new Error();
        requests.add(a.request_id);
      }
    }
    return m;
  }catch{throw new Error('Сохранённый batch повреждён или несовместим. Отправка заблокирована; сохраните UUID и проверьте историю в Java.');}
}

export class BatchRunner {
  constructor({storage,api=request,lock=batchLock,newId=()=>crypto.randomUUID(),changed=()=>{},busy=()=>{},rubricConsent=()=>null}) {
    Object.assign(this,{storage,api,lock,newId,changed,busy,rubricConsent});this.manifest=null;this.running=false;this.stopRequested=false;
  }
  load(){this.manifest=readManifest(this.storage);this.changed();return this.manifest;}
  save(){this.storage.setItem(BATCH_KEY,JSON.stringify(this.manifest));this.changed();}
  async exclusive(action){
    if(this.running)return;
    // Set before awaiting a lock, so double clicks cannot queue a second action.
    this.running=true;this.busy(true);this.changed();
    try{return await this.lock(async()=>{this.load();return action();});}
    finally{this.running=false;this.busy(false);this.changed();}
  }
  async create(group,checklist){
    return this.exclusive(async()=>{
      if(this.manifest)throw new Error('Сначала завершите и удалите локальный manifest предыдущего batch.');
      if(!text(group)||!checklist)throw new Error('Выберите группу и конкретную версию чек-листа.');
      const version=integer(checklist.version),key=checklist.key;
      // Fresh snapshot of membership, not a live filter used between items.
      const [rows,pinned]=await Promise.all([this.api('/api/conversations'),this.api('/api/checklists/'+pathId(key)+'?version='+version)]);
      if(pinned.key!==key||integer(pinned.version)!==version)throw new Error('Не удалось подтвердить выбранную версию.');
      const ids=rows.filter(c=>c.dataset_group_id===group).map(c=>c.id);
      if(!ids.length||new Set(ids).size!==ids.length)throw new Error('В выбранной группе нет корректного списка диалогов.');
      this.manifest={format:1,id:this.newId(),group,checklist_key:key,checklist_version:version,paused:true,
        items:ids.map(conversation_id=>({conversation_id,attempts:[]}))};
      this.save(); // If storage fails, no inference can start.
    });
  }
  pause(){if(!this.running||!this.manifest)return;this.stopRequested=true;this.manifest.paused=true;this.save();}
  async refresh(){return this.exclusive(async()=>{if(this.manifest){await this.reconcile();this.manifest.paused=true;this.save();}});}
  async reconcile(){
    for(const item of this.manifest.items)if(lastAttempt(item)&&(!item.blocked_code||!terminal.has(lastAttempt(item).state)))await this.check(item,lastAttempt(item));
  }
  async check(item,attempt){
    if(attempt.state==='conflict')return; // Never associate someone else's ledger with this item.
    try {
      const status=await this.api('/api/evaluation-requests/'+pathId(attempt.request_id));
      if(status.request_id!==attempt.request_id||!['pending','succeeded','failed','unknown'].includes(status.status))throw new Error();
      if(status.status==='succeeded') {
        if(!uuid.test(status.evaluation_id))throw new Error();
        const result=await this.api('/api/evaluations/'+pathId(status.evaluation_id));
        if(result.id!==status.evaluation_id||result.origin!=='model'||result.conversation_id!==item.conversation_id||
           result.checklist_key!==this.manifest.checklist_key||integer(result.checklist_version)!==this.manifest.checklist_version) {
          attempt.state='conflict';attempt.code='REQUEST_ID_CONFLICT';attempt.evaluation_id=null;this.save();return;
        }
        attempt.evaluation_id=result.id;
      }else attempt.evaluation_id=null;
      attempt.state=status.status;attempt.code=safeCode(status.error?.code);attempt.rejected=false;
    }catch(error){
      attempt.evaluation_id=null;
      // A positive, known preflight rejection followed by404 is a failed attempt, not queued work.
      attempt.state=error.status===404?(attempt.rejected?'failed':'not_found'):'unresolved';
    }
    this.save();
  }
  async send(item){
    // A refusal is not an inference attempt: persist its safe reason, never invent a UUID.
    let readiness;
    try {
      readiness=await this.api('/api/ai/status?conversation_id='+pathId(item.conversation_id)+
        '&checklist_key='+pathId(this.manifest.checklist_key)+'&checklist_version='+pathId(this.manifest.checklist_version));
      if(readiness.ready!==true){item.blocked_code=safeAdmissionCode(readiness.reason);this.save();return;}
      if(readiness.rubric_confirmation_required===true&&
         (!readiness.confirmation_scope||this.rubricConsent()!==readiness.confirmation_scope)){
        item.blocked_code='RUBRIC_CONFIRMATION_REQUIRED';this.save();return;
      }
    }catch(error){item.blocked_code=safeAdmissionCode(error.code||'EVALUATOR_BUSY');this.save();return;}
    delete item.blocked_code;
    const id=this.newId();
    if(!uuid.test(id)||this.manifest.items.some(i=>i.attempts.some(a=>a.request_id===id)))throw new Error('Не удалось создать уникальный UUID. Отправка остановлена.');
    const attempt={request_id:id,state:'sending',evaluation_id:null,code:null,rejected:false};
    item.attempts.push(attempt);this.save(); // Durable intent MUST precede POST, including an explicit retry.
    try {
      await this.api('/api/evaluations/auto',{method:'POST',timeout:75000,rubricConfirmed:readiness.rubric_confirmation_required===true,body:{request_id:id,
        conversation_id:item.conversation_id,checklist_key:this.manifest.checklist_key,checklist_version:decimal(this.manifest.checklist_version)}});
    }catch(error){
      attempt.code=safeCode(error.code);
      if(error.status===409&&error.code==='REQUEST_ID_CONFLICT')attempt.state='conflict';
      else attempt.rejected=!error.unknown&&preflight.has(error.code)&&[404,409,413,422,501,503].includes(error.status);
    }
    // Even a lost response is reconciled with GET; a POST is never replayed.
    await this.check(item,attempt);
  }
  async resume(allowUnknown=false){
    return this.exclusive(async()=>{
      if(!this.manifest)return;
      this.stopRequested=false;await this.reconcile();
      const blockers=this.manifest.items.map(itemState).filter(uncertain);
      if(blockers.some(s=>!['unknown','not_found'].includes(s))||(blockers.length&&!allowUnknown))throw new Error('Есть pending/непроверенные/unknown попытки. Проверьте статусы; unknown/404 требуют явного согласия продолжить остальные.');
      this.manifest.paused=false;this.save();
      try {
        for(const item of this.manifest.items){
          if(this.stopRequested)break;
          if(item.attempts.length||item.blocked_code)continue; // Never repeat any attempted item implicitly.
          await this.send(item);
          if(uncertain(itemState(item)))break;
        }
      }finally{this.manifest.paused=true;this.save();}
    });
  }
  async retry(conversationId,acknowledged){
    if(!acknowledged)throw new Error('Новая попытка может повторно списать средства. Требуется явное согласие.');
    return this.exclusive(async()=>{
      if(!this.manifest)return;
      await this.reconcile();
      if(this.manifest.items.some(i=>['pending','sending','unresolved'].includes(itemState(i))))
        throw new Error('Сначала проверьте все незавершённые UUID. Отсутствие записи после потери связи не доказывает отмену inference.');
      const item=this.manifest.items.find(i=>i.conversation_id===conversationId);
      if(!item||!['failed','unknown','conflict','not_found','blocked'].includes(itemState(item)))throw new Error('Для этого диалога новая попытка недоступна.');
      await this.send(item);this.manifest.paused=true;this.save();
    });
  }
  async forget(acknowledged){
    if(!acknowledged)throw new Error('Подтвердите удаление только локального manifest. Результаты останутся в Java.');
    return this.exclusive(async()=>{
      if(!this.manifest)return;await this.reconcile();
      if(this.manifest.items.some(i=>!terminal.has(itemState(i))))throw new Error('Нельзя удалить batch с неотправленными или неопределёнными элементами.');
      this.storage.removeItem(BATCH_KEY);this.manifest=null;this.changed();
    });
  }
}
