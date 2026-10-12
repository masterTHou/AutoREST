# AutoREST — AI-Driven REST Electronic Structure Automation

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![REST](https://img.shields.io/badge/REST-electronic_structure-green)](https://gitee.com/restgroup)
[![DSH Plugin](https://img.shields.io/badge/DSH-Plugin-blue)](https://www.deepseek.com/)

> **科学可信的量子化学计算助手。从自然语言到经过验证的 REST 计算结果，全自动闭环。**

---

## 两种安装方式

### 🟢 方式一：DSH 插件安装（推荐 — 聊天即计算）

和 AIFS 一样的安装方式：

1. 从 [Releases](https://github.com/your-org/AutoREST/releases) 下载 `autorest-1.0.0.tgz`
2. DSH 桌面版 → 「插件 → 添加插件」→ 填写 `.tgz` 绝对路径
3. 启用 AutoREST
4. 在聊天界面直接说：**"帮我算一个水分子的 B3LYP/def2-SVP 单点能"**

### 🔵 方式二：pip 命令行安装

```bash
git clone https://github.com/your-org/AutoREST.git
cd AutoREST
pip install -e .
autorest --help
```

---

## 架构：6 阶段科学闭环

```
科学问题
  ↓
[1] 交互式理解 → [2] 方法推荐(文献证据+选择面板)
  ↓
[3] REST能力检查 → [4] 输入卡生成(TOML模板+规则引擎)
  ↓
[5] 执行+解析(SCF监控+输出解析)
  ↓
[6] 科学验证 → 失败诊断+自动恢复 → 溯源记录
  ↓
交付报告(.in文件 + .provenance.json)
```

## 三层设计（借鉴 AIFS）

| 层次 | 核心职责 | 扩展方式 |
|------|---------|---------|
| **科学规划层** (Skill/LLM) | 理解用户目标、推荐方法、确认参数、交互式问答 | 按实际需求组织方案 |
| **通用工作流层** (`core/`) | 任务 IR、依赖管理、执行、解析、验证、诊断、溯源 | 复用通用规则，新增结果类型 |
| **REST 能力适配层** | 描述 REST 关键字和参数约束，生成并校验输入卡 | 核对源码，补充覆盖 |

---

## 核心模块

| 模块 | 路径 | 功能 |
|------|------|------|
| 任务 IR | `core/task_ir.py` | 机器可检查的任务描述（体系、方法、资源、验证条件） |
| 输入卡生成 | `core/input_gen.py` | REST TOML 输入卡生成引擎 |
| 执行器 | `core/runner.py` | REST 执行 + 实时 SCF 监控 |
| 解析器 | `core/parser.py` | 分层输出解析（0-based 轨道、Fermi Surface HOMO/LUMO） |
| 科学验证 | `core/verify.py` | PASS/WARN/FAIL 多级 QA |
| 失败诊断 | `core/diagnose.py` | 失败阶段分类 + 约束自动恢复 |
| 溯源记录 | `core/provenance.py` | 完整可哈希运行记录 |
| 报告生成 | `core/report.py` | 人类可读结果模板 |
| 闭环管线 | `pipeline.py` | 端到端：IR→生成→执行→解析→QA→诊断→溯源→报告 |

---

## DSH 对话示例

```
👤 "帮我算一下苯的激发态"

🤖 "要单重态还是三重态？精度要求？我推荐：
     ① SCAN/cc-pVDZ → G₀W₀-BSE (推荐，平衡精度和速度)
     ② PBE0/def2-TZVP → TD-DFT (快但定性)
     ③ M06-2X/def2-TZVPP → TD-DFT (更准更慢)"

👤 "选①，用这个xyz，8核"

🤖 "✅ benzene_singlet.in 已生成
     ✅ benzene_triplet.in 已生成
     ⚠️ REST 不支持溶剂效应，当前为气相"

👤 "帮我跑"

🤖 "SCF converged(12) | GW QP gap=10.63 eV | 
     S1=4.72 eV, brightest S4@7.13 eV(f=0.75) | 
     T1=3.58 eV | ΔEST=1.14 eV | QA: ✅ 全部通过
     📄 provenance 已保存"
```

### 对实验化学家的特别支持

直接说你要解决的科学问题，不用纠结技术参数：

> "我想知道这个催化剂能不能活化C-H键"

AutoREST 会自动理解你的目标 → 上网搜索类似体系 → 推荐方案 → 用通俗语言解释。

---

## 失败自动恢复

| 失败阶段 | 自动策略 |
|---------|---------|
| SCF 不收敛 | 电子数检查 → 换 initial_guess → 换 mixer → level_shift → smearing |
| Davidson 零根 | 自动 roots+10 / subspace+20 / restart+5 → 重跑 |
| GW 未完成 | 检查 QP warning → 扩大 explicit-QP 窗口 |
| 截断/超时 | 检查 OOM → 建议加资源或 resume |

---

## 项目结构

```
AutoREST/
├── AGENTS.md                    # AI Agent 开发指南
├── package.json                 # DSH 插件元数据
├── cordis.patch.yml             # Cordis 注册
├── pyproject.toml               # pip install 入口
├── README.md                    # ← 本文件
├── lib/index.js                 # DSH 插件激活
├── assets/skills/autorest/      # DSH Skill 核心
│   ├── SKILL.md                 # 6阶段闭环指令
│   ├── references/              # REST手册 + GW-BSE指南
│   ├── scripts/                 # Python 工具
│   └── templates/               # 输入卡模板
├── autorest/                    # Python 核心库
│   ├── core/                    # 确定性执行臂（LLM-free）
│   │   ├── task_ir.py           # 化学任务中间表示
│   │   ├── input_gen.py         # 输入卡生成
│   │   ├── runner.py            # REST 执行监控
│   │   ├── parser.py            # 输出解析
│   │   ├── verify.py            # 科学验证
│   │   ├── diagnose.py          # 失败诊断+自动恢复
│   │   ├── provenance.py        # 溯源记录
│   │   └── report.py            # 报告生成
│   └── pipeline.py              # 端到端闭环
├── examples/                    # 运行示例
└── tests/                       # 测试 + fixtures
    └── fixtures/                # 真实REST输出用于解析器测试
```

---

## 引用

- REST: Z. Li et al., *Chin. J. Chem. Phys.* DOI: 10.1063/1674-0068/cjcp2510156
- GW-BSE in REST: Q. Gao et al., *J. Chem. Phys.* 164, 214116 (2026)
- AutoREST: Z. Tong, *AutoREST*, 2026. https://github.com/your-org/AutoREST

---

**MIT License | pip install 即用 | 科学可信的量子化学计算助手**