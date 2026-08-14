import { afterEach, describe, expect, it, vi } from 'vitest';
import { clearAnswerDraftsForTests, deleteSessionDrafts, isAnswerDraftExpired, listSessionDrafts, saveAnswerDraft } from '../offline/answerDrafts';

afterEach(async()=>{await clearAnswerDraftsForTests();vi.unstubAllGlobals()});

describe('answer draft storage',()=>{
  it('expires device drafts after 24 hours',()=>{
    const draft={key:'draft',userId:2,kind:'study' as const,sessionId:'study-1',questionId:1,selectedAnswers:['A'],currentIndex:0,pending:true,updatedAt:'2026-08-14T00:00:00.000Z'};
    expect(isAnswerDraftExpired(draft,new Date('2026-08-15T00:00:00.001Z').getTime())).toBe(true);
    expect(isAnswerDraftExpired(draft,new Date('2026-08-14T23:59:59.999Z').getTime())).toBe(false);
  });

  it('keeps drafts isolated by user and session and deletes only the completed session',async()=>{
    vi.stubGlobal('indexedDB',undefined);
    await saveAnswerDraft({userId:2,kind:'mock-exam',sessionId:'exam-1',questionId:10,selectedAnswers:['B'],currentIndex:3,pending:true});
    await saveAnswerDraft({userId:3,kind:'mock-exam',sessionId:'exam-1',questionId:10,selectedAnswers:['A'],currentIndex:0,pending:false});
    expect(await listSessionDrafts(2,'mock-exam','exam-1')).toMatchObject([{selectedAnswers:['B'],currentIndex:3,pending:true}]);
    expect(await listSessionDrafts(3,'mock-exam','exam-1')).toHaveLength(1);
    await deleteSessionDrafts(2,'mock-exam','exam-1');
    expect(await listSessionDrafts(2,'mock-exam','exam-1')).toEqual([]);
    expect(await listSessionDrafts(3,'mock-exam','exam-1')).toHaveLength(1);
  });
});
