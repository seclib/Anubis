import type { AnubisView } from "../state/anubisStore";

type SidebarProps = {
  activeView: AnubisView;
  onChangeView: (view: AnubisView) => void;
};

const navigationItems: Array<{ id: AnubisView; label: string }> = [
  { id: "chat", label: "Chat" },
  { id: "vault", label: "Files / Vault" },
  { id: "tools", label: "Tools" },
  { id: "plugins", label: "Plugins" },
  { id: "settings", label: "Settings" },
];

export function Sidebar({ activeView, onChangeView }: SidebarProps) {
  return (
    <aside className="sidebar" aria-label="ANUBIS navigation">
      <div className="sidebar-brand">
        <span className="sidebar-mark">A</span>
        <span>ANUBIS</span>
      </div>

      <nav className="sidebar-nav" aria-label="Primary navigation">
        {navigationItems.map((item) => (
          <button
            className={`sidebar-item ${activeView === item.id ? "active" : ""}`}
            type="button"
            key={item.id}
            onClick={() => onChangeView(item.id)}
            aria-current={activeView === item.id ? "page" : undefined}
          >
            <span>{item.label}</span>
          </button>
        ))}
      </nav>
    </aside>
  );
}
