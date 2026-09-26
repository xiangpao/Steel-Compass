import { expect, test } from "@playwright/test";

test("柱脚接触参数显式录入且不静默生成刚度", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/qa/pergola-workbench-v2");
  await page.getByRole("button", { name: "基础", exact: true }).click();
  await page.getByRole("button", { name: /^F-A 一般柱下阶形基础/ }).click();
  await page.getByText("脱开接触与锚栓刚度", { exact: true }).click();
  await expect(page.getByLabel("接触支承刚度（kN/m³）")).toHaveValue("");
  await page.getByLabel("接触支承刚度（kN/m³）").fill("10000000");
  await page.getByLabel("接触与锚栓刚度来源").fill("QA fixture / not engineering evidence");
  await page.getByLabel("柱周焊缝构造").selectOption("true");
  await page.getByRole("button", { name: "添加锚栓刚度记录" }).click();
  await expect(page.getByLabel("轴向刚度（kN/m）")).toHaveValue("");
  await page.getByLabel("X 坐标（m）").fill("-0.13");
  await page.getByLabel("Y 坐标（m）").fill("0.13");
  await page.getByLabel("轴向刚度（kN/m）").fill("100000");
  await expect(page.getByRole("status").filter({ hasText: /需填写全部/ })).toBeVisible();
  await page.screenshot({ path: "output/playwright/completion-contact-mobile.png" });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.getByRole("button", { name: "移除锚栓 1 的刚度记录" }).click();
  await expect(page.getByLabel("轴向刚度（kN/m）")).toHaveCount(0);
});

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => window.localStorage.removeItem("steel-compass:qa:pergola-workbench-v2"));
});

async function modelPoint(page: import("@playwright/test").Page, u: number, v: number) {
  const stage = page.locator(".konvajs-content");
  const box = await stage.boundingBox();
  if (!box) throw new Error("二维画布不可见");
  const zoomLabel = await page.getByRole("button", { name: "恢复100%" }).textContent();
  const zoom = Number.parseFloat(zoomLabel?.replace("%", "") ?? "100") / 100;
  const spacing = 52 * zoom;
  const offsetX = Math.max(48, (box.width - 8 * spacing) / 2);
  const offsetY = Math.max(34, (box.height - 6 * spacing) / 2);
  return { x: box.x + offsetX + u * spacing, y: box.y + offsetY + (6 - v) * spacing };
}

test("QA工作台以56px入口栏、对象属性和并排二维三维呈现", async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 900 });
  await page.goto("/qa/pergola-workbench-v2");
  await expect(page.getByRole("complementary", { name: "亭廊工作台一级入口" })).toHaveCSS("width", "56px");
  await expect(page.getByText("二维精确编辑")).toBeVisible();
  await expect(page.getByText("三维实时视图")).toBeVisible();
  await expect(page.getByRole("img", { name: "当前亭廊结构和基础三维简图" })).toBeVisible();
  await expect(page.getByRole("button", { name: "显示全部" })).toBeVisible();
  await page.getByRole("button", { name: "放大", exact: true }).click();
  await expect(page.getByRole("button", { name: "恢复100%" })).not.toHaveText("117%");
  const splitter = page.getByRole("separator", { name: "调整二维与三维视图宽度" });
  await splitter.focus();
  await page.keyboard.press("ArrowRight");
  await expect(splitter).toHaveAttribute("aria-valuenow", "56");
  await splitter.dblclick();
  await expect(splitter).toHaveAttribute("aria-valuenow", "55");
});

test("场景库留在工作台内且项目条件驱动风雪地震荷载", async ({ page }) => {
  await page.goto("/qa/pergola-workbench-v2");
  await page.getByRole("button", { name: "场景库" }).click();
  await expect(page).toHaveURL(/\/qa\/pergola-workbench-v2$/);
  await expect(page.getByRole("button", { name: /亭廊 \/ 花架/ })).toBeVisible();
  await page.getByRole("button", { name: "项目条件" }).click();
  await page.getByLabel("地区档").selectOption("zhejiang_coastal");
  await page.getByLabel("抗震设防烈度 / 加速度").selectOption("8_020g");
  await expect(page.getByText("3 / 3")).toBeVisible();
  await page.getByRole("button", { name: "荷载", exact: true }).click();
  await expect(page.getByText("0.45 kPa 基本值")).toBeVisible();
  await expect(page.getByText("风 0.85 kPa · 8_020g")).toBeVisible();
  await page.getByLabel(/屋面构造/).selectOption("none");
  await expect(page.getByText("不适用", { exact: true })).toHaveCount(2);
});

test("选择单根柱后可用组合字段精确修改柱顶标高和截面", async ({ page }) => {
  await page.goto("/qa/pergola-workbench-v2");
  await page.getByRole("button", { name: "C 柱 9 根 · Q355B" }).click();
  await expect(page.getByText("C01", { exact: true })).toBeVisible();
  await expect(page.getByText("B-1-1 → T-1-1")).toBeVisible();
  await page.getByRole("spinbutton", { name: "终点Z m" }).fill("4.2");
  await page.getByRole("spinbutton", { name: "厚 mm" }).fill("10");
  await expect(page.getByRole("spinbutton", { name: "终点Z m" })).toHaveValue("4.2");
  await expect(page.getByRole("spinbutton", { name: "厚 mm" })).toHaveValue("10");
});

