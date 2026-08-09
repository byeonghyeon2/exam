import {createContext,useContext,type Dispatch,type SetStateAction} from 'react';

export type StudyExitGuard={sessionId:string;answeredCount:number;saveAndLeave:()=>Promise<unknown>;discardAndLeave:()=>Promise<unknown>};
export type StudyExitGuardContextValue={setGuard:Dispatch<SetStateAction<StudyExitGuard|null>>};

export const StudyExitGuardContext=createContext<StudyExitGuardContextValue|null>(null);

export function useStudyExitGuard(){
  const value=useContext(StudyExitGuardContext);
  if(!value)throw new Error('StudyExitGuardContext is missing');
  return value;
}
