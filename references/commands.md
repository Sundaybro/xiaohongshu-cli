# 常用命令与分页

以下针对本仓库功能分支。参数以已安装的 `xhs <command> --help` 为准，不使用真实写操作验证安装。

## 登录与读取

```bash
xhs status --json
xhs whoami --json
xhs login --qrcode
xhs search "旅行" --page 2 --json
xhs search "收纳" --type image --sort popular --json
xhs search "收纳" --type image --sort latest --json
xhs search "旅行" --time "一周内" --json
xhs search-user "摄影" --page 2 --page-size 20 --json
xhs read "<带 xsec_token 的笔记 URL>" --json
xhs comments "<笔记 URL>" --all --json
xhs sub-comments "<笔记 URL>" <comment_id> --json
xhs user <user_id> --json
xhs user-posts <user_id> --cursor "<游标>" --json
xhs feed --json
xhs hot -c food --json
xhs topics "旅行" --json
xhs likes --json
xhs favorites --json
xhs following --page 1 --page-size 200 --json
xhs history --json
xhs read "<笔记 URL>" --save-images --output ./downloads --json
xhs chats --limit 20 --json
xhs messages <user_id> --limit 30 --json
xhs unread --json
xhs notifications --type connections --json
xhs my-notes --page 0 --json
xhs my-notes-data --page 1 --page-size 10 --json
```

JSON 业务数据在 `.data`。搜索通常为 `.data.items[].note_card`；详情为 `.data.items[].note_card`；用户笔记为 `.data.notes`，其单条字段、互动字段与搜索卡片不同，先检查实际响应再解析。

搜索类型 `image` 的响应中，图文笔记 `type` 通常为 `normal`。点赞/收藏可能是含“万”或“+”的展示字符串，转换时保留近似属性；没有提供的指标不能补零。

## 分页

- `search-user` 从第 1 页开始，支持 `--page-size`、`--search-id`。连续页需要维持搜索会话时复用相同 search-id。
- `comments --all` 自动翻一级评论；楼中楼使用 `sub-comments`，按帮助传递所需令牌与续页参数。
- 用户笔记、收藏、赞过列表按各命令返回的游标续取；不同命令页码起点不同，勿统一假定。
- `following` 仅当前账号。接口 `/api/im/web/users/following/all` 参数为 `page`、`size`（CLI 为 `--page-size`）。保留原始关系 status，不筛为互关。`pagination_inferred=true` 表示由当页数量推断 has_more。
- 笔记历史使用 `/api/sns/web/v1/common/dual_feed`、`scene=browse_history`。续页同时使用返回的 `cursor` 和 `next_note_index`：

```bash
xhs history --cursor "<上一页 cursor>" --note-index <上一页 next_note_index> --json
```

历史 `has_more` 来源于 `has_no_more`；`/api/sns/web/v1/feed/browsing_history` 是直播历史，不用于笔记历史。

## 用户要求写操作后使用

```bash
xhs follow <user_id> --json
xhs unfollow <user_id> --json
xhs like "<笔记 URL>" --json
xhs like "<笔记 URL>" --undo --json
xhs favorite "<笔记 URL>" --json
xhs unfavorite "<笔记 URL>" --json
xhs comment "<笔记 URL>" -c "用户确定的正文" --json
xhs reply "<笔记 URL>" --comment-id <comment_id> -c "用户确定的正文" --json
xhs send <user_id> -c "用户确定的正文" --json
xhs post --title "标题" --body "正文" --images ./image.png --json
xhs post-video --title "标题" --body "正文" --video ./video.mp4 --private --json
```

删除命令 `delete`、`delete-comment` 及其参数先查帮助，确认目标与授权后使用。`logout` 会清除保存的凭证，不作为常规检查步骤。

私信默认每分钟一次，不解除节流来解决 `rate_limited`。提交结果不明时不盲目重发。图文与视频发布通道不同，大视频上传会读入内存；确认媒体有效性和账号权限后再发布。
