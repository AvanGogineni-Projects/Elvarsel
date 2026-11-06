import { useEffect } from "react";
import { animate, useMotionValue, useTransform, motion } from "framer-motion";

// Smoothly counts to `value` whenever it changes. Tabular figures so the
// width never jitters mid-animation.
export default function AnimatedNumber({
  value,
  digits = 1,
}: {
  value: number;
  digits?: number;
}) {
  const mv = useMotionValue(value);
  const text = useTransform(mv, (v) =>
    v.toLocaleString("en-GB", {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    })
  );

  useEffect(() => {
    const controls = animate(mv, value, {
      duration: 0.8,
      ease: [0.16, 1, 0.3, 1],
    });
    return controls.stop;
  }, [mv, value]);

  return <motion.span className="tabular">{text}</motion.span>;
}
