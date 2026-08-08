export const REPORT_TYPE_OPTIONS = [
  { value: 'wrong_answer', label: '정답 오류' },
  { value: 'missing_content', label: '문제·선택지 내용 오류' },
  { value: 'translation_error', label: '번역 오류' },
  { value: 'language_mismatch', label: '언어 불일치' },
  { value: 'wrong_answer_count', label: '정답 개수 오류' },
  { value: 'wrong_explanation', label: '해설 오류' },
  { value: 'missing_asset', label: '이미지·자료 누락' },
  { value: 'duplicate', label: '중복 문제' },
  { value: 'other', label: '기타' },
] as const;

export type ReportType = typeof REPORT_TYPE_OPTIONS[number]['value'];

export const REPORT_TYPE_LABELS = Object.fromEntries(
  REPORT_TYPE_OPTIONS.map(option => [option.value, option.label]),
) as Record<ReportType, string>;
