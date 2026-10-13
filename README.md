# AutoREST — 量子化学计算 DSH 智能助理

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![REST](https://img.shields.io/badge/REST-v2026-green)](https://gitee.com/restgroup)
[![DSH Plugin](https://img.shields.io/badge/DSH-Plugin-blue)](https://www.deepseek.com/)
[![Version](https://img.shields.io/badge/version-4.0.0-brightgreen)](https://github.com/masterTHou/AutoREST/releases)

> **在 DeepSeek Harness 里用聊天完成量子化学计算。真正的 DSH Cordis 插件，带 Tool 注册和 Python JSON Bridge。**
>
> 你说「帮我算一个水分子的单点能」，它会自动检测 REST 环境，然后自适应地引导你完成计算——新手会得到一步步的推荐引导，专家可以直接一句话搞定。输出标准的 `.in` 输入文件（TOML 格式），运行命令：`conda activate rest && rest -i 文件名.in > 文件名.out`。

---

## 目录

- [它解决了什么问题](#它解决了什么问题)
- [它能做什么](#它能做什么)
- [工作原理](#工作原理)
- [安装](#安装)
- [使用示例](#使用示例)
- [对两类用户的支持](#对两类用户的支持)
- [项目结构](#项目结构)
- [开发相关](#开发相关)
- [引用](#引用)
- [License](#license)

---

## 它解决了什么问题

量子化学程序（如 [REST](https://gitee.com/restgroup)）需要用户编写 TOML 格式的输入文件，里面要指定泛函（如 B3LYP、PBE0）、基组（如 def2-SVP、cc-pVDZ）、电荷、自旋多重度、色散校正等十几个参数。这对于非计算化学专业的研究者来说门槛很高：

- ❌ 不知道选 B3LYP 还是 PBE0
- ❌ 不清楚 def2-SVP 和 cc-pVTZ 的区别
- ❌ 不知道该不该加色散校正
- ❌ 手写 TOML 经常漏掉 `[ctrl]` 或把 `charge` 写到 `[geom]` 里去

**AutoREST 把这些专业知识内置到了 DSH 的对话里。** 你只需要说出你的化学问题，它在聊天框里弹出选择题面板，你点点选选，输入卡就自动生成了。

---

## 🆕 v4.0.0 — 真正的 DSH Cordis 插件 + Python JSON Bridge

### 架构升级

v3.0.0 将 AutoREST 从一个**纯 Markdown Skill** 升级为**真正的 DSH Cordis 插件**。安装后，DSH 自动注册 3 个可调用工具：

| 工具 | 功能 |
|------|------|
| `autorest_detect_rest` | **自动扫描**你的电脑上的 REST 安装（conda env、系统 PATH、当前 conda 环境）。找到就告诉你路径和版本；找不到就只生成 .in 文件 |
| `autorest_generate_input` | **确定性生成** REST .in 输入文件。接受结构、方法、基组等参数，输出严格符合 REST TOML 规范的卡片 |
| `autorest_parse_output` | **解析** REST 输出文件。提取 SCF 能量/收敛状态、GW QP gap、BSE 激发能/振子强度 |

### 安装后第一句话的效果

```
👤 "帮我算水分子"

🤖 [自动调用 autorest_detect_rest]
   "✅ REST 已检测到：D:\anaconda3\envs\rest\bin\rest.exe
    (REST 2026.1.1, conda env rest)
    生成 .in 文件后运行：
    conda activate rest && rest -i water_energy.in > water_energy.out
    现在你要算什么？"
```

或者没有 REST 的情况：

```
👤 "帮我算水分子"

🤖 [自动调用 autorest_detect_rest]
   "⚠️ REST 未检测到。我会只生成 .in 输入文件。
    安装命令：conda create -n rest -c restgroup rest
    安装后运行：conda activate rest && rest -i 文件名.in > 文件名.out
    现在你要算什么？"
```

### 保留 v2.x 全部功能

标准/快捷/批量三种工作模式、13 种关键词动态方法推荐、REST 任务语法速查表、SCF 收敛故障速查——全部保留。

---

## 它能做什么

| 你说的 | AutoREST 自动生成的 |
|--------|-------------------|
| 「帮我算水分子的能量」 | 单点能 `.in` 输入文件 (`job_type = "energy"`) |
| 「优化苯的结构」 | 几何优化 `.in` 输入文件 (`job_type = "opt"`) |
| 「算一下这个分子的振动频率」 | 频率 + 热化学 `.in` 输入文件 (`[hessian]` + `[thermo]`) |
| 「算紫外吸收光谱」 | TD-DFT 激发态 `.in` 输入文件 (`[tddft]`) |
| 「要更高精度的激发态」 | G₀W₀-BSE `.in` 输入文件 (`[quasiparticle_methods]`) |
| 「单重态和三重态能差」 | BSE singlet + triplet `.in` 输入文件 |

**所有生成的输入卡都是 `.in` 文件（REST 标准 TOML 格式）**，包含正确的 `[ctrl]` 和 `[geom]` 区块。运行命令：`conda activate rest && rest -i 文件名.in > 文件名.out`。

### 内置的方法知识库

AutoREST 知道什么时候推荐什么方法：

| 场景 | 推荐 |
|------|------|
| 有机分子快速计算 | B3LYP-D3BJ / def2-SVP |
| 需要定量精度 | PBE0-D3BJ / def2-TZVP |
| 发表级高精度 | XYG3 / def2-QZVPP |
| 激发态 | TD-DFT: PBE0/def2-TZVP 或 GW-BSE: SCAN/cc-pVDZ |
| 过渡金属 | PBE0-D3BJ / def2-TZVP（提醒可能收敛困难） |

---

## 工作原理

### 架构

AutoREST v4 是一个 **DSH Cordis 插件**（不是纯 Skill）。安装后，DSH 通过 `cordis.patch.yml` 加载插件，插件注册 3 个可调用 Tool，Tool 通过 DSH Shell seam 安全调用 Python JSON Bridge。

```
你说 "帮我算水分子"
       ↓
DSH Plugin 加载 (cordis.patch.yml → lib/index.js)
       ↓
注册 3 个 Tool + System Prompt + Bundled Skill
       ↓
LLM 调用 autorest_detect_rest → Python bridge → 检测 REST 环境
       ↓
LLM 自适应交互（新手引导 / 专家直达）
       ↓
LLM 调用 autorest_generate_input → Python bridge → InputGenerator
       ↓
输出 .in 文件（REST TOML 格式）
```

### 技术栈

| 组件 | 技术 |
|------|------|
| DSH 插件 | TypeScript Cordis plugin (`package.json` + `cordis.patch.yml`) |
| Tool 注册 | `ctx.tools.register(defineTool(...))` |
| Python Bridge | stdin JSON → stdout JSON（无状态，一次请求一进程） |
| 科学计算核心 | Python 3.9+ (`InputGenerator`, `OutputParser`, `ScientificValidator`) |
| 参考知识库 | Markdown + TXT (REST 手册、GW-BSE 指南、方法选择表) |
| 测试 | Python `unittest` + 真实 REST 输出 fixtures |

---

## 安装

### 方式一：DSH 插件安装（推荐）

1. 从 [Releases](https://github.com/masterTHou/AutoREST/releases) 下载 `autorest-dsh-4.0.0.tgz`
2. DSH 桌面版 → 插件 → 添加插件 → 填写 `.tgz` 绝对路径，**无需解压**
3. 启用 AutoREST
4. 在聊天里说：「帮我算一个水分子的单点能」

### 方式二：pip 命令行安装（不依赖 DSH）

```bash
git clone https://github.com/masterTHou/AutoREST.git
cd AutoREST
pip install -e .
autorest --help
```

---

## 使用示例

### 示例 1：最简单的单点能计算

```
👤 帮我算水分子的单点能

🤖 [弹出面板 1/3]
   📋 计算任务
   ○ 单点能（推荐）
   ○ 结构优化
   ○ 频率+热化学
   ○ TD-DFT 激发态
   ○ GW-BSE 高精度激发态

   📋 分子结构
   ○ 我提供坐标或化学式
   ○ AI 帮我生成结构（推荐）

   📋 电荷与自旋
   ○ 中性闭壳层（电荷 0、单重态，推荐）
   ○ 我不确定，帮我判断

👤 选「单点能」「AI 生成」「中性闭壳层」

🤖 [已生成水分子结构，展示 XYZ 坐标确认]

🤖 [弹出面板 2/3]
   📋 计算方法
   ○ B3LYP-D3BJ / def2-SVP（推荐）— 定性趋势，秒级
   ○ PBE0-D3BJ / def2-TZVP — 定量对比，分钟级
   ○ XYG3 / def2-QZVPP — 发表级精度，小时级

   📋 计算资源
   ○ 笔记本 4-8 核，等几分钟
   ○ 工作站 16-32 核，等几小时
   ○ 集群，无所谓时间

👤 选「B3LYP-D3BJ / def2-SVP」「笔记本 4 核」

🤖 ═══════════════════════════════════
     AutoREST 方案确认
   ═══════════════════════════════════
     体系:         H₂O
     计算类型:     单点能
     方法:         B3LYP-D3BJ / def2-SVP
     电荷 / 自旋:  0 / 1
     线程:         4
     预估耗时:     < 1 分钟
   ═══════════════════════════════════

👤 确认

🤖 [生成 water_energy.in 文件]
```

### 示例 2：高精度激发态计算

```
👤 帮我算一下苯分子的单重态和三重态激发能，要高精度的

🤖 [面板 1] 确认计算类型、结构来源、电荷自旋
   → 用户选「GW-BSE」「AI 生成」「中性闭壳层」

🤖 [面板 2] 推荐 SCAN/cc-pVDZ → G₀W₀-BSE
   解释：这是 GW-BSE 工作流的验证起点，会自动先做 GW 再做 BSE

👤 确认

🤖 生成 benzene_bse_singlet.in + benzene_bse_triplet.in
   重要提示：三重态 BSE 的 `spin=1` 不变，用 `bse_spin="triplet"` 选择通道
   预估 ΔE_ST 约 1.14 eV（基于 SCAN/cc-pVDZ 黄金回归数据）
```

### 示例 3：命令行模式（不用 DSH）

```bash
git clone https://github.com/masterTHou/AutoREST.git
cd AutoREST
pip install -e .

# 生成水分子单点能输入卡
python -m autorest.cli run --molecule H2O --task energy \
  --functional b3lyp --basis def2-SVP

# 解析 REST 输出
python -m autorest.cli analyze h2o.out --qa

# 诊断失败原因
python -m autorest.cli diagnose failed.out
```

---

## 对两类用户的支持

### 对于计算化学研究者

你大概知道要用 B3LYP 还是 PBE0。AutoREST 不会在你面前班门弄斧——它提供候选方案，你来选；如果你有明确的偏好（"我就要用 M06-2X/def2-TZVPP"），直接告诉它，跳过推荐面板。

### 对于实验化学家 / 非计算专业

你不懂 DFT 也没关系。直接描述你想解决的问题：

> 「我想算一下这个钌催化剂对 C-H 键的活化能力」

AutoREST 会：
1. 用自己的知识判断这是一个过渡金属体系
2. 上网搜索类似体系的计算文献
3. 推荐 PBE0-D3BJ/def2-TZVP，并**用通俗语言**解释为什么选这个
4. 提醒过渡金属体系可能收敛困难，给出备选方案
5. 全程不让你填看不懂的技术参数

---

## 项目结构

```
AutoREST/
├── dsh-plugin-autorest/              # ⭐ DSH Cordis 插件——这是用户安装的东西
│   ├── package.json                  #    npm 包元数据 (dsh.bundle)
│   ├── cordis.patch.yml              #    Cordis 注册补丁
│   ├── lib/index.js                  #    插件入口（Tool 注册 + Bridge + Skill）
│   ├── resources/skill/              #    捆绑的 Skill 文件（self-contained）
│   │   ├── SKILL.md                  #    自适应 UX 指令
│   │   ├── references/               #    REST 手册 + GW-BSE 指南
│   │   └── scripts/                  #    Python 工具脚本
│   └── vendor/python/autorest/       #    捆绑的 Python 源码（self-contained）
│       ├── dsh_bridge.py             #    JSON bridge 入口
│       ├── input_generator.py        #    输入卡生成引擎
│       ├── output_parser.py          #    输出解析
│       ├── scientific_validator.py   #    科学验证
│       ├── gwbse_parser.py           #    GW-BSE 专用解析器
│       └── core/                     #    task_ir, diagnose, provenance, pipeline
├── autorest/                         # Python CLI 库（`pip install -e .`）
│   ├── dsh_bridge.py                 #    JSON bridge 入口
│   ├── bridge/                       #    协议定义
│   └── core/                         #    科学核心
├── skills/autorest/                  # Skill 源码（打包时同步到 plugin）
├── examples/                         # 入门示例
├── tests/                            # 测试套件 + fixtures
├── pyproject.toml                    # pip install 配置
├── AGENTS.md                         # 开发者指南
└── README.md                         # ← 本文件
```

### 代码统计

| 类型 | 文件数 | 行数 |
|------|--------|------|
| Python 核心（`autorest/`） | 19 | ~10,100 |
| Skill 脚本（`.dsh/.../scripts/`） | 17 | ~10,100 |
| 参考文档（`.dsh/.../references/`） | 3 | ~3,500 |
| 测试 | 2 | ~320 |
| 示例 | 3 | ~160 |
| **总计** | **~48** | **~19,500** |

---

## 开发相关

### 运行测试

```bash
# 不需要 REST 也能跑（使用真实输出 fixtures）
python -m unittest discover -s tests -v
```

### 打包 Release

```powershell
# 在项目根目录执行：把 skill 和 Python 源码同步到插件目录，然后打 .tgz
Copy-Item "skills\autorest\*" "dsh-plugin-autorest\resources\skill\" -Recurse -Force
Copy-Item "autorest\*" "dsh-plugin-autorest\vendor\python\autorest\" -Recurse -Force
tar -czf autorest-dsh-4.0.0.tgz -C dsh-plugin-autorest .
```

---

## 引用

- **REST 程序**: Z. Li, T. Gao, S. Wang, et al. *REST: Embracing the Rust Programming Language for Modern Electronic Structure Theory.* Chin. J. Chem. Phys. (2025). DOI: [10.1063/1674-0068/cjcp2510156](https://doi.org/10.1063/1674-0068/cjcp2510156)
- **GW-BSE in REST**: Q. Gao, I. Y. Zhang, X. Xu. *J. Chem. Phys.* **164**, 214116 (2026). DOI: [10.1063/5.0331920](https://doi.org/10.1063/5.0331920)
- **AIFS (上游参考)**: [https://github.com/SII-chenlz/Ai-DFT](https://github.com/SII-chenlz/Ai-DFT)

如果你在论文或报告中使用了 AutoREST 生成的输入卡，请引用 REST 程序本身（上方的第一篇文献）。

---

## License

MIT — 详见 [LICENSE](LICENSE) 文件。

---

**Made with ❤️ for AI for Science | 让量子化学计算在聊天里完成**