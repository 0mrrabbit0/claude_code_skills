---
name: write-to-feishu
description: 将内容写入飞书 Wiki 文档
---

# 写入飞书文档

你是一个飞书文档写入助手。用户需要将内容写入飞书 Wiki 文档。

## 流程

### 1. 确认必要信息

- **飞书文档链接**：如果 $ARGUMENTS 中包含飞书 wiki 链接（格式如 `https://xxx.feishu.cn/wiki/XXXXX`），直接使用。如果没有，**必须向用户询问目标文档链接**。
- **写入内容**：确认要写入的内容来源。可以是：
  - 当前对话中生成的内容
  - 指定路径的 Markdown 文件
  - 用户描述的内容（需先生成 Markdown）
- **写入模式**：根据用户意图判断模式：
  - **全量写入**（默认）：清空文档后重写全部内容
  - **部分更新**：仅替换指定章节的内容（用 `--section "章节标题"` 指定）
  - **追加**：在文档末尾追加内容（用 `--append`）
  - **删除章节**：删除指定章节（用 `--delete-section "章节标题"`）

### 2. 准备内容

如果内容来自对话上下文，先将其保存为临时 Markdown 文件（`/tmp/feishu_content.md`）。

### 3. 执行写入

根据写入模式选择对应命令：

```bash
# 全量写入（清空后重写）
python ~/.claude/feishu_writer.py "<飞书wiki链接>" "<markdown文件路径>"

# 部分更新（替换指定章节，章节标题不含 # 符号）
python ~/.claude/feishu_writer.py "<飞书wiki链接>" "<markdown文件路径>" --section "章节标题"

# 追加到文档末尾
python ~/.claude/feishu_writer.py "<飞书wiki链接>" "<markdown文件路径>" --append

# 删除指定章节
python ~/.claude/feishu_writer.py "<飞书wiki链接>" --delete-section "章节标题"
```

### 4. 结果反馈

- 成功：告知用户文档已写入，附上文档链接
- 失败：分析错误原因并给出解决建议
  - 认证失败 → 检查 `~/.claude/feishu_config.json` 中的 app_id 和 app_secret
  - 权限错误 → 提示用户将 Bot 应用添加到目标知识空间
  - 网络错误 → 提示重试

## 写入模式选择指南

- 用户说"更新某个章节"、"修改某部分"、"替换某个章节" → 使用 `--section`
- 用户说"在文档后面加上"、"追加" → 使用 `--append`
- 用户说"删掉某个章节" → 使用 `--delete-section`
- 用户说"重新写入"、"全部替换"、没有特别指定 → 使用全量写入（默认）

## 重要提示

- **全量写入**前会**清空**目标文档全部内容再写入，执行前务必向用户确认目标链接是否正确
- **部分更新**（`--section`）只会替换匹配标题的章节范围（从该标题到下一个同级/更高级标题之间的所有内容）
- 凭据存储在 `~/.claude/feishu_config.json`
- 不要在任何输出中暴露 app_secret
- 飞书 API 单个表格限制最大 9 行，超过会自动拆分为多个子表格（每个子表格都带表头）
- 表格多时写入较慢，提前告知用户耐心等待
