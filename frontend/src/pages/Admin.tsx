import {useMutation,useQuery,useQueryClient} from '@tanstack/react-query';
import {useState} from 'react';
import {endpoints} from '../api/queries';
import {useUI} from '../stores/ui';
import {ErrorState,Loading,PageHeader} from '../components/common';

const domainLabels:Record<string,string>={
  'DEA-D1':'D1 · 수집 및 변환','DEA-D2':'D2 · 데이터 저장소','DEA-D3':'D3 · 운영 및 지원','DEA-D4':'D4 · 보안 및 거버넌스','DEA-UNCLASSIFIED':'미분류'
};

export function Admin(){
  const {adminKey,setAdminKey}=useUI();
  const [draft,setDraft]=useState('');
  if(!adminKey)return <><PageHeader eyebrow="관리자" title="관리자 접근" description="ADMIN_ACCESS_KEY가 설정된 환경에서는 동일한 키를 입력하세요."/><section className="panel form"><label>관리자 접근 키<input type="password" value={draft} onChange={event=>setDraft(event.target.value)} autoComplete="current-password"/></label><div className="actions"><button className="button secondary" onClick={()=>setAdminKey('local')}>로컬 관리자 열기</button><button className="button" disabled={!draft} onClick={()=>setAdminKey(draft)}>키로 열기</button></div></section></>;
  return <AdminContent/>;
}

function AdminContent(){
  const {adminKey,setAdminKey}=useUI();
  const client=useQueryClient();
  const dash=useQuery({queryKey:['admin-dashboard'],queryFn:()=>endpoints.adminDashboard(adminKey)});
  const report=useQuery({queryKey:['classification-report'],queryFn:()=>endpoints.classificationReport(adminKey)});
  const readiness=useQuery({queryKey:['mock-readiness'],queryFn:()=>endpoints.mockReadiness(adminKey)});
  const unclassified=useQuery({queryKey:['unclassified'],queryFn:()=>endpoints.unclassified(adminKey)});
  const refresh=()=>client.invalidateQueries({queryKey:['unclassified']}).then(()=>client.invalidateQueries({queryKey:['classification-report']})).then(()=>client.invalidateQueries({queryKey:['mock-readiness']}));
  const classify=useMutation({mutationFn:(ids?:number[])=>endpoints.classifyDomains(adminKey,ids),onSuccess:refresh});
  const manual=useMutation({mutationFn:({id,code}:{id:number;code:string})=>endpoints.setDomain(adminKey,id,code),onSuccess:refresh});
  return <><PageHeader eyebrow="DEA-C01 운영 센터" title="AWS 문제 및 단원 분류" description="미분류 문제를 검토하고 공식 비율 모의고사의 구성 가능 여부를 확인합니다." action={<button onClick={()=>setAdminKey('')}>잠금</button>}/>
    {dash.isLoading?<Loading/>:dash.isError?<ErrorState error={dash.error}/>:<div className="metrics">{Object.entries(dash.data!).map(([key,value])=><article key={key}><small>{key}</small><strong>{value.toLocaleString()}</strong></article>)}</div>}
    <section className="panel"><div className="section-title"><h2>모의고사 준비도</h2>{readiness.data&&<span className={`badge ${readiness.data.ready?'success':'danger'}`}>{readiness.data.ready?'구성 가능':'문제 부족'}</span>}</div>{readiness.isLoading?<Loading/>:readiness.isError?<ErrorState error={readiness.error}/>:<><p>미분류 활성 문제 {readiness.data!.unclassified}개</p><div className="table-wrap"><table><thead><tr><th>단원</th><th>필요</th><th>사용 가능</th><th>부족</th></tr></thead><tbody>{readiness.data!.domains.map(item=><tr key={item.domain_code}><td>{domainLabels[item.domain_code]}</td><td>{item.required}</td><td>{item.available}</td><td>{item.shortage}</td></tr>)}</tbody></table></div></>}</section>
    <section className="panel"><div className="section-title"><h2>단원별 문제 수</h2><span>{report.data?.certification}</span></div>{report.isLoading?<Loading/>:report.isError?<ErrorState error={report.error}/>:<div className="metrics">{Object.entries(report.data!.domain_counts).map(([code,count])=><article key={code}><small>{domainLabels[code]??code}</small><strong>{count}</strong></article>)}</div>}</section>
    <section className="panel"><div className="section-title"><h2>DEA-UNCLASSIFIED</h2><div className="actions"><span>{unclassified.data?.total??0}개</span><button className="button" disabled={classify.isPending||!unclassified.data?.total} onClick={()=>classify.mutate(undefined)}>전체 AI 분류</button></div></div>{classify.isError&&<ErrorState error={classify.error}/>} {unclassified.isLoading?<Loading/>:unclassified.isError?<ErrorState error={unclassified.error}/>:<div className="table-wrap"><table><thead><tr><th>ID</th><th>문제</th><th>상태/신뢰도</th><th>분류 근거</th><th>작업</th></tr></thead><tbody>{unclassified.data!.items.map(question=><tr key={question.id}><td>{question.question_uid}</td><td>{question.question_ko||question.question_en}</td><td>{question.classification_status??'대기'}<br/><small>{question.classification_confidence!=null?`${Math.round(question.classification_confidence*100)}%`:'—'}</small></td><td>{question.classification_reason??'아직 분류되지 않음'}</td><td><div className="actions"><button disabled={classify.isPending} onClick={()=>classify.mutate([question.id])}>AI 분류</button><select aria-label={`${question.question_uid} 단원 직접 지정`} defaultValue="" onChange={event=>event.target.value&&manual.mutate({id:question.id,code:event.target.value})}><option value="">직접 지정</option>{Object.entries(domainLabels).filter(([code])=>code!=='DEA-UNCLASSIFIED').map(([code,label])=><option key={code} value={code}>{label}</option>)}</select></div></td></tr>)}</tbody></table></div>}</section>
  </>;
}
