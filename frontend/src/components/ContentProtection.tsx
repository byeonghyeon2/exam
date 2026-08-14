import { type ReactNode, useEffect } from 'react';

const BLOCKED_CTRL_KEYS = new Set(['c', 'x', 's', 'u', 'p']);
const BLOCKED_DEVTOOLS_KEYS = new Set(['i', 'j', 'c']);

function isEditable(target: EventTarget | null): boolean {
  return target instanceof HTMLElement
    && (target.matches('input, textarea, select') || target.isContentEditable);
}

export function shouldBlockShortcut(event: KeyboardEvent): boolean {
  if (event.key === 'F12' || event.key === 'PrintScreen') return true;
  const modifier = event.ctrlKey || event.metaKey;
  if (!modifier) return false;
  const key = event.key.toLowerCase();
  if (isEditable(event.target) && ['c', 'x', 'v', 'a'].includes(key) && !event.shiftKey) return false;
  return BLOCKED_CTRL_KEYS.has(key) || (event.shiftKey && BLOCKED_DEVTOOLS_KEYS.has(key));
}

export function ContentProtection({ children, enabled = true }: { children: ReactNode; enabled?: boolean }) {
  useEffect(() => {
    if (!enabled) return;
    const prevent = (event: Event) => event.preventDefault();
    const preventPasteOutsideEditor = (event: ClipboardEvent) => {
      if (!isEditable(event.target)) event.preventDefault();
    };
    const blockKeyboard = (event: KeyboardEvent) => {
      if (shouldBlockShortcut(event)) event.preventDefault();
    };
    document.addEventListener('contextmenu', prevent);
    document.addEventListener('copy', prevent);
    document.addEventListener('cut', prevent);
    document.addEventListener('dragstart', prevent);
    document.addEventListener('paste', preventPasteOutsideEditor);
    document.addEventListener('keydown', blockKeyboard, true);
    return () => {
      document.removeEventListener('contextmenu', prevent);
      document.removeEventListener('copy', prevent);
      document.removeEventListener('cut', prevent);
      document.removeEventListener('dragstart', prevent);
      document.removeEventListener('paste', preventPasteOutsideEditor);
      document.removeEventListener('keydown', blockKeyboard, true);
    };
  }, [enabled]);

  return <div className={enabled ? 'protected-content' : undefined}>{children}</div>;
}
