export function resolveApiBase(configured:string|undefined,location:{protocol:string;hostname:string}){
  if(!configured)return `${location.protocol}//${location.hostname}:8000/api/v1`;
  const url=new URL(configured);
  if(['localhost','127.0.0.1'].includes(url.hostname)&&url.hostname!==location.hostname)url.hostname=location.hostname;
  return url.toString().replace(/\/$/,'');
}
const BASE=resolveApiBase(import.meta.env.VITE_API_BASE_URL as string|undefined,window.location);
export class ApiError extends Error { constructor(message:string,readonly status:number,readonly detail?:unknown){super(message)} }
export async function api<T>(path:string,init?:RequestInit):Promise<T>{const res=await fetch(`${BASE}${path}`,{...init,credentials:'include',headers:{'Content-Type':'application/json',...init?.headers}});const body:unknown=await res.json().catch(()=>null);if(!res.ok){const msg=typeof body==='object'&&body!==null&&'detail'in body?String(body.detail):'요청을 처리하지 못했습니다.';throw new ApiError(msg,res.status,body)}return body as T}
