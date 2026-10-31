import type { Module } from "@/lib/types";

const ARROW_XS = [55, 90, 125, 160, 195, 230];

function LoadArrows({ xs, from, to }: { xs: number[]; from: number; to: number }) {
  return xs.map((x) => (
    <path className="load-arrow" d={`M${x} ${from} L${x} ${to}`} key={x} markerEnd="url(#arrow)" />
  ));
}

export function StructureSketch({ module, inputs }: { module: Module; inputs: Record<string, unknown> }) {
  const span = Number(inputs.span_m ?? 3);
  const height = Number(inputs.height_m ?? 3);
  const isColumn = module.endsWith("column");
  const isFrame = ["portal_frame", "planar_frame"].includes(module);
  const isFoundation = module.endsWith("footing");
  return (
    <div className="structure-sketch" aria-label="结构模型示意">
      <svg viewBox="0 0 280 130" role="img">
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" />
          </marker>
        </defs>
        {isFoundation ? (
          <>
            <path className="member" d="M124 18 L156 18 L156 62 L228 92 L52 92 L124 62 Z" />
            <path className="support-line" d="M35 94 L245 94" />
            <LoadArrows xs={ARROW_XS} from={112} to={99} />
            <text x="140" y="126">基底压力示意</text>
          </>
        ) : isFrame ? (
          <>
            <path className="member" d="M45 108 L45 32 L235 32 L235 108" />
            <LoadArrows xs={[70, 105, 140, 175, 210]} from={8} to={25} />
            <path className="dimension" d="M45 120 L235 120" />
            <text x="140" y="128">L = {span} m</text>
            <text x="11" y="72" transform="rotate(-90 11 72)">H = {height} m</text>
          </>
        ) : isColumn ? (
          <>
            <path className="member" d="M140 18 L140 104" />
            <path className="load-arrow" d="M140 2 L140 14" markerEnd="url(#arrow)" />
            <path className="support-line" d="M112 106 L168 106" />
            <text x="154" y="62">H = {height} m</text>
          </>
        ) : (
          <>
            <path className="member" d="M35 76 L245 76" />
            <LoadArrows xs={ARROW_XS} from={38} to={67} />
            <path className="support" d="M35 80 L25 100 L45 100 Z" />
            <path className="support" d="M245 80 L235 100 L255 100 Z" />
            <path className="dimension" d="M35 116 L245 116" />
            <text x="140" y="126">L = {span} m</text>
          </>
        )}
      </svg>
      <span>结构模型示意 · 非施工图</span>
    </div>
  );
}
