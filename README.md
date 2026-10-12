# AutoREST — DSH Quantum Chemistry Skill

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![REST](https://img.shields.io/badge/REST-electronic_structure-green)](https://gitee.com/restgroup)
[![DSH Skill](https://img.shields.io/badge/DSH-Skill-blue)](https://www.deepseek.com/)

> **在 DSH 聊天界面用选择面板完成量子化学计算。安装后重启 DSH 即生效。不需要 TypeScript，不需要后端服务。**

---

## 安装（3 种方式）

### 方式一：下载 Release 压缩包（推荐）

1. 从 [Releases](https://github.com/masterTHou/AutoREST/releases) 下载 `autorest-skill.zip`
2. 解压到你的项目根目录，确保解压后出现 `你的项目/.dsh/skills/autorest/SKILL.md`
3. 重启 DSH

### 方式二：克隆项目后拷贝

```powershell
git clone https://github.com/masterTHou/AutoREST.git
cd AutoREST

# Windows — 拷贝到当前项目
New-Item -ItemType Directory -Force -Path "你的DSH项目\.dsh\skills\autorest"
Copy-Item ".dsh\skills\autorest\*" "你的DSH项目\.dsh\skills\autorest\" -Recurse -Force

# 重启 DSH
```

### 方式三：全局安装

```powershell
# Windows
git clone https://github.com/masterTHou/AutoREST.git
cd AutoREST
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.dsh\skills\autorest"
Copy-Item ".dsh\skills\autorest\*" "$env:USERPROFILE\.dsh\skills\autorest\" -Recurse -Force
```

```bash
# macOS / Linux
git clone https://github.com/masterTHou/AutoREST.git
cd AutoREST
mkdir -p ~/.dsh/skills/autorest
cp -r .dsh/skills/autorest/* ~/.dsh/skills/autorest/
```

---

## 使用

重启 DSH 后，在聊天里说：

> 帮我算一个水分子的单点能

DSH 自动发现 AutoREST Skill，弹出 3 步选择面板：

1. **面板 1**：算啥 → 分子从哪来 → 电荷/自旋
2. **面板 2**：选方法 (B3LYP/PBE0/XYG3...) → 选资源
3. **面板 3**：汇总确认 → 生成 REST TOML 输入卡

**重要**：AutoREST 生成的是 REST 标准的 **TOML** 格式输入卡（`[ctrl]` + `[geom]` 区块），不是 JSON。

---

## DSH Skill 发现原理

DSH 自动按优先级扫描：

| 优先级 | 目录 | 说明 |
|--------|------|------|
| 100 | `<项目>/.dsh/skills/<name>/SKILL.md` | 项目专属，最高优先 |
| 200 | `<项目>/.agents/skills/<name>/SKILL.md` | 项目备用 |
| 400 | `~/.dsh/skills/<name>/SKILL.md` | 全局安装 |

**不需要** `package.json`、Cordis 插件、TypeScript 编译。纯 Markdown + Python 脚本。

---

## 也支持 pip CLI（不依赖 DSH）

```bash
git clone https://github.com/masterTHou/AutoREST.git
cd AutoREST
pip install -e .
autorest --help
```

---

## 项目结构

```
AutoREST/
├── .dsh/skills/autorest/        # DSH Skill（这是核心！）
│   ├── SKILL.md                 # 3步交互面板指令
│   ├── references/              # REST手册 + GW-BSE指南
│   └── scripts/                 # Python 工具脚本
├── autorest/                    # Python CLI 库
│   └── core/                    # task_ir, diagnose, pipeline...
├── examples/                    # 入门示例
├── tests/                       # 测试
└── README.md                    # ← 本文件
```

---

**MIT License | 重启 DSH 即生效 | 在聊天里完成量子化学计算**