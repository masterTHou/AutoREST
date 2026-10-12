# AutoREST 完整指南

> **从自然语言科学问题到自动化 REST 电子结构计算**

---

## 一、核心设计理念

AutoREST 将电子结构计算拆解为 **五个独立阶段**，每阶段之间通过标准化接口衔接：

```
科学问题 ─→ 任务规划 ─→ 输入卡生成 ─→ 执行监控 ─→ 输出解析 ─→ 科学验证 ─→ 结果交付
   │            │            │           │           │           │
   │      化学知识库     REST手册     REST CLI    正则 + 解析器   物理检查
   │      方法证据      模板引擎     conda环境    GW-BSE解析    失败恢复
```

### 设计原则

1. **不猜测电荷/自旋**：必须由用户确认或在 notes 中明确记录假设
2. **基态自旋 ≠ BSE 激发态自旋**：对闭壳层单重态参考态，`spin=1` 始终保持，`bse_spin="triplet"` 选择三重态激发通道
3. **REST 关键词拼写随版本变化**：不静默修改（`ri_v` vs `ri-v`）
4. **区分"工作流成功"和"科学收敛"**：`Mission accomplished` 不等于结果已收敛
5. **保存失败轨迹作为训练数据**：失败的"知识轨迹"恢复路径是有价值的

---

## 二、支持的 REST 计算类型

### 2.1 基态计算

| 任务类型 | `job_type` | 说明 |
|---------|-----------|------|
| 单点能 | `energy` | SCF 单点能量计算 |
| 结构优化 | `opt` | 基于数值力的几何优化 |
| 受力计算 | `force` | 当前结构下的原子受力 |
| 数值偶极 | `numerical dipole` | 数值偶极矩计算 |

### 2.2 振动与热化学

| 任务类型 | 配置区块 | 说明 |
|---------|---------|------|
| 解析 Hessian | `[hessian]` | 解析二阶导数 |
| 频率计算 | `[hessian] frequencies = true` | 振动频率与简正模式 |
| 热化学分析 | `[thermo]` | ZPE、U、H、G、S、CV |

热化学区块的关键词：
- `temperature`: 温度 (K)，默认 298.15
- `pressure`: 压强 (atm)，默认 1.0
- `symmetry_number`: 转动对称数 σ，0=自动识别
- `electronic_energy`: 更高级别单点能（可选）
- `ilowfreq`: 低频处理模型 (0=RRHO, 1=Truhlar, 2=Grimme, 3=Minenkov)

### 2.3 激发态：TD-DFT

```toml
[tddft]
tddft_method = "tda"       # 或 "lr" (完整线性响应)
tddft_spin = "singlet"     # 或 "triplet" / "both"
nroots = 6
tddft_cutoff_energy = 100.0
```

### 2.4 激发态：GW-BSE

GW-BSE 是 REST 的高精度激发态方法，通过 `[quasiparticle_methods]` 区块配置。

数据流：
```
SCF/DFT → GW 准粒子能量 → BSE 电子-空穴 Hamiltonian → 中性激发能
```

**重要**：G₀W₀ 具有 starting-point dependence。SCAN 是已验证起点，但不是唯一正确起点。

---

## 三、DFT 方法选择指南

### 3.1 方法层次

| 层次 | 类型 | 代表性方法 | 适用场景 |
|------|------|-----------|---------|
| 1 | LDA | LDA | 基本不用 |
| 2 | GGA | BLYP, PBE | 快速预筛 |
| 3 | meta-GGA | SCAN, TPSS, M06-L | 平衡精度/成本 |
| 4 | Hybrid GGA | B3LYP, PBE0, X3LYP | 主流热化学 |
| 5 | Hybrid meta-GGA | M06-2X, SCAN0, MN15 | 动力学/热化学 |
| 6 | Double-Hybrid | XYG3, XYGJOS, xDH-PBE0 | 高精度能量 |
| 7 | RPA | RPA@PBE, scsRPA | 非共价相互作用 |

### 3.2 经验色散校正

