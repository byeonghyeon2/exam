import {createContext,useContext,type Dispatch,type SetStateAction} from 'react';

export type StudyExitGuard={kind:'study';sessionId:string;answeredCount:number;saveAndLeave:()=>Promise<unknown>;discardAndLeave:()=>Promise<unknown>};
export type ExamExitGuard={kind:'exam';sessionId:string;answeredCount:number;totalCount:number;unansweredNumbers:number[]};
export type NavigationExitGuard=StudyExitGuard|ExamExitGuard;
export type StudyExitGuardContextValue={setGuard:Dispatch<SetStateAction<NavigationExitGuard|null>>;requestExit:(to:string)=>void};

export const StudyExitGuardContext=createContext<StudyExitGuardContextValue|null>(null);

export function useStudyExitGuard(){
  const value=useContext(StudyExitGuardContext);
  if(!value)throw new Error('StudyExitGuardContext is missing');
  return value;
}
