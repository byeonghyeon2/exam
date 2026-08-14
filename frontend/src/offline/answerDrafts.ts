export type DraftKind='study'|'mock-exam';
export type AnswerDraft={
  key:string;userId:number;kind:DraftKind;sessionId:string;questionId:number;
  selectedAnswers:string[];currentIndex:number;pending:boolean;updatedAt:string;
};

const DB_NAME='hapgyeokbiseo-offline';
const STORE_NAME='answer-drafts';
const RETENTION_MS=24*60*60*1000;
const memory=new Map<string,AnswerDraft>();
const draftKey=(userId:number,kind:DraftKind,sessionId:string,questionId:number)=>`${userId}:${kind}:${sessionId}:${questionId}`;
export const isAnswerDraftExpired=(draft:AnswerDraft,now=Date.now())=>now-new Date(draft.updatedAt).getTime()>RETENTION_MS;

function openDatabase():Promise<IDBDatabase|null>{
  if(!globalThis.indexedDB)return Promise.resolve(null);
  return new Promise((resolve,reject)=>{
    const request=indexedDB.open(DB_NAME,1);
    request.onupgradeneeded=()=>{const db=request.result;if(!db.objectStoreNames.contains(STORE_NAME))db.createObjectStore(STORE_NAME,{keyPath:'key'})};
    request.onsuccess=()=>resolve(request.result);
    request.onerror=()=>reject(request.error??new Error('임시 답안 저장소를 열지 못했습니다.'));
  });
}

async function withStore<T>(mode:IDBTransactionMode,run:(store:IDBObjectStore,resolve:(value:T)=>void,reject:(reason?:unknown)=>void)=>void):Promise<T>{
  const db=await openDatabase();
  if(!db)throw new Error('IndexedDB unavailable');
  return new Promise<T>((resolve,reject)=>{
    const transaction=db.transaction(STORE_NAME,mode);
    run(transaction.objectStore(STORE_NAME),resolve,reject);
    transaction.onerror=()=>reject(transaction.error??new Error('임시 답안을 처리하지 못했습니다.'));
    transaction.oncomplete=()=>db.close();
  });
}

export async function saveAnswerDraft(input:Omit<AnswerDraft,'key'|'updatedAt'>):Promise<AnswerDraft>{
  const draft:AnswerDraft={...input,key:draftKey(input.userId,input.kind,input.sessionId,input.questionId),updatedAt:new Date().toISOString()};
  if(!globalThis.indexedDB){memory.set(draft.key,draft);return draft}
  await withStore<void>('readwrite',(store,resolve,reject)=>{const request=store.put(draft);request.onsuccess=()=>resolve();request.onerror=()=>reject(request.error)});
  return draft;
}

export async function listSessionDrafts(userId:number,kind:DraftKind,sessionId:string):Promise<AnswerDraft[]>{
  const prefix=`${userId}:${kind}:${sessionId}:`;
  if(!globalThis.indexedDB){
    [...memory.values()].filter(isAnswerDraftExpired).forEach(item=>memory.delete(item.key));
    return [...memory.values()].filter(item=>item.key.startsWith(prefix));
  }
  const all=await withStore<AnswerDraft[]>('readonly',(store,resolve,reject)=>{const request=store.getAll();request.onsuccess=()=>resolve(request.result as AnswerDraft[]);request.onerror=()=>reject(request.error)});
  const expired=all.filter(isAnswerDraftExpired);
  if(expired.length)await withStore<void>('readwrite',(store,resolve)=>{expired.forEach(item=>store.delete(item.key));resolve()});
  return all.filter(item=>!isAnswerDraftExpired(item)&&item.key.startsWith(prefix));
}

export async function deleteSessionDrafts(userId:number,kind:DraftKind,sessionId:string):Promise<void>{
  const drafts=await listSessionDrafts(userId,kind,sessionId);
  if(!globalThis.indexedDB){drafts.forEach(item=>memory.delete(item.key));return}
  await withStore<void>('readwrite',(store,resolve)=>{drafts.forEach(item=>store.delete(item.key));resolve()});
}

export async function deleteQuestionDraft(userId:number,kind:DraftKind,sessionId:string,questionId:number):Promise<void>{
  const key=draftKey(userId,kind,sessionId,questionId);
  if(!globalThis.indexedDB){memory.delete(key);return}
  await withStore<void>('readwrite',(store,resolve,reject)=>{const request=store.delete(key);request.onsuccess=()=>resolve();request.onerror=()=>reject(request.error)});
}

export async function clearAnswerDraftsForTests():Promise<void>{memory.clear()}