test("双坡屋脊可转到Y向并保持对象编号", async ({ page }) => {
  await page.goto("/qa/pergola-workbench-v2");
  await page.getByRole("button", { name: "荷载", exact: true }).click();
  await page.getByRole("spinbutton", { name: "屋脊方向" }).fill("90");
  await expect(page.getByText("双坡屋脊已旋转到 90°，构件编号保持不变。")).toBeVisible();
  await page.getByRole("button", { name: "模型", exact: true }).click();
  await expect(page.getByRole("button", { name: "X-M X向主梁 6 根 · Q355B" })).toBeVisible();
});

test("基础按F-A和F-B归类并可将单个实例拆分", async ({ page }) => {
  await page.goto("/qa/pergola-workbench-v2");
  await page.getByRole("button", { name: "基础", exact: true }).click();
  await expect(page.getByText("100–180 kPa")).toBeVisible();
  await expect(page.getByText("方案采用 100 kPa")).toBeVisible();
  await page.getByRole("button", { name: /^F-A 一般柱下阶形基础/ }).click();
  await expect(page.getByText("对应 C-1-2")).toBeVisible();
  await expect(page.getByRole("checkbox", { name: /钢筋混凝土短柱/ })).toBeChecked();
  await expect(page.getByRole("spinbutton", { name: "净高 mm" })).toHaveValue("650");
  await page.getByText("短柱详细配筋与构造").click();
  await expect(page.getByRole("spinbutton", { name: "加密区间距 mm" })).toHaveValue("90");
  await expect(page.getByRole("spinbutton", { name: "锚板/锚头直径 mm" })).toHaveValue("60");
  await expect(page.getByRole("checkbox", { name: /按开裂混凝土验算锚固区/ })).toBeChecked();
  await expect(page.getByText("短柱是附属构造，不是另一种基础形式。")).toBeVisible();
  await page.getByRole("button", { name: /从 F-A 分离为新类型/ }).click();
  await expect(page.getByText("F-C-01", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "基础", exact: true }).click();
  await page.getByRole("button", { name: "工程校核" }).click();
  await expect(page.getByText("报告资料在项目级录入一次")).toBeVisible();
  await expect(page.getByRole("spinbutton", { name: "压缩层厚度 m" })).toHaveValue("6");
  await expect(page.getByRole("spinbutton", { name: "允许沉降 mm" })).toHaveValue("30");
  await expect(page.getByText("承载力资料来源")).toHaveCount(0);
});

test("梁草稿取消不写入孤立节点且节点可在既有梁上拆分", async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 900 });
  await page.goto("/qa/pergola-workbench-v2");
  const editor = page.getByTestId("qa-plan-editor");
  const canvas = editor.locator("canvas");
  const box = await canvas.boundingBox();
  if (!box) throw new Error("二维画布不可见");
  await page.getByRole("button", { name: /^梁：/ }).click();
  await page.mouse.click(box.x + box.width - 30, box.y + box.height - 30);
  await page.keyboard.press("Escape");
  await expect(page.getByText("节点 18 · 构件 21 · 基础 9")).toBeVisible();
  await page.getByRole("button", { name: /^节点：/ }).click();
  const beamMidpoint = await modelPoint(page, 2, 3);
  await page.mouse.click(beamMidpoint.x, beamMidpoint.y);
  await expect(page.getByText("节点 19 · 构件 22 · 基础 9")).toBeVisible();
  await expect(page.getByText(/原杆件已拆分并继承属性/)).toBeVisible();
});

test("删除工具可直接删除图面构件且重置视图恢复100%", async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 900 });
  await page.goto("/qa/pergola-workbench-v2");
  const editor = page.getByTestId("qa-plan-editor");
  const canvas = editor.locator("canvas");
  const box = await canvas.boundingBox();
  if (!box) throw new Error("二维画布不可见");

  await page.getByRole("button", { name: /^删除工具：/ }).click();
  const beamMidpoint = await modelPoint(page, 2, 3);
  await page.mouse.click(beamMidpoint.x, beamMidpoint.y);
  await expect(page.getByText(/已删除所选构件/)).toBeVisible();
  await expect(page.getByText("节点 18 · 构件 20 · 基础 9")).toBeVisible();
  await page.getByRole("button", { name: "撤销" }).click();
  await expect(page.getByText("节点 18 · 构件 21 · 基础 9")).toBeVisible();

  await page.getByRole("button", { name: "放大", exact: true }).click();
  await expect(page.getByRole("button", { name: "恢复100%" })).not.toHaveText("100%");
  await page.getByRole("button", { name: "重置二维视图" }).click();
  await expect(page.getByRole("button", { name: "恢复100%" })).toHaveText("100%");
  await expect(page.getByText("二维视图已重置为 100%；模型数据没有改变。")).toBeVisible();
});

test("390px使用属性二维三维三个全屏标签且无横向溢出", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/qa/pergola-workbench-v2");
  await expect(page.getByRole("navigation", { name: "移动端工作台视图" })).toBeVisible();
  await expect(page.getByText("二维精确编辑")).toBeVisible();
  await page.getByRole("button", { name: "属性", exact: true }).click();
  await expect(page.getByRole("heading", { name: "对象属性" })).toBeVisible();
  await page.getByRole("button", { name: "三维", exact: true }).click();
  await expect(page.getByRole("img", { name: "当前亭廊结构和基础三维简图" })).toBeVisible();
  const dimensions = await page.evaluate(() => ({ client: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
  expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.client);
});