- D3/D3BJ/D4 适用于：LDA、GGA、Hybrid GGA、Hybrid meta-GGA
- **不适用于**：双杂化 (XYG3 系列)、RPA 方法
- 声明方式：`empirical_dispersion = "d3bj"`（独立关键词，不附加到 xc 名称后）

### 3.3 基组选择

| 精度级别 | 推荐基组 |
|---------|---------|
| 快速扫描 | def2-SVP |
| 标准计算 | def2-TZVP / cc-pVTZ |
| 高精度 | def2-QZVPP / cc-pVQZ |
| 后自洽场 | def2-QZVPP (REST 默认) |

- 辅助基组 (auxbas) 默认：`def2-universal-jkfit`
- Rydberg/CT 态需要 diffuse/augmented basis

---

## 四、SCF 收敛策略

### 4.1 收敛问题诊断

| 症状 | 可能原因 | 建议方案 |
|------|---------|---------|
| 能量振荡 | DIIS 子空间不稳定 | 切换到 `ediis+diis` |
| 近简并振荡 | 前线轨道简并 | `level_shift = 0.1`（0.1 Ha） |
| 收敛极慢 | 小 HOMO-LUMO gap | `smear = "fermi"`, `smear_sigma = 0.05` |
| 一直不收敛 | 糟糕的初始猜测 | `initial_guess = "vsap"` |

### 4.2 收敛器选项

```toml
mixer = "diis"            # 默认（快速）
mixer = "ediis+diis"      # 稳定性更好，速度不减
mixer = "adiis+diis"      # 数值更鲁棒
level_shift = 0.1         # 单位 Hartree，破坏简并
smear = "fermi"           # 分数占据加速
smear_sigma = 0.05        # 展宽参数
smear_anneal = true       # 退火收敛
```

---

## 五、输入卡模板

### 5.1 单点能计算

```toml
[ctrl]
num_threads = 10
print_level = 1
job_type = "energy"
xc = "b3lyp"
empirical_dispersion = "d3bj"
basis_path = "def2-SVP"
auxbas_path = "def2-SVP-ri"
eri_type = "ri-v"
charge = 0.0
spin = 1
spin_polarization = false

[geom]
name = "MOLECULE"
unit = "angstrom"
position = """
  Element x y z
  ...
"""
```

### 5.2 结构优化

```toml
[ctrl]
job_type = "opt"
opt_engine = "geometric-pyo3"
# ... 其余同单点能

[geometric_pyo3]
maxiter = 300
converge_energy = 1.0e-6
converge_grms = 3.0e-4
```

### 5.3 GW-BSE

```toml
[ctrl]
xc = "scan"
basis_path = "cc-pVDZ"
auxbas_path = "def2-SV(P)-JKFIT"
eri_type = "ri-v"
use_ri_symm = true
charge = 0.0
spin = 1
spin_polarization = false

[quasiparticle_methods]
gw_or_bse = "bse"
gw_scheme = "extrapolated"
use_low_rank_contour = true
bse_spin = "singlet"        # 或 "triplet"
bse_tda = true
bse_davidson_solver = true
davidson_target_excitations = 5
davidson_maximum_subspace_size = 50
davidson_restart_dimensions = 10
```

---

## 六、GW-BSE 特殊注意事项

### 6.1 铁律

1. **三线态 BSE 不改变 `spin=1`**：对闭壳层单重态参考态，`spin=1, spin_polarization=false` 始终保持，`bse_spin="triplet"` 选择激发通道
2. **HOMO/LUMO 靠 `Fermi Surface` 分界线判断，不靠 QP 能量正负号**
3. **REST 轨道编号是 0-based**
4. **三线态 oscillator strength = 0 是正常现象**（在闭壳层无 SOC 自旋适配 BSE 中）
5. **`First 0 excitations` 是 Davidson 收敛失败，不是"无激发态"**

### 6.2 Davidson 收敛故障修复顺序

1. 保持 `spin=1` 不变
2. 增加 `davidson_target_excitations`
3. 增加 `davidson_maximum_subspace_size`
4. 增加 `davidson_restart_dimensions`
5. 检查 residual/restart 轨迹
6. 检查 GW QP warning
7. 检查 BSE cutoff / virtual space

### 6.3 6分子回归测试集 (Golden Regression)

