import { BrainCircuit, ChevronLeft, ChevronRight, Database, History, Layers, MessageCircle, Shield, Sparkles } from "lucide-react";
import { memo, useState } from "react";
import type { AnubisView } from "../state/anubisStore";

type SidebarProps = {
  activeView: AnubisView;
  onChangeView: (view: AnubisView) => void;
};

const navigationItems: Array<{ id: AnubisView; label: string; icon: typeof MessageCircle }> = [
  { id: "chat", label: "Chat", icon: MessageCircle },
  { id: "vault", label: "Memory", icon: Database },
  { id: "tools", label: "Skills", icon: BrainCircuit },
  { id: "plugins", label: "Sessions", icon: History },
  { id: "settings", label: "Control", icon: Shield },
];

export const Sidebar = memo(function Sidebar({ activeView, onChangeView }: SidebarProps) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <aside className={`sidebar ${collapsed ? "collapsed" : ""}`} aria-label="ANUBIS navigation">
      <div className="sidebar-brand">
        <span className="sidebar-mark" aria-hidden="true">
          <Sparkles size={16} />
        </span>
        <span className="sidebar-title">ANUBIS OS</span>
        <button
          className="sidebar-collapse"
          type="button"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          onClick={() => setCollapsed((value) => !value)}
        >
          {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
      </div>

      <nav className="sidebar-nav" aria-label="Primary navigation">
        {navigationItems.map((item) => (
          <button
            className={`sidebar-item ${activeView === item.id ? "active" : ""}`}
            type="button"
            key={item.id}
            onClick={() => onChangeView(item.id)}
            aria-current={activeView === item.id ? "page" : undefined}
            title={collapsed ? item.label : undefined}
          >
            <item.icon size={17} />
            <span>{item.label}</span>
          </button>
        ))}
      </nav>

      <div className="sidebar-cluster" aria-label="Memory routing">
        <div className="cluster-title">
          <Layers size={14} />
          <span>Memory Mesh</span>
        </div>
        <span>Obsidian linked</span>
        <span>Qdrant indexed</span>
      </div>
    </aside>
  );
});
