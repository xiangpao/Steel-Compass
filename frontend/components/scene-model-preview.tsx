"use client";

import { Line, OrbitControls } from "@react-three/drei";
import { Canvas, useThree } from "@react-three/fiber";
import { useEffect, useMemo } from "react";
import * as THREE from "three";

import type {
  FoundationDesignSpecification,
  SceneGeometryProfile,
} from "@/lib/types";

type Props = {
  geometry: SceneGeometryProfile;
  foundation?: FoundationDesignSpecification | null;
  foundationsBySupportId?: Record<string, FoundationDesignSpecification>;
  selectedMemberId?: string | null;
  selectedFoundationId?: string | null;
  onSelectMember?: (memberId: string) => void;
  onSelectFoundation?: (foundationId: string) => void;
};

function FitCamera({ modelSize }: { modelSize: number }) {
  const { camera, size } = useThree();
  useEffect(() => {
    if (!(camera instanceof THREE.PerspectiveCamera) || size.width <= 0 || size.height <= 0) return;
    const aspect = size.width / size.height;
    const paddedSize = modelSize + 2.5;
    const distance = (paddedSize * 0.62) / Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) / Math.min(aspect, 1);
    camera.position.set(distance * 0.62, distance * 0.48, distance * 0.70);
    camera.near = Math.max(distance / 100, 0.05);
    camera.far = Math.max(distance * 10, 200);
    camera.lookAt(0, modelSize * 0.22, 0);
    camera.updateProjectionMatrix();
  }, [camera, modelSize, size.height, size.width]);
  return null;
}

function RoofPanel({ points }: { points: Array<[number, number, number]> }) {
  const geometry = useMemo(() => {
    const vertices: number[] = [];
    for (let index = 1; index < points.length - 1; index += 1) {
      vertices.push(...points[0], ...points[index], ...points[index + 1]);
    }
    const result = new THREE.BufferGeometry();
    result.setAttribute("position", new THREE.Float32BufferAttribute(vertices, 3));
    result.computeVertexNormals();
    return result;
  }, [points]);

  return (
    <mesh geometry={geometry}>
      <meshStandardMaterial
        color="#9ac7d3"
        opacity={0.28}
        transparent
        side={THREE.DoubleSide}
      />
    </mesh>
  );
}

function TaperedFoundation({ length, width, height }: { length: number; width: number; height: number }) {
  const geometry = useMemo(() => {
    const topLength = Math.max(length * 0.38, 0.35);
    const topWidth = Math.max(width * 0.38, 0.35);
    const y0 = -height;
    const y1 = 0;
    const vertices = [
      [-length / 2, y0, -width / 2], [length / 2, y0, -width / 2], [length / 2, y0, width / 2], [-length / 2, y0, width / 2],
      [-topLength / 2, y1, -topWidth / 2], [topLength / 2, y1, -topWidth / 2], [topLength / 2, y1, topWidth / 2], [-topLength / 2, y1, topWidth / 2],
    ];
    const faces = [0, 2, 1, 0, 3, 2, 4, 5, 6, 4, 6, 7, 0, 1, 5, 0, 5, 4, 1, 2, 6, 1, 6, 5, 2, 3, 7, 2, 7, 6, 3, 0, 4, 3, 4, 7];
    const result = new THREE.BufferGeometry();
    result.setAttribute("position", new THREE.Float32BufferAttribute(vertices.flat(), 3));
    result.setIndex(faces);
    result.computeVertexNormals();
    return result;
  }, [height, length, width]);
  return <mesh geometry={geometry}><meshStandardMaterial color="#c8b89f" /></mesh>;
}

function FoundationMesh({ item, position, selected = false, onClick }: { item: FoundationDesignSpecification; position: [number, number, number]; selected?: boolean; onClick?: () => void }) {
  const height = item.thickness_mm / 1000;
  return (
    <group position={position} onClick={(event) => { event.stopPropagation(); onClick?.(); }}>
      {item.section_shape === "tapered" ? (
        <TaperedFoundation length={item.length_m} width={item.width_m} height={height} />
      ) : (
        <>
          <mesh position={[0, -height / 2, 0]}>
            <boxGeometry args={[item.length_m, height, item.width_m]} />
            <meshStandardMaterial color={selected ? "#dc6b2f" : "#c8b89f"} />
          </mesh>
          {item.section_shape === "stepped" && (
            <mesh position={[0, 0.12, 0]}>
              <boxGeometry args={[Math.max(0.5, item.length_m * 0.58), 0.24, Math.max(0.5, item.width_m * 0.58)]} />
              <meshStandardMaterial color={selected ? "#bb5121" : "#b4a084"} />
            </mesh>
          )}
        </>
      )}
      {item.pedestal?.enabled && (
        <mesh position={[0, (item.pedestal.height_mm ?? 600) / 2000, 0]}>
          <boxGeometry args={[(item.pedestal.length_mm ?? 500) / 1000, (item.pedestal.height_mm ?? 600) / 1000, (item.pedestal.width_mm ?? 500) / 1000]} />
          <meshStandardMaterial color="#9b8a72" />
        </mesh>
      )}
    </group>
  );
}

