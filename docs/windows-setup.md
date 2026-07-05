# Windows 复用配置指南

本指南用于把 Mac 上的 `patent` skill 复制到 Windows 电脑后直接使用。

## 1. 目标目录

### Claude Code skill 目录

Windows 上放到：

```text
C:\Users\<你的用户名>\.claude\skills\patent\
```

### 专利案件工作目录

建议在桌面创建：

```text
C:\Users\<你的用户名>\Desktop\Patent\
```

后续案件文件夹、交底书 DOCX 放在该目录下；固定模板优先使用 skill 内置的 `assets/docx/专利撰写模板.docx`。

## 2. 从 Mac 复制 skill

将 Mac 上整个目录：

```text
/Users/example/.claude/skills/patent/
```

复制到 Windows：

```text
C:\Users\<你的用户名>\.claude\skills\patent\
```

复制后应至少包含：

```text
patent/
  SKILL.md
  rules.md
  assets/
    docx/
      专利撰写模板.docx
  docs/
  references/
  scripts/
  tests/        （可选，但建议保留）
```

## 3. 案件目录准备

在 Windows 桌面创建：

```text
C:\Users\<你的用户名>\Desktop\Patent\
```

固定专利撰写模板已经随 skill 放在：

```text
C:\Users\<你的用户名>\.claude\skills\patent\assets\docx\专利撰写模板.docx
```

如果用户明确指定其他模板，也可以把该模板放在案件目录或 `Desktop\Patent` 下，并在任务中说明具体路径。

每个案件建议单独建文件夹，例如：

```text
C:\Users\<你的用户名>\Desktop\Patent\一种配电设备火灾状态评估方法及主动灭火系统\
```

## 4. 路径适配规则

Mac 路径：

```text
/Users/example/Desktop/Patent/
```

Windows 对应路径：

```text
C:\Users\<你的用户名>\Desktop\Patent\
```

在 Windows 使用时，不要继续使用 Mac 的 `/Users/example/...` 路径；应改用当前 Windows 用户目录。

## 5. 使用前检查

在 Windows 终端检查：

```powershell
python --version
```

如果没有响应，可试：

```powershell
py --version
```

还需要确认：

- Claude Code 能识别 `patent` skill；
- `C:\Users\<你的用户名>\Desktop\Patent\` 已存在；
- 案件交底书 DOCX 已放入案件文件夹；
- 固定模板 `assets/docx/专利撰写模板.docx` 已随 skill 复制；除非用户另行指定模板路径，不需要在 `Desktop\Patent` 下再放一份 `模板.docx`。

## 6. 快速验证

在 Windows 的 Claude Code 新会话中输入：

```text
调用 patent skill，告诉我当前读取的是哪个 rules.md
```

期望结果应指向：

```text
C:\Users\<你的用户名>\.claude\skills\patent\rules.md
```

并且 `rules.md` 首行应为：

```text
# 专利撰写规则
```

## 7. 注意事项

- `rules.md` 是默认强制规则文件。
- 旧版规则备查文件已归档到 `docs/archive/rules_2.md`，正常工作流只读取 `rules.md`。
- 不要只复制 `SKILL.md`，必须复制整个 `patent` 文件夹。
- 若 Windows 端无法调用 DOCX 相关能力，应重启 Claude Code 或重新加载插件后再处理 DOCX。
- 修改专利 DOCX 时，若用户明确指定原文件路径，默认直接改原文件，不再创建 `.bak` 备份。
