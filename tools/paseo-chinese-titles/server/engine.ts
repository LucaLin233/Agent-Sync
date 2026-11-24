import { promises as fs } from "node:fs";
import { basename, join, resolve } from "node:path";
import type { PaseoAgent, PaseoApi, PaseoProject, PaseoWorkspace } from "./paseo-types";
import type { PluginSettings } from "@getpaseo/plugin/server";
import type { ChineseTitlesSettings } from "../shared/settings";
import { distinctWorkspaceTitle, isProvisional } from "../shared/title.ts";
import {
  createBootstrapWorkspaceViaCli,
  listAgentIdsViaCli,
  listProjectIdsViaCli,
  listProjectsViaCli,
  listWorkspaceIdsViaCli,
  renameAgentViaCli,
  renameProjectViaCli,
} from "./cli.ts";
import { pickFirstTask, type FirstTaskFact } from "../shared/first-task.ts";
import { selectableSessionsFor } from "../shared/session-options.ts";
import { isDiscontinuous, readSessionConversation, readSessionNamingMaterial } from "./conversation.ts";
import {
  generateConversationTitle,
  generateSessionTitle,
  generateTitle,
  HELPER_WORKSPACE_TITLE,
  isHelperAgent,
  type GenerationResult,
} from "./helper.ts";
import {
  afterSessionFailure,
  afterSessionSuccess,
  isLegacyRepairCandidate,
  isUnrepairedLegacyEntry,
  planSessionNaming,
  type SessionNamingState,
} from "../shared/session-naming.ts";
import { planWorkspaceTitleSeed, seededWorkspaceTitle, type WorkspaceMetadata, type WorkspaceSeedPlan } from "./seed.ts";
import {
  regenerateWorkspaceTitle as runWorkspaceRegeneration,
  RPC_DEADLINE_MS,
  type RegenerateResult,
  type RegenerateScope,
} from "./regenerate.ts";
import { helperDirectory, isInsideDirectory, loadState, markBaseline, safePluginPath, saveState, type ChineseTitlesState } from "./state.ts";

const STALE_GENERATING_MS = 3 * 60 * 1000;
/**
 * A session gets the first naming attempt after its first substantive answer
 * and at most one more on a later completed turn. Exhausting both stops.
 */
const MAX_SESSION_ATTEMPTS = 2;
/**
 * Paseo runs lifecycle hooks with a 30 s transport timeout. Keep the whole
 * naming step (scan + model + one rename + verification) below it so a slow
 * model still returns an enum failure instead of being abandoned mid-write.
 */
const SESSION_NAMING_BUDGET_MS = 20_000;
const SESSION_MODEL_TIMEOUT_MS = 15_000;
/** Below this the CLI rename plus its verification cannot finish in budget. */
const RENAME_MIN_BUDGET_MS = 3_000;
/** Keep enough of the rename budget for the post-write refresh. */
const RENAME_VERIFY_RESERVE_MS = 1_000;
const RENAME_MAX_TIMEOUT_MS = 10_000;
const BOOTSTRAP_TITLE = "中文标题引导";
const bootstrapDirectory = () => safePluginPath("helper", "bootstrap");

function isExactDirectory(path: string | null | undefined, directory: string): boolean {
  if (!path) return false;
  return resolve(path) === resolve(directory);
}

type Settings = PluginSettings<typeof import("../shared/settings").settingsSchema>;

/**
 * The one write the tests need to substitute: the official CLI is the only
 * way to rename a session, and a unit test has no daemon to call. Production
 * always uses the default.
 */
export interface EngineDependencies {
  renameAgent?: (
    settings: ChineseTitlesSettings,
    agentId: string,
    title: string,
    timeoutMs?: number,
  ) => Promise<{ ok: boolean; failure?: string }>;
}

export interface ReconcileSummary {
  ok: boolean;
  projects: number;
  workspaces: number;
  agents: number;
}

function now(): string {
  return new Date().toISOString();
}

function isSubagent(agent: { labels?: Readonly<Record<string, string>> }): boolean {
  const parent = agent.labels?.["paseo.parent-agent-id"];
  return typeof parent === "string" && parent.length > 0;
}

export class ChineseTitlesEngine {
  private state: ChineseTitlesState | null = null;
  private readonly ready: Promise<void>;
  private paseo: PaseoApi | null = null;
  private sdkTimer: ReturnType<typeof setInterval> | null = null;
  private cliTimer: ReturnType<typeof setInterval> | null = null;
  private reconciling = false;
  private readonly processingProjects = new Set<string>();
  private readonly processingWorkspaces = new Set<string>();
  private readonly processingAgents = new Set<string>();
  private readonly bootstrapWorkspaceIds = new Set<string>();
  private bootstrapSucceeded = false;
  private bootstrapProjectId: string | null = null;
  private disposed = false;

  private readonly settings: Settings;
  private readonly renameAgent: NonNullable<EngineDependencies["renameAgent"]>;

