# AutoREST — AI-Driven REST Electronic Structure Automation

> **DSH 插件 Skill 路由入口。加载 `assets/skills/autorest/SKILL.md` 获取完整交互式指令。**

## 触发条件

当用户说的任何话涉及以下内容时，加载本 Skill：
- "帮我算..." "生成输入卡" "REST计算"
- 量子化学、DFT、电子结构、激发态
- GW-BSE、TD-DFT、结构优化、频率计算

## 路由

→ 立即加载 `assets/skills/autorest/SKILL.md`

## 核心约束 (写在最前面，每次都要看)

- **绝不一言不发直接生成输入卡**
- 必须通过 4 步 `ask_user_question` 交互面板
- 面板1: 任务类型 + 分子来源 + 电荷自旋
- 面板2: 方法选择 (多候选方案)
- 面板3: 分子结构确认 (AI生成 / 用户提供)
- 面板4: 汇总确认 → 生成输入卡