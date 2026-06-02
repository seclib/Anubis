import type { ReactNode } from "react";
import type { AnubisView } from "../state/anubisStore";
import { Sidebar } from "./Sidebar";

type LayoutProps = {
  activeView: AnubisView;
  onChangeView: (view: AnubisView) => void;
  children: ReactNode;
};

export function Layout({ activeView, onChangeView, children }: LayoutProps) {
  return (
    <main className="app-layout">
      <Sidebar activeView={activeView} onChangeView={onChangeView} />
      <section className="chat-workspace" aria-label="ANUBIS chat workspace">
        <div className="chat-shell">{children}</div>
      </section>
    </main>
  );
}
