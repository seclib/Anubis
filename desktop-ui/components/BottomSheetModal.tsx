"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { panelSpring } from "../lib/motion";

export function BottomSheetModal({
  open,
  title,
  children,
  onClose,
}: {
  open: boolean;
  title: string;
  children: React.ReactNode;
  onClose: () => void;
}) {
  const reduceMotion = useReducedMotion();

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0, backdropFilter: "blur(0px)" }}
          animate={{ opacity: 1, backdropFilter: "blur(18px)" }}
          exit={{ opacity: 0, backdropFilter: "blur(0px)" }}
          className="fixed inset-0 z-40 flex items-end justify-center bg-slate-950/35 p-4"
          onMouseDown={onClose}
        >
          <motion.section
            initial={{ opacity: 0, y: 36, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 22, scale: 0.985 }}
            transition={reduceMotion ? { duration: 0 } : panelSpring}
            drag="y"
            dragConstraints={{ top: 0, bottom: 0 }}
            dragElastic={0.12}
            onDragEnd={(_, info) => {
              if (info.offset.y > 90 || info.velocity.y > 700) onClose();
            }}
            onMouseDown={(event) => event.stopPropagation()}
            className="glass w-[min(720px,calc(100vw-24px))] rounded-t-[24px] p-5"
          >
            <div className="mx-auto mb-4 h-1.5 w-12 rounded-full bg-white/10" />
            <h2 className="text-lg font-semibold text-slate-50">{title}</h2>
            <div className="mt-4">{children}</div>
          </motion.section>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
