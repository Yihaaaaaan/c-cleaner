# UI 设计能力手册(跨项目复用)

> 2026-08-22 调研沉淀。四路调研:AI-UI 技能生态 / 开源 UI 库 / 方法论 / Claude Design。
> 适用:Claude Code + 纯 HTML/CSS 或 React 小项目。

## 一、核心诊断:AI 生成 UI 为什么丑

模型不做设计决策,只输出训练数据的统计平均。修复本质 = **用明确决策替换泛化描述** + **做减法**。

**"AI 默认脸"识别表(全部禁用,除非有意为之):**
- 配色:紫蓝渐变、indigo/灰蓝默认组合、纯黑纯白背景、无主导色的平均分配
- Anthropic 官方点名的三种默认脸:①米色底+衬线+赤陶 ②近黑底+荧光绿/朱红 ③报纸式细线密栏
- 卡片:每张都套 1px 灰边、彩色左边条、`rounded-2xl shadow-lg p-6` 原样照搬、万物皆卡片
- 排版:Inter/Poppins/Space Grotesk 默认、全大写小节标签、装饰性等宽字体装极客
- 布局:居中 hero+徽章、1·2·3 编号步骤、一行三卡、默认 bento、没人要的暗色模式
- 其他:霓虹发光边、到处玻璃拟态、漂浮光球、emoji 当图标、千篇一律 fade-in

## 二、必装工具链(装一次,所有项目受益)

1. **Anthropic 官方 frontend-design skill** — `anthropics/skills` 仓库
   安装:`/plugin marketplace add anthropics/skills` 或拷 SKILL.md 到 `~/.claude/skills/frontend-design/`
   核心:两遍流程(先出 token 方案+signature 记忆点 → 自我批判"哪里像默认"再写码)+ 反 slop 禁令
2. **Playwright MCP 截图迭代闭环** — `claude mcp add playwright -- npx @playwright/mcp@latest`
   给 agent 眼睛:改→截图→自评→再改,典型 2-3 轮。对质量影响最大的单一杠杆。
   (无 MCP 时替代:Edge headless `--screenshot`,本会话已验证可用)
3. **DESIGN.md 模式** — `VoltAgent/awesome-claude-design`(68 份大牌设计系统 markdown)
   每个项目根目录放一份 DESIGN.md:YAML token(色/字/距/圆角/阴影/动效)+ 定性哲学 + Do/Don't。
   CLAUDE.md 加一句"严格遵循 DESIGN.md,禁止通用 AI 美学"。
4. **OneRedOak design-review** — `OneRedOak/claude-code-workflows`
   `/design-review` 命令:8 阶段审查(交互流/三档响应式 1440-768-375/视觉/无障碍/健壮性),
   产出按 Blocker/High/Medium/Nitpick 分级。
5. **Claude Design(claude.ai/design)** — `/design-login` 授权后用 DesignSync 推本地组件库,
   网页端可视化迭代设计系统,双向同步。Pro 订阅可用。

可选:`ui-ux-pro-max-skill`(检索式风格推荐,79 风格/192 色板)、vercel `web-design-guidelines`(工程守门)。
跳过:shadcn MCP / Magic MCP(React 专用)、Figma MCP(无设计稿场景)。

## 三、必须人工指定的硬规则(AI 默认做错)

- **间距**:8pt 网格,只用 4/8/12/16/24/32/48/64。外层 padding ≥ 内层。留白先给过量再删。
- **字体**:≤2 字族。正文 ≥16px,行长 60-80 字符。比例:应用 ×1.25,编辑 ×1.333。
  配对要高对比(display+mono、serif+几何 sans);字重用极端值(200 vs 800,别 400 vs 600)。
- **颜色**:≤3 色相,60/30/10 分配。不用纯黑白。中性色加 <5% 同温饱和度。
  对比 ≥4.5:1。**暗色界面不用阴影,用亮度分层**(容器与背景亮度差 ≤12%)。
- **阴影**:双层配方(大软偏移 + 紧深贴边),blur = Y 偏移 ×2,全站一种深度体系,光来自上方。
- **卡片**:默认无边框。层级优先序:留白 → 背景亮度差 3-5% → 软阴影 → 最后才是边框。
- **圆角**:嵌套 = 外圆角 − 间距。按钮 padding 横:纵 = 2:1。
- **细节**:SVG 图标不用 emoji;cursor-pointer;光学对齐 > 数学对齐。

## 四、提示技巧

- 点名文化美学方向("Swiss editorial"、"日式工业安全标识"),别用 modern/clean/beautiful
- 负面清单比正面更有效(明确禁 Inter、紫渐变、三卡行)
- 分维度指导:排版/颜色/动效/背景各一条,别一句"好看点"
- 规格代替形容词;贴参考截图统领美学
- 创意与实现分离:先纯文本 art direction spec,再交给实现

## 五、可偷的 token 体系

- **shadcn 命名法**:`--background/--foreground/--primary/--muted/--accent/--destructive/--radius`
  ——写进任何 `:root`,框架无关
- **Radix 12 步色阶逻辑**(radix-ui.com/colors/custom 输入品牌色自动生成):
  1-2 页面背景 / 3-5 组件背景 / 6-8 边框 / 9-10 实色(9=品牌色)/ 11-12 文字
- **Open Props**:350+ 现成 CSS 变量(阴影/缓动/渐变/字号阶梯),直接 link 或拷贝
- 纯 HTML 快速路径:**daisyUI 5 CDN**(+@tailwindcss/browser,34KB 可生产)或 **Pico.css**(classless 天花板)
- 工具:tweakcn(可视化调 shadcn 主题导出 CSS 变量)、uicolors.app、realtimecolors.com
- 片段库(MIT 可抄):uiverse.io(5800+ 纯 HTML/CSS)、HyperUI
- 数据密集参考:Tremor(KPI 卡/图表配色)、glance(信息密度典范)、shadcn-admin

## 六、标准工作流(每个新项目)

1. **品牌会话**:定 DESIGN.md(token + 哲学 + 禁令),参考 awesome-claude-design 模板起步
2. **每屏两遍**:先文本 spec(布局/风格/动效),批判"哪里像默认",再写码
3. **截图闭环**:渲染 → 截图 → 按 design-review 清单自评 → 修,2-3 轮
4. **交付 QA**:一种美学、≤3 色相、非默认字体、无边框卡片、8pt 间距、实测对比度、
   三档视口、loading/empty/error 三态、reduced-motion
