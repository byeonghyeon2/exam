import { useMutation } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { endpoints } from '../api/queries';
import { REPORT_TYPE_OPTIONS, type ReportType } from '../reporting';

export function ReportModal({ questionId, onClose }: { questionId: number; onClose: () => void }) {
  const [reportType, setReportType] = useState<ReportType | ''>('');
  const [description, setDescription] = useState('');
  const submit = useMutation({
    mutationFn: () => endpoints.reportQuestion(questionId, {
      report_type: reportType as ReportType,
      description: description.trim(),
    }),
  });

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !submit.isPending) onClose();
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [onClose, submit.isPending]);

  const canSubmit = Boolean(reportType && description.trim());

  return <div className="modal-backdrop" role="presentation" onMouseDown={event => {
    if (event.target === event.currentTarget && !submit.isPending) onClose();
  }}>
    <section className="modal" role="dialog" aria-modal="true" aria-labelledby="report-modal-title">
      {submit.isSuccess ? <>
        <h2 id="report-modal-title">신고가 접수되었습니다</h2>
        <p className="muted">관리자 화면에서 내용을 검토할 수 있습니다.</p>
        <div className="actions"><button className="button" onClick={onClose}>확인</button></div>
      </> : <form onSubmit={event => { event.preventDefault(); if (canSubmit) submit.mutate(); }}>
        <h2 id="report-modal-title">문제 신고</h2>
        <p className="muted">문제에서 이상한 부분을 알려주시면 검토에 활용합니다.</p>
        <label>신고 유형
          <select autoFocus required value={reportType} onChange={event => setReportType(event.target.value as ReportType)}>
            <option value="">유형을 선택해 주세요</option>
            {REPORT_TYPE_OPTIONS.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </label>
        <label>신고 내용
          <textarea required maxLength={4000} rows={6} value={description} onChange={event => setDescription(event.target.value)} placeholder="예: 정답이 이상한 것 같음" />
        </label>
        {submit.isError && <p className="form-error" role="alert">{submit.error instanceof Error ? submit.error.message : '신고를 저장하지 못했습니다.'}</p>}
        <div className="actions">
          <button type="button" disabled={submit.isPending} onClick={onClose}>취소</button>
          <button className="button" type="submit" disabled={!canSubmit || submit.isPending}>{submit.isPending ? '등록 중…' : '신고 등록'}</button>
        </div>
      </form>}
    </section>
  </div>;
}
