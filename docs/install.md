# patent skill 接入与配置指南（Windows / macOS / Linux）

本指南用于把 `patent` skill 装到一台新机器后**直接可用**。核心是第 3 步的**依赖自检**——它替代了过去"复制完不知道缺什么、跑到一半才报错"的盲区。

## 1. 目标目录

Claude Code skill 目录：

| 平台 | skill 目录 |
|---|---|
| Windows | `C:\Users\<用户名>\.claude\skills\patent\` |
| macOS / Linux | `~/.claude/skills/patent/` |

专利案件工作目录（建议放桌面）：

| 平台 | 案件目录 |
|---|---|
| Windows | `C:\Users\<用户名>\Desktop\Patent\` |
| macOS / Linux | `~/Desktop/Patent/` |

## 2. 复制 skill

把整个 skill 目录复制到上表的 skill 目录下，**复制整个文件夹，不要只复制 SKILL.md**。复制后应至少包含：

```text
patent/
  SKILL.md
  rules.md
  agents/            （多路 auditor 契约：global/claims/content/impl-auditor）
  assets/docx/专利撰写模板.docx
  docs/
  references/
  scripts/           （含 check_env.py 等）
  tests/             （可选，但建议保留）
```

## 3. 依赖自检（关键步骤，AI 会自动做）

skill 首次被接入时，AI 读到 `SKILL.md` 的"接入前环境自检"段后，会先跑：

```bash
python3 scripts/check_env.py --json
```

自检覆盖的依赖与处理方式：

| 依赖 | 类别 | 缺失时怎么办 |
|---|---|---|
| **python ≥ 3.9** | 系统级/必需 | 引导用户安装（macOS `brew install python@3.12`；Windows `winget install Python.Python.3.12`） |
| **python-docx** | pip/必需 | **AI 直接 `python3 scripts/check_env.py --fix` 自动安装** |
| **pandoc** | 系统级/**可选** | 缺失不阻断；真用到格式转换时再按提示装 |
| **document-skills:docx** | Claude Code 插件/必需 | 脚本检测不到，AI 在会话中确认能否调用；不能则重启 Claude Code / 重装插件 |

`missing_required=0` 即必需项就绪。也可手动跑查看人类可读报告：

```bash
python3 scripts/check_env.py          # 只看报告
python3 scripts/check_env.py --fix    # 顺带自动装 pip 类缺失项
```

**Windows 注意**：若 `python3` 无响应，改用 `py`：

```powershell
py --version
py scripts\check_env.py --json
```

## 4. 路径适配

skill 内部与规则文件不硬编码个人绝对路径。使用时，把案件路径换成当前机器的用户目录：

| macOS/Linux | Windows |
|---|---|
| `~/Desktop/Patent/<撰写者>/<案件名>/` | `C:\Users\<用户名>\Desktop\Patent\<撰写者>\<案件名>\` |

不要在新机器上沿用他人 `/Users/xxx/...` 的路径。

## 5. 快速验证

在 Claude Code 新会话中输入：

```text
接入 patent skill，先跑环境自检，再告诉我读取的是哪个 rules.md
```

期望：AI 先跑 `check_env.py` 报告依赖状态、补齐缺失项，再指向当前机器的 `.../patent/rules.md`。

## 6. 注意事项

- `rules.md` 是规则索引，`references/rules/global.md` 为默认强制读取；旧版规则在 `docs/archive/` 仅备查。
- DOCX 相关能力全部走官方 `document-skills:docx` 插件；Windows 端若无法调用，重启 Claude Code 或重新加载插件后再处理 DOCX。
- 修改专利 DOCX 时，若用户明确指定原文件路径，默认直接改原文件，不创建 `.bak` 备份。
- 返修署名不设默认值，每次由用户提供（见 `SKILL.md`「默认立场」）。
