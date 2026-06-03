import type { ReactNode } from "react";
import { Layout } from "./Layout";

type ShellProps = {
  children: ReactNode;
};

export function Shell({ children }: ShellProps) {
  return (
    <Layout
      activeView="chat"
      onChangeView={() => undefined}
    >
      {children}
    </Layout>
  );
}
