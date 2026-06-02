export default function activate(Anubis: any) {
  Anubis.registerCommand({
    id: "summarize",
    label: "Summarize Vault",
    description: "Ask ANUBIS to summarize local vault context.",
    keywords: ["vault", "memory", "context"],
    async run() {
      await Anubis.core.chat("/context summarize the current vault");
    },
  });

  Anubis.addChatAction({
    id: "save-last-message",
    label: "Save Last Message",
    async run(message: string) {
      await Anubis.core.chat(`/context save this as a reusable note: ${message}`);
    },
  });

  Anubis.registerTool({
    id: "word-count",
    description: "Count words in provided text.",
    async run(input: any) {
      const text = String(input?.text ?? "");
      return {
        words: text.trim().split(/\s+/).filter(Boolean).length,
      };
    },
  });
}
