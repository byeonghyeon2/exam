import {afterEach,describe,expect,it,vi} from 'vitest';
import {ApiError,api,resolveApiBase} from '../api/client';

afterEach(()=>vi.restoreAllMocks());

describe('resolveApiBase',()=>{
  const local={origin:'http://localhost:5173',hostname:'localhost'};

  it('uses the same-origin API path by default and accepts relative values',()=>{
    expect(resolveApiBase(undefined,local)).toBe('/api/v1');
    expect(resolveApiBase('',local)).toBe('/api/v1');
    expect(resolveApiBase('/api/v1/',local)).toBe('/api/v1');
    expect(resolveApiBase('api/v1',local)).toBe('/api/v1');
  });

  it('keeps local development and mobile access working with an absolute URL',()=>{
    expect(resolveApiBase('http://localhost:8000/api/v1',local)).toBe('http://localhost:8000/api/v1');
    expect(resolveApiBase('http://localhost:8000/api/v1',{origin:'http://192.168.0.15:5173',hostname:'192.168.0.15'})).toBe('http://192.168.0.15:8000/api/v1');
    for(const hostname of ['127.0.0.1','::1','10.0.0.8','172.16.0.8']){
      const origin=hostname==='::1'?'http://[::1]:5173':`http://${hostname}:5173`;
      expect(resolveApiBase('http://localhost:8000/api/v1',{origin,hostname})).toContain('/api/v1');
    }
    expect(resolveApiBase('//localhost:8000/api/v1',{origin:'http://10.0.0.8:5173',hostname:'10.0.0.8'})).toBe('http://10.0.0.8:8000/api/v1');
  });

  it('keeps an explicitly configured API URL',()=>{
    expect(resolveApiBase('https://api.example.com/v1',local)).toBe('https://api.example.com/v1');
  });

  it('never exposes a localhost API URL from a public production host',()=>{
    const production={origin:'http://bca.iptime.org',hostname:'bca.iptime.org'};
    expect(resolveApiBase('/api/v1',production)).toBe('/api/v1');
    expect(resolveApiBase('http://localhost:8000/api/v1',production)).toBe('/api/v1');
    expect(resolveApiBase('http://[',production)).toBe('/api/v1');
    expect(resolveApiBase('/api/v1',{origin:'not a valid origin',hostname:'localhost'})).toBe('/api/v1');
  });
});

describe('api',()=>{
  it('sends same-origin credentialed JSON requests and returns the response body',async()=>{
    const fetchMock=vi.spyOn(globalThis,'fetch').mockResolvedValue(new Response(JSON.stringify({status:'ok'}),{status:200,headers:{'Content-Type':'application/json'}}));
    await expect(api<{status:string}>('/health',{method:'POST',headers:{'x-test':'yes'}})).resolves.toEqual({status:'ok'});
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/health',expect.objectContaining({
      method:'POST',credentials:'include',headers:{'Content-Type':'application/json','x-test':'yes'},
    }));
  });

  it('throws a detailed ApiError for JSON API failures',async()=>{
    vi.spyOn(globalThis,'fetch').mockResolvedValue(new Response(JSON.stringify({detail:'로그인이 필요합니다'}),{status:401,headers:{'Content-Type':'application/json'}}));
    const request=api('/auth/me');
    await expect(request).rejects.toMatchObject({message:'로그인이 필요합니다',status:401,detail:{detail:'로그인이 필요합니다'}});
    await request.catch(error=>expect(error).toBeInstanceOf(ApiError));
  });

  it('uses the generic error when an error response has no JSON detail',async()=>{
    vi.spyOn(globalThis,'fetch').mockResolvedValue(new Response('not-json',{status:500}));
    await expect(api('/broken')).rejects.toMatchObject({status:500,detail:null});
  });
});
