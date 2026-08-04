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
  await page.route("**/api/v1/auth/me", (route) => route.fulfill({ json: { id: 1, username: "tester", display_name: "测试用户", is_admin: false, must_change_password: false } }));
  await page.route("**/api/v2/scenario-families", (route) => route.fulfill({ json: families }));
  await page.route("**/api/v2/calculation-library", (route) => route.fulfill({ json: calculationLibrary }));
  await page.route("**/api/v2/projects", (route) => {
    if (route.request().method() === "POST") {
      return route.fulfill({ json: { id: 9, name: "测试场景", description: "", created_at: "2026-07-31", updated_at: "2026-07-31", version_count: 0 } });
    }
    return route.fulfill({ json: [] });
  });
  await page.route("**/api/v2/projects/9/scene-instances", (route) => route.fulfill({ json: { id: 11, project_id: 9, family_id: "pergola-pavilion", variant_id: "flat-single", title: "测试场景", mode: "quick", template_version: "test-scenes-2.1", draft_state: {}, stale_node_ids: [], created_at: "2026-07-31", updated_at: "2026-07-31" } }));
  await page.route("**/api/v2/projects/9/scene-instances/11", (route) => route.fulfill({ json: { id: 11, project_id: 9, family_id: "pergola-pavilion", variant_id: "flat-single", title: "测试场景", mode: "quick", template_version: "test-scenes-2.1", draft_state: {}, stale_node_ids: [], created_at: "2026-07-31", updated_at: "2026-07-31" } }));
  await page.route("**/api/v2/projects/9/scene-revisions", (route) => route.fulfill({ json: {
    id: 21, project_id: 9, revision_number: 1, snapshot_schema_version: "2.1", scene_instance_id: 11,
    scene_result: { scene_family_id: "pergola-pavilion", scene_variant_id: "flat-single", mode: "quick", status: "passed", workflow_status: "ready", engineering_status: "passed", result_class: "quick_estimate", verification_status: "unverified", completed_nodes: 4, total_required_nodes: 4, node_results: Object.fromEntries(pergolaGraph.nodes.map((node) => [node.id, { node_id: node.id, label: node.label, status: node.calculation_module ? "passed" : "completed", maturity: node.maturity, stale: false }])), missing_nodes: [], stale_node_ids: [], control_path: pergolaGraph.nodes.map((node) => node.label), warnings: ["柱脚仍需专业复核。"], catalog_versions: { scenes: "test-scenes-2.1" }, load_cases: pergolaLoads.items },
    result_bundle: { roof_members: { schema_version: "2.0", engine_version: "test", trace_id: "trace", project_name: "测试", module: "steel_beam", mode: "quick", status: "passed", result_class: "quick_estimate", verification_status: "independently_verified", standards: [], input_summary: {}, combinations: [], reactions: {}, diagrams: [], steps: [], checks: [{ name: "弯曲", demand: { value: 1, unit: "kN.m" }, capacity: { value: 2, unit: "kN.m" }, utilization: 0.5, passed: true, reference: "test" }], warnings: [], assumptions: [], applicability: [], disclaimer: "" } },
    catalog_versions: {}, engine_version: "test", report_number: "SC-TEST-001", created_at: "2026-07-31",
  } }));
  await page.route("**/api/v2/catalogs/materials", (route) => route.fulfill({ json: { version: "test", standard_profile: "CN-2024", source_references: [], items: [] } }));
  await page.route("**/api/v2/catalogs/load-presets", (route) => route.fulfill({ json: { version: "test", confirmation_required: true, items: [] } }));
  await page.route("**/api/v2/catalogs/climate-locations", (route) => route.fulfill({ json: { version: "test-climate", coverage: "test", professional_use_requires_confirmation: true, items: [{ id: "beijing", province: "北京", city: "北京市", station: "北京站", elevation_m: 54, wind_kpa: { "10": 0.3, "50": 0.45, "100": 0.5 }, snow_kpa: { "10": 0.25, "50": 0.4, "100": 0.45 }, snow_zone: "Ⅱ" }] } }));
}

async function enterSingleCalculation(page: Page) {
  await page.getByRole("button", { name: "打开导航" }).click();
  const rail = page.locator("aside.left-rail");
  await rail.getByRole("button", { name: /单项计算/ }).click();
  await rail.getByRole("button", { name: /钢梁/ }).click();
  await rail.getByRole("button", { name: "应用并关闭" }).click();
}

test("移动抽屉选择期间保持打开，应用后关闭", async ({ page }) => {
  await mockWorkspace(page);
  await page.setViewportSize({ width: 900, height: 800 });
  await page.goto("/");
  await page.getByRole("button", { name: "打开导航" }).click();
  const rail = page.locator("aside.left-rail");
  await rail.getByRole("button", { name: /单项计算/ }).click();
  await rail.getByRole("button", { name: /钢梁/ }).click();
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

test("结果可保存方案并在修改输入后立即标记过期", async ({ page }) => {
  await mockWorkspace(page);
  await page.goto("/");
  await page.getByRole("button", { name: "计算并写入采用值" }).click();
  await page.getByRole("button", { name: "确认全部荷载" }).click();
  await page.getByRole("button", { name: "计算当前方案" }).click();
  await expect(page.getByText("方案快算已完成")).toBeVisible();
  await page.getByRole("button", { name: /保存为方案 A/ }).click();
  await expect(page.getByText("方案 A", { exact: true })).toBeVisible();
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