  constructor(settings: Settings, dependencies: EngineDependencies = {}) {
    this.settings = settings;
    this.renameAgent = dependencies.renameAgent ??
      ((values, agentId, title, timeoutMs) => renameAgentViaCli(values, agentId, title, timeoutMs));
    this.ready = this.load();
  }

  private async load(): Promise<void> {
    this.state = await loadState();
  }

  async dispose(): Promise<void> {
    this.disposed = true;
    if (this.sdkTimer) clearInterval(this.sdkTimer);
    if (this.cliTimer) clearInterval(this.cliTimer);
    this.sdkTimer = null;
    this.cliTimer = null;
  }

  private async currentSettings(): Promise<ChineseTitlesSettings | null> {
    const result = await this.settings.read();
    if (result.status !== "ready") {
      console.warn("[paseo-chinese-titles] settings invalid");
      return null;
    }
    return result.values;
  }

  private attach(paseo: PaseoApi): void {
    this.paseo = paseo;
    if (!this.sdkTimer && !this.disposed) {
      this.sdkTimer = setInterval(() => {
        const current = this.paseo;
        if (current) void this.reconcile(current).catch(() => undefined);
      }, 20_000);
    }
  }

  /**
   * Detects a new project through the official CLI when no SDK context exists.
   * A background workspace in our neutral directory is attached to that
   * project, which gives the create hook a same-daemon PaseoApi. It is archived
   * immediately and never receives a user task.
   */
  startCliPolling(): void {
    if (this.cliTimer || this.disposed) return;
    this.cliTimer = setInterval(() => {
      void (async () => {
        const settings = await this.currentSettings();
        if (settings) await this.bootstrapFromCliOnce(settings);
      })().catch(() => undefined);
    }, 20_000);
  }

  async usePaseo(paseo: PaseoApi): Promise<void> {
    await this.ready;
    this.attach(paseo);
  }

  async initializeFromCli(projectIds: readonly string[], workspaceIds: readonly string[], agentIds: readonly string[]): Promise<void> {
    await this.ready;
    if (!this.state || this.state.initialized) return;
    markBaseline(this.state, projectIds, workspaceIds, agentIds);
    await saveState(this.state);
  }

  /**
   * Runs inside workspace.create.before. Paseo v0.17.3's native auto-name
   * replaces a title that is empty or exactly the first-prompt title, so seed a
   * different Chinese fallback before the asynchronous native summary starts.
   */
  async workspaceTitleSeed(request: {
    title?: string | null;
    background?: boolean;
    metadata?: WorkspaceMetadata | null;
    firstAgentContext?: { prompt?: string } | null;
    source?: { kind: string; path?: string } | null;
  }): Promise<WorkspaceSeedPlan | null> {
    try {
      await this.ready;
      const settings = await this.currentSettings();
      if (!settings?.autoNameWorkspaces) return null;
      if (request.background) return null;
      if (request.title?.trim() === HELPER_WORKSPACE_TITLE) return null;
      if (request.source?.kind === "directory" && request.source.path &&
        isInsideDirectory(request.source.path, helperDirectory())) return null;
      return planWorkspaceTitleSeed({
        title: request.title,
        prompt: request.firstAgentContext?.prompt,
        metadata: request.metadata,
        maxChars: settings.titleMaxChars,
      });
    } catch {
      // Seeding is best-effort and must never block workspace creation.
      return null;
    }
  }

  /**
   * Manual per-workspace and/or per-session regeneration. It ignores automatic
   * baseline states and the auto-name switches, and shares the automatic claim
   * sets so the two paths cannot write the same workspace or session at once.
   */
  async regenerateWorkspaceTitle(
    workspaceId: string,
    paseo: PaseoApi,
    agentId?: string,
    scope?: RegenerateScope,
  ): Promise<RegenerateResult> {
    // Start the budget before any await: a slow state/settings read must not
    // let the RPC write after the daemon's transport timeout.
    const deadlineAt = Date.now() + RPC_DEADLINE_MS;
    await this.ready;
    const settings = await this.currentSettings();
    if (!settings) {
      return { status: "error", reason: "settings_unavailable", workspaceUpdated: false, sessionUpdated: false };
    }
    this.attach(paseo);
    const result = await runWorkspaceRegeneration({
      paseo,
      settings,
      workspaceId,
      ...(agentId ? { agentId } : {}),
      ...(scope ? { scope } : {}),
      claims: this.processingWorkspaces,
      agentClaims: this.processingAgents,
      deadlineAt,
      generateConversation: (request, timeoutMs, generateDeadlineAt) =>
        generateConversationTitle(paseo, settings, request, { timeoutMs, deadlineAt: generateDeadlineAt }),
      listAgents: () => this.listAgents(paseo),
      readConversation: (sessionId) => readSessionConversation(paseo, sessionId, { deadlineAt }),
      renameSession: async (sessionId, title, timeoutMs) => {
        const renamed = await renameAgentViaCli(settings, sessionId, title, timeoutMs);
        return renamed.ok ? { ok: true } : { ok: false, failure: renamed.failure ?? "failed" };
      },
    });
    if (this.state) {
      let changed = false;
      if (result.status === "done" || result.status === "partial") {
        if (result.workspaceUpdated && result.title) {
          this.state.workspaces[workspaceId] = { status: "done", at: now(), title: result.title };
          changed = true;
        }
        if (result.sessionUpdated && result.agentId && result.title) {
          this.state.agents[result.agentId] = { status: "done", at: now(), title: result.title };
          changed = true;
        }
      }
      if (changed) await saveState(this.state);
    }
    return result;
  }

