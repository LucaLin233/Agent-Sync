import type { RegenerateResult } from "./regenerate";

/**
 * One manual title generation running in the plugin process. The job exists
 * because the daemon's plugin RPC transport abandons a call after 30 s; the
 * model work is therefore started here and the panel watches this state
 * instead of holding one long RPC.
 */
export type RegenerationJobState =
  | { status: "running"; jobId: string }
  | { status: "done"; jobId: string; result: RegenerateResult };

export type StartRegenerationOutcome =
  | { status: "started"; jobId: string }
  | { status: "busy" };

export type RegenerationStatusOutcome =
  | { status: "running"; jobId: string }
  | { status: "done"; jobId: string; result: RegenerateResult }
  | { status: "unknown" };

interface JobRecord {
  jobId: string;
  /** The mutual-exclusion key: a workspace, or one selected session. */
  claimKey: string;
  workspaceId: string;
  startedAt: number;
  finishedAt: number | null;
  result: RegenerateResult | null;
  cancelled: boolean;
}

export interface RegenerationJobOptions {
  now?: () => number;
  /** How long a finished job stays readable, so a remounted panel sees the result. */
  retentionMs?: number;
  /** Upper bound on retained jobs; the oldest finished job is dropped first. */
  maxRetained?: number;
  /** Creates the sampling id; injectable for deterministic tests. */
  id?: () => string;
}

const DEFAULT_RETENTION_MS = 5 * 60 * 1000;
const DEFAULT_MAX_RETAINED = 50;

/**
 * One line per failed job, keyed by its jobId so it can be matched with the
 * panel's request. It carries identifiers, the terminal reason and the elapsed
 * time only: never conversation text, titles, prompts or raw exception text.
 */
function logFailure(job: JobRecord, result: RegenerateResult): void {
  try {
    // One argument, so the line stays a single searchable record in stderr and plugin logs.
    const fields = {
      jobId: job.jobId,
      workspaceId: job.workspaceId,
      ...(result.agentId ? { agentId: result.agentId } : {}),
      status: result.status,
      reason: result.reason ?? "unspecified",
      elapsedMs: job.finishedAt !== null ? job.finishedAt - job.startedAt : null,
    };
    console.warn(`[paseo-chinese-titles] regeneration job failed ${JSON.stringify(fields)}`);
  } catch {
    // Diagnostics must never change the job's outcome.
  }
}

/**
 * In-memory job registry. It is deliberately not a persistent queue: a daemon
 * or plugin restart drops the job, the panel shows `unknown`, and no stale work
 * writes a title after its owner is gone.
 */
export class RegenerationJobs {
  private readonly jobs = new Map<string, JobRecord>();
  private readonly now: () => number;
  private readonly retentionMs: number;
  private readonly maxRetained: number;
  private readonly makeId: () => string;
  private disposed = false;

  constructor(options: RegenerationJobOptions = {}) {
    this.now = options.now ?? Date.now;
    this.retentionMs = options.retentionMs ?? DEFAULT_RETENTION_MS;
    this.maxRetained = options.maxRetained ?? DEFAULT_MAX_RETAINED;
    this.makeId = options.id ?? (() => `rg_${this.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`);
  }

  /** True while a job holding this exact claim is running. */
  isRunning(claimKey: string): boolean {
    for (const job of this.jobs.values()) {
      if (job.claimKey === claimKey && job.result === null && !job.cancelled) return true;
    }
    return false;
  }

  /**
   * Registers a job and starts `run`. `run` receives a cancellation probe the
   * worker must check before every write; it is true once the registry is
   * disposed (plugin reload or stop).
   */
  start(
    input: { workspaceId: string; claimKey: string },
    run: (isCancelled: () => boolean) => Promise<RegenerateResult>,
  ): StartRegenerationOutcome {
    this.prune();
    if (this.disposed || this.isRunning(input.claimKey)) return { status: "busy" };
    const job: JobRecord = {
      jobId: this.makeId(),
      claimKey: input.claimKey,
      workspaceId: input.workspaceId,
      startedAt: this.now(),
      finishedAt: null,
      result: null,
      cancelled: false,
    };
    this.jobs.set(job.jobId, job);
    void run(() => job.cancelled || this.disposed)
      .then((result) => {
        if (job.cancelled || this.disposed) return;
        job.result = result;
        job.finishedAt = this.now();
        if (result.status === "error") logFailure(job, result);
      })
      .catch(() => {
        if (job.cancelled || this.disposed) return;
        job.result = { status: "error", reason: "internal_failed", workspaceUpdated: false, sessionUpdated: false };
        job.finishedAt = this.now();
        logFailure(job, job.result);
      })
      .finally(() => this.prune());
    return { status: "started", jobId: job.jobId };
  }

  /**
   * Reads a job by id, or the newest job of one workspace so a remounted panel
   * can reattach to work that is still running.
   */
  status(input: { jobId?: string; workspaceId?: string }): RegenerationStatusOutcome {
    this.prune();
    const job = input.jobId
      ? this.jobs.get(input.jobId)
      : this.newestForWorkspace(input.workspaceId ?? "");
    if (!job || job.cancelled) return { status: "unknown" };
    if (!job.result) return { status: "running", jobId: job.jobId };
    return { status: "done", jobId: job.jobId, result: job.result };
  }

  /** Stops retaining state and makes every running job refuse its next write. */
  dispose(): void {
    this.disposed = true;
    for (const job of this.jobs.values()) job.cancelled = true;
    this.jobs.clear();
  }

  private newestForWorkspace(workspaceId: string): JobRecord | null {
    let newest: JobRecord | null = null;
    for (const job of this.jobs.values()) {
      if (job.workspaceId !== workspaceId || job.cancelled) continue;
      if (!newest || job.startedAt >= newest.startedAt) newest = job;
    }
    return newest;
  }

  private prune(): void {
    const cutoff = this.now() - this.retentionMs;
    for (const [id, job] of this.jobs) {
      if (job.finishedAt !== null && job.finishedAt < cutoff) this.jobs.delete(id);
    }
    if (this.jobs.size <= this.maxRetained) return;
    const finished = [...this.jobs.values()]
      .filter((job) => job.result !== null)
      .sort((left, right) => left.startedAt - right.startedAt);
    for (const job of finished) {
      if (this.jobs.size <= this.maxRetained) break;
      this.jobs.delete(job.jobId);
    }
  }
}
