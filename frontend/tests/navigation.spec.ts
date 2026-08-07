import { expect, test, type Page } from "@playwright/test";

const pergolaGraph = {
  id: "pergola-flat-chain",
  version: "test-scenes-2.1",
  nodes: [
    {
      id: "environment",
      label: "顶面恒载、活载与风雪",
      role: "load",
      required: true,
      applicability: "required",
      maturity: "verified",
      verification_status: "independently_verified",
      description: "",
    },
    {
      id: "roof_members",
      label: "檩条 / 椽条",
      role: "secondary_member",
      calculation_module: "steel_beam",
      required: true,
      applicability: "required",
      maturity: "beta",
      verification_status: "independently_verified",
      description: "",
    },
    {
      id: "base_connection",
      label: "柱脚与锚栓",
      role: "connection",
      required: true,
      applicability: "required",
      maturity: "beta",
      verification_status: "unverified",
      quick_assumption: "按保守连接假定完成方案快算。",
      description: "",
    },
    {
      id: "foundation",
      label: "柱下基础",
      role: "foundation",
      calculation_module: "spread_footing",
      required: true,
      applicability: "required",
      maturity: "beta",
      verification_status: "unverified",
      description: "",
    },
  ],
  connections: [],
};

const pergolaLoads = {
  id: "pergola-flat-loads",
  version: "test-loads-2.1",
  title: "廊架平顶场景荷载包",
  description: "廊架专用荷载。",
  items: [
    {
      id: "pergola-dead",
      label: "顶面附加恒载",
      kind: "dead",
      value_type: "reference_range",
      recommended_min: 0.3,
      recommended_default: 0.5,
      recommended_max: 0.8,
      adopted_value: 0.5,
      unit: "kN/m2",
      source_reference: "项目构造层复核值",
      applicable_when: "平顶廊架",
      distribution: "area",
      direction: "gravity",
      application_target: "roof_members",
      confirmed: false,
      notes: "",
    },
    {
      id: "pergola-wind-uplift",
      label: "顶面风吸力",
      kind: "wind",
      value_type: "calculated",
      adopted_value: 0,
      unit: "kN/m2",
      source_reference: "GB 50009-2012 风荷载向导",
      applicable_when: "平顶廊架受风工况",
      distribution: "pressure",
      direction: "uplift",
      application_target: "roof_members",
      confirmed: false,
      notes: "",
    },
  ],
};

const families = [
  {
    id: "pergola-pavilion",
    title: "廊架 / 景亭",
    description: "从顶面、檩条、主框架、柱脚一直计算到基础。",
    icon: "pergola",
    maturity: "beta",
    availability: "public",
    default_variant_id: "flat-single",
    variants: [
      {
        id: "flat-single",
        title: "平顶单跨",
        description: "规则平顶单跨构架。",
        availability: "public",
        support_system: "column_supported",
        roof_form: "flat",
        material_systems: ["钢", "木", "钢木混合"],
        parameters: [
          {
            key: "span_m",
            label: "跨度",
            value_type: "number",
            unit: "m",
            default: 4,
            options: [],
            required: true,
          },
        ],
        graph_template: pergolaGraph,
        load_package: pergolaLoads,
      },
    ],
    graph_template: pergolaGraph,
    boundaries: ["不支持任意三维自由建模"],
  },
  {
    id: "canopy",
    title: "雨棚",
    description: "墙附式和柱支式采用不同传力链。",
    icon: "canopy",
    maturity: "beta",
    availability: "public",
    default_variant_id: "wall-cantilever",
    variants: [
      {
        id: "wall-cantilever",
        title: "墙附悬挑",
        description: "通过墙体基材和锚栓组支承。",
        availability: "public",
        support_system: "wall_attached",
        material_systems: ["钢"],
        parameters: [
          { key: "cantilever_m", label: "悬挑长度", value_type: "number", unit: "m", default: 1.8, options: [], required: true },
        ],
        graph_template: {
          id: "canopy-wall-chain",
          version: "test-scenes-2.1",
          nodes: [
            { id: "cover", label: "覆盖层与风雪", role: "load", required: true, applicability: "required", maturity: "verified", verification_status: "independently_verified", description: "" },
            { id: "cantilever", label: "悬挑梁", role: "primary_member", calculation_module: "steel_beam", required: true, applicability: "required", maturity: "beta", verification_status: "independently_verified", description: "" },
            { id: "wall_anchor", label: "墙体基材与锚栓组", role: "connection", required: true, applicability: "required", maturity: "beta", verification_status: "unverified", quick_assumption: "快算按已确认墙体基材与锚固假定。", description: "" },
          ],
          connections: [],
        },
        load_package: { ...pergolaLoads, id: "canopy-loads", title: "墙附雨棚荷载包" },
      },
    ],
    graph_template: { id: "canopy", version: "test", nodes: [], connections: [] },
    boundaries: ["墙体基材需专项复核"],
  },
  {
    id: "water-feature-pool",
    title: "水景池体",
    description: "水池与抗浮。",
    icon: "pool",
    maturity: "planned",
    availability: "development",
    variants: [],
    graph_template: { id: "pool", version: "test", nodes: [], connections: [] },
    boundaries: [],
  },
];