  /**
   * The sessions the panel may offer for this workspace. The list is display
   * metadata only; the selection itself is validated again by
   * regenerateWorkspaceTitle before any text is read.
   */
  async listWorkspaceSessions(
    workspaceId: string,
    paseo: PaseoApi,
  ): Promise<Array<{ id: string; title: string | null; lastActivityAt: string | null }>> {
    this.attach(paseo);
    const workspace = await paseo.workspaces.ref(workspaceId).refresh();
    // Never expose another workspace's sessions, a background workspace or the
    // plugin's own helper directory through this list.
    if (!workspace || workspace.archivingAt || workspace.background ||
      isInsideDirectory(workspace.workspaceDirectory, helperDirectory())) {
      return [];
    }
    const agents = await this.listAgents(paseo);
    return selectableSessionsFor(
      agents.filter((agent) => !isInsideDirectory(agent.cwd, helperDirectory())).map((agent) => ({
        id: agent.id,
        workspaceId: agent.workspaceId,
        title: agent.title,
        background: agent.background,
        internal: agent.internal,
        archivedAt: agent.archivedAt,
        labels: agent.labels,
        metadata: agent.metadata,
        lastActivityAt: agent.lastUserMessageAt ?? agent.updatedAt ?? null,
        createdAt: agent.createdAt,
      })),
      workspaceId,
    );
  }

  async onWorkspaceCreated(workspace: { id: string; projectId: string }, paseo: PaseoApi): Promise<void> {
    await this.ready;
    if (!this.state) return;
    this.attach(paseo);
    await this.ensureBaseline(paseo, { workspaceId: workspace.id });
    const snapshot = await paseo.workspaces.ref(workspace.id).refresh();
    if (!snapshot) return;
    const isBootstrap =
      snapshot.background === true &&
      isExactDirectory(snapshot.workspaceDirectory, bootstrapDirectory()) &&
      workspace.projectId === this.bootstrapProjectId &&
      (this.bootstrapWorkspaceIds.has(workspace.id) || snapshot.title === BOOTSTRAP_TITLE);
    if (isBootstrap) {
      this.bootstrapWorkspaceIds.delete(workspace.id);
      this.bootstrapProjectId = null;
      delete this.state.workspaces[workspace.id];
      await paseo.workspaces.ref(workspace.id).archive().catch(() => undefined);
      await this.reconcile(paseo);
      return;
    }
    if (snapshot.background || isInsideDirectory(snapshot.workspaceDirectory, helperDirectory())) return;
    this.state.workspaces[workspace.id] ??= { status: "pending", at: now() };
    await saveState(this.state);
  }

  async onAgentCreated(agentId: string, paseo: PaseoApi): Promise<void> {
    await this.ready;
    if (!this.state) return;
    this.attach(paseo);
    await this.ensureBaseline(paseo, { agentId });
    const snapshot = await paseo.agents.ref(agentId).refresh();
    const agent = snapshot?.agent;
    if (!agent || agent.background || isSubagent(agent) || isHelperAgent(agent) || isInsideDirectory(agent.cwd, helperDirectory())) return;
    this.state.agents[agentId] ??= { status: "pending", at: now() };
    await saveState(this.state);
  }

  /**
   * Before a turn only the workspace may be named, from its first task. Session
   * naming waits for a finished answer, so it is not attempted here.
   */
  async onTurnBefore(agentId: string, turnId: string | null, paseo: PaseoApi): Promise<void> {
    await this.ready;
    if (!this.state) return;
    this.attach(paseo);
    await this.ensureBaseline(paseo, { agentId });
    await this.processAgent(agentId, turnId, paseo, "before", false);
  }

  /**
   * After a turn, session naming runs only when the turn completed and its
   * answer is substantive. A failed, canceled or tool-only turn never spends a
   * naming attempt.
   */
  async onTurnAfter(agentId: string, turnId: string | null, paseo: PaseoApi, completed: boolean): Promise<void> {
    await this.ready;
    if (!this.state) return;
    this.attach(paseo);
    await this.ensureBaseline(paseo, { agentId });
    await this.processAgent(agentId, turnId, paseo, "after", completed);
  }

