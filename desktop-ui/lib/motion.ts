import type { Variants } from "framer-motion";

export const spring = {
  type: "spring",
  stiffness: 360,
  damping: 34,
  mass: 0.9,
} as const;

export const softSpring = {
  type: "spring",
  stiffness: 260,
  damping: 30,
  mass: 1,
} as const;

export const panelSpring = {
  type: "spring",
  stiffness: 220,
  damping: 32,
  mass: 1.08,
} as const;

export const messageVariants: Variants = {
  initial: { opacity: 0, y: 10, filter: "blur(5px)" },
  animate: { opacity: 1, y: 0, filter: "blur(0px)", transition: softSpring },
  exit: { opacity: 0, y: 4, filter: "blur(4px)", transition: { duration: 0.16 } },
};

export const drawerVariants: Variants = {
  closed: { x: -340, opacity: 0.86, transition: { ...panelSpring, stiffness: 260 } },
  open: { x: 0, opacity: 1, transition: panelSpring },
};

export const overlayVariants: Variants = {
  closed: { opacity: 0, backdropFilter: "blur(0px)" },
  open: { opacity: 1, backdropFilter: "blur(18px)", transition: { duration: 0.28 } },
};

export const panelVariants: Variants = {
  initial: { opacity: 0, x: 18, scale: 0.98 },
  animate: { opacity: 1, x: 0, scale: 1, transition: panelSpring },
  exit: { opacity: 0, x: 14, scale: 0.985, transition: { duration: 0.2 } },
};

export const paletteVariants: Variants = {
  initial: { opacity: 0, scale: 0.96, y: 8 },
  animate: { opacity: 1, scale: 1, y: 0, transition: panelSpring },
  exit: { opacity: 0, scale: 0.97, y: 6, transition: { duration: 0.18 } },
};

export const staggerList: Variants = {
  animate: { transition: { staggerChildren: 0.045 } },
};