const calculationLibrary = {
  version: "test-library",
  items: [
    { id: "steel-beam", title: "钢梁", task: "superstructure", task_title: "上部构件", material: "steel", module: "steel_beam", maturity: "beta", description: "简支梁和悬挑梁。", presets: ["廊架檩条"] },
    { id: "spread-footing", title: "柱下独立基础", task: "foundations_geotechnical", task_title: "基础与地基", material: "concrete", module: "spread_footing", maturity: "beta", description: "柱底反力至浅基础。", presets: [] },
  ],
};

async function mockWorkspace(page: Page) {
  const baseInstance = { id: 11, project_id: 9, family_id: "pergola-pavilion", variant_id: "flat-single", title: "测试场景", mode: "quick", template_version: "test-scenes-2.1", draft_state: {}, stale_node_ids: [], archived: false, created_at: "2026-07-31", updated_at: "2026-07-31" };
  const copiedInstance = { ...baseInstance, id: 12, title: "测试场景（副本）" };
  let instances = [baseInstance];
  await page.route("**/api/v1/auth/me", (route) => route.fulfill({ json: { id: 1, username: "tester", display_name: "测试用户", is_admin: false, must_change_password: false } }));
  await page.route("**/api/v2/scenario-families", (route) => route.fulfill({ json: families }));
  await page.route("**/api/v2/calculation-library", (route) => route.fulfill({ json: calculationLibrary }));
  await page.route("**/api/v2/projects", (route) => {
    if (route.request().method() === "POST") {
      return route.fulfill({ json: { id: 9, name: "测试场景", description: "", created_at: "2026-07-31", updated_at: "2026-07-31", version_count: 0 } });
    }
    return route.fulfill({ json: [] });
  });
  await page.route("**/api/v2/projects/9/scene-instances", (route) => {
    if (route.request().method() === "GET") return route.fulfill({ json: instances });
    return route.fulfill({ json: baseInstance });
  });
  await page.route("**/api/v2/projects/9/scene-instances/11", (route) => route.fulfill({ json: baseInstance }));
  await page.route("**/api/v2/projects/9/scene-instances/11/duplicate", (route) => {
    instances = [copiedInstance, baseInstance];
    return route.fulfill({ json: copiedInstance });
  });
  const revision = {
    id: 21, project_id: 9, revision_number: 1, snapshot_schema_version: "2.1", scene_instance_id: 11,
    scene_result: { scene_family_id: "pergola-pavilion", scene_variant_id: "flat-single", mode: "quick", status: "passed", workflow_status: "ready", engineering_status: "passed", result_class: "quick_estimate", verification_status: "unverified", completed_nodes: 4, total_required_nodes: 4, node_results: Object.fromEntries(pergolaGraph.nodes.map((node) => [node.id, { node_id: node.id, label: node.label, status: node.calculation_module ? "passed" : "completed", maturity: node.maturity, stale: false }])), missing_nodes: [], stale_node_ids: [], control_path: pergolaGraph.nodes.map((node) => node.label), warnings: ["柱脚仍需专业复核。"], catalog_versions: { scenes: "test-scenes-2.1" }, load_cases: pergolaLoads.items },
    result_bundle: { roof_members: { schema_version: "2.0", engine_version: "test", trace_id: "trace", project_name: "测试", module: "steel_beam", mode: "quick", status: "passed", result_class: "quick_estimate", verification_status: "independently_verified", standards: [], input_summary: {}, combinations: [], reactions: {}, diagrams: [], steps: [], checks: [{ name: "弯曲", demand: { value: 1, unit: "kN.m" }, capacity: { value: 2, unit: "kN.m" }, utilization: 0.5, passed: true, reference: "test" }], warnings: [], assumptions: [], applicability: [], disclaimer: "" } },
    catalog_versions: {}, engine_version: "test", report_number: "SC-TEST-001", created_at: "2026-07-31",
  };
  await page.route("**/api/v2/projects/9/scene-revisions**", (route) => {
    if (route.request().method() === "GET") {
      const instanceId = new URL(route.request().url()).searchParams.get("scene_instance_id");
      return route.fulfill({ json: instanceId === "12" ? [{ ...revision, id: 22, scene_instance_id: 12, report_number: "SC-TEST-002" }] : [revision] });
    }
    return route.fulfill({ json: revision });
  });
  await page.route("**/api/v2/catalogs/materials", (route) => route.fulfill({ json: { version: "test", standard_profile: "CN-2024", source_references: [], items: [] } }));
  await page.route("**/api/v2/catalogs/load-presets", (route) => route.fulfill({ json: { version: "test", confirmation_required: true, items: [] } }));
  await page.route("**/api/v2/catalogs/climate-locations", (route) => route.fulfill({ json: { version: "test-climate", coverage: "test", professional_use_requires_confirmation: true, items: [{ id: "beijing", province: "北京", city: "北京市", station: "北京站", elevation_m: 54, wind_kpa: { "10": 0.3, "50": 0.45, "100": 0.5 }, snow_kpa: { "10": 0.25, "50": 0.4, "100": 0.45 }, snow_zone: "Ⅱ" }] } }));
}

