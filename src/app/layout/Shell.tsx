import type { ReactNode } from "react";

type ShellProps = {
  children: ReactNode;
};

export function Shell({ children }: ShellProps) {
  return (
    <main className="app-shell">
      <section className="focus-window" aria-label="ANUBIS desktop shell">
        <header className="topbar">
          <div className="brand">
            <span>ANUBIS</span>
          </div>
        </header>

        {children}
      </section>
    </main>
  );
}