  async reconcile(paseo: PaseoApi): Promise<ReconcileSummary> {
    await this.ready;
    if (!this.state || this.reconciling) return { ok: false, projects: 0, workspaces: 0, agents: 0 };
    this.attach(paseo);
    this.reconciling = true;
    let projects = 0;
    let workspaces = 0;
    let agents = 0;
    try {
      await this.ensureBaseline(paseo);
      await this.recoverStaleGenerating();
      const settings = await this.currentSettings();
      if (!settings) return { ok: false, projects, workspaces, agents };

      const allProjects = await this.listProjects(paseo);
      const allWorkspaces = await this.listWorkspaces(paseo);
      const allAgents = await this.listAgents(paseo);
      const workspaceById = new Map(allWorkspaces.map((workspace) => [workspace.id, workspace]));

      for (const workspace of allWorkspaces) {
        if (workspace.background || isInsideDirectory(workspace.workspaceDirectory, helperDirectory())) continue;
        this.state.workspaces[workspace.id] ??= { status: "pending", at: now() };
      }
      for (const agent of allAgents) {
        if (agent.background || isSubagent(agent) || isHelperAgent(agent) || isInsideDirectory(agent.cwd, helperDirectory())) continue;
        this.state.agents[agent.id] ??= { status: "pending", at: now() };
      }

      if (settings.autoNameProjects) {
        for (const project of allProjects) {
          if (this.state.projects[project.projectId]?.status === "legacy") continue;
          if (isInsideDirectory(project.projectRootPath, helperDirectory())) {
            this.state.projects[project.projectId] = { status: "skipped", at: now() };
            continue;
          }
          if (await this.processProject(project, settings, paseo)) projects += 1;
        }
      }

      for (const agent of allAgents) {
        if (agent.background || isSubagent(agent) || isHelperAgent(agent) || isInsideDirectory(agent.cwd, helperDirectory())) continue;
        if (!agent.workspaceId || !agent.lastUserMessageAt) continue;
        // A reconcile scan has no turn id, so it may only make the first naming
        // attempt. Retries need a provably different completed turn.
        if (this.state.agents[agent.id]?.status !== "pending") continue;
        if ((this.state.agents[agent.id]?.attempts ?? 0) > 0) continue;
        if (!workspaceById.has(agent.workspaceId)) continue;
        const before = this.state.agents[agent.id]?.status;
        await this.processAgent(agent.id, null, paseo, "after", false);
        if (before === "pending" && this.state.agents[agent.id]?.status !== "pending") agents += 1;
      }

      await saveState(this.state);
      return { ok: true, projects, workspaces, agents };
    } catch {
      console.warn("[paseo-chinese-titles] reconcile failed");
      return { ok: false, projects, workspaces, agents };
    } finally {
      this.reconciling = false;
    }
  }

  private async bootstrapFromCliOnce(settings: ChineseTitlesSettings): Promise<void> {
    await this.ready;
    if (!this.state || this.disposed || this.paseo || this.bootstrapSucceeded) return;
    if (!settings.autoNameProjects) return;
    if (!this.state.initialized) {
      const [projects, workspaces, agents] = await Promise.all([
        listProjectIdsViaCli(settings),
        listWorkspaceIdsViaCli(settings),
        listAgentIdsViaCli(settings),
      ]);
      if (projects && workspaces && agents) await this.initializeFromCli(projects, workspaces, agents);
      return;
    }
    const projects = await listProjectsViaCli(settings);
    if (!projects) return;
    const target = projects.find((project) =>
      !this.state?.projects[project.projectId] && !isInsideDirectory(project.path, helperDirectory()));
    if (!target) return;
    const directory = safePluginPath("helper", "bootstrap");
    await fs.mkdir(directory, { recursive: true, mode: 0o700 });
    this.bootstrapProjectId = target.projectId;
    const created = await createBootstrapWorkspaceViaCli(settings, target.projectId, directory, BOOTSTRAP_TITLE);
    if (!created.ok) {
      this.bootstrapProjectId = null;
      return;
    }
    this.bootstrapSucceeded = true;
    if (created.workspaceId) this.bootstrapWorkspaceIds.add(created.workspaceId);
  }

  private async ensureBaseline(paseo: PaseoApi, except?: { workspaceId?: string; agentId?: string }): Promise<void> {
    if (!this.state || this.state.initialized) return;
    const projects = await this.listProjects(paseo);
    const workspaces = await this.listWorkspaces(paseo);
    const agents = await this.listAgents(paseo);
    markBaseline(
      this.state,
      projects.map((project) => project.projectId),
      workspaces.filter((workspace) => workspace.id !== except?.workspaceId).map((workspace) => workspace.id),
      agents.filter((agent) => agent.id !== except?.agentId).map((agent) => agent.id),
    );
    if (except?.workspaceId) this.state.workspaces[except.workspaceId] ??= { status: "pending", at: now() };
    if (except?.agentId) this.state.agents[except.agentId] ??= { status: "pending", at: now() };
    await saveState(this.state);
  }

  private async recoverStaleGenerating(): Promise<void> {
    if (!this.state) return;
    const cutoff = Date.now() - STALE_GENERATING_MS;
    for (const group of [this.state.projects, this.state.workspaces, this.state.agents]) {
      for (const entry of Object.values(group)) {
        if (entry.status === "generating" && Date.parse(entry.at) < cutoff) {
          entry.status = "pending";
          entry.at = now();
        }
      }
    }
  }

