import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { endpoints } from '../api/queries';
import { Empty, ErrorState, Loading, PageHeader } from '../components/common';

function formatWrongTime(value: string) {
  const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/.test(value) ? value : `${value}Z`;
  const parts = new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false,
  }).formatToParts(new Date(normalized));
  const get = (type: Intl.DateTimeFormatPartTypes) => parts.find(part => part.type === type)?.value ?? '';
  return `${get('year')}.${get('month')}.${get('day')} ${get('hour')}:${get('minute')}`;
}

export function WrongNotes() {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<number[]>([]);
  const query = useQuery({ queryKey: ['wrong-notes'], queryFn: endpoints.wrongNotes });
  const remove = useMutation({
    mutationFn: () => endpoints.deleteWrongNotes(selected),
    onSuccess: async () => { setSelected([]); await queryClient.invalidateQueries({ queryKey: ['wrong-notes'] }); },
  });
  const notes = query.data ?? [];
  const toggle = (id: number) => setSelected(current => current.includes(id) ? current.filter(item => item !== id) : [...current, id]);
  const allSelected = notes.length > 0 && selected.length === notes.length;

  return <>
    <PageHeader eyebrow="기억 보관" title="오답노트" description="삭제할 문제를 직접 선택할 수 있습니다." action={notes.length ? <div className="wrong-actions">
      <label><input type="checkbox" checked={allSelected} onChange={() => setSelected(allSelected ? [] : notes.map(note => note.question_id))} /> 전체 선택</label>
      <button className="button" disabled={!selected.length || remove.isPending} onClick={() => remove.mutate()}>{remove.isPending ? '삭제 중…' : `선택 삭제 (${selected.length})`}</button>
    </div> : undefined} />
    {query.isLoading ? <Loading /> : query.isError ? <ErrorState error={query.error} /> : !notes.length
      ? <Empty>학습 중 틀린 문제가 여기에 자동으로 모입니다.</Empty>
      : <div className="list wrong-list">{notes.map(note => <article key={note.question_id}>
        <input aria-label={`${note.question_uid} 선택`} type="checkbox" checked={selected.includes(note.question_id)} onChange={() => toggle(note.question_id)} />
        <div><h3>{formatWrongTime(note.last_wrong_at)} · 누적 {note.wrong_count}회</h3><span className="badge">{note.question_uid}</span><p>{note.question_ko}</p></div>
        <button className="button">다시 풀기</button>
      </article>)}</div>}
    {remove.isError && <ErrorState error={remove.error} />}
  </>;
}