async function enterSingleCalculation(page: Page) {
  await page.getByRole("button", { name: "打开导航" }).click();
  const rail = page.locator("aside.left-rail");
  await rail.getByRole("button", { name: /单项计算/ }).click();
  await rail.getByRole("button", { name: /^SB 钢梁 / }).click();
  await rail.getByRole("button", { name: "应用并关闭" }).click();
}

test("移动抽屉选择期间保持打开，应用后关闭", async ({ page }) => {
  await mockWorkspace(page);
  await page.setViewportSize({ width: 900, height: 800 });
  await page.goto("/");
  await page.getByRole("button", { name: "打开导航" }).click();
  const rail = page.locator("aside.left-rail");
  await rail.getByRole("button", { name: /单项计算/ }).click();
  await rail.getByRole("button", { name: /^SB 钢梁 / }).click();
  await expect(rail).toHaveClass(/open/);
  await rail.getByRole("button", { name: "应用并关闭" }).click();
  await expect(rail).not.toHaveClass(/open/);
  await expect(page.getByRole("heading", { name: "钢梁" })).toBeVisible();
});

test("场景只保留设置和结果两个主状态并在同页编辑主要输入", async ({ page }) => {
  await mockWorkspace(page);
  await page.goto("/");
  await expect(page.getByRole("button", { name: /设置/ })).toHaveClass(/active/);
  await expect(page.getByText("方案与结构体系")).toBeVisible();
  await expect(page.getByText("尺寸、连接与支承")).toBeVisible();
  await expect(page.getByText("荷载与环境")).toBeVisible();
  await expect(page.getByText("廊架平顶场景荷载包")).toBeVisible();
  await expect(page.getByText("0.3–0.8 kN/m2")).toBeVisible();
  await expect(page.getByText("风雪荷载向导")).toBeVisible();
  await page.getByRole("button", { name: "添加项目资料荷载" }).click();
  await expect(page.getByText("资料名称")).toBeVisible();
  await expect(page.getByText("页码 / 条款")).toBeVisible();
  await expect(page.getByText("下一步")).not.toBeVisible();
});

test("墙附悬挑雨棚不显示基础和120kPa通用默认值", async ({ page }) => {
  await mockWorkspace(page);
  await page.goto("/");
  await page.locator("aside.left-rail").getByRole("button", { name: /雨棚/ }).click();
  await expect(page.getByRole("heading", { name: "雨棚" })).toBeVisible();
  await expect(page.getByText("墙体基材与锚栓组", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("基础策略")).not.toBeVisible();
  await expect(page.getByText("地基承载力特征值")).not.toBeVisible();
  await expect(page.getByText("当前变体通过墙体基材与锚栓组支承")).toBeVisible();
});

test("结果可复制为服务端方案并在修改输入后立即标记过期", async ({ page }) => {
  await mockWorkspace(page);
  await page.goto("/");
  await page.getByRole("button", { name: "计算并写入采用值" }).click();
  await expect(page.getByRole("button", { name: "确认全部荷载" })).toHaveCount(0);
  await expect(page.getByText("我已确认场景假定")).toHaveCount(0);
  await page.getByRole("button", { name: "计算当前方案" }).click();
  await expect(page.getByText("方案快算已完成")).toBeVisible();
  await page.getByRole("button", { name: /复制为方案 B/ }).click();
  await expect(page.getByText("测试场景（副本）", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "修改参数" }).click();
  await page.getByLabel("跨度").fill("5");
  await expect(page.getByText("输入已修改，旧结果不再代表当前方案")).toBeVisible();
});

test("开发中场景不可进入且390宽页面无横向溢出", async ({ page }) => {
  await mockWorkspace(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "打开导航" }).click();
  const pool = page.locator("aside.left-rail").getByRole("button", { name: /水景池体/ });
  await expect(pool).toBeDisabled();
  await page.keyboard.press("Escape");
  const metrics = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(metrics.scrollWidth).toBeLessThanOrEqual(metrics.clientWidth);
  await expect(page.getByRole("button", { name: "计算当前方案" })).toBeVisible();
});