| 分子 | AO | QP Gap (eV) | S1 (eV) | T1 (eV) | ΔE_ST (eV) | 最亮单重态 |
|------|-----|-------------|---------|---------|------------|-----------|
| H₂O | 24 | 16.1099 | 6.9549 | 6.1395 | 0.8154 | S3 @ 10.0710 |
| NH₃ | 29 | 14.5961 | 7.0365 | 6.1442 | 0.8923 | S5 @ 12.1289 |
| CH₃COCH₃ | 86 | 10.8984 | 3.3838 | 2.7121 | 0.6718 | S2 @ 5.6305 |
| C₆H₆ | 114 | 10.6339 | 4.7204 | 3.5802 | 1.1402 | S4 @ 7.1321 |
| PNA | 170 | 9.4950 | 2.5759 | 1.9275 | 0.6484 | S5 @ 4.6009 |
| Coumarin | 184 | 7.7742 | 3.3055 | 2.1554 | 1.1501 | S4 @ 4.1483 |

---

## 七、科学验证清单

每次计算完成后，自动执行以下检查：

| 检查项 | 通过条件 | 严重程度 |
|--------|---------|---------|
| SCF 收敛 | `SCF is converged` | ERROR (不通过则计算无效) |
| 任务完成 | `REST: Mission accomplished` | WARNING |
| 能量合理性 | 中性分子能量 < 0, 非 NaN | ERROR |
| 虚频检查 | 无虚频 (< -50 cm⁻¹) 或合理数量 | WARNING |
| 自旋污染 (UHF) | <S²> 偏差 < 10% | WARNING |
| 轨道占据 | HOMO < Fermi < LUMO | ERROR |
| BSE 类型匹配 | 输出 BSE type == 输入 bse_spin | ERROR |
| Davidson 收敛 | 获得根数 == 请求根数 | WARNING |
| QP warning | 无关键轨道上的 Newton warning | INFO |

---

## 八、命令行接口

```bash
# 单点能计算
python -m autorest --task energy --functional b3lyp --basis def2-SVP \
  --geometry water.xyz --charge 0 --spin 1

# 结构优化 + 频率
python -m autorest --task optimization --functional pbe0 --basis cc-pVTZ \
  --geometry mol.xyz --charge 0 --spin 1 --freq

# GW-BSE (单重态 + 三重态)
python -m autorest --task gwbse --functional scan --basis cc-pVDZ \
  --geometry mol.xyz --charge 0 --spin 1 --bse-roots 5

# 仅生成输入卡（不执行）
python -m autorest --task energy --functional b3lyp --basis def2-SVP \
  --geometry water.xyz --charge 0 --spin 1 --dry-run --output card.in
```

---

## 九、配置参考

```toml
# autorest_config.toml
[rest]
conda_env = "rest"
executable = ""              # 留空 = 自动从 conda 环境检测
num_threads = 4
max_memory_mb = 4000

[output]
default_dir = "./calc"
save_cards = true
save_logs = true

[validation]
check_scf = true
check_stability = false
check_frequencies = true
frequency_threshold_cm1 = -50.0

[gwbse]
default_functional = "scan"
default_basis = "cc-pVDZ"
default_auxbas = "def2-SV(P)-JKFIT"
default_n_roots = 5
davidson_max_subspace = 50
davidson_restart = 10
use_low_rank_contour = true
```

---

## 十、与 DSH 的集成

### 作为 DSH Skill 使用

将 `SKILL.md` 放置在 DSH Skill 目录中，DSH 会自动加载。当用户请求涉及 REST 计算时，Agent 会：
1. 加载本指南 (`references/auto_rest_guide.md`)
2. 按需加载 GW-BSE 伴侣 (`references/rest_gwbse_skill_guide.md`)
3. 调用 Python 脚本生成输入卡 / 执行 / 解析
4. 进行科学验证并交付结果

### 离线使用（无 DSH）

所有 Python 模块都可以独立使用（通过 CLI 或 Python API），不依赖 DSH 服务。
只需安装 REST 和 Python 3.9+。

---

**AutoREST v1.0 | AI for Science | 让量子化学计算真正自动化**