  private async listProjects(paseo: PaseoApi): Promise<PaseoProject[]> {
    const result = await paseo.projects.list();
    return [...(result.projects ?? [])] as PaseoProject[];
  }

  private async listWorkspaces(paseo: PaseoApi): Promise<PaseoWorkspace[]> {
    const result = await paseo.workspaces.list();
    return [...(result.entries ?? [])] as PaseoWorkspace[];
  }

  private async listAgents(paseo: PaseoApi): Promise<PaseoAgent[]> {
    const out: PaseoAgent[] = [];
    let cursor: string | undefined;
    for (let page = 0; page < 50; page += 1) {
      const result = await paseo.agents.list({
        includeBackground: true,
        page: { limit: 200, ...(cursor ? { cursor } : {}) },
      });
      for (const entry of result.entries ?? []) out.push(entry.agent);
      if (!result.pageInfo?.hasMore || !result.pageInfo.nextCursor) break;
      cursor = result.pageInfo.nextCursor;
    }
    return out;
  }

  private async processProject(project: PaseoProject, settings: ChineseTitlesSettings, paseo: PaseoApi): Promise<boolean> {
    if (!this.state || this.processingProjects.has(project.projectId)) return false;
    const existing = this.state.projects[project.projectId];
    if (existing && existing.status !== "pending" && existing.status !== "error") return false;
    if (project.projectCustomName?.trim()) {
      this.state.projects[project.projectId] = { status: "skipped", at: now() };
      await saveState(this.state);
      return false;
    }
    this.processingProjects.add(project.projectId);
    this.state.projects[project.projectId] = { status: "generating", at: now() };
    await saveState(this.state);
    try {
      const generated = await generateTitle(paseo, settings, {
        kind: "project",
        projectName: project.projectDisplayName,
        baseName: basename(project.projectRootPath),
        projectId: project.projectId,
        maxChars: settings.projectMaxChars,
      });
      // Re-read the original override immediately before the only write.
      const latest = (await this.listProjects(paseo)).find((entry) => entry.projectId === project.projectId);
      if (!latest || latest.projectCustomName?.trim()) {
        this.state.projects[project.projectId] = { status: "skipped", at: now() };
        return false;
      }
      const renamed = await renameProjectViaCli(settings, project.projectId, generated.title);
      if (!renamed.ok) {
        this.state.projects[project.projectId] = { status: "error", at: now(), error: renamed.failure ?? "failed" };
        console.warn("[paseo-chinese-titles] project rename CLI failed", { projectId: project.projectId, code: renamed.failure ?? "failed" });
        return false;
      }
      const verified = (await this.listProjects(paseo)).find((entry) => entry.projectId === project.projectId);
      if (verified?.projectCustomName?.trim() !== generated.title) {
        this.state.projects[project.projectId] = { status: "error", at: now(), error: "verification_failed" };
        return false;
      }
      this.state.projects[project.projectId] = {
        status: "done",
        at: now(),
        title: generated.title,
        ...(generated.errorCode ? { error: generated.errorCode } : {}),
      };
      return true;
    } catch {
      this.state.projects[project.projectId] = { status: "error", at: now(), error: "internal_failed" };
      return false;
    } finally {
      this.processingProjects.delete(project.projectId);
      if (this.state) await saveState(this.state);
    }
  }

  private async processAgent(
    agentId: string,
    turnId: string | null,
    paseo: PaseoApi,
    phase: "before" | "after",
    completed: boolean,
  ): Promise<void> {
    if (!this.state || this.processingAgents.has(agentId)) return;
    // A finished entity does no more work on later turns: no extra refresh,
    // timeline read or model call. Only a not-yet-repaired legacy
    // `done + model_failed|provider_unavailable` entry is still inspected,
    // because whether it may be repaired depends on the live title.
    const prior = this.state.agents[agentId];
    if (prior && prior.status !== "pending" && prior.status !== "error" &&
      !isUnrepairedLegacyEntry(prior)) {
      // Nothing left to name for this session. Only a workspace still waiting
      // for its own first task can need this turn, and an unknown workspace
      // (an older state file) falls through once to record it.
      const workspacePending = prior.workspaceId !== undefined &&
        this.state.workspaces[prior.workspaceId]?.status === "pending";
      if (prior.workspaceId !== undefined && !workspacePending) return;
    }
    // Claim before any await so two hooks cannot both pass the state check.
    this.processingAgents.add(agentId);
    try {
      const settings = await this.currentSettings();
      if (!settings) return;
      const refreshed = await paseo.agents.ref(agentId).refresh();
      const agent = refreshed?.agent;
      if (!agent || agent.background || isSubagent(agent) || isHelperAgent(agent) || isInsideDirectory(agent.cwd, helperDirectory())) {
        this.state.agents[agentId] = { ...this.state.agents[agentId], status: "skipped", at: now() };
        return;
      }
      if (!agent.workspaceId) {
        this.state.agents[agentId] = { ...this.state.agents[agentId], status: "skipped", at: now() };
        return;
      }
      const workspace = await paseo.workspaces.ref(agent.workspaceId).refresh();
      if (!workspace || workspace.background || isInsideDirectory(workspace.workspaceDirectory, helperDirectory())) {
        this.state.agents[agentId] = { ...this.state.agents[agentId], status: "skipped", at: now() };
        return;
      }
      // Remember the workspace so a named session can skip later turns without
      // another refresh or timeline read. Persist once for an older state file.
      const remembered = this.state.agents[agentId]?.workspaceId === agent.workspaceId;
      this.state.agents[agentId] = {
        ...(this.state.agents[agentId] ?? { status: "pending", at: now() }),
        workspaceId: agent.workspaceId,
      };
      if (!remembered) await saveState(this.state);
      const prompt = await this.readFirstPrompt(paseo, agent.id);
      if (!prompt) return;

      // The workspace keeps its existing first-task behaviour: it is named from
      // the workspace's first task, on that first turn (or a reconcile scan).
      const onFirstTurn = turnId === null || prompt.turnId === null || prompt.turnId === turnId;
      if (onFirstTurn) {
        await this.nameWorkspaceFromFirstTask(paseo, settings, agent, workspace, prompt);
      }

      // A session is named only after a completed turn produced a real answer,
      // from the first question and that answer together.
      await this.nameSession(paseo, settings, agent, workspace, prompt, turnId, phase, completed);
    } catch {
      if (this.state) {
        this.state.agents[agentId] = { ...this.state.agents[agentId], status: "error", at: now(), error: "internal_failed" };
        await saveState(this.state);
      }
    } finally {
      this.processingAgents.delete(agentId);
    }
  }

