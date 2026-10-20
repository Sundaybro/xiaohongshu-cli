# 扩展功能版

发布分支：`local/pr-features`。上游基线：`4d63f3c`，包版本仍为 `0.6.4`。

已合入 PR：#87、#47、#64（含 #63 的扫码插件修复）、#84（含 #83）、#52、#15、#88。
本分支以扩展功能快照发布；上游主干历史保留。上述 PR 来源于 jackwener/xiaohongshu-cli。

## 新增能力

```bash
xhs sub-comments "<带 xsec_token 的笔记 URL>" <comment_id> --json
xhs search "旅行" --time "一周内" --json
xhs search-user "摄影" --page 2 --page-size 20 --json
xhs following --page 1 --page-size 200 --json
xhs history --json
xhs read "<笔记 URL>" --save-images --output ./downloads --json
xhs chats --limit 20 --json
xhs messages <user_id> --limit 30 --json
xhs send <user_id> -c "消息正文" --json
xhs my-notes-data --page 1 --page-size 10 --json
xhs post-video --title "标题" --body "正文" --video ./video.mp4 --private --json
```

私信发送默认每分钟一次。不要把安装或测试视为发送消息/发布笔记的授权。

图文和视频发布的话题正文会转换为小红书原生 `#名称[话题]#`，同时提交解析所得的有效话题元数据。原生标记不重复叠加，URL fragment 保持原样，未解析到的普通标签保留原文。该功能来自 PR #88，并适配了视频发布及边界情况；验证使用模拟发布，不代表已执行真实发帖。
私信与发布请求遇到超时或服务端错误不自动重发，避免产生重复内容。
视频发布支持 MP4/MOV、可选封面、多次 `--topic` 和正文话题提取。
视频编码/时长等媒体有效性仍由服务器判断；上传实现会将文件读入内存。

## 本机适配

- HERMES 补丁已提交到源码：`extract_browser_cookies()` 直接返回 `None`，避免 macOS 钥匙串弹窗。
- 登录使用已有保存的 Cookie 或 `xhs login --qrcode`；普通浏览器 Cookie 自动提取已禁用。
- 无法识别当前账号时，私信方向标记为 `unknown`。
- 视频与封面先检查，再开始上传；进度写到 stderr，stdout 保持 JSON 信封。
- 保留原有图文发布的请求通道，视频使用 PR #15 的 creator 通道。
- 单元测试隔离账号配置目录；真实接口测试必须单独运行。

## 后续更新

本分支包含本地提交，不能再用主干的 `git pull --ff-only` 流程。

```bash
cd xiaohongshu-cli
git switch local/pr-features
git status --short
git fetch upstream
git merge upstream/main
# 如有冲突，解决并测试后再安装；保留 HERMES 补丁。
uv tool install --force .
xhs --help
```

新 PR 同样先下载、审查、逐个合并和测试，再重装。
不要直接升级成 PyPI 包，否则会覆盖本地功能及 HERMES 补丁。

## 验证范围

组合代码的 211 项单元测试与 Ruff 检查通过。单元测试排除
`tests/test_integration.py` 和 `tests/test_smoke.py`，不发送真实私信、不发布笔记。
私信发送和视频发布的服务器端结果尚需在用户明确指定内容后单独实测。

已增加 result 包装兼容与嵌套失败检查，避免把服务端拒绝显示为成功。

## 用户搜索与关系列表

`search-user` 支持 `--page`（从 1 开始）、`--page-size`、可选 `--search-id`。
默认参数保持原行为；需要复用搜索会话时，在连续页中传入相同 search-id。
用户搜索分页已通过只读接口验证。

`following` 使用 `/api/im/web/users/following/all`，仅支持当前账号。
参数是 `page`、`size`（CLI 为 `--page-size`），分页已通过只读接口验证。
数据保留原始关系 `status`，不筛选为互关列表。
服务端没有显式 has_more；按网页逻辑由当页数量推断下一页，输出标注
`pagination_inferred=true`，满页时可以继续请求下一页。

`history` 使用 `/api/sns/web/v1/common/dual_feed`，参数
`scene=browse_history`、`cursor_score`、`note_index`、`image_formats`。
这是服务器保存的当前账号笔记浏览历史，已与历史计数接口交叉验证。
使用返回的 `cursor`、`next_note_index` 续取：

```bash
xhs history --cursor "<上一页 cursor>" --note-index <上一页 next_note_index> --json
```

笔记保留 `browse_time` 和原始笔记字段。Rich 显示本机时区的浏览时间。
`has_more` 来源于服务端 `has_no_more`；嵌套错误及缺失分页标志会报错。
`/api/sns/web/v1/feed/browsing_history` 实际是直播历史，本次未封装。

以上接口定义来自 2026-10-13 当前网页公开主脚本
`/formula-static/xhs-pc-web/public/resource/js/index.c7cc70de.js`。
粉丝名单的有效接口仍未确认；新增关注通知属于事件记录，不能代表完整粉丝名单。
