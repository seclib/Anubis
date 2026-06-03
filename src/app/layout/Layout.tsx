import { memo, useCallback } from "react";
import type { ReactNode } from "react";
import type { AnubisView } from "../state/anubisStore";
import { Sidebar } from "./Sidebar";
import { SystemStatusPanel } from "./SystemStatusPanel";

type LayoutProps = {
  activeView: AnubisView;
  onChangeView: (view: AnubisView) => void;
  children: ReactNode;
};

export const Layout = memo(function Layout({
  activeView,
  onChangeView,
  children,
}: LayoutProps) {
  const changeView = useCallback((view: AnubisView) => {
    onChangeView(view);
  }, [onChangeView]);

  return (
    <main className="app-layout">
      <Sidebar activeView={activeView} onChangeView={changeView} />
      <section className="main-content" aria-label="ANUBIS main content">
        <div className="chat-shell">{children}</div>
      </section>
      <SystemStatusPanel />
    </main>
  );
});
