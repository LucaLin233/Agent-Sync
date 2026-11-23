import { promises as fs } from "node:fs";
import { basename, join, resolve } from "node:path";
import type { PaseoAgent, PaseoApi, PaseoProject, PaseoWorkspace } from "./paseo-types";
import type { PluginSettings } from "@getpaseo/plugin/server";
import type { ChineseTitlesSettings } from "../shared/settings";
import { isProvisional } from "../shared/title";
import {
  createBootstrapWorkspaceViaCli,
  listAgentIdsViaCli,
  listProjectIdsViaCli,
  listProjectsViaCli,
  listWorkspaceIdsViaCli,
  renameAgentViaCli,
  renameProjectViaCli,
} from "./cli";
import { pickFirstTask, type FirstTaskFact } from "../shared/first-task";
import { generateTitle, isHelperAgent, type GenerationResult } from "./helper";
import { planTitleGeneration } from "../shared/generation-plan";
import { helperDirectory, isInsideDirectory, loadState, markBaseline, saveState, type ChineseTitlesState } from "./state";

const STALE_GENERATING_MS = 3 * 60 * 1000;
const BOOTSTRAP_TITLE = "中文标题引导";
const bootstrapDirectory = () => join(helperDirectory(), "bootstrap");

function isExactDirectory(path: string | null | undefined, directory: string): boolean {
  if (!path) return false;
  return resolve(path) === resolve(directory);
}

