import type { AgentAssignment, UserProfile, ViewId } from "../types";
import type { ControlApi } from "../api";

export interface PageProps {
  api: ControlApi;
  profile: UserProfile;
  agents: AgentAssignment[];
  selectedAgent: string;
  onNavigate: (view: ViewId) => void;
}

export function formatTime(value?: string) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).format(new Date(value));
}

export function remaining(value?: string) {
  if (!value) return "无窗口";
  const milliseconds = new Date(value).getTime() - Date.now();
  if (milliseconds <= 0) return "已到期";
  const minutes = Math.floor(milliseconds / 60_000);
  return minutes >= 60 ? `${Math.floor(minutes / 60)}时 ${minutes % 60}分` : `${minutes}分`;
}

