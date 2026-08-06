import {create} from 'zustand';
type UIState={dark:boolean;adminKey:string;toggleDark:()=>void;setAdminKey:(v:string)=>void};
export const useUI=create<UIState>((set)=>({dark:localStorage.getItem('theme')==='dark',adminKey:sessionStorage.getItem('adminKey')??'',toggleDark:()=>set(s=>{const dark=!s.dark;localStorage.setItem('theme',dark?'dark':'light');return{dark}}),setAdminKey:(adminKey)=>{sessionStorage.setItem('adminKey',adminKey);set({adminKey})}}));
