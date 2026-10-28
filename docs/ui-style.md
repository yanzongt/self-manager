# 页面统一风格

个人主页是 Self Manager 的视觉基准：米白背景、深绿正文、柔和绿色点缀、浅色卡片、细边框和留白。主页、PDCA、力量训练、投资回测、打卡和传感器视场已共用 `apps/shared/theme.css`。后续新增页面必须沿用这一主题。

## 引用共享样式

Vue 应用在 `src/main.ts` 中先导入主题，再导入页面布局样式：

```ts
import '../../shared/theme.css'
import './style.css'
```

静态页面先加载 `/shared/theme.css`，再加载页面自己的样式。新增静态页面可参考 `apps/shared/page-template.html`。主题由现有 Python 服务提供；Vue 构建时会将主题打包到应用资源中。

## 常用元素

| 元素 | 共享类 |
| --- | --- |
| 页面宽度和手机边距 | `sm-container` |
| 顶部导航、品牌和标记 | `sm-header`、`sm-brand`、`sm-mark` |
| 返回主页 | `sm-back` |
| 页面介绍、英文引导、标题和说明 | `sm-intro`、`sm-eyebrow`、`sm-title`、`sm-description` |
| 内容面板 | `sm-panel` |
| 普通按钮和主按钮 | `sm-button`、`sm-button sm-button-primary` |
| 输入框、下拉框、文本域 | `sm-control` |
| 页脚 | `sm-footer` |

页面 CSS 只定义专有布局、数据展示与交互状态。颜色使用 `--sm-*` 变量；SVG 的 `fill`、`stroke` 同样支持 `var(--sm-chart)` 等变量。需要新的通用视觉能力时修改共享主题，避免在页面里重新定义 `body`、全站字体和独立配色。

绿色表示主操作和正常状态，琥珀色表示等待或提醒，红色用于危险操作；图表沿用共享颜色。全站保持浅色，卡片使用共享圆角和边框，避免高饱和色、厚重阴影和装饰性渐变。

## 修改与验证

修改共享主题后重新构建受影响的 Vue 应用：

```sh
npm run build --prefix apps/strength
npm run build --prefix apps/investment
npm run build --prefix apps/pdca
npm run build --prefix apps/checkins
npm run build --prefix apps/sensor-fov
```

检查桌面与手机宽度下的页头、正文、表单、弹窗和图表，确保没有整页横向溢出，并保留键盘焦点提示。已有页面的业务回归命令见根目录 README。

力量训练与投资模块已接入共享主题；图表使用 `apps/shared/LineChart.vue`，颜色直接引用主题变量。
