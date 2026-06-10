import { useEffect, useMemo, useState } from "react";
import { LogOut, Save, UserCircle } from "lucide-react";
import { logoutCurrentUser, updateCurrentUserProfile } from "../api/client";
import { useToastStore } from "../stores/toastStore";
import type { CurrentUser, Team } from "../types";
import { GlobalModal } from "./GlobalModal";

interface Props {
  currentUser: CurrentUser | null;
  teams: Team[];
  onUserUpdated?: () => Promise<void> | void;
}

export function UserAccountMenu({ currentUser, teams, onUserUpdated }: Props) {
  const [open, setOpen] = useState(false);
  const [displayName, setDisplayName] = useState(currentUser?.displayName ?? "");
  const [avatarUrl, setAvatarUrl] = useState(currentUser?.avatarUrl ?? "");
  const [busy, setBusy] = useState(false);
  const pushToast = useToastStore((state) => state.pushToast);
  const initials = useMemo(() => {
    const source = currentUser?.displayName || currentUser?.username || currentUser?.email || "AH";
    return source.trim().slice(0, 2).toUpperCase();
  }, [currentUser]);

  useEffect(() => {
    setDisplayName(currentUser?.displayName ?? "");
    setAvatarUrl(currentUser?.avatarUrl ?? "");
  }, [currentUser]);

  const saveProfile = async () => {
    if (!currentUser) return;
    setBusy(true);
    try {
      await updateCurrentUserProfile({
        displayName: displayName.trim() || currentUser.displayName,
        avatarUrl: avatarUrl.trim() || null,
      });
      await onUserUpdated?.();
      pushToast({ kind: "success", title: "资料已保存" });
      setOpen(false);
    } catch (error) {
      pushToast({
        kind: "error",
        title: "资料保存失败",
        description: error instanceof Error ? error.message : undefined,
      });
    } finally {
      setBusy(false);
    }
  };

  const signOut = async () => {
    setBusy(true);
    try {
      await logoutCurrentUser();
    } finally {
      window.location.reload();
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="agenthub-nav-idle flex w-full items-center gap-2 rounded-2xl px-2.5 py-2 text-left text-sm transition"
        aria-label="用户资料"
      >
        <Avatar user={currentUser} initials={initials} />
        <span className="min-w-0 flex-1">
          <span className="block truncate">{currentUser?.displayName ?? "未登录"}</span>
          <span className="agenthub-faint block truncate text-[11px]">
            {currentUser?.username ? `@${currentUser.username}` : currentUser?.email ?? "云端身份"}
          </span>
        </span>
        <UserCircle size={15} className="agenthub-muted shrink-0" />
      </button>

      {open && (
        <GlobalModal
          title="个人资料"
          icon={<UserCircle size={18} />}
          panelClassName="max-w-md"
          closeDisabled={busy}
          onClose={() => setOpen(false)}
          footer={(
            <div className="flex flex-col gap-2 sm:flex-row sm:justify-between">
              <button
                type="button"
                onClick={() => void signOut()}
                disabled={busy}
                className="agenthub-icon-button inline-flex h-10 items-center justify-center gap-2 rounded-full px-4 text-sm disabled:opacity-50"
              >
                <LogOut size={15} />
                退出登录
              </button>
              <button
                type="button"
                onClick={() => void saveProfile()}
                disabled={busy || !currentUser || !displayName.trim()}
                className="agenthub-primary-button inline-flex h-10 items-center justify-center gap-2 rounded-full px-5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Save size={15} />
                保存资料
              </button>
            </div>
          )}
        >
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <Avatar user={currentUser} initials={initials} large />
              <div className="min-w-0">
                <p className="agenthub-strong truncate text-sm font-medium">{currentUser?.email ?? "未登录"}</p>
                <p className="agenthub-faint truncate text-xs">{currentUser?.username ? `@${currentUser.username}` : "个人空间"}</p>
              </div>
            </div>
            <label className="block space-y-2" htmlFor="agenthub-profile-name">
              <span className="agenthub-muted text-xs font-medium">显示名称</span>
              <input
                id="agenthub-profile-name"
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                className="agenthub-composer h-11 w-full rounded-2xl border px-3 text-sm outline-none"
              />
            </label>
            <label className="block space-y-2" htmlFor="agenthub-profile-avatar">
              <span className="agenthub-muted text-xs font-medium">头像 URL</span>
              <input
                id="agenthub-profile-avatar"
                value={avatarUrl}
                onChange={(event) => setAvatarUrl(event.target.value)}
                className="agenthub-composer h-11 w-full rounded-2xl border px-3 text-sm outline-none"
                inputMode="url"
              />
            </label>
            <div className="grid gap-2 text-sm sm:grid-cols-2">
              <Info label="团队" value={teams.length ? `${teams.length}` : "0"} />
              <Info label="默认空间" value={currentUser?.defaultSpace?.name ?? "个人空间"} />
            </div>
          </div>
        </GlobalModal>
      )}
    </>
  );
}

function Avatar({ user, initials, large = false }: { user: CurrentUser | null; initials: string; large?: boolean }) {
  const size = large ? "h-12 w-12 text-sm" : "h-8 w-8 text-[11px]";
  if (user?.avatarUrl) {
    return (
      <img
        src={user.avatarUrl}
        alt=""
        className={`${size} shrink-0 rounded-full border object-cover`}
        style={{ borderColor: "var(--ah-border)" }}
      />
    );
  }
  return (
    <span className={`agenthub-soft agenthub-muted flex ${size} shrink-0 items-center justify-center rounded-full border font-semibold`}>
      {initials}
    </span>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <span className="agenthub-faint block text-xs">{label}</span>
      <span className="agenthub-strong mt-1 block truncate">{value}</span>
    </div>
  );
}
