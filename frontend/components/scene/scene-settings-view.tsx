"use client";

import { FoundationSpecEditor } from "@/components/scene/foundation-spec-editor";
import { CustomSectionEditor, MemberSpecEditor, SectionCatalogToolbar } from "@/components/scene/member-spec-editor";
import { SceneConditionsPanel } from "@/components/scene/scene-conditions-panel";
import { SceneLoadCases } from "@/components/scene/scene-load-cases";
import { SceneGeotechFields, SceneParameterFields, SpecialistParameterSections } from "@/components/scene/scene-settings-fields";
import { SettingsSection } from "@/components/scene/settings-section";
import type { SceneSettingsModel } from "@/components/scene/scene-settings-model";

/** Settings tab of the legacy scene workspace. */
export function SceneSettingsView({ scene }: { scene: SceneSettingsModel }) {
  const {
    family,
    variant,
    variantId,
    selectVariant,
    material,
    setMaterial,
    sceneTitle,
    setSceneTitle,
    markChanged,
    visibleNodes,
    nodeLabel,
    visibleParameters,
    parameters,
    setParameters,
    updateParameter,
    specs,
    memberSpecifications,
    setMemberSpecifications,
    foundationSpecifications,
    setFoundationSpecifications,
    working,
    hasGenericFoundation,
    geotech,
    setGeotech,
    conditionProfile,
    hasConditions,
    needs,
    conditions,
    setConditions,
    exposure,
    setExposure,
    climateCatalog,
    seismicCatalog,
    selectedClimate,
    factors,
    climateInputsReady,
    roofAssemblies,
    loadCases,
    updateLoadCase,
    addCustomLoad,
    projects,
    selectedProject,
    setSelectedProject,
    projectInstances,
    instance,
    instanceRevisions,
    hydrateFromInstance,
  } = scene;
  return (
    <div className="settings-stack">
      <SettingsSection title="方案与结构体系" subtitle="变体、材料和方案名称">
        <div className="variant-grid compact-grid">
          {family.variants.map((item) => {
            const disabled = item.availability === "development";
            return (
              <button key={item.id} disabled={disabled} className={variantId === item.id ? "active" : ""} onClick={() => selectVariant(item.id)}>
                <strong>{item.title}</strong>
                <span>{item.description}</span>
                <small>{disabled ? "开发中" : item.material_systems.join(" / ")}</small>
              </button>
            );
          })}
        </div>
        {variant && (
          <div className="parameter-grid compact-parameters">
            <label>
              <span>材料体系</span>
              <select
                value={material}
                onChange={(event) => {
                  setMaterial(event.target.value);
                  markChanged();
                }}
              >
                {variant.material_systems.map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>
            </label>
            <label>
              <span>方案名称</span>
              <input value={sceneTitle} onChange={(event) => setSceneTitle(event.target.value)} />
            </label>
          </div>
        )}
      </SettingsSection>

      {(memberSpecifications.length > 0 || foundationSpecifications.length > 0) && (
        <SettingsSection title="构件与基础选型" subtitle="所有关键规格均显式保存">
          {memberSpecifications.length > 0 && <SectionCatalogToolbar onToggle={() => specs.setCustomSectionOpen((value) => !value)} />}
          {specs.customSectionOpen && (
            <CustomSectionEditor
              draft={specs.customSectionDraft}
              preview={specs.customSectionPreview}
              working={working || specs.creatingSection}
              onChange={specs.setCustomSectionDraft}
              onCreate={specs.createCustomSection}
            />
          )}
          {memberSpecifications.map((specification, index) => (
            <MemberSpecEditor
              key={`${specification.node_id}-${specification.member_role}`}
              specification={specification}
              nodeLabel={nodeLabel(specification.node_id)}
              availableSections={specs.availableSections}
              customSection={specs.customSections.find((item) => item.id === specification.section_catalog_id)}
              onRequestCustomSection={() => specs.setCustomSectionOpen(true)}
              onChange={(patch) =>
                setMemberSpecifications((current) => current.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)))
              }
            />
          ))}
          {foundationSpecifications.map((specification, index) => (
            <FoundationSpecEditor
              key={specification.node_id}
              specification={specification}
              nodeLabel={nodeLabel(specification.node_id)}
              onChange={(update) =>
                setFoundationSpecifications((current) => current.map((item, itemIndex) => (itemIndex === index ? update(item) : item)))
              }
            />
          ))}
          {hasGenericFoundation && (
            <div className="boundary-note">
              联合基础、偏心基础＋拉梁为高级选型；整板/筏板仅面向规则池体或密集多柱。桩承台仅在有项目勘察和桩基资料时开放，当前不会自动切换。
            </div>
          )}
        </SettingsSection>
      )}

      <SettingsSection title="尺寸、连接与支承" subtitle="几何参数和条件化地基">
        <div className="parameter-grid">
          <SceneParameterFields parameters={parameters} variantParameters={visibleParameters} onChange={updateParameter} />
          {hasGenericFoundation && (
            <SceneGeotechFields
              geotech={geotech}
              onChange={(patch) => {
                setGeotech((current) => ({ ...current, ...patch }));
                if ("baseFriction" in patch) markChanged();
              }}
            />
          )}
        </div>
        {!hasGenericFoundation && conditionProfile.geotechnical_mode === "generic" && (
          <div className="boundary-note success-note">当前变体通过墙体预埋件与锚筋支承，不需要基础或地勘输入。</div>
        )}
        {conditionProfile.geotechnical_mode === "variant_owned" && (
          <div className="boundary-note success-note">
            当前场景的土、水、抗浮和地基参数已在本场景专属输入中设置，不重复显示通用基础面板。
          </div>
        )}
      </SettingsSection>

      <SpecialistParameterSections
        familyId={family.id}
        nodes={visibleNodes}
        parameters={parameters}
        onChange={(nodeId, key, value) =>
          setParameters((current) => {
            const nodeInputs = (current.scene_node_inputs as Record<string, Record<string, unknown>> | undefined) ?? {};
            return { ...current, scene_node_inputs: { ...nodeInputs, [nodeId]: { ...(nodeInputs[nodeId] ?? {}), [key]: value } } };
          })
        }
      />

      <SettingsSection title="荷载与环境" subtitle={variant?.load_package?.title ?? "场景荷载包"}>
        {(hasConditions || conditionProfile.wind === "optional") && (
          <SceneConditionsPanel
            conditionProfile={conditionProfile}
            needs={needs}
            conditions={conditions}
            onConditionsChange={(patch) => setConditions((current) => ({ ...current, ...patch }))}
            exposure={exposure}
            onExposureChange={(patch) => setExposure((current) => ({ ...current, ...patch }))}
            climateCatalog={climateCatalog}
            seismicCatalog={seismicCatalog}
            selectedClimate={selectedClimate}
            factors={factors}
            climateInputsReady={climateInputsReady}
            roofAssemblies={roofAssemblies}
          />
        )}
        <SceneLoadCases
          loadCases={loadCases}
          climateInputsReady={climateInputsReady}
          nodes={visibleNodes}
          onChange={updateLoadCase}
          onAdd={addCustomLoad}
        />
      </SettingsSection>

      <div className="project-strip scene-project-strip compact-project-strip">
        <label>
          <span>保存位置</span>
          <select
            value={selectedProject}
            onChange={(event) => setSelectedProject(event.target.value === "new" ? "new" : Number(event.target.value))}
          >
            <option value="new">新建项目</option>
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </select>
        </label>
        {selectedProject !== "new" && projectInstances.length > 0 && (
          <label>
            <span>当前方案</span>
            <select
              value={instance?.id ?? ""}
              onChange={(event) => {
                const selected = projectInstances.find((item) => item.id === Number(event.target.value));
                if (selected) hydrateFromInstance(selected, instanceRevisions[selected.id] ?? []);
              }}
            >
              {projectInstances.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.title}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
    </div>
  );
}
