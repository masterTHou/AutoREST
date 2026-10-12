# AutoREST — 量子化学计算 DSH 智能助理

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![REST](https://img.shields.io/badge/REST-v2026-green)](https://gitee.com/restgroup)
[![DSH Skill](https://img.shields.io/badge/DSH-Skill-blue)](https://www.deepseek.com/)
[![Version](https://img.shields.io/badge/version-2.1.0-brightgreen)](https://github.com/masterTHou/AutoREST/releases)

> **在 DeepSeek Harness 里用聊天完成量子化学计算。**
>
> 你说「帮我算一个水分子的单点能」，它会弹出选择题面板，引导你一步步选出合适的计算方法和参数，最后自动生成 REST 可以运行的 TOML 输入文件。不需要你懂 DFT 泛函、基组、色散校正——AutoREST 会帮你选。

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

## 它能做什么

| 你说的 | AutoREST 自动生成的 |
|--------|-------------------|
| 「帮我算水分子的能量」 | 单点能输入卡 (`job_type = "energy"`) |
| 「优化苯的结构」 | 几何优化输入卡 (`job_type = "opt"`) |
| 「算一下这个分子的振动频率」 | 频率 + 热化学输入卡 (`[hessian]` + `[thermo]`) |
| 「算紫外吸收光谱」 | TD-DFT 激发态输入卡 (`[tddft]`) |
| 「要更高精度的激发态」 | G₀W₀-BSE 输入卡 (`[quasiparticle_methods]`) |
| 「单重态和三重态能差」 | BSE singlet + triplet 双卡 |

**所有生成的输入卡都是 REST 标准 TOML 格式**，包含正确的 `[ctrl]` 和 `[geom]` 区块，不会生成 JSON 或其他格式。

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

### 它是什么

AutoREST 是一个 **DSH Skill**——一份 Markdown 格式的指令文件，被 DeepSeek Harness 的 Skill 子系统自动发现和加载。它不是 Cordis 插件，不需要 TypeScript 编译，不需要 Python 后端服务。

```
你说 "帮我算水分子"
       ↓
DSH 的 Skill 子系统扫描项目目录
       ↓
发现 .dsh/skills/autorest/SKILL.md (rank 100，最高优先级)
       ↓
LLM 读取 SKILL.md 里的指令：弹面板 → 问参数 → 推荐方法 → 生成 TOML
       ↓
输出 REST 输入卡 (.in 文件)
```

### DSH 如何发现它

DSH 启动时按优先级扫描以下目录：

| 优先级 | 路径 | 说明 |
|--------|------|------|
| 100 | `<项目>/.dsh/skills/<name>/SKILL.md` | 项目专属，最高优先 |
| 200 | `<项目>/.agents/skills/<name>/SKILL.md` | 项目备用 |
| 400 | `~/.dsh/skills/<name>/SKILL.md` | 全局安装，所有项目可用 |

你把 `.dsh/skills/autorest/` 放到项目根目录下，重启 DSH，Skill 就生效了。不需要 `package.json`、不需要 Cordis patch、不需要任何编译步骤。

### 技术栈

| 组件 | 技术 |
|------|------|
| Skill 指令 | Markdown (`.dsh/skills/autorest/SKILL.md`) |
| 参考知识库 | Markdown + TXT (REST 手册、GW-BSE 指南、方法选择表) |
| Python 工具脚本 | Python 3.9+ (`input_generator.py`, `output_parser.py`, `gwbse_parser.py` 等) |
| 测试 | Python `unittest` + 真实 REST 输出 fixtures |

---

## 安装

### 方式一：下载 Release 压缩包（最简单）

1. 从 [Releases](https://github.com/masterTHou/AutoREST/releases) 下载 `autorest-skill-v2.1.0.zip`
2. 解压到你的 DSH 项目根目录——解压后应该出现 `你的项目/.dsh/skills/autorest/SKILL.md`
3. **完全退出 DSH 再重新打开**
4. 在聊天里说：「帮我算一个水分子的单点能」

### 方式二：克隆后运行安装脚本

```powershell
# Windows
git clone https://github.com/masterTHou/AutoREST.git
cd AutoREST
.\install.ps1   # 安装到当前目录的项目中

# 或指定目标目录
.\install.ps1 -TargetDir "D:\MyDSHProject"
```

```bash
# macOS / Linux
git clone https://github.com/masterTHou/AutoREST.git
cd AutoREST
bash install.sh          # 安装到当前目录
bash install.sh /path/to/project   # 安装到指定项目
```

### 方式三：全局安装（所有 DSH 项目都能用）

```powershell
# Windows PowerShell
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

### 验证安装

重启 DSH 后，在聊天框输入：

> 帮我算一个水分子的单点能

如果弹出了选择面板（而不是直接给你一段 TOML 或 JSON），说明安装成功。

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
├── .dsh/skills/autorest/        # ⭐ DSH Skill 核心——这是用户要的东西
│   ├── SKILL.md                 #    交互式面板指令（YAML frontmatter + Markdown）
│   ├── references/              #    知识库
│   │   ├── rest_readme.txt      #      REST 完整关键词手册 (1336 行)
│   │   ├── rest_guide.md        #      方法选择表 + 模板 + 工作流
│   │   └── gwbse_guide.md       #      GW-BSE 12 条铁律 + 6 分子回归数据
│   └── scripts/                 #    Python 工具脚本
│       ├── input_generator.py   #      REST TOML 输入卡生成引擎
│       ├── output_parser.py     #      REST 输出解析
│       ├── gwbse_parser.py      #      GW-BSE 专用解析器
│       ├── scientific_validator.py #   10 项科学验证检查
│       ├── diagnose.py          #      失败诊断 + 约束自动恢复
│       ├── provenance.py        #      溯源记录
│       └── ...
├── autorest/                    # Python CLI 库（`pip install -e .`）
│   ├── cli.py                   #    命令行入口
│   └── core/                    #    task_ir, pipeline, verify, report...
├── examples/                    # 入门示例
│   ├── water_energy.py          #    H₂O 单点能
│   ├── water_gwbse.py           #    H₂O GW-BSE
│   └── acetone_workflow.py      #    丙酮多步骤工作流
├── tests/                       # 测试套件
│   ├── test_parser.py           #    解析器回归测试
│   ├── test_integration.py      #    集成测试
│   └── fixtures/                #    真实 REST 输出样本
├── install.ps1                  # Windows 安装脚本
├── install.sh                   # macOS/Linux 安装脚本
├── release.ps1                  # Release 打包脚本
├── pyproject.toml               # pip install 配置
├── AGENTS.md                    # 开发者指南
└── README.md                    # ← 本文件
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
.\release.ps1 -Version "2.1.1"
# 生成 autorest-skill-v2.1.1.zip
```

### 修改 Skill 指令

编辑 `.dsh/skills/autorest/SKILL.md`，重启 DSH 后生效。不需要编译。

### 添加新的计算方法

编辑 `.dsh/skills/autorest/references/rest_guide.md` 中的方法推荐表。

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