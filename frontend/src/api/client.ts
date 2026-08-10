const DEFAULT_API_BASE='/api/v1';
type ApiLocation={origin:string;hostname:string};

function isLocalHost(hostname:string){
  return hostname==='localhost'||hostname==='127.0.0.1'||hostname==='::1'||hostname.startsWith('10.')||hostname.startsWith('192.168.')||/^172\.(1[6-9]|2\d|3[01])\./.test(hostname);
}

export function resolveApiBase(configured:string|undefined,location:ApiLocation){
  const value=configured?.trim()||DEFAULT_API_BASE;
  const isAbsolute=/^[a-z][a-z\d+.-]*:\/\//i.test(value)||value.startsWith('//');
  if(!isAbsolute){
    try{
      const relative=new URL(value.startsWith('/')?value:`/${value}`,location.origin);
      return `${relative.pathname}${relative.search}`.replace(/\/$/,'')||DEFAULT_API_BASE;
    }catch{return DEFAULT_API_BASE;}
  }
  try{
    const url=new URL(value,location.origin);
    if(['localhost','127.0.0.1','::1'].includes(url.hostname)&&url.hostname!==location.hostname){
      if(!isLocalHost(location.hostname))return DEFAULT_API_BASE;
      url.hostname=location.hostname;
    }
    return url.toString().replace(/\/$/,'');
  }catch{return DEFAULT_API_BASE;}
}
const BASE=resolveApiBase(import.meta.env.VITE_API_BASE_URL as string|undefined,window.location);
export class ApiError extends Error { constructor(message:string,readonly status:number,readonly detail?:unknown){super(message)} }
export async function api<T>(path:string,init?:RequestInit):Promise<T>{const res=await fetch(`${BASE}${path}`,{...init,credentials:'include',headers:{'Content-Type':'application/json',...init?.headers}});const body:unknown=await res.json().catch(()=>null);if(!res.ok){const msg=typeof body==='object'&&body!==null&&'detail'in body?String(body.detail):'요청을 처리하지 못했습니다.';throw new ApiError(msg,res.status,body)}return body as T}