test("单项计算仍可使用移动抽屉进入", async ({ page }) => {
  await mockWorkspace(page);
  await page.setViewportSize({ width: 900, height: 800 });
  await page.goto("/");
  await enterSingleCalculation(page);
  await expect(page.getByRole("heading", { name: "钢梁" })).toBeVisible();
});

test("十一个Schema 3.2单项模块均生成判别输入并沿用通用结果页", async ({ page }) => {
  await mockWorkspace(page);
  const submitted: Array<Record<string, unknown>> = [];
  await page.route("**/api/v2/calculate", async (route) => {
    const payload = route.request().postDataJSON() as Record<string, unknown>;
    submitted.push(payload);
    const calculationModule = String(payload.module);
    await route.fulfill({
      json: {
        schema_version: "3.2",
        engine_version: "3.2.0-test",
        trace_id: `trace-${calculationModule}`,
        project_name: "前端新模块测试",
        module: calculationModule,
        mode: "quick",
        status: "passed",
        workflow_status: "ready",
        engineering_status: null,
        quick_outcome: "screening_passed",
        result_class: "quick_estimate",
        verification_status: "unverified",
        standards: [],
        input_summary: {},
        combinations: [{ name: "ULS 用户输入组合", limit_state: "ULS", factors: {}, factored_by_kind: {}, total: { value: 1, unit: "kN" } }],
        reactions: {},
        diagrams: [],
        steps: [{ name: "矩阵分析", equation: "Kd=F", substitution: "test", result: { value: 0.5, unit: "1" }, reference: "test" }],
        checks: [{ name: "控制验算", demand: { value: 1, unit: "kN" }, capacity: { value: 2, unit: "kN" }, utilization: 0.5, passed: true, reference: "test" }],
        governing_check: "控制验算",
        warnings: [],
        assumptions: [],
        applicability: ["参数化模块测试"],
        catalog_versions: { schema: "3.2" },
      },
    });
  });
  await page.goto("/");
  const rail = page.locator("aside.left-rail");
  await rail.getByRole("button", { name: /单项计算/ }).click();

  const modules = [
    ["连续梁", "continuous_beam"],
    ["参数化平面框架", "planar_frame"],
    ["平面桁架", "planar_truss"],
    ["混凝土双向板", "two_way_slab"],
  ] as const;
  for (const [label, moduleId] of modules) {
    const button = rail.getByRole("button", { name: new RegExp(label) });
    await expect(button).toBeEnabled();
    await button.click();
    await expect(page.getByRole("heading", { name: label, exact: true })).toBeVisible();
    await page.getByRole("button", { name: "运行验算" }).click();
    await expect(page.locator("#result-panel")).toBeVisible();
    expect((submitted.at(-1)?.typed_inputs as { module: string }).module).toBe(moduleId);
  }

  await rail.getByRole("button", { name: "连接与支承" }).click();
  for (const [label, moduleId] of [
    ["木柱脚 / 金属连接件", "timber_connection"],
    ["墙附锚栓组", "wall_anchor"],
  ] as const) {
    const button = rail.getByRole("button", { name: new RegExp(label) });
    await expect(button).toBeEnabled();
    await button.click();
    await expect(page.getByRole("heading", { name: label, exact: true })).toBeVisible();
    await page.getByRole("button", { name: "运行验算" }).click();
    expect((submitted.at(-1)?.typed_inputs as { module: string }).module).toBe(moduleId);
  }

  await rail.getByRole("button", { name: "上部构件" }).click();
  for (const [label, moduleId] of [
    ["钢木景观人行桥", "bridge_steel_timber"],
    ["全混凝土景观人行桥", "bridge_rc"],
  ] as const) {
    const button = rail.getByRole("button", { name: new RegExp(label) });
    await expect(button).toBeEnabled();
    await button.click();
    await expect(page.getByRole("heading", { name: label, exact: true })).toBeVisible();
    await expect(page.getByLabel("墩台基础策略")).toBeVisible();
    await page.getByRole("button", { name: "运行验算" }).click();
    expect((submitted.at(-1)?.typed_inputs as { module: string }).module).toBe(moduleId);
  }

  await rail.getByRole("button", { name: "基础与地基" }).click();
  await rail.getByRole("button", { name: /群桩与承台/ }).click();
  await expect(page.getByRole("heading", { name: "群桩与承台", exact: true })).toBeVisible();
  await expect(page.getByLabel("基础支承策略")).toHaveValue("four_pile_cap");
  await page.getByRole("button", { name: "运行验算" }).click();
  const pilePayload = submitted.at(-1)?.typed_inputs as {
    module: string;
    piles: Array<{ x: { unit: string } }>;
  };
  expect(pilePayload.module).toBe("pile_group_cap");
  expect(pilePayload.piles).toHaveLength(4);
  expect(pilePayload.piles[0].x.unit).toBe("mm");

  await rail.getByRole("button", { name: "挡土与池体" }).click();
  for (const [label, moduleId] of [
    ["矩形水景池体", "pool_structure"],
    ["重力式挡土墙", "gravity_retaining_wall"],
  ] as const) {
    await rail.getByRole("button", { name: new RegExp(label) }).click();
    await expect(page.getByRole("heading", { name: label, exact: true })).toBeVisible();
    await expect(page.getByLabel("地下水条件")).toHaveValue("no_influence");
    await expect(page.getByLabel("基础支承策略")).toBeVisible();
    await page.getByRole("button", { name: "运行验算" }).click();
    expect((submitted.at(-1)?.typed_inputs as { module: string }).module).toBe(moduleId);
  }

  expect(submitted).toHaveLength(11);
  for (const payload of submitted) {
    expect(payload.schema_version).toBe("3.2");
    expect(payload.standard_profile).toBe("CN-2026.1");
    expect(payload.inputs).toBeUndefined();
    expect(payload.loads).toEqual([]);
  }
});

