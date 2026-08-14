import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ContentProtection } from '../components/ContentProtection';

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe('ContentProtection', () => {
  it('keeps protection on for public and learner screens but disables it for admin', () => {
    const { rerender } = render(<ContentProtection enabled><p>로그인 화면</p></ContentProtection>);
    const blocked = new MouseEvent('contextmenu', { bubbles: true, cancelable: true });
    screen.getByText('로그인 화면').dispatchEvent(blocked);
    expect(blocked.defaultPrevented).toBe(true);

    rerender(<ContentProtection enabled={false}><p>관리자 화면</p></ContentProtection>);
    const allowed = new MouseEvent('contextmenu', { bubbles: true, cancelable: true });
    screen.getByText('관리자 화면').dispatchEvent(allowed);
    expect(allowed.defaultPrevented).toBe(false);
  });

  it('blocks extraction gestures and common source/devtools shortcuts', () => {
    render(<ContentProtection><p>보호할 문제</p></ContentProtection>);
    const content = screen.getByText('보호할 문제');

    for (const event of [
      new MouseEvent('contextmenu', { bubbles: true, cancelable: true }),
      new Event('copy', { bubbles: true, cancelable: true }),
      new Event('cut', { bubbles: true, cancelable: true }),
      new Event('dragstart', { bubbles: true, cancelable: true }),
    ]) {
      content.dispatchEvent(event);
      expect(event.defaultPrevented).toBe(true);
    }

    for (const options of [
      { key: 'F12' }, { key: 'u', ctrlKey: true }, { key: 's', ctrlKey: true },
      { key: 'p', ctrlKey: true }, { key: 'i', ctrlKey: true, shiftKey: true },
      { key: 'c', ctrlKey: true, shiftKey: true }, { key: 'j', ctrlKey: true, shiftKey: true },
    ]) {
      const event = new KeyboardEvent('keydown', { ...options, bubbles: true, cancelable: true });
      document.dispatchEvent(event);
      expect(event.defaultPrevented).toBe(true);
    }
  });

  it('allows ordinary typing and paste in editable fields while blocking page paste', () => {
    render(<ContentProtection><input aria-label="관리 입력" /><p>보호할 문제</p></ContentProtection>);
    const input = screen.getByLabelText('관리 입력');
    const pagePaste = new Event('paste', { bubbles: true, cancelable: true });
    screen.getByText('보호할 문제').dispatchEvent(pagePaste);
    expect(pagePaste.defaultPrevented).toBe(true);

    const inputPaste = new Event('paste', { bubbles: true, cancelable: true });
    input.dispatchEvent(inputPaste);
    expect(inputPaste.defaultPrevented).toBe(false);
    fireEvent.keyDown(input, { key: 'c', ctrlKey: true });
  });

  it('does not expose the signed-in account in a background watermark', () => {
    render(<ContentProtection><p>내용</p></ContentProtection>);
    expect(screen.queryByTestId('content-watermark')).not.toBeInTheDocument();
    expect(document.querySelector('.content-watermark')).not.toBeInTheDocument();
  });
});
