import {describe,expect,it} from 'vitest';
import {resolveApiBase} from '../api/client';

describe('resolveApiBase',()=>{
  it('uses the host that served the frontend for local and mobile access',()=>{
    expect(resolveApiBase(undefined,{protocol:'http:',hostname:'192.168.0.15'})).toBe('http://192.168.0.15:8000/api/v1');
    expect(resolveApiBase(undefined,{protocol:'http:',hostname:'127.0.0.1'})).toBe('http://127.0.0.1:8000/api/v1');
    expect(resolveApiBase('http://localhost:8000/api/v1',{protocol:'http:',hostname:'192.168.0.15'})).toBe('http://192.168.0.15:8000/api/v1');
  });

  it('keeps an explicitly configured API URL',()=>{
    expect(resolveApiBase('https://api.example.com/v1',{protocol:'http:',hostname:'localhost'})).toBe('https://api.example.com/v1');
  });
});
