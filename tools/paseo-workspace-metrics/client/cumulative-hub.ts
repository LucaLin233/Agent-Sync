/** One finished cumulative read for a workspace; `rate: null` means no valid snapshot. */
export interface CumulativeReading {
  rate: number | null;
  error: string | null;
}

/**
 * Captured when a read starts. `cleared`/`epoch` reject a reply from a scope that
 * has since changed. `seq` is a monotonic request signature: a reply is accepted
 * only when it is newer than the last accepted one, so an older read that returns
 * late never replaces fresher data, while a newer read that returns second still
 * overwrites an older reading already shown.
 */
export interface CumulativeTicket {
  cleared: number;
  epoch: number;
  seq: number;
}

/**
 * The cumulative reading both entry points share. The composer pill runtime and
 * the panel run the same cumulative RPC; whichever finishes first feeds the
 * shared label; an overlapping read never voids another's valid reply, and the
 * monotonic request signature only stops a late older reply from displacing a
 * newer adopted one.
 */
export function createCumulativeHub() {
  const entries = new Map<string, CumulativeReading>();
  const adoptedSeq = new Map<string, number>();
  const clearedAt = new Map<string, number>();
  const listeners = new Set<() => void>();
  let clears = 0;
  let epoch = 0;
  let seq = 0;

  const notify = () => {
    for (const listener of listeners) listener();
  };

  return {
    /** The stored entry itself; unchanged until an accepted read replaces it. */
    read(workspaceId: string): CumulativeReading | undefined {
      return entries.get(workspaceId);
    },
    begin(workspaceId: string): CumulativeTicket {
      return {
        cleared: clearedAt.get(workspaceId) ?? 0,
        epoch,
        seq: ++seq,
      };
    },
    /**
     * Applies a read from the current scope whose request signature is newer
     * than the last adopted one. This is the only ordering gate: overlapping
     * requests never void each other, the first reply to arrive is shown, and a
     * later-started request that answers second still replaces it.
     */
    publish(workspaceId: string, ticket: CumulativeTicket, reading: CumulativeReading): boolean {
      if (ticket.epoch !== epoch) return false;
      if (ticket.cleared !== (clearedAt.get(workspaceId) ?? 0)) return false;
      if (ticket.seq <= (adoptedSeq.get(workspaceId) ?? 0)) return false;
      adoptedSeq.set(workspaceId, ticket.seq);
      // A fresh object per accepted read keeps `read()` a plain snapshot.
      entries.set(workspaceId, { rate: reading.rate, error: reading.error });
      notify();
      return true;
    },
    /** Voids in-flight reads for a workspace but keeps the reading already shown. */
    invalidate(workspaceId: string) {
      clearedAt.set(workspaceId, ++clears);
    },
    /** Drops what a workspace shows and voids its in-flight reads. */
    clear(workspaceId: string) {
      clearedAt.set(workspaceId, ++clears);
      adoptedSeq.delete(workspaceId);
      if (entries.delete(workspaceId)) notify();
    },
    /** A settings generation change: every workspace and every in-flight read. */
    clearAll() {
      epoch += 1;
      entries.clear();
      adoptedSeq.clear();
      notify();
    },
    /** Called whenever any entry this hub holds changes; re-read `read()`. */
    subscribeAll(listener: () => void): () => void {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}

export type CumulativeHub = ReturnType<typeof createCumulativeHub>;
