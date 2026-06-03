import { Activity, Cpu, DatabaseZap, MemoryStick, RadioTower, Zap } from "lucide-react";
import { memo } from "react";

const statusRows = [
  { label: "CPU", value: "18%", icon: Cpu },
  { label: "Memory", value: "3.8 GB", icon: MemoryStick },
  { label: "Vector DB", value: "Ready", icon: DatabaseZap },
  { label: "Signal", value: "Local", icon: RadioTower },
];

const activeSkills = ["planner", "coder", "memory", "sandbox"];

export const SystemStatusPanel = memo(function SystemStatusPanel() {
  return (
    <aside className="status-panel" aria-label="ANUBIS system status">
      <header className="status-header">
        <div>
          <span className="eyebrow">System</span>
          <h2>ONLINE</h2>
        </div>
        <span className="live-orb" aria-label="Runtime online" />
      </header>

      <div className="status-grid">
        {statusRows.map((row) => (
          <div className="status-row" key={row.label}>
            <row.icon size={16} />
            <span>{row.label}</span>
            <strong>{row.value}</strong>
          </div>
        ))}
      </div>

      <section className="status-section" aria-label="Active skills">
        <div className="status-section-title">
          <Zap size={14} />
          <span>Active Skills</span>
        </div>
        <div className="skill-pills">
          {activeSkills.map((skill) => (
            <span key={skill}>{skill}</span>
          ))}
        </div>
      </section>

      <section className="status-section" aria-label="Agent loop">
        <div className="status-section-title">
          <Activity size={14} />
          <span>Agent Loop</span>
        </div>
        <div className="loop-meter">
          <span />
        </div>
        <p>Context, plan, execute, remember.</p>
      </section>
    </aside>
  );
});
