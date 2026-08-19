import { act, cleanup, fireEvent, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { endpoints } from '../api/queries';
import { ApiError } from '../api/client';
import {
  SESSION_EXPIRED_EVENT,
  SESSION_HEARTBEAT_MS,
  SESSION_IDLE_MS,
  SessionActivity,
} from '../components/SessionActivity';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.useRealTimers();
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
});

describe('SessionActivity', () => {
  it('expires only after thirty minutes without user activity', () => {
    vi.useFakeTimers();
    const expired = vi.fn();
    window.addEventListener(SESSION_EXPIRED_EVENT, expired);
    render(<SessionActivity />);

    act(() => { vi.advanceTimersByTime(SESSION_IDLE_MS - 1); });
    expect(expired).not.toHaveBeenCalled();
    fireEvent.pointerDown(document);
    act(() => { vi.advanceTimersByTime(SESSION_IDLE_MS - 1); });
    expect(expired).not.toHaveBeenCalled();
    act(() => { vi.advanceTimersByTime(1); });
    expect(expired).toHaveBeenCalledTimes(1);
    window.removeEventListener(SESSION_EXPIRED_EVENT, expired);
  });

  it('refreshes the same server session with the measured idle time', async () => {
    vi.useFakeTimers();
    vi.spyOn(endpoints, 'sessionActivity').mockResolvedValue();
    render(<SessionActivity />);

    act(() => { vi.advanceTimersByTime(30_000); });
    fireEvent.keyDown(document, { key: 'ArrowDown' });
    await act(async () => { await vi.advanceTimersByTimeAsync(SESSION_HEARTBEAT_MS - 30_000); });

    expect(endpoints.sessionActivity).toHaveBeenCalledWith(30);
  });

  it('does not treat background events as activity', () => {
    vi.useFakeTimers();
    const expired = vi.fn();
    window.addEventListener(SESSION_EXPIRED_EVENT, expired);
    const heartbeat = vi.spyOn(endpoints, 'sessionActivity').mockResolvedValue();
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' });
    render(<SessionActivity />);
    fireEvent.touchStart(document);
    act(() => { vi.advanceTimersByTime(SESSION_IDLE_MS); });
    expect(expired).toHaveBeenCalledTimes(1);
    expect(heartbeat).not.toHaveBeenCalled();

    window.removeEventListener(SESSION_EXPIRED_EVENT, expired);
  });

  it('retries temporary failures but expires when the server rejects the session', async () => {
    vi.useFakeTimers();
    const expired = vi.fn();
    window.addEventListener(SESSION_EXPIRED_EVENT, expired);
    const heartbeat = vi.spyOn(endpoints, 'sessionActivity')
      .mockRejectedValueOnce(new Error('DB 연결 실패'))
      .mockRejectedValueOnce(new ApiError('로그인이 필요합니다', 401));
    render(<SessionActivity />);

    fireEvent.scroll(document);
    await act(async () => { await vi.advanceTimersByTimeAsync(SESSION_HEARTBEAT_MS); });
    expect(heartbeat).toHaveBeenCalledTimes(1);
    expect(expired).not.toHaveBeenCalled();
    fireEvent.pointerDown(document);
    await act(async () => { await Promise.resolve(); });
    expect(heartbeat).toHaveBeenCalledTimes(2);
    expect(expired).toHaveBeenCalledTimes(1);

    window.removeEventListener(SESSION_EXPIRED_EVENT, expired);
  });

  it('flushes pending activity when hidden and checks elapsed time when visible again', async () => {
    vi.useFakeTimers();
    const heartbeat = vi.spyOn(endpoints, 'sessionActivity').mockResolvedValue();
    const expired = vi.fn();
    window.addEventListener(SESSION_EXPIRED_EVENT, expired);
    render(<SessionActivity />);
    fireEvent.pointerDown(document);

    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' });
    fireEvent(document, new Event('visibilitychange'));
    await act(async () => { await Promise.resolve(); });
    expect(heartbeat).toHaveBeenCalledWith(0);

    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
    fireEvent(document, new Event('visibilitychange'));
    expect(expired).not.toHaveBeenCalled();
    vi.setSystemTime(Date.now() + SESSION_IDLE_MS);
    fireEvent(document, new Event('visibilitychange'));
    expect(expired).toHaveBeenCalledTimes(1);
    window.removeEventListener(SESSION_EXPIRED_EVENT, expired);
  });

  it('expires instead of refreshing when a pending activity has already become idle', async () => {
    vi.useFakeTimers();
    const heartbeat = vi.spyOn(endpoints, 'sessionActivity').mockRejectedValue(new Error('DB 연결 실패'));
    const expired = vi.fn();
    window.addEventListener(SESSION_EXPIRED_EVENT, expired);
    render(<SessionActivity />);
    fireEvent.scroll(document);

    await act(async () => { await vi.advanceTimersByTimeAsync(SESSION_IDLE_MS); });

    expect(heartbeat).toHaveBeenCalled();
    expect(expired).toHaveBeenCalledTimes(1);
    window.removeEventListener(SESSION_EXPIRED_EVENT, expired);
  });
});
