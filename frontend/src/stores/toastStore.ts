import { create } from "zustand";

export type ToastKind = "success" | "error" | "info" | "warning";

export interface ToastItem {
  id: string;
  kind: ToastKind;
  title: string;
  description?: string;
  durationMs: number;
}

interface ToastState {
  toasts: ToastItem[];
  pushToast: (toast: Omit<ToastItem, "id" | "durationMs"> & { durationMs?: number }) => string;
  removeToast: (id: string) => void;
}

let toastCounter = 0;

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  pushToast: (toast) => {
    toastCounter += 1;
    const id = `toast-${Date.now()}-${toastCounter}`;
    set((state) => ({
      toasts: [
        ...state.toasts,
        {
          id,
          kind: toast.kind,
          title: toast.title,
          description: toast.description,
          durationMs: toast.durationMs ?? 3600,
        },
      ].slice(-5),
    }));
    return id;
  },
  removeToast: (id) => {
    set((state) => ({
      toasts: state.toasts.filter((toast) => toast.id !== id),
    }));
  },
}));
