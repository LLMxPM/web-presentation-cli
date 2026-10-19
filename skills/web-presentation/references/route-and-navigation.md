# 路由与导航

页面的 project_id 表示归属，路由树决定导航顺序、分组、路径及可见性；创建页面不会自动挂载。草稿可以不在路由中，完整演示交付必须核对所需页面均已挂载。

新增单个页面挂载优先使用 `route add`，不必手工重写已有树：

```bash
wp project route add <project_id> --page-id <page_id> --route overview --idempotency-key <key>
wp project route add <project_id> --page-id <page_id> --route details --parent chapter-1 --idempotency-key <key>
```

`--parent` 只能指向已有顶层分组；不提供时新增顶层页面。默认追加到同级最大 `order` 之后，也可指定 `--order` 与 `--hidden`。相同路径已绑定同一页面且设置一致时直接返回当前树；不同绑定不覆盖。`route update` 只修改已有节点，不能新增、重绑定或移动；创建分组、移动节点或批量重排使用 `route replace`。

先执行 `wp project route replace --help` 获取当前契约，再 `wp --json project route get <project_id>` 和 `wp --json page list --project-id <project_id>` 读取基线。

当前结构最多两层：顶层为 page 或 group，group 下只能是页面。group 必须有 group_title 和至少一个子页面，不能绑定 page_id；page 必须绑定当前项目真实页面，不能包含 group_title 或 children。route 是单段相对路径，不能使用 `/`、`/home`、`home/` 或 `a/b`。同级路径不得重复，order 决定同级顺序，hidden 控制导航隐藏。

以下为教学用最小写入示例，ID 必须替换成查询结果；不是离线契约：

```json
{"routes":[{"route_type":"page","route":"cover","order":0,"hidden":false,"page_id":1},{"route_type":"group","route":"chapter-1","group_title":"第一章","order":1,"children":[{"route":"overview","order":0,"hidden":false,"page_id":2}]}]}
```

`wp project route replace <project_id> --route-file .tmp/web-presentation/route-tree.json --idempotency-key <key>` 是整树替换，遗漏的节点会被移除。GET 响应包含 id、page_code、display_title 等只读字段，不能原样回写；按当前写入 Schema 构造请求。

替换前重新读取整树并保留任务范围外的节点。`route add` 和 `route update` 也通过读取当前树后整树写回实现，自动保留其它节点和原始放映覆盖；当前接口没有版本条件，读取后仍可能发生并发覆盖，幂等键不能解决并发冲突。不要并行修改同一项目路由，发现基线变化应重新协调，而非盲目覆盖。

## 放映配置与路由覆盖

项目默认放映配置通过 `wp project slideshow get <project_id>` 读取，通过 `wp project slideshow update <project_id> --slideshow-file <file>` 写回。`--slideshow-file` 可以是完整 slideshow 对象，也可以是包含 `slideshow` 字段的对象；写入时必须完整提供 `transition`、`advance`、`loop`、`auto_start`，CLI 和 Backend 都不会猜测补全。

```json
{
  "transition": {"effect": "fade", "duration_ms": 400},
  "advance": {"mode": "timer", "delay_ms": 5000, "media_timeout_ms": 300000},
  "loop": true,
  "auto_start": true
}
```

`advance.mode` 只接受 `manual`、`timer`、`media_end`；`delay_ms` 必填，`media_timeout_ms` 范围为 1000–3600000（默认 300000）。使用 `media_end` 或提供 `media_timeout_ms` 前，CLI 会读取工作空间 capability 的 `slideshow`：服务端未声明 `media_end`、或 Schema 低于 2 时直接失败（`SLIDESHOW_MEDIA_CAPABILITY_MISSING`），不会把媒体模式降级成 timer，也不会发送旧服务不认识的字段。未知模式返回 `SLIDESHOW_ADVANCE_MODE_UNKNOWN`。

```json
{
  "transition": {"effect": "fade", "duration_ms": 400},
  "advance": {"mode": "media_end", "delay_ms": 5000, "media_timeout_ms": 120000},
  "loop": false,
  "auto_start": true
}
```

`media_end` 表示等到本页非循环音视频全部结束再翻页；循环背景不参与等待，没有参与媒体时按 `delay_ms` 停留。保存成功只代表配置已写入，浏览器是否允许有声自动播放由 Runtime 与用户手势决定。

音频能力与放映配置相互独立：`capabilities.slideshow.audio` 决定旁白和 cue 是否开放；`page_narration=false` 时不要生成旁白，`audio_cues=false` 时 cue 绑定不会发声。旁白开放后，旁白页优先使用 `media_end`，让整页过渡和 render-ready 完成后再开始；`timer` 可能在旁白结束前翻页，`manual` 不因旁白结束翻页。cue 属于项目级音频设置，切页音效由真实页面切换触发，不要为了音效伪造路由变化；会话静音不写回项目配置。

路由覆盖使用 `wp project route update <project_id> --edit-file <file>`。该命令会先读取当前整树，按完整路由路径应用编辑，再整树写回；自动保留未编辑节点的原始 `transition`/`advance`，并过滤 `id`、`page_code`、`page_title`、`display_title`、`effective_slideshow` 等只读字段。路由路径顶层写 `cover`，分组子页写 `chapter-1/overview`。

```json
[
  {"route": "cover", "order": 1, "hidden": false},
  {"route": "chapter-1/overview", "transition": {"effect": "fade", "duration_ms": 400}, "advance": null},
  {"route": "video", "advance": {"mode": "media_end", "delay_ms": 5000, "media_timeout_ms": 120000}}
]
```

`transition` 和 `advance` 是整组覆盖：提供对象表示完整覆盖，显式 `null` 表示恢复继承项目默认值；省略字段表示本次不修改。分组节点只接受 `order`、`hidden`、`group_title`。`wp project route replace` 仍是原始整树替换入口，需要自行按当前写入 Schema 构造载荷，遗漏节点会被移除。

配置写入只代表平台保存了放映设置，不代表已控制任何浏览器窗口的播放状态；`auto_start` 只决定进入全屏放映时的初始自动/手动模式，运行中可在放映控制条切换，暂停和单窗口放映由 Runtime 在具备相应能力的版本中执行。不要用 CLI 冒充“已经播放”或跨设备远控。

替换后重新读取路由及页面列表，核对页数、顺序、可见性、真实页面 ID 和挂载状态，再截图复核目录、页码和导航。失败时报告错误与未完成项，不重复创建已经成功的页面。