  /** Workspace first-task naming; unchanged apart from living in its own step. */
  private async nameWorkspaceFromFirstTask(
    paseo: PaseoApi,
    settings: ChineseTitlesSettings,
    agent: PaseoAgent,
    workspace: PaseoWorkspace,
    prompt: { text: string; turnId: string | null; at: string },
  ): Promise<void> {
    if (!this.state) return;
    if (this.processingWorkspaces.has(workspace.id)) return;
    const workspaceState = this.state.workspaces[workspace.id];
    if (!settings.autoNameWorkspaces || workspaceState?.status !== "pending") return;
    this.processingWorkspaces.add(workspace.id);
    let workspaceResult: GenerationResult | null = null;
    try {
      const winner = await this.pickWorkspaceFirstTask(paseo, workspace.id, agent.id, prompt);
      const workspacePrompt = winner?.text ?? prompt.text;
      const seededTitle = seededWorkspaceTitle(workspace.metadata);
      const eligible = Boolean(
        winner !== null &&
        (isProvisional(workspace.title, workspacePrompt) ||
          (seededTitle !== null && workspace.title === seededTitle)),
      );
      if (!eligible) return;
      this.state.workspaces[workspace.id] = { status: "generating", at: now(), previousTitle: workspace.title ?? null };
      await saveState(this.state);
      workspaceResult = await generateTitle(paseo, settings, {
        kind: "workspace",
        prompt: workspacePrompt,
        projectName: workspace.projectDisplayName,
        baseName: workspace.name,
        projectId: workspace.projectId,
        maxChars: settings.titleMaxChars,
      });
      // Re-read the original override. Only one final write; no placeholder.
      const current = await paseo.workspaces.ref(workspace.id).refresh();
      const previous = this.state.workspaces[workspace.id]?.previousTitle ?? null;
      const finalTitle = distinctWorkspaceTitle(workspaceResult.title, workspacePrompt, settings.titleMaxChars);
      if (current && (current.title === previous || current.title === null || current.title === "" || isProvisional(current.title, workspacePrompt))) {
        await paseo.workspaces.ref(workspace.id).setTitle(finalTitle);
        const verified = await paseo.workspaces.ref(workspace.id).refresh();
        if (verified?.title !== finalTitle) {
          this.state.workspaces[workspace.id] = { status: "error", at: now(), error: "verification_failed" };
        } else {
          this.state.workspaces[workspace.id] = {
            status: "done",
            at: now(),
            title: finalTitle,
            previousTitle: previous,
            ...(workspaceResult.errorCode ? { error: workspaceResult.errorCode } : {}),
          };
        }
      } else {
        // A manual rename won the race; never clobber it.
        this.state.workspaces[workspace.id] = { status: "skipped", at: now(), previousTitle: previous };
      }
    } finally {
      this.processingWorkspaces.delete(workspace.id);
      if (this.state) await saveState(this.state);
    }
  }

