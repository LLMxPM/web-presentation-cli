# Scene 动效创作

先读当前 `wp standards page` 与真实项目配置，再查询版本化能力：

```powershell
wp --json workspace capabilities
wp --json runtime-kit get usePageScene.v1
wp --json runtime-kit get useStaticPresentation.v1
wp --json runtime-kit get AssetModel.v3
wp --json runtime-kit get createSceneMediaTask.v1
wp --json runtime-kit get useAudioCue.v2
```

当前能力字段为 scene，放映 schema 4。import_path 以查询结果为准，开发入口可用不等于实机验收完成。组件首轮不自行声明页级 Scene，页面统一持有任务。

## 多条正向序列

```ts
import { ref } from 'vue'
import { usePageScene } from '@runtime-kit/public/composables/motion/usePageScene.v1'
import { useStaticPresentation } from '@runtime-kit/public/composables/static/useStaticPresentation.v1'
const root = ref<HTMLElement | null>(null)
useStaticPresentation({ root, mode: 'default' })
usePageScene({ root, define(scene) {
  const output = scene.root.querySelector('[data-count]')!
  const before = output.textContent, counter = { value: 0 }
  scene.onCleanup(() => { output.textContent = before })
  scene.visual({ id: 'number', role: 'blocking', define(tl) {
    tl.to(counter, { value: 100, duration: 1, onUpdate() { output.textContent = String(Math.round(counter.value)) } })
  } })
  scene.visual({ id: 'title', role: 'blocking', afterTrack: 'number', define(tl) {
    tl.fromTo('.title', { y: 20, opacity: 0 }, { y: 0, opacity: 1, duration: 0.4 })
  } })
} })
```

模板默认就应显示完整正文与 100，不依赖动画回调才能读到内容。`scene.visual` 支持 to/from/fromTo/set/addLabel/call、回调、位置、stagger、DOM/SVG 属性与数值对象；打字机可更新本页文本，SVG 描边可改 strokeDashoffset。禁止直接导入 GSAP 或插件；粒子使用 DOM/CSS/Canvas，不用插件。视觉 duration/位置用秒；任务 startMs/offsetMs 用毫秒。

有限 blocking 实际完成才参与 scene_end；无限 repeat:-1 只允许 ambient，且不能作为前驱。任务 id 唯一，用 afterTrack 等待真实完成，不按预估 duration 排程。有限 Canvas 自定义任务 run 返回真实结束 Promise，清理 RAF/监听，setSuspended 合并冻结，恢复不补跑积压。

## 真实模型与媒体

先查资源详情 `analysis_metadata.model3d.animations`，要求 supported=true，使用真实 index/signature；不能猜动作名或从动画数量推断支持。AssetModel.v3 的组件 ref.getHandle() 只在真实首帧后返回句柄。注册 `scene.task(handle.animation({id,role:'blocking',clipIndex,signature}))`，第二段加 afterTrack。一个实例不能同时播放两个动作；相机/transform 是数值副本，onUpdate 调 invalidate，清理调 reset。不支持 seek、倒放或模型采样。

AssetAudio.v1 的 purpose=narration、AssetVideo.v1 的 purpose=automatic 经 media-ready 点名给 createSceneMediaTask.v1，真实 ended 才完成。content 只由用户手动播放，不交给 Scene。每页最多一个自动发声主媒体，其它自动视频 muted；旁白不能 loop。受阻媒体必须在当前 Runtime/观众窗口点击允许播放，控制台或 Editor 父窗口不能代替该手势，全屏也不保证发声许可。

useAudioCue.v2 的 playCue('interaction.*') 返回真实播放许可的 Promise，不等待 cue 结束，不作为 blocking 主媒体。没有 provider/绑定、静音或静态上下文按稳定结果处理。

联合样例应同时包含数字、打字机、SVG、DOM/CSS/Canvas 粒子、两个真实动作、旁白和 cue。源码与类型验证不能替代浏览器、WebGL、发声或正式双窗口实测。

## 独立静态态与结果

同根 useStaticPresentation 的 default/poster/unsupported 与 Scene 完全独立。capture/export/thumbnail 不创建 Scene、不快进或取动画帧；poster prepare 响应 AbortSignal，unsupported 附短原因。STATIC_PRESENTATION_UNAVAILABLE 为内容 unavailable，不覆盖已完成布局诊断，不把资源错误、Renderer 超时归成静态不支持。

`wp --json page screenshot <page_id> --job --target-version <version>` 使用独立静态截图任务；`--no-wait` 或等待到期返回 pending 和 job_id，可用 `--job-id` 继续。ready 才落盘；unavailable 是内容决定，skipped 是任务跳过，failed 是执行失败并非成功截图。任意时刻取帧参数已删除。

项目只有 manual/timer/scene_end、delay_ms、completion_delay_ms 与 loop。完成停留可为零，scene_end 必须有 blocking，timer 到点终止本页。保持/释放只阻止自动翻页，不暂停 Scene 或改写配置。截图不能证明动画已播完或声音可听；未实测项明确列出。
