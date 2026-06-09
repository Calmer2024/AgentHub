import { useCallback, useEffect, useMemo, useState } from "react";
import { Cloud, FileArchive, GitBranch, HardDrive, Plus, RotateCcw, Shield, Users, type LucideIcon } from "lucide-react";
import {
  addTeamMember,
  createSecret,
  createWorkspaceSnapshot,
  fetchAuditLogs,
  fetchQuotaSummary,
  fetchWorkspace,
  importWorkspaceGithub,
  importWorkspaceZip,
  restoreWorkspaceSnapshot,
} from "../api/client";
import { useToastStore } from "../stores/toastStore";
import type { AuditLog, CloudWorkspace, CurrentUser, Project, QuotaSummary, Team, TeamRole } from "../types";
import { formatChinaDateTime } from "../utils/time";

interface Props {
  project: Project | null;
  currentUser: CurrentUser | null;
  teams: Team[];
  onRefreshProjects: () => Promise<void>;
  variant?: "auto" | "local" | "cloud";
}

export function WorkspaceSettingsPage({
  project,
  currentUser,
  teams,
  onRefreshProjects,
  variant = "auto",
}: Props) {
  const [workspace, setWorkspace] = useState<CloudWorkspace | null>(null);
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [quota, setQuota] = useState<QuotaSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [snapshotLabel, setSnapshotLabel] = useState("手动快照");
  const [repoUrl, setRepoUrl] = useState("https://github.com/example/repo");
  const [branch, setBranch] = useState("main");
  const [memberEmail, setMemberEmail] = useState("");
  const [memberRole, setMemberRole] = useState<TeamRole>("member");
  const [secretName, setSecretName] = useState("");
  const [secretValue, setSecretValue] = useState("");
  const pushToast = useToastStore((state) => state.pushToast);

  const projectTeam = useMemo(
    () => teams.find((team) => team.id === project?.teamId) ?? null,
    [project?.teamId, teams],
  );
  const isCloud = variant === "cloud" || (variant === "auto" && project?.workspaceMode === "cloud");

  const loadCloudData = useCallback(async () => {
    if (!project || !isCloud || !project.workspaceId) {
      setWorkspace(null);
      setAuditLogs([]);
      setQuota(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [workspaceData, logs, quotaData] = await Promise.all([
        fetchWorkspace(project.workspaceId),
        fetchAuditLogs({ projectId: project.id }),
        fetchQuotaSummary(),
      ]);
      setWorkspace(workspaceData);
      setAuditLogs(logs);
      setQuota(quotaData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载云端工作区失败");
    } finally {
      setLoading(false);
    }
  }, [isCloud, project]);

  useEffect(() => {
    void loadCloudData();
  }, [loadCloudData]);

  const runAction = useCallback(async (
    key: string,
    action: () => Promise<void>,
    success: string,
  ) => {
    setBusy(key);
    setError(null);
    setNotice(null);
    try {
      await action();
      setNotice(success);
      pushToast({ kind: "success", title: success });
      await loadCloudData();
      await onRefreshProjects();
    } catch (err) {
      const message = err instanceof Error ? err.message : "操作失败";
      setError(message);
      pushToast({ kind: "error", title: message });
    } finally {
      setBusy(null);
    }
  }, [loadCloudData, onRefreshProjects, pushToast]);

  if (!project) {
    return (
      <main className="agenthub-chat flex min-h-0 flex-1 items-center justify-center px-6 text-center">
        <span className="agenthub-muted text-lg">选择项目后查看工作区</span>
      </main>
    );
  }

  if (!isCloud) {
    return <LocalProjectSettingsContent project={project} />;
  }

  return (
    <main className="agenthub-chat min-h-0 flex-1 overflow-y-auto">
      <header className="agenthub-header border-b px-5 py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="agenthub-faint text-xs">云端工作区设置</p>
            <h1 className="agenthub-strong text-lg font-semibold">{project.name}</h1>
          </div>
          <ModeBadge mode={project.workspaceMode} />
        </div>
      </header>

      <section className="border-b px-5 py-4" style={{ borderColor: "var(--ah-border)" }}>
        <div className="grid gap-3 text-sm md:grid-cols-3">
          <InfoCell label="项目 ID" value={project.id} />
          <InfoCell label="作用域" value={projectTeam?.name ?? "个人空间"} />
          <InfoCell label="当前用户" value={currentUser?.email ?? "未登录"} />
          <InfoCell label="Workspace ID" value={project.workspaceId ?? "未创建"} />
          <InfoCell label="存储 URI" value={workspace?.storageUri ?? "未创建"} />
          <InfoCell label="Provider" value={workspace?.provider ?? "cloud"} />
          <InfoCell label="状态" value={workspace?.status ?? project.status} />
        </div>
      </section>

      {error && (
        <div className="mx-5 mt-4 rounded-lg border border-[color:var(--ah-danger)] bg-[color:var(--ah-danger-soft)] px-3 py-2 text-sm text-[color:var(--ah-danger)]">
          {error}
        </div>
      )}
      {notice && (
        <div className="mx-5 mt-4 rounded-lg border px-3 py-2 text-sm agenthub-muted" style={{ borderColor: "var(--ah-border)" }}>
          {notice}
        </div>
      )}

      {loading ? (
        <LoadingSections />
      ) : (
        <div className="divide-y" style={{ borderColor: "var(--ah-border)" }}>
          <section className="px-5 py-4">
            <SectionTitle icon={Cloud} title="运行时" />
            <div className="mt-3 grid gap-3 text-sm md:grid-cols-4">
              <InfoCell label="并发" value={quota ? `${quota.concurrentRunsUsed}/${quota.concurrentRunsLimit}` : "--"} />
              <InfoCell label="运行时长" value={quota ? `${quota.runtimeSecondsLimit}s` : "--"} />
              <InfoCell label="内存" value={quota ? `${quota.memoryMbLimit} MB` : "--"} />
              <InfoCell label="磁盘" value={quota ? `${quota.diskMbLimit} MB` : "--"} />
            </div>
            <div className="mt-3 flex gap-2">
              <input
                value={secretName}
                onChange={(event) => setSecretName(event.target.value)}
                className="agenthub-composer w-44 rounded-lg border px-3 text-sm outline-none"
                placeholder="PHASE10_TOKEN"
                aria-label="Secret 名称"
              />
              <input
                value={secretValue}
                onChange={(event) => setSecretValue(event.target.value)}
                className="agenthub-composer min-w-0 flex-1 rounded-lg border px-3 text-sm outline-none"
                type="password"
                placeholder="Secret value"
                aria-label="Secret 值"
              />
              <IconAction
                title="保存 Secret"
                disabled={Boolean(busy) || !secretName.trim() || !secretValue}
                icon={Shield}
                onClick={() => void runAction(
                  "secret",
                  async () => {
                    await createSecret({ name: secretName, value: secretValue, scope: "user" });
                    setSecretName("");
                    setSecretValue("");
                  },
                  "Secret 已保存",
                )}
              />
            </div>
          </section>

          <section className="px-5 py-4">
            <SectionTitle icon={FileArchive} title="导入" />
            <div className="mt-3 grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
              <label className="agenthub-nav-idle flex min-h-[44px] cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm">
                <FileArchive size={16} className="agenthub-muted" />
                <span className="min-w-0 flex-1 truncate">上传 zip</span>
                <input
                  type="file"
                  accept=".zip,application/zip"
                  className="hidden"
                  disabled={Boolean(busy)}
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    event.target.value = "";
                    if (!file || !project.workspaceId) return;
                    void runAction(
                      "zip",
                      async () => { await importWorkspaceZip(project.workspaceId as string, file); },
                      "zip 导入已完成",
                    );
                  }}
                />
              </label>
              <div className="flex min-w-0 gap-2">
                <input
                  value={repoUrl}
                  onChange={(event) => setRepoUrl(event.target.value)}
                  className="agenthub-composer min-w-0 flex-1 rounded-lg border px-3 text-sm outline-none"
                  aria-label="GitHub 仓库地址"
                />
                <input
                  value={branch}
                  onChange={(event) => setBranch(event.target.value)}
                  className="agenthub-composer w-24 rounded-lg border px-3 text-sm outline-none"
                  aria-label="GitHub 分支"
                />
                <IconAction
                  title="导入 GitHub"
                  disabled={Boolean(busy) || !repoUrl.trim() || !project.workspaceId}
                  icon={GitBranch}
                  onClick={() => void runAction(
                    "github",
                    async () => {
                      await importWorkspaceGithub(project.workspaceId as string, {
                        repoUrl,
                        branch: branch || null,
                      });
                    },
                    "GitHub 导入任务已排队",
                  )}
                />
              </div>
            </div>
            <DenseList
              empty="暂无导入记录"
              items={(workspace?.imports ?? []).map((item) => ({
                id: item.id,
                left: `${item.source} · ${item.status}`,
                middle: item.detail,
                right: formatChinaDateTime(item.createdAt),
              }))}
            />
          </section>

          <section className="px-5 py-4">
            <SectionTitle icon={RotateCcw} title="快照" />
            <div className="mt-3 flex gap-2">
              <input
                value={snapshotLabel}
                onChange={(event) => setSnapshotLabel(event.target.value)}
                className="agenthub-composer min-w-0 flex-1 rounded-lg border px-3 text-sm outline-none"
                aria-label="快照标签"
              />
              <IconAction
                title="创建快照"
                disabled={Boolean(busy) || !project.workspaceId}
                icon={Plus}
                onClick={() => void runAction(
                  "snapshot",
                  async () => { await createWorkspaceSnapshot(project.workspaceId as string, snapshotLabel); },
                  "快照已创建",
                )}
              />
            </div>
            <div className="mt-3 space-y-2">
              {(workspace?.snapshots ?? []).length === 0 ? (
                <p className="agenthub-faint rounded-lg border px-3 py-3 text-sm" style={{ borderColor: "var(--ah-border)" }}>
                  暂无快照
                </p>
              ) : workspace?.snapshots.map((snapshot) => (
                <div key={snapshot.id} className="agenthub-nav-idle flex items-center gap-3 rounded-lg border px-3 py-2 text-sm">
                  <span className="min-w-0 flex-1">
                    <span className="block truncate">{snapshot.label ?? "未命名快照"}</span>
                    <span className="agenthub-faint block truncate text-xs">{formatChinaDateTime(snapshot.createdAt)}</span>
                  </span>
                  <IconAction
                    title="恢复快照"
                    disabled={Boolean(busy) || !project.workspaceId}
                    icon={RotateCcw}
                    onClick={() => void runAction(
                      `restore-${snapshot.id}`,
                      async () => {
                        await restoreWorkspaceSnapshot(project.workspaceId as string, snapshot.id, "replace");
                      },
                      "快照已恢复",
                    )}
                  />
                </div>
              ))}
            </div>
          </section>

          <section className="px-5 py-4">
            <SectionTitle icon={Users} title="成员" />
            {project.teamId ? (
              <div className="mt-3 flex gap-2">
                <input
                  value={memberEmail}
                  onChange={(event) => setMemberEmail(event.target.value)}
                  className="agenthub-composer min-w-0 flex-1 rounded-lg border px-3 text-sm outline-none"
                  placeholder="member@example.com"
                  aria-label="成员邮箱"
                />
                <select
                  value={memberRole}
                  onChange={(event) => setMemberRole(event.target.value as TeamRole)}
                  className="agenthub-composer w-28 rounded-lg border px-3 text-sm outline-none"
                  aria-label="成员角色"
                >
                  <option value="admin">admin</option>
                  <option value="member">member</option>
                  <option value="viewer">viewer</option>
                </select>
                <IconAction
                  title="添加成员"
                  disabled={Boolean(busy) || !memberEmail.trim()}
                  icon={Plus}
                  onClick={() => void runAction(
                    "member",
                    async () => {
                      await addTeamMember(project.teamId as string, memberEmail, memberRole);
                      setMemberEmail("");
                    },
                    "成员已添加",
                  )}
                />
              </div>
            ) : (
              <p className="agenthub-faint mt-3 rounded-lg border px-3 py-3 text-sm" style={{ borderColor: "var(--ah-border)" }}>
                个人空间项目
              </p>
            )}
          </section>

          <section className="px-5 py-4">
            <SectionTitle icon={Shield} title="审计日志" />
            <DenseList
              empty="暂无审计日志"
              items={auditLogs.map((item) => ({
                id: item.id,
                left: item.action,
                middle: item.resourceType,
                right: formatChinaDateTime(item.createdAt),
              }))}
            />
          </section>
        </div>
      )}
    </main>
  );
}

