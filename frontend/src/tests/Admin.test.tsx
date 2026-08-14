import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { endpoints } from '../api/queries';
import { Admin } from '../pages/Admin';
import styles from '../styles.css?raw';

function renderAdmin() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}><Admin /></QueryClientProvider>);
}

function mockAdminData() {
  vi.spyOn(endpoints, 'adminDashboard').mockResolvedValue({ questions: 295, verified: 295 });
  vi.spyOn(endpoints, 'users').mockResolvedValue([{
    id: 1, username: 'user', role: 'user', is_active: true,
    password_managed_by_environment: false, passkey_registered: true, created_at: '2026-08-09T00:00:00Z', last_login_at: null,
  }]);
  vi.spyOn(endpoints, 'resetUserPasskey').mockResolvedValue();
  vi.spyOn(endpoints, 'deleteUser').mockResolvedValue();
  vi.spyOn(endpoints, 'adminReports').mockResolvedValue([{
    id: 7, question_id: 149, question_uid: 'AWS-DEA-C01-000149',
    question_ko: '긴 문제 내용', question_en: 'Long question', report_type: 'explanation_error',
    description: '해설에 오타 존재', status: 'received', resolution_note: null,
    created_at: '2026-08-12T00:14:22Z', resolved_at: null,
  }]);
  vi.spyOn(endpoints, 'mockReadiness').mockResolvedValue({
    ready: true, question_count: 65, unclassified: 0,
    domains: [
      { domain_code: 'DEA-D1', required: 22, available: 106, shortage: 0 },
      { domain_code: 'DEA-D2', required: 17, available: 76, shortage: 0 },
      { domain_code: 'DEA-D3', required: 14, available: 64, shortage: 0 },
      { domain_code: 'DEA-D4', required: 12, available: 49, shortage: 0 },
    ],
  });
  vi.spyOn(endpoints, 'classificationReport').mockResolvedValue({
    certification: 'DEA-C01', domain_counts: { 'DEA-D1': 106, 'DEA-D2': 76, 'DEA-D3': 64, 'DEA-D4': 49 }, status_counts: {},
  });
  vi.spyOn(endpoints, 'unclassified').mockResolvedValue({ items: [], total: 0 });
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe('Admin mobile layout', () => {
  it('renders account data with mobile labels and avoids an empty unclassified table', async () => {
    mockAdminData();
    renderAdmin();

    const user = await screen.findByText('user');
    expect(user.closest('td')).toHaveAttribute('data-label', '아이디');
    expect(screen.getByText('사용 중').closest('td')).toHaveAttribute('data-label', '상태');
    expect(screen.getByText('등록됨').closest('td')).toHaveAttribute('data-label', 'Passkey');
    expect(screen.getByRole('button', { name: '기기 초기화' })).toBeInTheDocument();
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
    const alert = vi.spyOn(window, 'alert').mockImplementation(() => undefined);
    await userEvent.click(screen.getByRole('button', { name: '기기 초기화' }));
    expect(confirm).toHaveBeenCalledWith('기기를 초기화하시겠습니까?\n등록된 Passkey가 삭제되고 모든 로그인 세션이 종료됩니다.');
    await waitFor(() => expect(endpoints.resetUserPasskey).toHaveBeenCalledWith(1));
    await waitFor(() => expect(alert).toHaveBeenCalledWith('기기 초기화가 완료되었습니다.'));
    await userEvent.click(screen.getByRole('button', { name: '계정 삭제' }));
    expect(confirm).toHaveBeenLastCalledWith('user 계정을 삭제하시겠습니까?\n학습 기록과 인증 정보가 모두 삭제되며 복구할 수 없습니다.');
    await waitFor(() => expect(endpoints.deleteUser).toHaveBeenCalledWith(1));
    await waitFor(() => expect(alert).toHaveBeenCalledWith('계정이 삭제되었습니다.'));
    expect(screen.getByText('미분류 문제가 없습니다.')).toBeInTheDocument();
    expect(screen.queryByRole('columnheader', { name: '상태/신뢰도' })).not.toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: '사용 가능' })).toBeInTheDocument();
    const reports = within(screen.getByRole('heading', { name: '문제 신고' }).closest('section')!);
    expect(reports.getByRole('columnheader', { name: '접수 시각' })).toHaveClass('report-time');
    expect(reports.getByRole('columnheader', { name: '유형' })).toHaveClass('report-type');
    expect(reports.queryByRole('columnheader', { name: '상태' })).not.toBeInTheDocument();
  });

  it('does not reset without confirmation and alerts when reset fails', async () => {
    mockAdminData();
    renderAdmin();
    await screen.findByText('user');
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    const alert = vi.spyOn(window, 'alert').mockImplementation(() => undefined);

    await userEvent.click(screen.getByRole('button', { name: '기기 초기화' }));
    expect(confirm).toHaveBeenCalled();
    expect(endpoints.resetUserPasskey).not.toHaveBeenCalled();

    confirm.mockReturnValue(true);
    vi.mocked(endpoints.resetUserPasskey).mockRejectedValueOnce(new Error('서버 오류'));
    await userEvent.click(screen.getByRole('button', { name: '기기 초기화' }));
    await waitFor(() => expect(alert).toHaveBeenCalledWith('기기 초기화에 실패했습니다. 다시 시도해주세요.'));

    confirm.mockReturnValue(false);
    await userEvent.click(screen.getByRole('button', { name: '계정 삭제' }));
    expect(endpoints.deleteUser).not.toHaveBeenCalled();

    confirm.mockReturnValue(true);
    vi.mocked(endpoints.deleteUser).mockRejectedValueOnce(new Error('서버 오류'));
    await userEvent.click(screen.getByRole('button', { name: '계정 삭제' }));
    await waitFor(() => expect(alert).toHaveBeenCalledWith('계정 삭제에 실패했습니다. 다시 시도해주세요.'));
  });

  it('keeps admin responsive rules scoped to the admin page', () => {
    const compact = styles.replace(/\s+/g, '');
    expect(compact).toContain('.admin-responsive-tablethead{display:none}');
    expect(compact).toContain('.admin-responsive-tabletd::before{content:attr(data-label)');
    expect(compact).toContain('.admin-readinesstable{table-layout:fixed;font-size:12px}');
    expect(compact).toContain('.admin-domain-counts.metrics{grid-template-columns:1fr;gap:8px}');
    expect(compact).toContain('.admin-reports-table.report-time{width:145px;min-width:145px;white-space:nowrap}');
    expect(compact).toContain('.admin-reports-table.report-type{width:92px;min-width:92px;white-space:nowrap;word-break:keep-all}');
    expect(compact).toContain('@media(max-width:380px){.admin-page.panel{padding:18px13px}');
  });
});
