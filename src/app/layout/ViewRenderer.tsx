import { memo } from "react";
import type { ReactNode } from "react";
import type { AnubisView } from "../state/anubisStore";

type ViewRendererProps = {
  activeView: AnubisView;
  chatView: ReactNode;
};

export const ViewRenderer = memo(function ViewRenderer({ activeView, chatView }: ViewRendererProps) {
  if (activeView === "chat") {
    return <div className="chat-shell">{chatView}</div>;
  }

  return <div className="chat-shell">{chatView}</div>;
});