  /**
   * Automatic session naming. The material is the first user question plus the
   * substantive answer of the completed turn, so the title reflects what the
   * session actually did instead of Paseo's first-sentence provisional text.
   *
   * One model failure keeps the provisional title and spends one attempt; only
   * a later, different completed turn may spend the second. A duplicate event,
   * a restart, a failed or tool-only turn and concurrent hooks never spend an
   * attempt they have not been recorded as spending.
   */
  private async nameSession(
    paseo: PaseoApi,
    settings: ChineseTitlesSettings,
    agent: PaseoAgent,
    workspace: PaseoWorkspace,
    prompt: { text: string; turnId: string | null; at: string },
    turnId: string | null,
    phase: "before" | "after",
    completed: boolean,
  ): Promise<void> {
    if (!this.state) return;
    // Sending a prompt is not an answer. Only the after-turn hook may name.
    if (phase !== "after") return;
    // Automatic session naming stays opt-in; a disabled setting leaves any
    // recorded state untouched for when the user enables it again.
    if (!settings.autoNameSessions) return;
    const agentState = this.state.agents[agent.id];
    // A legacy baseline entry is never touched, and a skipped entry has already
    // stopped. `done` is handled by the repair rule below.
    if (agentState?.status === "legacy" || agentState?.status === "skipped") return;

    const provisional = isProvisional(agent.title, prompt.text);
    // A named session is an explicit choice unless it still equals the title we
    // recorded for a not-yet-verified repair candidate.
    const repairCandidate = isLegacyRepairCandidate(agentState, agent.title);
    if (!provisional && !repairCandidate) {
      if (agentState?.status === "pending" || agentState?.status === "error" || agentState?.status === "generating") {
        this.state.agents[agent.id] = { ...agentState, status: "skipped", at: now() };
        await saveState(this.state);
      } else if (isUnrepairedLegacyEntry(agentState)) {
        // The live title differs from the recorded fallback: the user renamed
        // it. Close the one-time repair question so later turns do no work.
        this.state.agents[agent.id] = { ...agentState, repairUsed: true, at: now() };
        await saveState(this.state);
      }
      return;
    }

    // One deadline covers the scan, the model and the single write, so a slow
    // step cannot push the others past the daemon's hook timeout.
    const namingDeadlineAt = Date.now() + SESSION_NAMING_BUDGET_MS;
    let material: Awaited<ReturnType<typeof readSessionNamingMaterial>> = null;
    if (completed || repairCandidate || turnId === null) {
      material = await readSessionNamingMaterial(paseo, agent.id, { turnId, deadlineAt: namingDeadlineAt });
    }
    const hasAnswer = Boolean(material?.answer);
    // A reconcile scan has no turn id and no outcome. A readable substantive
    // answer is enough evidence that the first turn finished, but such a scan
    // may still only make the first attempt (see planSessionNaming).
    const plan = planSessionNaming({
      state: agentState,
      currentTitle: agent.title,
      prompt: prompt.text,
      hasAnswer,
      turnId,
      completed: completed || (turnId === null && hasAnswer),
      maxAttempts: MAX_SESSION_ATTEMPTS,
      provisional,
    });
    if (plan.kind === "generate") {
      // Persist the spent attempt before the model call. A crash or restart
      // during generation must not hand the same turn a fresh attempt, and a
      // duplicate event for this turn is then recognised by `lastTurnId`.
      this.state.agents[agent.id] = {
        status: "pending",
        at: now(),
        attempts: plan.attempt,
        lastTurnId: turnId,
        workspaceId: agent.workspaceId,
        ...(plan.repair ? { repairUsed: true } : {}),
      };
      await saveState(this.state);
      const generated = await generateSessionTitle(paseo, settings, {
        question: material?.question ?? prompt.text,
        answer: material?.answer ?? "",
        projectName: workspace.projectDisplayName,
        baseName: workspace.name,
        projectId: workspace.projectId,
        maxChars: settings.titleMaxChars,
      }, {
        timeoutMs: SESSION_MODEL_TIMEOUT_MS,
        deadlineAt: namingDeadlineAt,
      });
      // Keep the workspace on every recorded outcome so a finished session can
      // skip later turns without another refresh.
      const record = (state: SessionNamingState) => {
        this.state!.agents[agent.id] = { ...state, workspaceId: agent.workspaceId };
      };
      if (!generated.title) {
        // No usable model title: the live provisional title stays as it is.
        record(afterSessionFailure({
          errorCode: generated.errorCode ?? "model_failed",
          attempt: plan.attempt,
          maxAttempts: MAX_SESSION_ATTEMPTS,
          turnId,
          repair: plan.repair,
          at: now(),
        }));
        await saveState(this.state);
        return;
      }
      // Re-read immediately before the only write: a manual rename that landed
      // during generation must win, and an agent that disappeared, was archived
      // or moved to another workspace must not be renamed through a stale ref.
      const current = (await paseo.agents.ref(agent.id).refresh())?.agent;
      const liveTitle = current?.title?.trim() ?? "";
      // A missing agent refreshes to `undefined`; the provisional check would
      // treat that as "still ours", so existence is checked first.
      const stillOurs = current !== undefined &&
        (current.workspaceId ?? null) === (agent.workspaceId ?? null) &&
        !current.archivedAt &&
        (isProvisional(current.title, prompt.text) ||
          (plan.repair && liveTitle === agentState?.title?.trim()));
      if (!stillOurs) {
        this.state.agents[agent.id] = {
          status: "skipped",
          at: now(),
          attempts: plan.attempt,
          lastTurnId: turnId,
          workspaceId: agent.workspaceId,
          ...(plan.repair ? { repairUsed: true } : {}),
        };
        await saveState(this.state);
        return;
      }
      // The whole naming step shares one deadline. If the refresh and the model
      // used it up, the CLI write would outlive the hook timeout, so record a
      // timeout instead of starting a rename that cannot be verified in time.
      const remainingMs = namingDeadlineAt - Date.now();
      if (remainingMs < RENAME_MIN_BUDGET_MS) {
        record(afterSessionFailure({
          errorCode: "timeout",
          attempt: plan.attempt,
          maxAttempts: MAX_SESSION_ATTEMPTS,
          turnId,
          repair: plan.repair,
          at: now(),
        }));
        await saveState(this.state);
        return;
      }
      const renameTimeoutMs = Math.min(remainingMs - RENAME_VERIFY_RESERVE_MS, RENAME_MAX_TIMEOUT_MS);
      const renamed = await this.renameAgent(settings, agent.id, generated.title, renameTimeoutMs);
      const verified = renamed.ok ? await paseo.agents.ref(agent.id).refresh() : null;
      if (!renamed.ok || verified?.agent.title?.trim() !== generated.title) {
        // A failed or unverified write is not a model failure: spend this
        // attempt but keep the remaining one for a later completed turn, so a
        // transient CLI timeout does not strand the session forever.
        const error = renamed.ok ? "verification_failed" : renamed.failure ?? "failed";
        record(afterSessionFailure({
          errorCode: error,
          attempt: plan.attempt,
          maxAttempts: MAX_SESSION_ATTEMPTS,
          turnId,
          repair: plan.repair,
          at: now(),
        }));
        if (!renamed.ok) {
          console.warn("[paseo-chinese-titles] agent rename CLI failed", { agentId: agent.id, code: error });
        }
        await saveState(this.state);
        return;
      }
      record(afterSessionSuccess({
        title: generated.title,
        attempt: plan.attempt,
        turnId,
        repair: plan.repair,
        at: now(),
      }));
      await saveState(this.state);
      return;
    }
    if (plan.kind === "blocked" && plan.reason === "exhausted") {
      // Both attempts are spent: stop looking at this session.
      this.state.agents[agent.id] = {
        status: "skipped",
        at: now(),
        workspaceId: agent.workspaceId,
        ...(agentState?.error ? { error: agentState.error } : {}),
        ...(agentState?.attempts !== undefined ? { attempts: agentState.attempts } : {}),
        ...(agentState?.lastTurnId !== undefined ? { lastTurnId: agentState.lastTurnId } : {}),
      };
      await saveState(this.state);
    }
  }

