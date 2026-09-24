// Minimal inline SVG icon set — no external dependency.
const paths = {
  mic: "M12 2a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3zM5 10v1a7 7 0 0 0 14 0v-1M12 19v3",
  script:
    "M4 4h11l5 5v11a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V4zM14 4v5h5M8 13h8M8 17h5",
  quiz: "M9 9a3 3 0 1 1 4 2.8c-.8.4-1 .9-1 1.7M12 17h.01M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z",
  video: "M4 5h11a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1zM16 9l5-3v12l-5-3",
  transcript: "M4 6h16M4 10h16M4 14h10M4 18h13",
  plus: "M12 5v14M5 12h14",
  check: "M20 6 9 17l-5-5",
  clock: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7v5l3 2",
  play: "M8 5v14l11-7z",
  pause: "M6 4h4v16H6zM14 4h4v16h-4z",
  wave: "M3 12h2l2-6 3 12 3-9 2 5 2-3h4",
  arrow: "M5 12h14M13 6l6 6-6 6",
  spark: "M12 3l1.9 5.6L19.5 10l-5.6 1.4L12 17l-1.9-5.6L4.5 10l5.6-1.4L12 3z",
  copy: "M9 9h10a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H9a1 1 0 0 1-1-1V10a1 1 0 0 1 1-1zM5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1",
  refresh: "M21 12a9 9 0 1 1-2.6-6.4M21 3v5h-5",
  chat: "M21 12a8 8 0 0 1-11.2 7.3L4 21l1.7-5.8A8 8 0 1 1 21 12zM9 11h.01M12 11h.01M15 11h.01",
  close: "M18 6 6 18M6 6l12 12",
  // Feather icons (MIT)
  upload: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12",
  trash: "M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M10 11v6M14 11v6",
  link: "M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71",
  alert: "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zM12 8v4M12 16h.01",
};

export default function Icon({ name, size = 18, stroke = 1.8, fill = "none", style }) {
  const filled = name === "play";
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={filled ? "currentColor" : fill}
      stroke={filled ? "none" : "currentColor"}
      strokeWidth={stroke}
      strokeLinecap="round"
      strokeLinejoin="round"
      style={style}
      aria-hidden="true"
    >
      <path d={paths[name]} />
    </svg>
  );
}
