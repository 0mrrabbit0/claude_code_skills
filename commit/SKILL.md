---
name: commit
description: 按照 Conventional Commits 规范执行 git 提交
---

# Git Conventional Commit

请按照以下 Conventional Commits 规范执行 git 提交。

## 提交格式

```
<type>(<scope>): <subject>

<body>

<footer>
```

## 提交类型 (Type)

只允许使用以下类型（全小写）：

| Type       | 含义                         |
|------------|------------------------------|
| `feat`     | 新功能 (Feature)              |
| `fix`      | Bug 修复                      |
| `docs`     | 仅修改文档/注释                |
| `style`    | 不影响逻辑的代码格式变更        |
| `refactor` | 既不修 Bug 也不加功能的重构     |
| `perf`     | 提升性能的代码更改              |
| `test`     | 增加或修改测试用例              |
| `chore`    | 构建过程或辅助工具变更           |

## 规则

1. **Type** 全小写，从上表中选择最匹配的一个
2. **Scope** 可选，用括号包裹，表示影响范围（模块/组件名），例如 `feat(login):`
3. **Subject** 必填：
   - 不超过 50 个字符
   - 结尾不加标点符号
   - 使用祈使句（"add" 而非 "added"）
   - 简短描述变更内容
4. **Body** 可选，空一行后写详细描述修改动机
5. **Footer** 可选，用于标注重大变更 `BREAKING CHANGE: ...` 或关联 issue

## 执行步骤

1. 运行 `git status` 查看变更文件（不使用 -uall）
2. 运行 `git diff --staged` 和 `git diff` 查看具体变更内容
3. 运行 `git log --oneline -5` 查看最近提交风格以保持一致
4. 根据变更内容分析：
   - 判断最合适的 **type**
   - 判断影响的 **scope**（如果明确的话）
   - 撰写简洁的 **subject**
   - 如果变更复杂，撰写 **body**
5. 使用 `git add` 暂存相关文件（精确指定文件名，不要用 `git add -A` 或 `git add .`）
6. 使用以下 HEREDOC 格式提交：

```bash
git commit -m "$(cat <<'EOF'
<type>(<scope>): <subject>

<body>

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

## 示例

```
feat(auth): add JWT token refresh mechanism

fix(api): resolve null pointer in user query

docs: update README with deployment instructions

refactor(utils): simplify date formatting logic

chore: upgrade webpack to v5
```

## 注意事项

- 不要提交可能包含敏感信息的文件（.env、credentials 等）
- 不要主动推送到远程仓库，除非用户明确要求
- 提交前确认所有变更都已正确暂存
- 如果 pre-commit hook 失败，修复问题后创建新提交，不要 amend
