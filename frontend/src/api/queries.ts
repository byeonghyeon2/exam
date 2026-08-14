import {api} from './client';
import type {Certification,ClassificationReport,Domain,ExamQuestionIndex,ExamResult,Explanation,MockReadiness,Question,QuestionReport,StudyHistory,StudySession,StudySummary,Submission,User,WrongNote} from '../types';
import type {ReportType} from '../reporting';

export const endpoints={
  login:(username:string,password:string)=>api<User>('/auth/login',{method:'POST',body:JSON.stringify({username,password})}),
  logout:()=>api<void>('/auth/logout',{method:'POST'}),me:()=>api<User>('/auth/me'),
  passkeyRegistrationOptions:()=>api<Record<string,unknown>>('/auth/passkeys/registration/options',{method:'POST'}),
  verifyPasskeyRegistration:(credential:Record<string,unknown>)=>api<User>('/auth/passkeys/registration/verify',{method:'POST',body:JSON.stringify({credential})}),
  passkeyAuthenticationOptions:()=>api<Record<string,unknown>>('/auth/passkeys/authentication/options',{method:'POST'}),
  verifyPasskeyAuthentication:(credential:Record<string,unknown>)=>api<User>('/auth/passkeys/authentication/verify',{method:'POST',body:JSON.stringify({credential})}),
  users:()=>api<User[]>('/admin/users'),
  createUser:(body:{username:string;password:string;role:'user'|'admin'})=>api<User>('/admin/users',{method:'POST',body:JSON.stringify(body)}),
  updateUser:(id:number,body:{is_active?:boolean;password?:string})=>api<User>(`/admin/users/${id}`,{method:'PATCH',body:JSON.stringify(body)}),
  resetUserPasskey:(id:number)=>api<void>(`/admin/users/${id}/passkey`,{method:'DELETE'}),
  deleteUser:(id:number)=>api<void>(`/admin/users/${id}`,{method:'DELETE'}),
  certifications:()=>api<Certification[]>('/certifications'),certification:(code:string)=>api<Certification>(`/certifications/${code}`),domains:(code:string)=>api<Domain[]>(`/certifications/${code}/domains`),
  createStudy:(body:object)=>api<StudySession>('/study/sessions',{method:'POST',body:JSON.stringify(body)}),study:(id:string)=>api<StudySession>(`/study/sessions/${id}`),completeStudy:(id:string)=>api<StudySummary>(`/study/sessions/${id}/complete`,{method:'POST'}),studyHistory:()=>api<StudyHistory[]>('/study/history'),retryStudyHistory:(id:string)=>api<StudySession>(`/study/history/${id}/retry`,{method:'POST'}),deleteStudyHistory:(id:string)=>api<{deleted_count:number}>(`/study/history/${id}`,{method:'DELETE'}),nextStudy:(id:string)=>api<Question>(`/study/sessions/${id}/next`),submitStudy:(id:number,sessionId:string,body:object)=>api<Submission>(`/study/questions/${id}/submit?session_id=${encodeURIComponent(sessionId)}`,{method:'POST',body:JSON.stringify(body)}),
  leaveStudy:(id:string,saveResults:boolean)=>api<StudySummary>(`/study/sessions/${id}/leave`,{method:'POST',body:JSON.stringify({save_results:saveResults})}),
  generateExplanation:(id:number)=>api<Explanation>(`/questions/${id}/explanation/generate`,{method:'POST',body:JSON.stringify({language:'ko'})}),reportQuestion:(id:number,body:{report_type:ReportType;description:string})=>api<{id:number}>(`/questions/${id}/reports`,{method:'POST',body:JSON.stringify(body)}),
  createExam:(body:object)=>api<{id:string}>('/mock-exams',{method:'POST',body:JSON.stringify(body)}),examQuestions:(id:string)=>api<ExamQuestionIndex>(`/mock-exams/${id}/questions`),examQuestion:(exam:string,q:number)=>api<Question>(`/mock-exams/${exam}/questions/${q}`),saveAnswer:(exam:string,q:number,answers:string[])=>api<void>(`/mock-exams/${exam}/answers/${q}`,{method:'PUT',body:JSON.stringify({selected_answers:answers})}),submitExam:(id:string)=>api<ExamResult>(`/mock-exams/${id}/submit`,{method:'POST'}),leaveExam:(id:string)=>api<{status:string}>(`/mock-exams/${id}/leave`,{method:'POST',keepalive:true}),result:(id:string)=>api<ExamResult>(`/mock-exams/${id}/result`),
  wrongNotes:()=>api<WrongNote[]>('/wrong-notes'),deleteWrongNotes:(questionIds:number[])=>api<{deleted_count:number}>('/wrong-notes',{method:'DELETE',body:JSON.stringify({question_ids:questionIds})}),
  adminDashboard:()=>api<Record<string,number>>('/admin/dashboard'),adminReports:()=>api<QuestionReport[]>('/admin/reports'),adminQuestions:()=>api<{items:Question[];total:number}>('/admin/questions'),unclassified:()=>api<{items:Question[];total:number}>('/admin/classification/unclassified'),classificationReport:()=>api<ClassificationReport>('/admin/classification/report'),mockReadiness:()=>api<MockReadiness>('/admin/mock-exam-readiness'),classifyDomains:(questionIds?:number[],force=false)=>api<Record<string,number>>('/admin/classification/run',{method:'POST',body:JSON.stringify({question_ids:questionIds,only_unclassified:true,force,batch_size:10})}),setDomain:(id:number,domain_code:string)=>api<{status:string;domain_code:string}>(`/admin/questions/${id}/domain`,{method:'PATCH',body:JSON.stringify({domain_code})})
};
