import { useCallback, useEffect, useMemo, useState } from "react";
import { CirclePlus, Cloud, FileArchive, GitBranch, HardDrive, RotateCcw, Shield, Trash2, Users, type LucideIcon } from "lucide-react";
import {
  addTeamMember,
  createSecret,
  createWorkspaceSnapshot,
  fetchAuditLogs,
  fetchQuotaSummary,
  fetchTeamMembers,
  fetchWorkspace,
  importWorkspaceGithub,
  importWorkspaceZip,
  removeTeamMember,
  restoreWorkspaceSnapshot,
  updateTeamMemberRole,
} from "../api/client";
import { useToastStore } from "../stores/toastStore";
import { MenuSelect } from "./MenuSelect";
import type {
  AuditLog,
  CloudWorkspace,
  CurrentUser,
  Project,
  QuotaSummary,
  SecretCreateInput,
  Team,
  TeamMember,
  TeamRole,
} from "../types";
import { formatChinaDateTime } from "../utils/time";

type SecretScope = NonNullable<SecretCreateInput["scope"]>;

const TEAM_ROLE_OPTIONS: Array<{ value: TeamRole; label: string }> = [
  { value: "owner", label: "owner" },
  { value: "admin", label: "admin" },
  { value: "member", label: "member" },
  { value: "viewer", label: "viewer" },
];

interface Props {
  project: Project | null;
  currentUser: CurrentUser | null;
  teams: Team[];
  onRefreshProjects: () => Promise<void>;
}

export function WorkspaceSettingsPage({
  project,
  currentUser,
  teams,
  onRefreshProjects,
}: Props) {
  const [workspace, setWorkspace] = useState<CloudWorkspace | null>(null);
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [quota, setQuota] = useState<QuotaSummary | null>(null);
  const [teamMembers, setTeamMembers] = useState<TeamMember[]>([]);
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
  const [secretScope, setSecretScope] = useState<SecretScope>("user");
  const pushToast = useToastStore((state) => state.pushToast);

  const projectTeam = useMemo(
    () => teams.find((team) => team.id === project?.teamId) ?? null,
    [project?.teamId, teams],
  );
  const isCloud = project?.workspaceMode === "cloud";
  const secretScopeOptions = useMemo(() => [
    { value: "user" as SecretScope, label: "我的凭据" },
    ...(project?.teamId ? [{ value: "team" as SecretScope, label: "团队共享" }] : []),
    { value: "project" as SecretScope, label: "项目共享" },
  ], [project?.teamId]);
  const addMemberRoleOptions = useMemo(
    () => TEAM_ROLE_OPTIONS.filter((option) => option.value !== "owner" || projectTeam?.role === "owner"),
    [projectTeam?.role],
  );

  const loadCloudData = useCallback(async () => {
    if (!project || !isCloud || !project.workspaceId) {
      setWorkspace(null);
      setAuditLogs([]);
      setQuota(null);
      setTeamMembers([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [workspaceData, logs, quotaData, members] = await Promise.all([
        fetchWorkspace(project.workspaceId),
        fetchAuditLogs({ projectId: project.id }),
        fetchQuotaSummary(),
        project.teamId ? fetchTeamMembers(project.teamId) : Promise.resolve([]),
      ]);
      setWorkspace(workspaceData);
      setAuditLogs(logs);
      setQuota(quotaData);
      setTeamMembers(members);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载云端工作区失败");
    } finally {
      setLoading(false);
    }
  }, [isCloud, project]);

  useEffect(() => {
    void loadCloudData();
  }, [loadCloudData]);

  useEffect(() => {
    if (secretScope === "team" && !project?.teamId) {
      setSecretScope("user");
    }
  }, [project?.teamId, secretScope]);

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
    return (
      <main className="agenthub-chat flex min-h-0 flex-1 items-center justify-center px-6 text-center">
        <span className="agenthub-muted text-lg">选择云端项目后查看工作区</span>
      </main>
    );
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
            <div className="mt-3 grid gap-2 md:grid-cols-[150px_180px_minmax(0,1fr)_40px]">
              <MenuSelect
                value={secretScope}
                ariaLabel="Secret 作用域"
                options={secretScopeOptions}
                onChange={setSecretScope}
                className="h-10"
              />
              <input
                value={secretName}
                onChange={(event) => setSecretName(event.target.value)}
                className="agenthub-composer h-10 min-w-0 rounded-lg border px-3 text-sm outline-none"
                placeholder="PHASE10_TOKEN"
                aria-label="Secret 名称"
              />
              <input
                value={secretValue}
                onChange={(event) => setSecretValue(event.target.value)}
                className="agenthub-composer h-10 min-w-0 rounded-lg border px-3 text-sm outline-none"
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
                    const input: SecretCreateInput = {
                      name: secretName,
                      value: secretValue,
                      scope: secretScope,
                    };
                    if (secretScope === "team" && project.teamId) {
                      input.ownerId = project.teamId;
                    }
                    if (secretScope === "project") {
                      input.ownerId = project.id;
                    }
                    await createSecret(input);
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
                icon={CirclePlus}
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
              <div className="mt-3 space-y-3">
                <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_128px_40px]">
                  <input
                    value={memberEmail}
                    onChange={(event) => setMemberEmail(event.target.value)}
                    className="agenthub-composer h-10 min-w-0 rounded-lg border px-3 text-sm outline-none"
                    placeholder="member@example.com"
                    aria-label="成员邮箱"
                  />
                  <MenuSelect
                    value={memberRole}
                    options={addMemberRoleOptions}
                    onChange={setMemberRole}
                    ariaLabel="成员角色"
                    className="h-10"
                  />
                  <IconAction
                    title="添加成员"
                    disabled={Boolean(busy) || !memberEmail.trim()}
                    icon={CirclePlus}
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
                <div className="space-y-1.5">
                  {teamMembers.length === 0 ? (
                    <p className="agenthub-faint rounded-lg border px-3 py-3 text-sm" style={{ borderColor: "var(--ah-border)" }}>
                      暂无团队成员
                    </p>
                  ) : teamMembers.map((member) => (
                    <div key={member.id} className="agenthub-nav-idle grid items-center gap-2 rounded-lg border px-3 py-2 text-sm md:grid-cols-[minmax(0,1fr)_128px_40px]">
                      <span className="min-w-0">
                        <span className="agenthub-strong block truncate">{member.displayName || member.email}</span>
                        <span className="agenthub-faint block truncate text-xs">{member.email}</span>
                      </span>
                      <MenuSelect
                        value={member.role}
                        onChange={(role) => void runAction(
                          `member-role-${member.id}`,
                          async () => {
                            await updateTeamMemberRole(project.teamId as string, member.id, role);
                          },
                          "成员角色已更新",
                        )}
                        options={TEAM_ROLE_OPTIONS.filter((option) => (
                          option.value !== "owner" || projectTeam?.role === "owner" || member.role === "owner"
                        ))}
                        disabled={Boolean(busy)}
                        ariaLabel={`成员角色 ${member.email}`}
                        className="h-9"
                      />
                      <IconAction
                        title={`移除成员 ${member.email}`}
                        disabled={Boolean(busy)}
                        icon={Trash2}
                        onClick={() => void runAction(
                          `member-remove-${member.id}`,
                          async () => {
                            await removeTeamMember(project.teamId as string, member.id);
                          },
                          "成员已移除",
                        )}
                      />
                    </div>
                  ))}
                </div>
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

export function CloudWorkspaceSettings(props: Props) {
  return <WorkspaceSettingsPage {...props} />;
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