  private async pickWorkspaceFirstTask(
    paseo: PaseoApi,
    workspaceId: string,
    currentAgentId: string,
    currentPrompt: { text: string; turnId: string | null; at: string },
  ): Promise<FirstTaskFact | null> {
    const agents = (await this.listAgents(paseo)).filter((candidate) =>
      candidate.workspaceId === workspaceId &&
      !candidate.background &&
      !isSubagent(candidate) &&
      !isHelperAgent(candidate));
    const facts: FirstTaskFact[] = [];
    for (const candidate of agents) {
      if (candidate.id === currentAgentId) {
        facts.push({ id: candidate.id, text: currentPrompt.text, turnId: currentPrompt.turnId, at: currentPrompt.at });
        continue;
      }
      if (!candidate.lastUserMessageAt) continue;
      const first = await this.readFirstPrompt(paseo, candidate.id);
      if (!first) continue;
      facts.push({ id: candidate.id, text: first.text, turnId: first.turnId, at: first.at });
    }
    return pickFirstTask(facts);
  }

  /**
   * The first visible user message. It is read forward from the head with a
   * small page and time budget: the hook that calls it must stay inside the
   * daemon's hook timeout, and a discontinuity page proves nothing about the
   * real opening.
   */
  private async readFirstPrompt(paseo: PaseoApi, agentId: string): Promise<{ text: string; turnId: string | null; at: string } | null> {
    const timeline = paseo.agents.ref(agentId).timeline;
    const deadlineAt = Date.now() + 5_000;
    let cursor: { epoch: string; seq: number } | undefined;
    for (let page = 0; page < 50; page += 1) {
      if (Date.now() >= deadlineAt) return null;
      const result = await timeline.refetch({
        direction: "after",
        projection: "projected",
        limit: 20,
        ...(cursor ? { cursor } : {}),
      });
      if (result.error) return null;
      // A stale cursor or sequence gap makes the daemon return a tail page.
      // That page may start mid-session, so it can never prove the real first
      // prompt, and a first page that is already such a reset is no exception.
      if (isDiscontinuous(result)) return null;
      for (const entry of result.entries ?? []) {
        if (entry.item.type === "user_message" && entry.item.text.trim()) {
          return { text: entry.item.text, turnId: entry.turnId ?? null, at: entry.timestamp };
        }
      }
      if (!result.hasNewer || !result.endCursor) return null;
      cursor = result.endCursor;
    }
    return null;
  }
}
