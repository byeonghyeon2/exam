import {create} from 'zustand';
type UIState={dark:boolean;toggleDark:()=>void};
export const useUI=create<UIState>((set)=>({dark:localStorage.getItem('theme')==='dark',toggleDark:()=>set(s=>{const dark=!s.dark;localStorage.setItem('theme',dark?'dark':'light');return{dark}})}));
