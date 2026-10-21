# Motion 创作

本参考用于制作平台内有具体业务目标的动画页面。先阅读平台导览、页面生成流程和当前 `wp standards page`，再查询：

```powershell
wp --profile local --workspace <id> --json workspace capabilities
wp --profile local --workspace <id> --json runtime-kit get usePageTimeline.v1
```

时间轴默认关闭。只有 capabilities.timeline.enabled=true 且真实能力目录返回入口时才可使用；用户授权的本地内测不等于 G1/G2 通过。未开放时报告限制，不猜路径、不访问开发仓库或私有服务。

## 单页入口

路径以查询返回为准。当前入口支持以下形状：

```ts
import { ref } from 'vue'
import { usePageTimeline, seconds } from '@runtime-kit/public/composables/motion/usePageTimeline.v1'

const pageRoot = ref<HTMLElement | null>(null)
const story = usePageTimeline({
  root: pageRoot,
  bindings: {},
  applyPoster: true,
  timelineId: 'workflow-intro',
  poster: { atLabel: 'readable' },
  define(ctx) {
    return {
      plan: ctx.resources().build(),
      visual(tl) {
        tl.fromTo('.title', { opacity: 0, y: 24 },
          { opacity: 1, y: 0, duration: seconds(400) }, 0)
        tl.fromTo('.step', { opacity: 0, x: 32 },
          { opacity: 1, x: 0, duration: seconds(350), stagger: seconds(150) }, 0.5)
        tl.addLabel('readable')
      },
    }
  },
})
```

将 ref 绑定到本页原生根元素，如 `<section ref="pageRoot">`；该元素包住所有动画目标，外层仍遵守 DefaultContainer 和固定画布规范。同页只声明一个时间轴，bindings 可为空。默认由 Editor 预览控制和放映宿主播放，不在 mounted/watch/RAF 中自行 play，不导入 GSAP 或创建第二个时钟。

define 只在挂载时运行一次，返回资源计划和 visual 填充函数。纯视觉可以用空资源计划；旧 definition/DOM preset 只兼容已有内部内容，不作为新任务默认写法。

## 受控原生视觉

- 只支持 fromTo、addLabel、原生位置字符串、非负数值 stagger 及普通函数复用。from/to 必须声明相同属性，属性限 opacity/x/y/scale/rotation；duration 必须为正数，ease 使用名称。
- 资源、poster、定位统一毫秒；原生 GSAP 的 duration、stagger、位置用秒，通过 seconds(ms) 转换。
- 允许同元素同属性的顺序段落，禁止区间重叠。布局定位和动画变换用不同包裹层。禁止 call/add/to/from、回调、插件、无限重复、外部目标或独立播放者。
- 资源 id 自动登记为视觉标签，例如在 'demo' 或 'demo+=0.2' 追加段落。纯视觉也可以 addLabel，再用标签组织段落。
- Runtime 托管暂停时间轴、显式初态、静默采样和释放。默认在所有视觉段落之后调用 `tl.addLabel('readable')`，用 `poster: { atLabel: 'readable' }` 锚定可读终态；需要窗口化项目预览先显示海报时设置 `applyPoster: true`，由宿主开始播放时再回到起点。
- 不猜固定 poster.atMs，也不要简单给动画时长额外加等待时间：海报必须处于真实计划的 0–durationMs 内。确需指定中间态时使用当前编排中的标签或已确认范围内的毫秒值。调整段落或错峰后仍须检查海报；越界会导致初始化失败，必须按诊断的 code/fieldPath 和实际时长修正，不能以静态画面或 Job 编译成功宣称动画完成。
- reduce 保留可读状态，预览可通过宿主模拟 full/reduced。

## 有限资源 builder

按需要使用 `ctx.resources().voice(id, options).audio(id, options).video(id, options).clip(id, queriedClip, options).build()`。不需要媒体时不要为了展示 API 额外造素材。

- voice 为主音频并从 0 开始；video 默认静音。音视频 options 包括真实 asset 逻辑名、startMs 或 afterTrack/offsetMs、inMs/outMs、rate 和有限 repeat，以当前返回的规范为准。
- clip 引用真实查询得到的 index、signature、durationMs（由资源 duration_ms 映射），引用不支持或过期动作会被拒绝；不猜动作名称或时长。
- 同步资源通过当前公开的 AssetAudio.v2、AssetVideo.v2、AssetModel.v2 渲染，使用前分别读取能力详情；不用 v1 手动媒体代替同步目标。
- timeline 音频和独立旁白/cue 是不同能力。不要因为 timeline 开放就使用被 slideshow.audio 关闭的 narration/cue 用途。
- 只有 slideshow.advance_modes 包含 timeline_end 才能保存该模式；业务任务默认可保留手动翻页，不静默替换用户指定的推进方式。

## 交付

通过 wp 提交页面/组件，等待 Mutation Job 成功并重新读取版本，保留正常编译和布局错误修正；交付项目/页面 ID、页序、短期预览地址及实际限制。用户负责验收时，不开展 G1/G2、评分或长时间稳定性测试，不把静态截图或任务成功说成动画已验收。