test("池体地下水三态中未知水位会阻止提交且已知水位要求资料来源", async ({ page }) => {
  await mockWorkspace(page);
  let calculateRequests = 0;
  await page.route("**/api/v2/calculate", async (route) => {
    calculateRequests += 1;
    await route.abort();
  });
  await page.goto("/");
  const rail = page.locator("aside.left-rail");
  await rail.getByRole("button", { name: /单项计算/ }).click();
  await rail.getByRole("button", { name: "挡土与池体" }).click();
  await rail.getByRole("button", { name: /矩形水景池体/ }).click();

  await page.getByLabel("地下水条件").selectOption("unknown");
  await page.getByRole("button", { name: "运行验算" }).click();
  await expect(page.getByText(/地下水位未知时不能运行验算/)).toBeVisible();
  expect(calculateRequests).toBe(0);

  await page.getByLabel("地下水条件").selectOption("known_water_table");
  await page.getByRole("button", { name: "运行验算" }).click();
  await expect(page.getByText(/已知地下水位必须填写资料来源/)).toBeVisible();
  expect(calculateRequests).toBe(0);
});

test("未独立验证模块即使收到passed也不在专业模式显示通过", async ({ page }) => {
  await mockWorkspace(page);
  await page.route("**/api/v2/calculate", (route) =>
    route.fulfill({
      json: {
        schema_version: "3.2",
        engine_version: "3.2.0-test",
        trace_id: "trace-professional-unverified",
        project_name: "专业状态测试",
        module: "gravity_retaining_wall",
        mode: "professional",
        status: "passed",
        workflow_status: "ready",
        engineering_status: null,
        result_class: "professional_check",
        verification_status: "unverified",
        standards: [], input_summary: {}, combinations: [], reactions: {}, diagrams: [], steps: [],
        checks: [{ name: "临时验算", demand: { value: 1, unit: "1" }, capacity: { value: 2, unit: "1" }, utilization: 0.5, passed: true, reference: "test" }],
        governing_check: "临时验算", warnings: [], assumptions: [], applicability: [],
      },
    }),
  );
  await page.goto("/");
  const rail = page.locator("aside.left-rail");
  await rail.getByRole("button", { name: /单项计算/ }).click();
  await rail.getByRole("button", { name: "挡土与池体" }).click();
  await rail.getByRole("button", { name: /重力式挡土墙/ }).click();
  await page.getByRole("button", { name: "专业计算" }).click();
  await page.getByRole("button", { name: "运行验算" }).click();
  await expect(page.locator("#result-panel")).toContainText("资料不完整");
  await expect(page.locator("#result-panel .result-status")).not.toContainText("通过");
});
