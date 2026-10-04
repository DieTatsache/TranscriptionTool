import { useState } from "react";

// Small, dependency-free chart primitives. Values always appear as text next to the
// marks (or in the cards beside a chart), so nothing is readable only by hovering.

const SIZE = 320;
const CENTER = SIZE / 2;
const RADIUS = 100;
const RINGS = [2, 4, 6, 8, 10];
const LINE_HEIGHT = 15; // label line height in viewBox units (12.5px text * 1.25)
const LABEL_GAP = 18; // between the outer ring and the axis labels

function polar(index, count, radius) {
  const angle = -Math.PI / 2 + (index * 2 * Math.PI) / count;
  return [CENTER + radius * Math.cos(angle), CENTER + radius * Math.sin(angle)];
}

// A value on its axis, clamped to the scale.
function point(index, count, value, max) {
  return polar(index, count, (Math.max(0, Math.min(value, max)) / max) * RADIUS);
}

function polygon(count, valueAt, max) {
  return Array.from({ length: count }, (_, i) => point(i, count, valueAt(i), max).join(",")).join(" ");
}

// axes: [{ key, label, value }] scored 0..max. One series: one hue, a light wash, 2px line.
export function RadarChart({ axes, max = 10, title }) {
  const [active, setActive] = useState(null);
  const count = axes.length;
  const summary = axes.map((a) => `${a.label} ${a.value} of ${max}`).join(", ");

  return (
    <div className="radar">
      <svg viewBox={`0 0 ${SIZE} ${SIZE}`} role="img" aria-label={`${title}: ${summary}`}>
        {RINGS.map((ring) => (
          <polygon key={ring} className="radar-ring" points={polygon(count, () => ring, max)} />
        ))}
        {axes.map((axis, i) => {
          const [x, y] = point(i, count, max, max);
          return <line key={axis.key} className="radar-spoke" x1={CENTER} y1={CENTER} x2={x} y2={y} />;
        })}
        {[5, 10].map((tick) => (
          <text key={tick} className="radar-tick" x={CENTER + 4} y={CENTER - (tick / max) * RADIUS + 11}>
            {tick}
          </text>
        ))}
        <polygon className="radar-area" points={polygon(count, (i) => axes[i].value, max)} />
        {axes.map((axis, i) => {
          const [x, y] = point(i, count, axis.value, max);
          return (
            <g key={axis.key}>
              <circle className={"radar-dot" + (active === i ? " active" : "")} cx={x} cy={y} r={5} />
              {/* Hit area bigger than the mark; keyboard users get the same readout. */}
              <circle
                className="radar-hit"
                cx={x}
                cy={y}
                r={14}
                tabIndex={0}
                aria-label={`${axis.label}: ${axis.value} of ${max}`}
                onPointerEnter={() => setActive(i)}
                onPointerLeave={() => setActive(null)}
                onFocus={() => setActive(i)}
                onBlur={() => setActive(null)}
              />
            </g>
          );
        })}
        {axes.map((axis, i) => {
          const [x, y] = polar(i, count, RADIUS + LABEL_GAP);
          const anchor = Math.abs(x - CENTER) < 1 ? "middle" : x > CENTER ? "start" : "end";
          // Labels above the centre grow upwards, so their value line stays clear of the ring.
          const top = y < CENTER - 1 ? y - LINE_HEIGHT : y;
          return (
            <text key={axis.key} className="radar-label" x={x} y={top} textAnchor={anchor}>
              <tspan className="radar-label-name">{axis.label}</tspan>
              <tspan className="radar-label-value" x={x} dy="1.25em">
                {axis.value}/{max}
              </tspan>
            </text>
          );
        })}
      </svg>
      {active !== null && <RadarTooltip axis={axes[active]} index={active} count={count} max={max} />}
    </div>
  );
}

function RadarTooltip({ axis, index, count, max }) {
  const [x, y] = point(index, count, axis.value, max);
  return (
    <div className="chart-tooltip" style={{ left: `${(x / SIZE) * 100}%`, top: `${(y / SIZE) * 100}%` }} role="status">
      <strong>
        {axis.value} / {max}
      </strong>
      <span>{axis.label}</span>
    </div>
  );
}

// One horizontal bar with its value at the tip. `tone`: "series" (default), "good", "muted".
export function BarRow({ label, value, max, display, tone = "series", icon = null, detail }) {
  const width = max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0;
  return (
    <div className={"bar-row " + tone} title={detail}>
      <span className="bar-row-label">
        {icon}
        {label}
      </span>
      <span className="bar-track" aria-hidden="true">
        {/* No mark at all for zero: the minimum width only keeps tiny values visible. */}
        <span className={"bar-fill" + (width > 0 ? "" : " zero")} style={{ width: `${width}%` }} />
      </span>
      <span className="bar-row-value">{display}</span>
    </div>
  );
}
