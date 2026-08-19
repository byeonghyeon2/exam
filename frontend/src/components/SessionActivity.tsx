import { useEffect } from 'react';
import { endpoints } from '../api/queries';
import { ApiError } from '../api/client';

export const SESSION_IDLE_MS = 30 * 60 * 1000;
export const SESSION_HEARTBEAT_MS = 60 * 1000;
export const SESSION_EXPIRED_EVENT = 'hapgyeokbiseo:session-expired';

export function SessionActivity() {
  useEffect(() => {
    let lastActivityAt = Date.now();
    let lastSyncedAt = Date.now();
    let dirty = false;
    let syncing = false;
    let expired = false;
    let idleTimer = 0;

    const expire = () => {
      if (expired) return;
      expired = true;
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
    };
    const scheduleExpiration = () => {
      window.clearTimeout(idleTimer);
      idleTimer = window.setTimeout(expire, Math.max(0, SESSION_IDLE_MS - (Date.now() - lastActivityAt)));
    };
    const syncActivity = async () => {
      if (expired || syncing || !dirty) return;
      const idleMilliseconds = Date.now() - lastActivityAt;
      if (idleMilliseconds >= SESSION_IDLE_MS) {
        expire();
        return;
      }
      syncing = true;
      dirty = false;
      try {
        await endpoints.sessionActivity(Math.floor(idleMilliseconds / 1000));
        lastSyncedAt = Date.now();
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) expire();
        else dirty = true;
      } finally {
        syncing = false;
      }
    };
    const recordActivity = () => {
      if (expired || document.visibilityState !== 'visible') return;
      lastActivityAt = Date.now();
      dirty = true;
      scheduleExpiration();
      if (lastActivityAt - lastSyncedAt >= SESSION_HEARTBEAT_MS) void syncActivity();
    };
    const handleVisibility = () => {
      if (document.visibilityState === 'hidden') {
        void syncActivity();
      } else if (Date.now() - lastActivityAt >= SESSION_IDLE_MS) {
        expire();
      } else {
        scheduleExpiration();
      }
    };
    const activityEvents: Array<keyof DocumentEventMap> = ['pointerdown', 'keydown', 'touchstart', 'scroll'];
    activityEvents.forEach(event => document.addEventListener(event, recordActivity, { passive: true }));
    document.addEventListener('visibilitychange', handleVisibility);
    const heartbeat = window.setInterval(() => void syncActivity(), SESSION_HEARTBEAT_MS);
    scheduleExpiration();
    return () => {
      activityEvents.forEach(event => document.removeEventListener(event, recordActivity));
      document.removeEventListener('visibilitychange', handleVisibility);
      window.clearInterval(heartbeat);
      window.clearTimeout(idleTimer);
    };
  }, []);

  return null;
}
