// Quiet animated backdrop: a faint dot grid plus two slow-drifting colour
// blooms. Pure CSS/transform animation — no video, no WebGL — so it stays
// cheap and appropriate for a monitoring surface.
export default function AuroraBackground() {
  return (
    <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      <div className="absolute inset-0 bg-ink-900" />
      <div
        className="absolute inset-0 opacity-[0.35]"
        style={{
          backgroundImage:
            "radial-gradient(rgba(148,163,210,0.12) 1px, transparent 1px)",
          backgroundSize: "34px 34px",
          maskImage:
            "radial-gradient(ellipse 80% 60% at 50% 0%, #000 40%, transparent 100%)",
          WebkitMaskImage:
            "radial-gradient(ellipse 80% 60% at 50% 0%, #000 40%, transparent 100%)",
        }}
      />
      <div className="absolute -top-40 left-1/4 h-[36rem] w-[36rem] animate-aurora rounded-full bg-se1/20 blur-[120px]" />
      <div
        className="absolute -right-40 top-20 h-[32rem] w-[32rem] animate-aurora rounded-full bg-se3/20 blur-[120px]"
        style={{ animationDelay: "-6s" }}
      />
      <div
        className="absolute bottom-0 left-1/3 h-[28rem] w-[28rem] animate-aurora rounded-full bg-se2/10 blur-[120px]"
        style={{ animationDelay: "-11s" }}
      />
    </div>
  );
}
