import { useMemo } from "react";
import QRCode from "qrcode";

const QUIET_ZONE = 2; // modules of white border, needed by scanners

// The QR code drawn as React SVG elements: no markup string is injected into the page.
export default function QrCode({ value, size = 260, label }) {
  const path = useMemo(() => {
    try {
      const { modules } = QRCode.create(value, { errorCorrectionLevel: "M" });
      let d = "";
      for (let row = 0; row < modules.size; row += 1) {
        for (let col = 0; col < modules.size; col += 1) {
          if (modules.get(row, col)) d += `M${col + QUIET_ZONE} ${row + QUIET_ZONE}h1v1h-1z`;
        }
      }
      return { d, extent: modules.size + 2 * QUIET_ZONE };
    } catch {
      return null; // e.g. text too long for a QR code
    }
  }, [value]);

  if (!path) return <p className="qr-error">The QR code could not be created.</p>;
  return (
    <svg
      className="qr-svg"
      viewBox={`0 0 ${path.extent} ${path.extent}`}
      width={size}
      height={size}
      role="img"
      aria-label={label}
      shapeRendering="crispEdges"
    >
      <rect width={path.extent} height={path.extent} fill="#ffffff" />
      <path d={path.d} fill="#0f1117" />
    </svg>
  );
}
