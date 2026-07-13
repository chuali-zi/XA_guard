import type { ReactNode, SVGProps } from "react";

export function Icon({ name, ...props }: SVGProps<SVGSVGElement> & { name: string }) {
  const paths: Record<string, ReactNode> = {
    agents: <><circle cx="8" cy="7" r="3"/><path d="M3 18v-2a5 5 0 0 1 10 0v2M16 5h5v5M18.5 5v5M16 7.5h5"/></>,
    ticket: <><path d="M5 3h14v18H5zM8 8h8M8 12h8M8 16h5"/></>,
    effects: <><path d="M4 12h4l2-7 4 14 2-7h4M4 20h16"/></>,
    approvals: <><path d="M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7zM8 12l2.5 2.5L16 9"/></>,
    assignments: <><path d="M4 5h16M4 12h16M4 19h16M8 3v4M15 10v4M11 17v4"/></>,
    evidence: <><path d="M6 3h9l4 4v14H6zM15 3v5h4M9 13l2 2 4-5"/></>,
    refresh: <><path d="M20 7v5h-5M4 17v-5h5M6.1 9A7 7 0 0 1 18 6l2 6M18 15a7 7 0 0 1-12 3l-2-6"/></>,
    exit: <><path d="M10 4H4v16h6M14 8l4 4-4 4M8 12h10"/></>,
    arrow: <path d="M5 12h14M14 7l5 5-5 5"/>,
  };
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="square" strokeLinejoin="miter" aria-hidden="true" {...props}>{paths[name]}</svg>;
}
