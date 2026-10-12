# AutoREST — AI-Driven REST Electronic Structure Automation

> **DSH Skill 入口。加载 `assets/skills/autorest/SKILL.md` 获取完整指令。**

## 路由规则

当用户请求涉及以下内容时，加载 `assets/skills/autorest/SKILL.md`：
- REST 电子结构计算、输入卡生成
- DFT 泛函和基组选择
- 单点能、结构优化、频率、热化学
- TD-DFT 激发态
- GW / G₀W₀ / BSE 激发态
- "帮我算一个XX分子"
- 计算失败诊断和恢复

## 项目结构

```
AutoREST/
├── SKILL.md                         # ← 本文件 (DSH 路由入口)
├── AGENTS.md                        # AI Agent 开发指南
├── README.md                        # GitHub 项目文档
├── package.json                     # DSH 插件元数据
├── cordis.patch.yml                 # DSH Cordis 注册
├── pyproject.toml                   # pip install 入口
├── assets/skills/autorest/          # DSH Skill 核心
│   ├── SKILL.md                     # 6阶段闭环指令 (主脑)
│   ├── references/                  # REST手册 + GW-BSE指南
│   ├── scripts/                     # Python 工具
│   └── templates/                   # 输入卡模板
└── autorest/                        # Python 核心库 (CLI用)
    └── core/                        # 确定性执行臂 (task_ir, diagnose, provenance, pipeline)
```

## 核心铁律

1. 绝不猜测电荷/自旋
2. `spin` ≠ `bse_spin`（三重态BSE时 spin=1 不动）
3. HOMO/LUMO 靠 Fermi Surface 分界线
4. "程序跑完" ≠ "科学可信"
5. 每次运行记录溯源 (provenance)