type Settings = PluginSettings<typeof import("../shared/settings").settingsSchema>;

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

  constructor(private readonly settings: Settings) {
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

  async onTurn(agentId: string, turnId: string | null, paseo: PaseoApi): Promise<void> {
    await this.ready;
    if (!this.state) return;
    this.attach(paseo);
    await this.ensureBaseline(paseo, { agentId });
    await this.processAgent(agentId, turnId, paseo);
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
        if (this.state.agents[agent.id]?.status !== "pending") continue;
        if (!workspaceById.has(agent.workspaceId)) continue;
        const before = this.state.agents[agent.id]?.status;
        await this.processAgent(agent.id, null, paseo);
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
    const directory = bootstrapDirectory();
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

  private async processAgent(agentId: string, turnId: string | null, paseo: PaseoApi): Promise<void> {
    if (!this.state || this.processingAgents.has(agentId)) return;
    // Claim before any await so two hooks cannot both pass the state check.
    this.processingAgents.add(agentId);
    let claimedWorkspace: string | null = null;
    try {
      const agentState = this.state.agents[agentId];
      if (agentState && agentState.status !== "pending" && agentState.status !== "error") return;
      const settings = await this.currentSettings();
      if (!settings) return;
      const refreshed = await paseo.agents.ref(agentId).refresh();
      const agent = refreshed?.agent;
      if (!agent || agent.background || isSubagent(agent) || isHelperAgent(agent) || isInsideDirectory(agent.cwd, helperDirectory())) {
        this.state.agents[agentId] = { status: "skipped", at: now() };
        return;
      }
      if (!agent.workspaceId) {
        this.state.agents[agentId] = { status: "skipped", at: now() };
        return;
      }
      const workspace = await paseo.workspaces.ref(agent.workspaceId).refresh();
      if (!workspace || workspace.background || isInsideDirectory(workspace.workspaceDirectory, helperDirectory())) {
        this.state.agents[agentId] = { status: "skipped", at: now() };
        return;
      }
      const prompt = await this.readFirstPrompt(paseo, agent.id);
      if (!prompt) return;
      if (turnId !== null && prompt.turnId !== null && prompt.turnId !== turnId) return;

      const workspaceState = this.state.workspaces[workspace.id];
      const candidate = Boolean(settings.autoNameWorkspaces && workspaceState?.status === "pending");
      if (candidate && !this.processingWorkspaces.has(workspace.id)) {
        this.processingWorkspaces.add(workspace.id);
        claimedWorkspace = workspace.id;
      }
      const winner = claimedWorkspace !== null
        ? await this.pickWorkspaceFirstTask(paseo, workspace.id, agent.id, prompt)
        : null;
      const workspacePrompt = winner?.text ?? prompt.text;
      const workspaceEligible = Boolean(
        claimedWorkspace !== null &&
        winner !== null &&
        isProvisional(workspace.title, workspacePrompt),
      );
      const agentEligible = Boolean(settings.autoNameSessions && isProvisional(agent.title, prompt.text));
      if (!workspaceEligible && !agentEligible) {
        if (settings.autoNameSessions && !isProvisional(agent.title, prompt.text)) {
          this.state.agents[agent.id] = { status: "skipped", at: now() };
        }
        // A lost workspace claim is contention, not a manual title. Leave the
        // pending state for the claim holder instead of marking it skipped.
        return;
      }

      if (workspaceEligible) {
        this.state.workspaces[workspace.id] = { status: "generating", at: now(), previousTitle: workspace.title ?? null };
        await saveState(this.state);
      }
      if (agentEligible) {
        this.state.agents[agent.id] = { status: "generating", at: now(), previousTitle: agent.title ?? null };
        await saveState(this.state);
      }

      const plan = planTitleGeneration({
        workspaceEligible,
        agentEligible,
        winnerIsAgent: winner?.id === agent.id,
      });
      let workspaceResult: GenerationResult | null = null;
      let agentResult: GenerationResult | null = null;
      if (plan.workspace) {
        workspaceResult = await generateTitle(paseo, settings, {
          kind: "workspace",
          prompt: workspacePrompt,
          projectName: workspace.projectDisplayName,
          baseName: workspace.name,
          projectId: workspace.projectId,
          maxChars: settings.titleMaxChars,
        });
      }
      if (plan.agent === "reuse-workspace") {
        agentResult = workspaceResult;
      } else if (plan.agent === "generate") {
        agentResult = await generateTitle(paseo, settings, {
          kind: "session",
          prompt: prompt.text,
          projectName: workspace.projectDisplayName,
          baseName: workspace.name,
          projectId: workspace.projectId,
          maxChars: settings.titleMaxChars,
        });
      }

      if (workspaceEligible) {
        // Re-read the original override. Only one final write; no placeholder.
        const current = await paseo.workspaces.ref(workspace.id).refresh();
        const previous = this.state.workspaces[workspace.id]?.previousTitle ?? null;
        if (workspaceResult && current && (current.title === previous || current.title === null || current.title === "" || isProvisional(current.title, workspacePrompt))) {
          await paseo.workspaces.ref(workspace.id).setTitle(workspaceResult.title);
          const verified = await paseo.workspaces.ref(workspace.id).refresh();
          if (verified?.title !== workspaceResult.title) {
            this.state.workspaces[workspace.id] = { status: "error", at: now(), error: "verification_failed" };
          } else {
            this.state.workspaces[workspace.id] = {
              status: "done",
              at: now(),
              title: workspaceResult.title,
              previousTitle: previous,
              ...(workspaceResult.errorCode ? { error: workspaceResult.errorCode } : {}),
            };
          }
        } else {
          // A manual rename won the race; never clobber it.
          this.state.workspaces[workspace.id] = { status: "skipped", at: now(), previousTitle: previous };
        }
        await saveState(this.state);
      }

      if (agentEligible) {
        const current = await paseo.agents.ref(agent.id).refresh();
        if (agentResult && current?.agent && isProvisional(current.agent.title, prompt.text)) {
          const renamed = await renameAgentViaCli(settings, agent.id, agentResult.title);
          if (!renamed.ok) {
            this.state.agents[agent.id] = { status: "error", at: now(), error: renamed.failure ?? "failed" };
            console.warn("[paseo-chinese-titles] agent rename CLI failed", { agentId: agent.id, code: renamed.failure ?? "failed" });
          } else {
            const verified = await paseo.agents.ref(agent.id).refresh();
            if (verified?.agent.title?.trim() !== agentResult.title) {
              this.state.agents[agent.id] = { status: "error", at: now(), error: "verification_failed" };
            } else {
              this.state.agents[agent.id] = {
                status: "done",
                at: now(),
                title: agentResult.title,
                ...(agentResult.errorCode ? { error: agentResult.errorCode } : {}),
              };
            }
          }
        } else {
          this.state.agents[agent.id] = { status: "skipped", at: now() };
        }
        await saveState(this.state);
      }
    } catch {
      if (this.state) {
        this.state.agents[agentId] = { status: "error", at: now(), error: "internal_failed" };
        await saveState(this.state);
      }
    } finally {
      if (claimedWorkspace) this.processingWorkspaces.delete(claimedWorkspace);
      this.processingAgents.delete(agentId);
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

  private async readFirstPrompt(paseo: PaseoApi, agentId: string): Promise<{ text: string; turnId: string | null; at: string } | null> {
    const timeline = paseo.agents.ref(agentId).timeline;
    let cursor: { epoch: string; seq: number } | undefined;
    for (let page = 0; page < 50; page += 1) {
      const result = await timeline.refetch({
        direction: "after",
        projection: "projected",
        limit: 20,
        ...(cursor ? { cursor } : {}),
      });
      if (result.error) return null;
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