function Model({ geometry, foundation, foundationsBySupportId, selectedMemberId, selectedFoundationId, onSelectMember, onSelectFoundation }: Props) {
  const nodes = useMemo(() => new Map(geometry.nodes.map((node) => [node.id, node])), [geometry.nodes]);
  const bounds = useMemo(() => {
    const xs = geometry.nodes.map((item) => item.x_m);
    const ys = geometry.nodes.map((item) => item.y_m);
    const zs = geometry.nodes.map((item) => item.z_m);
    return {
      center: [(Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...zs) + Math.max(...zs)) / 2, (Math.min(...ys) + Math.max(...ys)) / 2] as [number, number, number],
      size: Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys), Math.max(...zs) - Math.min(...zs), 1),
    };
  }, [geometry.nodes]);

  const convert = (node: SceneGeometryProfile["nodes"][number]): [number, number, number] => [
    node.x_m - bounds.center[0],
    node.z_m - bounds.center[1],
    node.y_m - bounds.center[2],
  ];

  return (
    <>
      <ambientLight intensity={1.7} />
      <directionalLight position={[8, 12, 6]} intensity={2.2} />
      <FitCamera modelSize={bounds.size} />
      <gridHelper args={[Math.max(12, bounds.size * 1.6), 12, "#b7c0c7", "#e2e7ea"]} position={[0, -0.02, 0]} />
      {geometry.roof_surfaces.map((surface) => {
        const points = surface.node_ids.map((id) => nodes.get(id)).filter(Boolean).map((node) => convert(node!));
        return points.length >= 3 ? <RoofPanel key={surface.id} points={points} /> : null;
      })}
      {geometry.members.map((member) => {
        const start = nodes.get(member.start_node_id);
        const end = nodes.get(member.end_node_id);
        if (!start || !end) return null;
        return (
          <Line
            key={member.id}
            points={[convert(start), convert(end)]}
            color={selectedMemberId === member.id ? "#dc6b2f" : member.role === "column" ? "#1e6675" : member.role === "brace" ? "#d97942" : "#263d4a"}
            lineWidth={selectedMemberId === member.id ? 7 : member.role === "column" ? 4 : 3}
            onClick={(event) => { event.stopPropagation(); onSelectMember?.(member.id); }}
          />
        );
      })}
      {(geometry.supports ?? []).map((support) => {
        const node = nodes.get(support.node_id);
        const instance = geometry.foundation_instances?.find((item) => item.support_id === support.id);
        const item = foundationsBySupportId?.[support.id] ?? foundation;
        return node && item ? (
          <FoundationMesh
            key={`foundation-${support.id}`}
            item={item}
            position={convert(node)}
            selected={Boolean(instance && selectedFoundationId === instance.id)}
            onClick={() => instance && onSelectFoundation?.(instance.id)}
          />
        ) : null;
      })}
      <OrbitControls makeDefault enableDamping minDistance={2} maxDistance={60} target={[0, bounds.size * 0.22, 0]} />
    </>
  );
}

export function SceneModelPreview({ geometry, foundation, foundationsBySupportId, selectedMemberId, selectedFoundationId, onSelectMember, onSelectFoundation }: Props) {
  return (
    <div className="scene-model-preview" role="img" aria-label="当前亭廊结构和基础三维简图">
      <Canvas camera={{ position: [9, 7, 10], fov: 42, near: 0.1, far: 200 }} dpr={[1, 1.75]}>
        <Model geometry={geometry} foundation={foundation} foundationsBySupportId={foundationsBySupportId} selectedMemberId={selectedMemberId} selectedFoundationId={selectedFoundationId} onSelectMember={onSelectMember} onSelectFoundation={onSelectFoundation} />
      </Canvas>
      <div className="scene-model-legend">
        <span><i className="legend-column" />柱</span>
        <span><i className="legend-beam" />梁 / 屋面杆件</span>
        <span>拖动旋转 · 滚轮缩放</span>
      </div>
    </div>
  );
}
