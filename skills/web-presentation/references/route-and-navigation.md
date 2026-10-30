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

项目默认放映配置通过 `wp project slideshow get <project_id>` 读取，通过 `wp project slideshow update <project_id> --slideshow-file <file>` 整体写回。schema 4 的完整对象：

```json
{"transition":{"effect":"fade","duration_ms":400},"advance":{"mode":"scene_end","delay_ms":5000,"completion_delay_ms":300},"loop":false}
```

advance 只接受 manual/timer/scene_end。delay_ms 为 1000–3600000，completion_delay_ms 为 0–3600000、默认 300；零表示实际完成后立即翻页。旧模式、旧超时和自动开始已删除。CLI 在新 advance 写入前确认服务 schema 4，缺失为 SLIDESHOW_CAPABILITY_MISSING，不降级 timer。scene_end 必须有有限 blocking，循环 ambient 不计入；timer 到点停止本页。播放必须显式开始，保持/释放只影响推进。

路由覆盖通过 `wp project route update <project_id> --edit-file <file>`，按完整路径修改并保留未编辑节点原覆盖，过滤 id/effective_slideshow 等只读字段。transition/advance 整组覆盖，null 恢复继承；省略表示不修改。分组仅接受 order/hidden/group_title。整树 replace 会移除未包含节点，不要并发修改同一项目。

```json
[{"route":"cover","order":1},{"route":"chapter-1/overview","advance":null},{"route":"narration","advance":{"mode":"scene_end","delay_ms":5000,"completion_delay_ms":0}}]
```

音频设置不再受阶段开关限制，仍校验真实资源、权限和严格音量。Scene 旁白实际 ended 才完成；同页最多一个自动发声主媒体，cue 不参与该完成目标。配置保存不能证明任何浏览器已播放。写后重新读取页数、顺序、可见性和绑定，截图仅复核静态布局，正式播放留待真实预览验证。
