# C-CLEANER 设计系统 · "勘探仪器"

> 概念:磁盘是一片待勘测的地层,界面是一台精密勘探仪器。
> 用户在焦虑时刻(C盘快满)打开它——仪器必须冷静、精确、值得信任。
> 禁令:近黑+荧光绿、米色+衬线+赤陶、紫渐变、Inter 默认脸、万物皆卡片、emoji 图标。

## Tokens

```yaml
color:
  bg:          "#12161d"   # 蓝铸石墨,非中性黑
  bg-raised:   "#181d26"   # 抬升面 (暗色不用阴影,用亮度分层,差 ≤12%)
  bg-high:     "#1f2530"   # 再抬升 (hover/浮层)
  line:        "rgba(214,222,235,0.10)"  # 发丝线
  text:        "#e8ecf2"
  text-2:      "rgba(232,236,242,0.60)"
  text-3:      "rgba(232,236,242,0.36)"
  gauge:       "#e8c98a"   # 香槟金——仪器刻度/指针/品牌色,全站唯一强调色,用量<10%
  # 安全等级 = 勘探图分区材质(低饱和填充,不是霓虹徽章)
  zone-safe:   "#7fb08a"   # 灰绿
  zone-warn:   "#c9a86a"   # 土黄
  zone-danger: "#c47a6d"   # 铁锈红
  zone-locked: "#8b9bb4"   # 青灰蓝 (受保护 = 冷静,不是警告)
  zone-inert:  "#3a414d"   # 系统/未识别 (惰性岩层)

type:
  display: "'Chakra Petch', 'Microsoft YaHei', sans-serif"  # 仅大写拉丁/数字标识用
  data:    "'IBM Plex Mono', Consolas, monospace"           # 一切数字,tabular-nums
  body:    "'Segoe UI', system-ui, 'Microsoft YaHei', sans-serif"
  scale:   "12 / 13 / 15(正文) / 19 / 24 / 38(hero数字)"   # ×1.25 应用比例
  weight:  "300 与 600 拉开,不用 400v500"

space: "8pt 网格: 4/8/12/16/24/32/48/64"
radius: "6px 常规 / 10px 面板 / 2px 地层块(地质剖面是方的)"
shadow: "无。暗色靠亮度分层。"
motion: "150-250ms ease 微渐变;地层块 hover 提亮;respect prefers-reduced-motion"
```

## Signature(唯一的大胆处)

**磁盘地层剖面 hero**:全宽横向地层条,每层材质对应安全等级;剩余 4.33GB 是
右端一道窄铁锈色裂缝,勘探图式引线标注。它同时是数据(容量分布)、
论点(空间快用完了)、和导航(点击层进入对应视图)。其余一切保持安静。

## 结构语言

- 面板 = 亮度差,默认无边框;分区靠留白与 1px 发丝线
- 仪器铭牌:面板左上角小号 display 字体大写标签(SEC.01 SURVEY 式),
  编号真实对应视图顺序——结构即信息
- 受保护项(微信/OneNote):青灰蓝 + 锁形 SVG,文案"已保护",永不出现在建议里
- 危险操作:铁锈红仅给"清空隔离区"一处;主按钮 = 香槟金描边幽灵按钮
- 文案:动词按钮("移入隔离区",不是"确定");错误直说原因;空状态给指引

## Do / Don't

- Do: 数字一律 data 字体 + tabular-nums;单位小一号浅一档
- Do: 图标一律 stroke SVG (1.5px),同一套视觉重量
- Don't: 阴影、渐变按钮、玻璃(仅清理篮浮条可用 blur)、发光、圆角>10px
- Don't: 三卡并排 hero、居中大标题+徽章、01/02/03 装饰编号