export function LocalProjectSettings(props: Omit<Props, "variant">) {
  return <WorkspaceSettingsPage {...props} variant="local" />;
}

export function CloudWorkspaceSettings(props: Omit<Props, "variant">) {
  return <WorkspaceSettingsPage {...props} variant="cloud" />;
}

function LocalProjectSettingsContent({ project }: { project: Project }) {
  return (
    <main className="agenthub-chat min-h-0 flex-1 overflow-y-auto">
      <header className="agenthub-header border-b px-5 py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="agenthub-faint text-xs">本机项目设置</p>
            <h1 className="agenthub-strong text-lg font-semibold">{project.name}</h1>
          </div>
          <ModeBadge mode="local" />
        </div>
      </header>

      <section className="border-b px-5 py-4" style={{ borderColor: "var(--ah-border)" }}>
        <div className="grid gap-3 text-sm md:grid-cols-3">
          <InfoCell label="项目 ID" value={project.id} />
          <InfoCell label="状态" value={project.status} />
          <InfoCell label="文件数" value={String(project.fileCount)} />
          <InfoCell label="大小" value={`${project.totalSizeBytes} B`} />
        </div>
      </section>

      <section className="px-5 py-5">
        <SectionTitle icon={HardDrive} title="本机工作区" />
        <div className="mt-3 grid gap-2 text-sm">
          <div className="agenthub-nav-idle rounded-lg border px-3 py-3" style={{ borderColor: "var(--ah-border)" }}>
            <span className="agenthub-faint block text-xs">路径</span>
            <span className="agenthub-strong mt-1 block break-all">{project.workspacePath ?? "未绑定"}</span>
          </div>
          <div className="agenthub-nav-idle rounded-lg border px-3 py-3" style={{ borderColor: "var(--ah-border)" }}>
            <span className="agenthub-faint block text-xs">运行环境</span>
            <span className="agenthub-strong mt-1 block">本机 CLI Agent 与本机预览/构建/导出</span>
          </div>
        </div>
      </section>
    </main>
  );
}

