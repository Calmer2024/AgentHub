import { useEffect, useMemo, useState } from "react";
import { Loader2, MessageCircleMore, Save, UserRoundMinus, UserRoundPlus } from "lucide-react";
import type { AgentConfig, Session } from "../types";
import { AgentAvatar } from "./AgentAvatar";
import { UiSelect } from "./UiSelect";
import { GlobalModal } from "./GlobalModal";

const MAX_GROUP_AGENTS = 12;
const MIN_GROUP_AGENTS = 2;

interface Props {
  open: boolean;
  session: Session | null;
  members: AgentConfig[];
  agents: AgentConfig[];
  loading?: boolean;
  onClose: () => void;
  onRename: (title: string) => Promise<void>;
  onAddMember: (agentId: string) => Promise<void>;
  onRemoveMember: (agentId: string) => Promise<void>;
}

export function GroupManagementDialog({
  open,
  session,
  members,
  agents,
  loading = false,
  onClose,
  onRename,
  onAddMember,
  onRemoveMember,
}: Props) {
  const [title, setTitle] = useState("");
  const [selectedAgentId, setSelectedAgentId] = useState("");
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);

  const agentById = useMemo(() => new Map(agents.map((agent) => [agent.id, agent])), [agents]);
  const memberIds = useMemo(() => new Set(members.map((member) => member.id)), [members]);
  const memberAgents = useMemo(
    () => members.map((member) => agentById.get(member.id) ?? member),
    [agentById, members],
  );
  const availableAgents = useMemo(
    () => agents.filter((agent) => agent.isActive && !memberIds.has(agent.id)),
    [agents, memberIds],
  );

  useEffect(() => {
    if (!open) return;
    setTitle(session?.title ?? "");
    setLocalError(null);
  }, [open, session?.title]);

  useEffect(() => {
    if (!availableAgents.some((agent) => agent.id === selectedAgentId)) {
      setSelectedAgentId(availableAgents[0]?.id ?? "");
    }
  }, [availableAgents, selectedAgentId]);

  if (!open || !session) return null;

  const canSaveTitle = Boolean(title.trim()) && title.trim() !== session.title;
  const canAdd = Boolean(selectedAgentId) && members.length < MAX_GROUP_AGENTS;
  const canRemove = members.length > MIN_GROUP_AGENTS;

  const runAction = async (key: string, action: () => Promise<void>) => {
    setBusyAction(key);
    setLocalError(null);
    try {
      await action();
    } catch (error) {
      setLocalError(error instanceof Error ? error.message : "操作失败，请稍后重试");
    } finally {
      setBusyAction(null);
    }
  };

  return (
    <GlobalModal
      title="群管理"
      subtitle={`${members.length} 个成员`}
      icon={<AgentAvatar kind="group" name={session.title} size="md" />}
      zIndexClass="z-[1400]"
      panelClassName="max-w-3xl"
      onClose={onClose}
      closeLabel="关闭群管理"
    >
      <div className="space-y-4">
        <section className="agenthub-card rounded-3xl border p-4">
          <div className="mb-3 flex items-center gap-2">
            <span className="agenthub-soft flex h-8 w-8 items-center justify-center rounded-full border">
              <MessageCircleMore size={16} />
            </span>
            <h3 className="agenthub-strong text-sm font-semibold">群聊信息</h3>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              className="agenthub-composer agenthub-textarea agenthub-focus-ring h-10 min-w-0 flex-1 rounded-2xl border px-3 text-sm"
              placeholder="群聊名称"
            />
            <button
              type="button"
              onClick={() => runAction("rename", () => onRename(title.trim()))}
              disabled={!canSaveTitle || busyAction !== null}
              className="agenthub-primary-button inline-flex h-10 items-center justify-center gap-2 rounded-full px-4 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
            >
              {busyAction === "rename" ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
              保存
            </button>
          </div>
        </section>

        <section className="agenthub-card rounded-3xl border p-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <h3 className="agenthub-strong text-sm font-semibold">成员</h3>
            <span className="agenthub-muted text-xs">{members.length}/{MAX_GROUP_AGENTS}</span>
          </div>
          {loading ? (
            <div className="agenthub-muted flex items-center gap-2 rounded-2xl border px-3 py-3 text-sm">
              <Loader2 size={15} className="animate-spin" />
              正在同步成员
            </div>
          ) : (
            <div className="max-h-[32dvh] space-y-1.5 overflow-y-auto pr-1">
              {memberAgents.map((member) => (
                <div key={member.id} className="agenthub-soft flex items-center gap-3 rounded-2xl border px-3 py-2.5">
                  <AgentAvatar agent={member} size="sm" />
                  <span className="min-w-0 flex-1">
                    <span className="agenthub-strong block truncate text-sm font-medium">{member.name}</span>
                    <span className="agenthub-muted mt-0.5 block truncate text-xs">
                      {member.primarySkill === "orchestrator_planner"
                        ? "调度器"
                        : member.description || member.cliTool}
                    </span>
                  </span>
                  <button
                    type="button"
                    onClick={() => runAction(`remove-${member.id}`, () => onRemoveMember(member.id))}
                    disabled={!canRemove || busyAction !== null}
                    className="agenthub-icon-button inline-flex h-8 w-8 items-center justify-center rounded-full disabled:cursor-not-allowed disabled:opacity-40"
                    aria-label={`移除 ${member.name}`}
                    title={canRemove ? "移除成员" : `至少保留 ${MIN_GROUP_AGENTS} 个成员`}
                  >
                    {busyAction === `remove-${member.id}` ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : (
                      <UserRoundMinus size={14} />
                    )}
                  </button>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="agenthub-card rounded-3xl border p-4">
          <div className="mb-3 flex items-center gap-2">
            <span className="agenthub-soft flex h-8 w-8 items-center justify-center rounded-full border">
              <UserRoundPlus size={16} />
            </span>
            <h3 className="agenthub-strong text-sm font-semibold">添加成员</h3>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <div className="min-w-0 flex-1">
              <UiSelect
                ariaLabel="选择要添加的成员"
                value={selectedAgentId}
                options={availableAgents.length === 0
                  ? [{ value: "", label: "没有可添加的 Agent", disabled: true }]
                  : availableAgents.map((agent) => ({
                    value: agent.id,
                    label: agent.name,
                    description: agent.primarySkill === "orchestrator_planner"
                      ? "调度器"
                      : agent.description || agent.cliTool,
                  }))}
                onValueChange={setSelectedAgentId}
                disabled={availableAgents.length === 0 || members.length >= MAX_GROUP_AGENTS}
              />
            </div>
            <button
              type="button"
              onClick={() => runAction("add", () => onAddMember(selectedAgentId))}
              disabled={!canAdd || busyAction !== null}
              className="agenthub-primary-button inline-flex h-10 items-center justify-center gap-2 rounded-full px-4 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
            >
              {busyAction === "add" ? <Loader2 size={15} className="animate-spin" /> : <UserRoundPlus size={15} />}
              添加
            </button>
          </div>
          {members.length >= MAX_GROUP_AGENTS && (
            <p className="agenthub-muted mt-2 text-xs">已达到成员上限。</p>
          )}
        </section>

        {localError && (
          <div className="agenthub-status-error rounded-2xl border px-3 py-2 text-sm">
            {localError}
          </div>
        )}
      </div>
    </GlobalModal>
  );
}

