# AutoREST — AI-Driven REST Electronic Structure Automation

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![REST](https://img.shields.io/badge/REST-electronic_structure-green)](https://gitee.com/restgroup)
[![DSH Skill](https://img.shields.io/badge/DSH-Skill-blue)](https://www.deepseek.com/)

> **在 DSH 里像聊天一样完成量子化学计算。交互式选择面板 → 方法推荐 → 输入卡生成 → 科学验证。**

---

## 是什么 & 不是什么

| | AutoREST |
|---|---|
| ✅ 是 | **DSH Skill**（Markdown 指令集，LLM 读取后执行） |
| ✅ 也是 | **Python CLI 工具**（`pip install -e .` 后命令行使用） |
| ❌ 不是 | Cordis 插件（不需要 TypeScript、不需要后端服务） |

AutoREST 和 AIFS 不同：AIFS 是一个 Cordis 插件（有 TypeScript 编译产物 + Python 后端），AutoREST 是一个 **DSH Skill**——纯 Markdown + Python 脚本，利用 DSH 的 Skill 子系统被 LLM 发现和加载。

---

## 安装方式

### 🟢 作为 DSH Skill 使用（推荐）

DSH 自动从以下目录发现 Skill：

```
你的项目/.agents/skills/<name>/SKILL.md    ← rank 200
你的用户目录/.dsh/skills/<name>/SKILL.md   ← rank 400
```

**方法一：克隆到项目工作区**

```bash
git clone https://github.com/masterTHou/AutoREST.git
cd AutoREST
# 然后把 .agents/skills/autorest/ 复制到你用 DSH 打开的项目根目录
cp -r .agents/skills/autorest /你的DSH项目/.agents/skills/
```

重启 DSH 后，在聊天界面说「帮我算一个水分子的单点能」，DSH 会自动发现 AutoREST Skill 并弹出交互选择面板。

**方法二：安装到用户目录（全局可用）**

```powershell
# Windows PowerShell
mkdir -Force "$env:USERPROFILE\.dsh\skills\autorest"
Copy-Item ".agents\skills\autorest\*" "$env:USERPROFILE\.dsh\skills\autorest\" -Recurse -Force
```

```bash
# macOS / Linux
mkdir -p ~/.dsh/skills/autorest
cp -r .agents/skills/autorest/* ~/.dsh/skills/autorest/
```

### 🔵 命令行安装（不依赖 DSH）

```bash
git clone https://github.com/masterTHou/AutoREST.git
cd AutoREST
pip install -e .
autorest --help
```

---

## 交互式使用体验

在 DSH 聊天界面说话，AutoREST 会**弹出选择面板**，不是直接丢 TOML：

```
👤 "帮我算水分子单点能"

🤖 [弹出面板 1]
   你要算什么？
   ○ 单点能  ○ 结构优化  ○ 频率+热化学
   分子结构从哪里来？
   ○ 我提供坐标  ○ AI 帮我生成
   电荷和自旋？
   ○ 中性闭壳层  ○ 我不确定

👤 选「单点能」「AI生成」「中性闭壳层」

🤖 [弹出面板 2]
   选择计算方法：
   ○ B3LYP-D3BJ / def2-SVP (推荐)
   ○ PBE0-D3BJ / def2-TZVP
   ○ XYG3 / def2-QZVPP

👤 选第一个

🤖 ══════════════════════════════
     AutoREST 计算方案确认
   ══════════════════════════════
     分子: H₂O (水)
     方法: B3LYP-D3BJ / def2-SVP
     电荷: 0  自旋: 1
   ══════════════════════════════
   ✅ water_energy.in 已生成
```

---

## 项目结构

```
AutoREST/
├── .agents/skills/autorest/      # DSH Skill（核心）
│   ├── SKILL.md                  # YAML frontmatter + 指令
│   ├── references/               # REST手册 + GW-BSE指南
│   │   ├── rest_readme.txt
│   │   ├── rest_guide.md
│   │   └── gwbse_guide.md
│   └── scripts/                  # Python 工具
│       ├── input_generator.py
│       ├── output_parser.py
│       ├── scientific_validator.py
│       ├── gwbse_parser.py
│       ├── diagnose.py
│       ├── provenance.py
│       └── ...
├── autorest/                     # Python CLI 库
│   └── core/                     # task_ir, diagnose, pipeline...
├── examples/                     # 入门示例
├── tests/                        # 测试
├── pyproject.toml                # pip install 入口
├── AGENTS.md                     # 开发者指南
└── README.md                     # ← 本文件
```

---

## 引用

- REST: Z. Li et al., *Chin. J. Chem. Phys.* DOI: 10.1063/1674-0068/cjcp2510156
- GW-BSE in REST: Q. Gao et al., *J. Chem. Phys.* 164, 214116 (2026)

---

**MIT License | DSH Skill + Python CLI | 科学可信的量子化学计算助手**