function LoadingSections() {
  return (
    <div className="space-y-3 px-5 py-5" aria-label="正在加载工作区">
      {Array.from({ length: 4 }).map((_, index) => (
        <div key={index} className="agenthub-skeleton h-20 animate-pulse rounded-lg border" />
      ))}
    </div>
  );
}

function ModeBadge({ mode }: { mode: Project["workspaceMode"] }) {
  const Icon = mode === "cloud" ? Cloud : HardDrive;
  return (
    <span className="agenthub-soft agenthub-muted inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm">
      <Icon size={14} />
      {mode === "cloud" ? "云端" : "本机"}
    </span>
  );
}

function InfoCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <span className="agenthub-faint block text-xs">{label}</span>
      <span className="agenthub-strong mt-1 block truncate text-sm" title={value}>{value}</span>
    </div>
  );
}

function SectionTitle({
  icon: Icon,
  title,
}: {
  icon: LucideIcon;
  title: string;
}) {
  return (
    <h2 className="agenthub-strong flex items-center gap-2 text-sm font-semibold">
      <Icon size={16} className="agenthub-muted" />
      {title}
    </h2>
  );
}

function IconAction({
  icon: Icon,
  title,
  disabled,
  onClick,
}: {
  icon: LucideIcon;
  title: string;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="agenthub-icon-button inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full disabled:cursor-not-allowed disabled:opacity-50"
      title={title}
      aria-label={title}
    >
      <Icon size={16} />
    </button>
  );
}

function DenseList({
  empty,
  items,
}: {
  empty: string;
  items: Array<{ id: string; left: string; middle: string; right: string }>;
}) {
  if (items.length === 0) {
    return (
      <p className="agenthub-faint mt-3 rounded-lg border px-3 py-3 text-sm" style={{ borderColor: "var(--ah-border)" }}>
        {empty}
      </p>
    );
  }
  return (
    <div className="mt-3 space-y-1.5">
      {items.map((item) => (
        <div key={item.id} className="agenthub-nav-idle grid gap-2 rounded-lg border px-3 py-2 text-sm md:grid-cols-[1fr_1.5fr_140px]">
          <span className="truncate">{item.left}</span>
          <span className="agenthub-muted truncate">{item.middle}</span>
          <span className="agenthub-faint truncate md:text-right">{item.right}</span>
        </div>
      ))}
    </div>
  );
}
