import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ContentProtection } from '../components/ContentProtection';

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe('ContentProtection', () => {
  it('blocks extraction gestures and common source/devtools shortcuts', () => {
    render(<ContentProtection username="learner"><p>보호할 문제</p></ContentProtection>);
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
    render(<ContentProtection username="learner"><input aria-label="관리 입력" /><p>보호할 문제</p></ContentProtection>);
    const input = screen.getByLabelText('관리 입력');
    const pagePaste = new Event('paste', { bubbles: true, cancelable: true });
    screen.getByText('보호할 문제').dispatchEvent(pagePaste);
    expect(pagePaste.defaultPrevented).toBe(true);

    const inputPaste = new Event('paste', { bubbles: true, cancelable: true });
    input.dispatchEvent(inputPaste);
    expect(inputPaste.defaultPrevented).toBe(false);
    fireEvent.keyDown(input, { key: 'c', ctrlKey: true });
  });

  it('renders a non-interactive user watermark', () => {
    render(<ContentProtection username="learner"><p>내용</p></ContentProtection>);
    const watermark = screen.getByTestId('content-watermark');
    expect(watermark).toHaveAttribute('aria-hidden', 'true');
    expect(watermark).toHaveTextContent('learner');
  });
});
