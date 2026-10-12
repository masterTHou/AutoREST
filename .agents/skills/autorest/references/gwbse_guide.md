# REST GW–BSE 激发态计算：Skill / Agent 集成指南与六分子验证案例

> **定位**：这是一份可以直接放入 Skill `references/` 目录的知识与操作手册。它面向需要让 Agent 具备 REST 中 GW、G₀W₀–BSE、singlet/triplet 激发态输入生成、运行检查、结果解析、收敛诊断与回归验证能力的场景。  
> **验证基础**：本文 6 个分子、12 个 BSE 输入（6 singlet + 6 triplet）均来自同一批已经实际跑通的任务。  
> **核心原则**：把“本批实跑事实”“REST 当前文档定义”“GW–BSE 通用理论”“Agent 工程建议”严格区分，防止 Agent 把某个案例参数误当成普适定律。

---

## 目录

1. [给 Agent 的十二条硬规则](#1-给-agent-的十二条硬规则)
2. [信息可信度标签](#2-信息可信度标签)
3. [GW–BSE 激发态方法简介](#3-gwbse-激发态方法简介)
4. [从 SCF 到 G₀W₀ 再到 BSE 的数据流](#4-从-scf-到-gw-再到-bse-的数据流)
5. [为什么选择这 6 个分子](#5-为什么选择这-6-个分子)
6. [本批已验证结果：Golden Regression](#6-本批已验证结果golden-regression)
7. [统一输入设计](#7-统一输入设计)
8. [`[ctrl]` 参数字典](#8-ctrl-参数字典)
9. [`[quasiparticle_methods]` 参数字典](#9-quasiparticle_methods-参数字典)
10. [如何根据体系自动选择参数](#10-如何根据体系自动选择参数)
11. [六个分子的精确已验证输入](#11-六个分子的精确已验证输入)
12. [六个案例分别在测试什么](#12-六个案例分别在测试什么)
13. [如何解析 REST GW–BSE 输出](#13-如何解析-rest-gwbse-输出)
14. [Davidson 收敛与 C₆H₆ triplet 故障案例](#14-davidson-收敛与-c₆h₆-triplet-故障案例)
15. [科研级收敛测试](#15-科研级收敛测试)
16. [Rydberg、CT、暗态、亮态、triplet 的特殊处理](#16-rydbergct暗态亮态triplet-的特殊处理)
17. [常见错误与自动诊断规则](#17-常见错误与自动诊断规则)
18. [Agent 端到端工作流](#18-agent-端到端工作流)
19. [推荐结果数据结构](#19-推荐结果数据结构)
20. [建议的自动 QA / 回归判据](#20-建议的自动-qa--回归判据)
21. [尚未由这批数据验证的范围](#21-尚未由这批数据验证的范围)
22. [REST 版本兼容策略](#22-rest-版本兼容策略)
23. [如何并入 Skill](#23-如何并入-skill)
24. [可直接复制进 `SKILL.md` 的控制规则](#24-可直接复制进-skillmd-的控制规则)
25. [推荐的 Agent 输出模板](#25-推荐的-agent-输出模板)
26. [参考资料](#26-参考资料)
27. [最终定位](#27-最终定位)

---

## 1. 给 Agent 的十二条硬规则

1. **把基态自旋与 BSE 激发态自旋分开。**  
   对本文 6 个中性闭壳层分子，ground-state reference 一直是：
   ```toml
   charge = 0.0
   spin = 1.0
   spin_polarization = false
   ```
   triplet excitation 由：
   ```toml
   bse_spin = "triplet"
   ```
   控制。**绝不能因为用户要 triplet 激发态就自动把 `spin` 改成 3。**

2. **BSE 不是“DFT 轨道差换个名字”。**  
   本工作流是 `SCF/DFT → GW quasiparticle energies → BSE electron–hole problem → neutral excitations`。

3. **`gw_scheme = "extrapolated"` 的 `threshold` 是 GW 显式 QP 计算的能量窗口，不是 Davidson 收敛阈值。**

4. **`bse_tda = true` 表示 Tamm–Dancoff approximation。**  
   本文 12 个金标准任务全部使用 TDA。切到 full BSE 后不能继续把本文数值当作严格回归目标。

5. **数值不收敛时先调整 solver，再改变物理模型。**  
   优先检查：root 数 → Davidson 子空间 → restart → QP warning → BSE 截断/轨道空间。不要第一步就改自旋或几何。

6. **HOMO/LUMO 必须以 REST 输出中的 `Fermi Surface` 标记为界，不要按 QP 能量正负号猜。**  
   coumarin 的 LUMO QP 能量在当前能量零点下仍可为负；用正负号切 HOMO/LUMO 会错。

7. **REST 输出的 MO index 是 0-based。**  
   不要在内部解析时偷偷 `+1`，除非面向用户显示时明确注明转换。

8. **triplet oscillator strength = 0 在本文无 SOC、闭壳层自旋适配工作流里是正常现象，不等于失败。**

9. **`Mission accomplished` 不是唯一成功标准。**  
   同时检查 SCF、GW、BSE 类型、请求 root 数、Davidson 收敛、warning 和输出是否截断。

10. **“跑通”与“科研级收敛”是两件事。**  
    `SCAN/cc-pVDZ` 很适合回归；Rydberg 和 CT 定量计算通常需要 diffuse/basis/starting-point 等额外收敛测试。

11. **记录 REST 版本。**  
    GW/BSE、UBSE、Davidson、非 TDA 求解器和频率积分实现仍在演进。升级后应先跑 H₂O/NH₃ 小体系回归。

12. **把本文 12 个输入视为 golden regression，不要把每个数值参数视为“所有体系的最佳参数”。**

---

## 2. 信息可信度标签

本文使用四类标签：

- **[VERIFIED-RUN]**：来自当前 6 分子、12 个实际完成输出，可直接作为回归基线。
- **[REST-DOC]**：来自 REST 当前在线文档/项目说明；换版本时需要重新核对。
- **[MBPT-THEORY]**：GW/BSE 多体微扰理论的通用内容。
- **[RECOMMENDATION]**：为 Agent 稳健自动化给出的工程建议，不是 REST 的硬编码要求。

这四类信息不要混用。例如：

- “C₆H₆ triplet 用 `10/60/15` 跑通”是 **[VERIFIED-RUN]**；
- “因此所有 triplet 都必须用 `10/60/15`”是错误泛化；
- “新版 REST 的 Davidson 默认值”属于 **[REST-DOC]**，不应反向覆盖旧回归文件。

---

## 3. GW–BSE 激发态方法简介

### 3.1 为什么不只看 KS-DFT 轨道能量？

Kohn–Sham DFT 首先是基态理论。KS 轨道和本征值是构造基态密度的重要中间量，但一般不能把任意 KS 能级差直接当成实验可观测的带电准粒子能量或中性光学激发能。

GW 和 BSE 分别处理两个层次：

- **GW**：改进电子添加/移除的单粒子准粒子能量；
- **BSE**：在准粒子基础上显式处理电子–空穴相互作用，得到中性激发。

### 3.2 GW：准粒子修正

**[MBPT-THEORY]** GW 自能最常见的紧凑表达为：

\[
\Sigma = iGW
\]

其中：

- \(G\)：单粒子 Green's function；
- \(W=\epsilon^{-1}v\)：屏蔽 Coulomb 相互作用；
- \(v\)：裸 Coulomb 相互作用；
- \(\epsilon\)：介电响应。

准粒子能量的概念式：

\[
E_n^{QP}
=
\varepsilon_n^{KS}
+
\langle\psi_n|
\Sigma(E_n^{QP})-V_{xc}
|\psi_n\rangle.
\]

本文使用的是 one-shot 型工作流：从选定的 DFT/SCF 起点构造 \(G_0\) 与 \(W_0\)，进行 G₀W₀ 准粒子修正。

**关键影响**：G₀W₀ 具有 starting-point dependence。  
因此 `xc = "scan"` 是本文统一的已验证起点，不是 GW 理论规定的唯一泛函。

### 3.3 BSE：电子–空穴中性激发

GW 得到的是“带电准粒子”层面的能量；光吸收则是保持体系总电荷不变的中性激发。BSE 在 particle–hole 组态空间建立有效电子–空穴 Hamiltonian：

\[
H^{BSE}=D^{QP}+K^{eh},
\]

其中：

- \(D^{QP}\) 的对角成分主要来自 \(E_a^{QP}-E_i^{QP}\)；
- \(K^{eh}\) 是 electron–hole kernel；
- 解本征问题得到 \(\Omega_S\)，即中性激发能。

因此通常：

\[
E_{\mathrm{QP\ gap}}\neq E_{S_1}.
\]

`QP gap - optical gap` 能直观反映 electron–hole attraction 的量级，但对于有限分子，Agent 不应在没有定义和边界条件的情况下把它机械地称为唯一严格的“exciton binding energy”。

### 3.4 BSE 的 resonant / anti-resonant 结构与 TDA

完整 BSE 含 resonant、anti-resonant 以及二者耦合的块结构。Tamm–Dancoff approximation 忽略 resonant–anti-resonant coupling，只求 resonant block：

\[
H^{BSE,TDA}X=\Omega X.
\]

本文全部验证任务：

```toml
bse_tda = true
```

优点：

- 问题更简单；
- 更适合求少量低根；
- 通常更稳健；
- Davidson 实现更直接。

代价：

- 忽略 resonant/anti-resonant coupling；
- 对某些体系或高精度目标，full BSE 可能产生可见差异。

所以“full BSE”不是无条件更好，“TDA”也不是无条件足够；必须以目标与收敛验证为准。

### 3.5 singlet / triplet BSE

对于 closed-shell singlet reference，可在 spin-adapted electron–hole space 中分别构造 singlet 和 triplet 激发通道。

本文实际输出给出一个非常有用的程序级特征：

- singlet BSE 中有 screened interaction 和 Coulomb/exchange-like 操作；
- triplet BSE 中本批输出的 Coulomb operator 调用为 0；
- 本批 triplet oscillator strength 均为 0。

这和无 SOC 条件下 spin-forbidden triplet 光跃迁的预期是一致的。

**Agent 必须区分：**

```text
spin              = ground-state SCF multiplicity
bse_spin          = target BSE excitation spin channel
```

### 3.6 Davidson 为什么适合 BSE？

BSE particle–hole 维度粗略随：

\[
N_{\mathrm{occ}}\times N_{\mathrm{virt}}
\]

增长。若只需要最低 5–10 个激发根，完整对角化整个矩阵通常浪费内存与计算。Davidson 利用迭代子空间逐步逼近所需低根，因此非常适合这种“大矩阵、少量本征对”的场景。

Agent 需要监控的不是“有没有 Davidson 这个词”，而是：

- residual 是否下降；
- search space 是否持续膨胀；
- 是否 restart；
- 请求的 roots 是否全部返回；
- 近简并根是否发生 root swapping；
- 最终 residual 与能量变化是否达到当前版本的收敛标准。

---

## 4. 从 SCF 到 GW 再到 BSE 的数据流

```text
Geometry
  │
  ├── charge / ground-state multiplicity
  │
  ▼
SCF / DFT reference
  │
  ├── KS orbitals
  ├── KS eigenvalues
  ├── density
  └── RI tensors / response ingredients
  │
  ▼
G0W0
  │
  ├── explicit QP solutions near Fermi
  ├── extrapolated QP corrections for remaining orbitals
  └── QP HOMO / LUMO / gap
  │
  ▼
BSE electron-hole Hamiltonian
  │
  ├── singlet OR triplet channel
  ├── TDA in this regression suite
  └── occupied→virtual configuration space
  │
  ▼
Davidson eigensolver
  │
  ├── excitation energies
  ├── residuals
  ├── transition amplitudes
  └── eigenvectors
  │
  ▼
Spectroscopic / analysis layer
  ├── S1 / T1
  ├── ΔEST = S1 - T1
  ├── oscillator strength
  ├── transition dipole
  ├── brightest state
  ├── dominant orbital transitions
  └── simulated absorption spectrum
```

### 4.1 这里“激发态”是什么？

本文是在**同一个固定 ground-state geometry**上求 vertical electronic excitation。

因此输出的 BSE 激发能不要自动解释成：

- 0–0 energy；
- adiabatic excitation energy；
- emission maximum；
- 含振动结构的 vibronic peak；
- 溶液相吸收峰。

若用户要这些量，需要进一步做 excited-state geometry、zero-point correction、solvent/environment、vibronic/SOC 等额外处理。

---

## 5. 为什么选择这 6 个分子？

| 分子 | 主要角色 | Skill 中的价值 |
|---|---|---|
| H₂O | 小体系 / Rydberg 敏感 | 极快 smoke test；同时提醒 diffuse basis 重要性 |
| NH₃ | 小型闭壳层回归 | 第二个独立的 SCF→GW→BSE 快速验证点 |
| CH₃COCH₃ | n→π* | 检查低能暗态、亮态、主组态与 singlet/triplet 差异 |
| C₆H₆ | 高对称 π→π* | 近简并 roots、Davidson root tracking 与 solver stress test |
| PNA | push–pull CT | 检查 CT、starting point、diffuse basis 和环境敏感性 |
| coumarin | 较大共轭发色团 | 本集合最大 AO 规模，兼顾真实光学体系与性能增长 |

### 5.1 这 6 个分子不是“随机示例”

建议把它们定义为三级 regression suite：

```text
Tier 1 — installation / smoke
  H2O
  NH3

Tier 2 — electronic-character coverage
  CH3COCH3       n→π*
  C6H6           π→π*, high symmetry / near degeneracy
  PNA            charge transfer

Tier 3 — size / performance / realistic chromophore
  coumarin
```

这样 Agent 可以根据任务目的选择测试深度，而不是每次安装都先跑最大体系。

---

## 6. 本批已验证结果：Golden Regression

> **[VERIFIED-RUN]** 以下是当前 12 个已完成任务的计算回归指纹。它们用于验证“相同或兼容 REST 构建 + 相同输入”是否保持一致，不等于实验基准值，也不代表已经达到 basis-set limit。

| Molecule | Atoms | AO | QP gap (eV) | S1 (eV) | T1 (eV) | ΔE_ST (eV) | Brightest singlet | f_max | Time S/T (s) |
|---|---:|---:|---:|---:|---:|---:|---|---:|---:|
| H₂O | 3 | 24 | 16.1099 | 6.9549 | 6.1395 | 0.8154 | S3 @ 10.0710 eV | 0.074004 | 0.460/0.266 |
| NH₃ | 4 | 29 | 14.5961 | 7.0365 | 6.1442 | 0.8923 | S5 @ 12.1289 eV | 0.229809 | 0.342/0.343 |
| CH₃COCH₃ (acetone) | 10 | 86 | 10.8984 | 3.3838 | 2.7121 | 0.6718 | S2 @ 5.6305 eV | 0.023382 | 5.379/5.275 |
| C₆H₆ (benzene) | 12 | 114 | 10.6339 | 4.7204 | 3.5802 | 1.1402 | S4 @ 7.1321 eV | 0.751110 | 20.481/23.614 |
| p-nitroaniline (PNA) | 16 | 170 | 9.4950 | 2.5759 | 1.9275 | 0.6484 | S5 @ 4.6009 eV | 0.003012 | 80.728/76.330 |
| coumarin | 17 | 184 | 7.7742 | 3.3055 | 2.1554 | 1.1501 | S4 @ 4.1483 eV | 0.124942 | 88.797/85.788 |

### 6.1 数据集级回归指纹

- Molecules: **6**
- Runs: **12**
- Successful runs: **12/12**
- Parsed excited states: **65**
- Mean \(\Delta E_{ST}\): **0.8864 eV**
- C₆H₆ triplet: **10 roots**
- 其余任务：**5 roots**
- 所有任务均有 `REST: Mission accomplished`
- 所有任务均完成 SCF、GW 和目标 BSE 通道
- C₆H₆ 的 GW 在 orbital #23 附近出现 Newton solver warning，但任务仍完成；warning 应保留到 QA 报告中，而不是静默丢弃

若同时配套使用本项目的统计脚本，还可把 QP 轨道表、transition amplitudes、Mulliken charge、SCF/Davidson iteration、operator timing 等全部纳入回归。

### 6.2 为什么不能按 QP 能量正负号找 HOMO/LUMO？

REST 输出中有明确分界：

```text
-------Fermi Surface--------
```

解析规则必须是：

```text
HOMO = Fermi Surface 之前最后一个 QP orbital
LUMO = Fermi Surface 之后第一个 QP orbital
```

不要写：

```text
HOMO = highest QP energy < 0
LUMO = lowest QP energy > 0
```

因为能量零点不保证刚好位于 HOMO/LUMO 之间；coumarin 就是很好的反例。

---

## 7. 统一输入设计

本批 12 个成功任务的共同基线：

```toml
[ctrl]
print_level = 1
num_threads = 30
xc = "scan"
basis_path = "cc-pVDZ"
auxbas_path = "def2-SV(P)-JKFIT"
eri_type = "ri_v"
use_ri_symm = true
charge = 0.0
spin = 1.0
spin_polarization = false

[quasiparticle_methods]
gw_or_bse = "bse"
gw_scheme = "extrapolated"
use_low_rank_contour = true
bse_spin = "singlet"           # triplet 卡改为 "triplet"
bse_tda = true
bse_davidson_solver = true
davidson_target_excitations = 5
davidson_maximum_subspace_size = 50
davidson_restart_dimensions = 10
```

唯一明显的 solver 特例是 C₆H₆ triplet：

```toml
[quasiparticle_methods]
gw_or_bse = "bse"
gw_scheme = "extrapolated"
bse_spin = "triplet"
bse_tda = true
bse_davidson_solver = true
davidson_target_excitations = 10
davidson_maximum_subspace_size = 60
davidson_restart_dimensions = 15
```

其成功文件没有显式写 `use_low_rank_contour = true`。  
**严格复现这次回归时应保持文件原样；但不能据此得出“benzene triplet 必须关闭 low-rank contour”的因果结论。**

---

## 8. `[ctrl]` 参数字典

### 8.1 总览表

| 参数 | 本批值 | 作用 | 如何设置 | Agent 警告 |
|---|---|---|---|---|
| `print_level` | `1` | 输出详细程度 | 正常回归用 1 | 太低会损害自动 QA |
| `num_threads` | `30` | CPU 并行线程 | 按实际调度资源 | 不是物理参数，不要硬编码 30 |
| `xc` | `"scan"` | DFT/SCF 起点 | 回归保持；科研可做起点敏感性 | G₀W₀ 有 starting-point dependence |
| `basis_path` | `"cc-pVDZ"` | 主 AO 基组 | 回归方便；科研做基组收敛 | Rydberg/CT 常需要 diffuse |
| `auxbas_path` | `"def2-SV(P)-JKFIT"` | RI 辅助基组 | 精确复现保持 | 与 cc-pVDZ 不是天然同系列匹配 |
| `eri_type` | `"ri_v"` | RI-V / DF 积分路径 | 以安装版本语法为准 | 当前文档也常写 `"ri-v"` |
| `use_ri_symm` | `true` | RI 对称/存储优化路径 | 通常保持 | 不等于点群约束 |
| `charge` | `0.0` | 总电荷 | 按真实体系 | 不要根据“常见分子”盲猜 |
| `spin` | `1.0` | ground-state multiplicity | 闭壳层 singlet = 1 | **不是 BSE triplet 开关** |
| `spin_polarization` | `false` | restricted/unpolarized reference | 闭壳层 false | triplet BSE 不要求改 true |

### 8.2 `print_level = 1`

**[VERIFIED-RUN]** 当前输出已经足够包含：

- 输入回显；
- basis / aux basis 信息；
- SCF convergence；
- QP energy；
- Fermi surface；
- GW warning；
- BSE type；
- Davidson iteration；
- excitation energy；
- oscillator strength；
- dominant transitions；
- timing；
- mission status。

**[RECOMMENDATION]**

- 正常生产与回归：1；
- 数值故障排查：按 REST 版本提高；
- 不建议 Agent 默认用极低日志等级，否则后续无法判断任务到底在哪一步失败。

### 8.3 `num_threads = 30`

这只反映当前服务器资源配置。

Agent 应：

1. 从作业调度器/用户输入读取核数；
2. 不知道时采用保守值并提示；
3. 避免在同一节点启动多个“每个都占满全核”的任务；
4. 不把线程数变化解释成物理方法变化。

### 8.4 `xc = "scan"`

SCAN 是 meta-GGA。这里它的角色是**产生 ground-state starting point**。

**为什么这批用 SCAN：**

- 6 个体系统一；
- 已实跑验证；
- 便于把差异归因于分子/激发通道，而不是起点混用。

**科研计算需要知道：**

G₀W₀ 结果依赖 DFT starting point，所以：

```text
SCAN result ≠ PBE result ≠ hybrid-starting-point result
```

如果用户目标是定量论文结论，Agent 应建议至少做起点敏感性，而不是把 SCAN 宣称为“GW-BSE 唯一正确起点”。

### 8.5 `basis_path = "cc-pVDZ"`

本批 AO 数从 H₂O 的 24 到 coumarin 的 184，说明它很适合构造低成本到中等规模的统一 regression suite。

但：

- H₂O 低激发可能含 Rydberg 成分；
- PNA 低激发可能含显著 CT 成分；
- Rydberg/CT 对空间延展性敏感；
- 非增强型 double-zeta 不应被当作这些态的最终基组极限。

**Agent 策略：**

```text
workflow/regression:
    cc-pVDZ

quantitative excitation:
    test double-zeta → triple-zeta

Rydberg / CT:
    additionally test diffuse / augmented basis
```

### 8.6 `auxbas_path = "def2-SV(P)-JKFIT"`

这是一套 RI/JK fitting 辅助基组。当前输入与主基组是“已经实跑可用”的组合。

但需区分：

- **复现要求**：保持；
- **理论匹配最优性**：当前数据并没有证明它是 cc-pVDZ 的唯一/最优辅助基组。

REST 当前文档中的默认辅助基组选项已经与这批旧回归文件不同，因此 Agent 升级版本时不能无声替换后再宣称“同一个输入”。

### 8.7 `eri_type = "ri_v"`

RI-V / density fitting 用辅助基展开 Coulomb 相关张量，显著降低四中心积分与后续 GW/BSE 的成本。

**版本注意**：

- 本批成功卡：`"ri_v"`
- 当前文档中常见：`"ri-v"`

因此 Skill 应把“REST keyword/value spelling is version-sensitive”作为规则，而不是擅自格式化。

### 8.8 `use_ri_symm = true`

这是 RI 数据结构/对称相关的实现优化。

不要把它解释成：

```text
“自动把分子强制到某点群”
```

也不要把它当成 benzene Davidson 近简并问题的直接控制旋钮。

### 8.9 `charge`

本批全部中性：

```toml
charge = 0.0
```

新体系必须从真实化学组成决定。

Agent 在自动生成输入前至少应检查：

- 总电子数；
- charge；
- multiplicity 的奇偶兼容性；
- 用户是否提供离子态。

若 charge/multiplicity 不确定，不要静默猜。

### 8.10 `spin`

**[REST-DOC]** `spin` 表示 ground-state multiplicity \(2S+1\)。

闭壳层 singlet：

\[
S=0,\quad 2S+1=1.
\]

所以本文所有 singlet BSE 与 triplet BSE 的 ground-state reference 都是：

```toml
spin = 1.0
```

当前文档把它描述成整数语义；本文回归构建接受 `1.0`。对**新版本新卡片**可优先使用 `spin = 1`，但对 golden files 不要改写。

### 8.11 `spin_polarization = false`

对本文闭壳层体系使用 restricted/unpolarized ground-state reference。

最重要的错误模式：

```text
用户要 triplet excitation
→ Agent 把 spin_polarization 改 true
→ Agent 把 spin 改 3
```

这是错误的任务重定义。

triplet BSE 只需要在相同 ground-state reference 上：

```toml
bse_spin = "triplet"
```

---

## 9. `[quasiparticle_methods]` 参数字典

### 9.1 总览

| 参数 | 本批设置 | 意义 | 什么时候改 |
|---|---|---|---|
| `gw_or_bse` | `"bse"` | 做 GW 后继续 BSE | 只要 QP 时用 GW-only |
| `gw_scheme` | `"extrapolated"` | 显式求近 Fermi QP、其余外推 | 精度/成本权衡 |
| `threshold` | 未显式写 | GW 显式 QP 窗口 | 做 QP-window convergence |
| `use_low_rank_contour` | 多数 `true` | GW contour 低秩加速 | 版本/精度测试 |
| `bse_spin` | singlet/triplet | 激发态自旋通道 | 按目标态 |
| `bse_tda` | `true` | TDA | full BSE 比较 |
| `bse_davidson_solver` | `true` | Davidson 低根求解 | solver 策略 |
| `davidson_target_excitations` | 5；C₆H₆ T=10 | 请求 roots | 光谱/近简并时增大 |
| `davidson_maximum_subspace_size` | 50；C₆H₆ T=60 | 最大搜索子空间 | 收敛慢/近简并时增大 |
| `davidson_restart_dimensions` | 10；C₆H₆ T=15 | restart 保留维数 | 近简并多根时适度增大 |
| `davidson_converge_threshold` | 未显式写 | 新版统一 Davidson 收敛阈值 | 需要改精度时 |
| `bse_cutoff_energy` | 未显式写 | BSE 虚轨道能量截断 | 大体系成本控制 |
| `scgw` / `evgw_rounds` | 未启用 | eigenvalue-self-consistent GW | 用户明确要 evGW |
| RS 相关 | 未启用 | renormalized-singles variants | 文献复现/高级方法 |

### 9.2 `gw_or_bse = "bse"`

语义是：进入 quasiparticle 方法，并继续做 BSE。

如果用户只要：

- ionization-like QP levels；
- electron affinity-like QP levels；
- QP gap；

可以用 GW-only 路径：

```toml
gw_or_bse = "gw"
```

**不要为了拿一个 QP gap 强制做 BSE。**

### 9.3 `gw_scheme = "extrapolated"`

REST 的该模式不是对所有轨道都独立完整解 QP equation，而是：

1. 在 Fermi level 附近选取一组轨道；
2. 显式求这些轨道的 QP energy；
3. 从它们的 SCF→QP correction 推断/外推其他轨道。

因此输出会同时出现：

```text
(calculated)   QP Energy ...
(extrapolated) QP Energy ...
```

**Agent 应额外统计：**

- explicit QP orbital count；
- extrapolated count；
- explicit fraction；
- 目标 BSE 态涉及的轨道是否主要来自 explicit window；
- QP Newton warning 是否落在关键轨道上。

### 9.4 `threshold`

当前 REST 文档中，`threshold` 用于 `extrapolated` GW scheme 的 explicit-QP Fermi-window，单位 Hartree，文档默认约为 0.1 Ha。

**这不是 Davidson tolerance。**

对新体系：

```text
目标低激发主要由 HOMO/LUMO 附近轨道组成
→ 默认/较窄窗口可能足够做 workflow

目标激发涉及远离 Fermi 的轨道
或关键轨道仍是 extrapolated
或 QP warning 接近关键轨道
→ 增大 threshold 做 convergence
```

每次改变 threshold 都应把“explicit QP orbital indices / count”写入报告。

### 9.5 `use_low_rank_contour = true`

这是 GW 频率积分/contour 相关的低秩加速路径。

本文：

- 绝大多数成功输入显式 `true`；
- 成功的 C₆H₆ triplet 卡未显式写该项。

正确结论是：

> 这 12 张卡按当前形式均已跑通。

错误结论是：

> benzene triplet 必须关闭 low-rank contour。

当前数据不能建立这种因果关系。

### 9.6 `bse_spin`

```toml
bse_spin = "singlet"
```

或：

```toml
bse_spin = "triplet"
```

它决定 BSE electron–hole spin channel。

**Agent 永远要同时记录两个自旋字段：**

```yaml
ground_state_multiplicity: 1
bse_spin: triplet
```

这样不会因为只写“triplet”而丢失 reference 的物理含义。

### 9.7 `bse_tda = true`

本项目的 golden regression 一律 TDA。

切到：

```toml
bse_tda = false
```

意味着 Hamiltonian 结构与 solver 问题不同，结果可能系统变化。Agent 必须把它当成“方法变更”，不是“数值参数微调”。

### 9.8 `bse_davidson_solver = true`

用于迭代求低根。

什么时候合适：

- 只需要少量低能 excitation；
- BSE dimension 较大；
- 不值得 full diagonalization。

当 root 数接近总空间很大比例时，Davidson 的优势会减弱；此时应按 REST 版本支持的其他 solver 决定，而不是机械坚持。

### 9.9 `davidson_target_excitations`

普通基线：

```toml
davidson_target_excitations = 5
```

C₆H₆ triplet：

```toml
davidson_target_excitations = 10
```

**为什么不要只求 1 root？**

即使用户只问 S1/T1，求多个根也能帮助：

- 识别 root swapping；
- 看近简并；
- 找 brightest state；
- 判断 S1 是否暗；
- 发现目标根是否被 solver 漏掉。

推荐：

```text
只要最低态：3–5 roots
普通光谱：按能量窗口估计，通常 >5
高对称/近简并：适当增加 roots
```

### 9.10 `davidson_maximum_subspace_size`

普通：

```toml
50
```

benzene triplet：

```toml
60
```

太小可能导致：

- roots 尚未分离就 restart；
- residual 长期卡住；
- 近简并态反复交换；
- 根数不足。

太大则会增加：

- 子空间向量内存；
- 小型 projected eigenproblem 的成本。

所以它是“收敛空间 vs 内存”的平衡旋钮。

### 9.11 `davidson_restart_dimensions`

普通：

```toml
10
```

benzene triplet：

```toml
15
```

restart 后保留太少向量可能丢掉多个近简并态的信息；保留过多又会削弱 restart 的内存释放效果。

高对称、多根、near-degeneracy 情况下，适度增大通常比“只追一个根”更稳健。

### 9.12 `davidson_converge_threshold`

本批 golden input 没显式写。

REST 当前统一 Davidson 文档提供这一类收敛控制，并说明当前 solver 同时检查 residual 与 eigenvalue change。

**Agent 规则：**

- 不要和 GW `threshold` 混淆；
- 默认复现时不随便加入；
- 用户要更严/更松 tolerance 时，记录版本与新阈值；
- tolerance 变化后 golden regression 必须重新定义。

### 9.13 `bse_cutoff_energy`

当前 REST 文档定义为：按虚轨道能量限制进入 BSE kernel 的 unoccupied space，用于降低规模；当前文档给出默认示例约 1.5 Ha。

本文成功输入没有显式设置。

对大体系：

- 较小 cutoff：更快、更省内存；
- 过小：可能删掉重要虚轨道，尤其伤害 Rydberg、高能光谱、某些 CT 态。

因此正确做法是做：

```text
cutoff convergence
```

而不是只追求最小计算时间。

### 9.14 `scgw` / `evgw_rounds`

当前 REST 文档支持 eigenvalue-self-consistent GW 路径。本文没有开启，所以 golden suite 应按 G₀W₀ 理解。

如果用户明确要求 evGW：

- 允许切换；
- 但必须把它视为方法升级；
- 不能与本文 G₀W₀ S1/T1 进行“同方法 bitwise 回归”。

### 9.15 renormalized-singles 等高级选项

REST 文档中还可见 RS 相关起点/修正选项。本文未验证。

Skill 中的策略应是：

```text
默认基础 GW-BSE任务 → 不启用
文献明确要求 RS-GW/RS-BSE → 查当前版本文档后启用
```

不要为了“看起来高级”自动叠加。

---

## 10. 如何根据体系自动选择参数

### 10.1 新的中性闭壳层分子：最低 singlet + triplet

起点模板：

```toml
charge = 0.0
spin = 1
spin_polarization = false

[quasiparticle_methods]
gw_or_bse = "bse"
gw_scheme = "extrapolated"
bse_tda = true
bse_davidson_solver = true
davidson_target_excitations = 5
davidson_maximum_subspace_size = 50
davidson_restart_dimensions = 10
```

然后分别：

```toml
bse_spin = "singlet"
```

与：

```toml
bse_spin = "triplet"
```

### 10.2 用户只想要 absorption spectrum

优先 singlet，并且：

- roots 数必须足以覆盖目标能量范围；
- 不能只报告 S1；
- 要找 brightest state；
- 要保留 oscillator strength；
- 需要用 line broadening 构造模拟谱时，明确 broadening 参数只是绘图参数，不是量子化学计算参数。

### 10.3 高对称 / 近简并体系

若出现：

```text
First 0 excitations:
```

或 roots 不足，建议顺序：

1. 保持 ground-state `spin` 不变；
2. 增加 `davidson_target_excitations`；
3. 增加 `davidson_maximum_subspace_size`；
4. 适度增加 `davidson_restart_dimensions`；
5. 看 residual / restart 轨迹；
6. 检查关键 QP warning；
7. 检查 BSE cutoff/virtual space；
8. 再考虑其他 solver / full diagonalization（取决于版本）；
9. 微小破坏几何对称性只能作为**诊断性 workaround**，且必须单独标记结果。

### 10.4 Rydberg 态

重点不是 Davidson，而是：

- diffuse basis；
- 虚轨道空间；
- GW explicit QP window；
- 足够高的 BSE cutoff；
- basis convergence。

H₂O 可以“跑通”并不等于非增强型 cc-pVDZ 已经把 Rydberg 态做准。

### 10.5 CT 态

PNA 类体系重点检查：

- donor–acceptor 几何；
- diffuse functions；
- DFT/GW starting point；
- QP gap；
- dominant transition 的空间位置；
- 环境/溶剂屏蔽；
- BSE virtual space。

### 10.6 较大共轭体系

coumarin 类体系重点检查：

- AO 数；
- aux basis 数；
- RI memory；
- BSE dimension；
- Davidson subspace；
- roots 数；
- cutoff；
- 运行时间与内存上限。

### 10.7 GW-only 最小模板

如果只要 QP：

```toml
[ctrl]
print_level = 1
num_threads = 30
xc = "scan"
basis_path = "cc-pVDZ"
auxbas_path = "def2-SV(P)-JKFIT"
eri_type = "ri_v"
use_ri_symm = true
charge = 0.0
spin = 1
spin_polarization = false

[quasiparticle_methods]
gw_or_bse = "gw"
gw_scheme = "extrapolated"
use_low_rank_contour = true

[geom]
name = "MOLECULE"
unit = "angstrom"
position = """
...
"""
```

这里的 `num_threads=30` 只是沿用回归配置；新环境应改成实际分配核数。

---

## 11. 六个分子的精确已验证输入

> **[VERIFIED-RUN]** 以下 12 张输入卡由当前 `generated_inputs` 直接写入本报告，没有手工重抄坐标。  
> 它们适合当作 golden examples。  
> 如果你的 Agent 只想存“每个分子一张”，建议至少保存 singlet 卡，并让规则说明 triplet 是在相同 ground-state reference 上修改 `bse_spin`；但从可靠性看，保留 singlet + triplet 两张更好。

### 11.1 H₂O — 小体系 / Rydberg 敏感性测试

**为什么放进 Skill：** 运行极快，适合作为安装后第一轮 smoke test。它同时提醒 Agent：流程正确不代表 Rydberg 态已经在非增强型 cc-pVDZ 上达到基组收敛。

#### Singlet：精确已验证输入

```toml
[ctrl]
print_level = 1
num_threads = 30

xc = "scan"

basis_path = "cc-pVDZ"
auxbas_path = "def2-SV(P)-JKFIT"

eri_type = "ri_v"
use_ri_symm = true

charge = 0.0
spin = 1.0
spin_polarization = false


[quasiparticle_methods]

gw_or_bse = "bse"

gw_scheme = "extrapolated"

use_low_rank_contour = true


bse_spin = "singlet"

bse_tda = true

bse_davidson_solver = true

davidson_target_excitations = 5

davidson_maximum_subspace_size = 50

davidson_restart_dimensions = 10



[geom]

name = "H2O"

unit = "angstrom"

position = """
O -0.86256579 2.06483611 0.32113915
H 0.11006499 2.12811944 0.32113915
H -1.12744298 3.00284187 0.32113915
"""
```

#### Triplet：精确已验证输入

```toml
[ctrl]
print_level = 1
num_threads = 30

xc = "scan"

basis_path = "cc-pVDZ"
auxbas_path = "def2-SV(P)-JKFIT"

eri_type = "ri_v"
use_ri_symm = true

charge = 0.0
spin = 1.0
spin_polarization = false


[quasiparticle_methods]

gw_or_bse = "bse"

gw_scheme = "extrapolated"

use_low_rank_contour = true


bse_spin = "triplet"

bse_tda = true

bse_davidson_solver = true

davidson_target_excitations = 5

davidson_maximum_subspace_size = 50

davidson_restart_dimensions = 10



[geom]

name = "H2O"

unit = "angstrom"

position = """
O -0.86256579 2.06483611 0.32113915
H 0.11006499 2.12811944 0.32113915
H -1.12744298 3.00284187 0.32113915
"""
```

### 11.2 NH₃ — 小型闭壳层快速回归

**为什么放进 Skill：** 与 H₂O 一起构成双重最小回归点。两者都很便宜，但电子结构不同，适合排除“只对某一个分子偶然能跑”的情况。

#### Singlet：精确已验证输入

```toml
[ctrl]
print_level = 1
num_threads = 30

xc = "scan"

basis_path = "cc-pVDZ"
auxbas_path = "def2-SV(P)-JKFIT"

eri_type = "ri_v"
use_ri_symm = true

charge = 0.0
spin = 1.0
spin_polarization = false


[quasiparticle_methods]

gw_or_bse = "bse"

gw_scheme = "extrapolated"

use_low_rank_contour = true


bse_spin = "singlet"

bse_tda = true

bse_davidson_solver = true

davidson_target_excitations = 5

davidson_maximum_subspace_size = 50

davidson_restart_dimensions = 10



[geom]

name = "NH3"

unit = "angstrom"

position = """
N -1.41694694 -0.69435721 0.00000000
H -0.98939307 -1.63250945 0.00000000
H -0.98932171 -0.22531007 0.81244350
H -0.98932171 -0.22531007 -0.81244350
"""
```

#### Triplet：精确已验证输入

```toml
[ctrl]
print_level = 1
num_threads = 30

xc = "scan"

basis_path = "cc-pVDZ"
auxbas_path = "def2-SV(P)-JKFIT"

eri_type = "ri_v"
use_ri_symm = true

charge = 0.0
spin = 1.0
spin_polarization = false


[quasiparticle_methods]

gw_or_bse = "bse"

gw_scheme = "extrapolated"

use_low_rank_contour = true


bse_spin = "triplet"

bse_tda = true

bse_davidson_solver = true

davidson_target_excitations = 5

davidson_maximum_subspace_size = 50

davidson_restart_dimensions = 10



[geom]

name = "NH3"

unit = "angstrom"

position = """
N -1.41694694 -0.69435721 0.00000000
H -0.98939307 -1.63250945 0.00000000
H -0.98932171 -0.22531007 0.81244350
H -0.98932171 -0.22531007 -0.81244350
"""
```

### 11.3 CH₃COCH₃ (acetone) — n→π* / 暗态测试

**为什么放进 Skill：** 羰基孤对电子相关低激发是检查“最低态不一定最亮”的经典场景。Agent 应同时解析 S1、oscillator strength 和 brightest state。

#### Singlet：精确已验证输入

```toml
[ctrl]
print_level = 1
num_threads = 30

xc = "scan"

basis_path = "cc-pVDZ"
auxbas_path = "def2-SV(P)-JKFIT"

eri_type = "ri_v"
use_ri_symm = true

charge = 0.0
spin = 1.0
spin_polarization = false


[quasiparticle_methods]

gw_or_bse = "bse"

gw_scheme = "extrapolated"

use_low_rank_contour = true


bse_spin = "singlet"

bse_tda = true

bse_davidson_solver = true

davidson_target_excitations = 5

davidson_maximum_subspace_size = 50

davidson_restart_dimensions = 10



[geom]

name = "CH3COCH3"

unit = "angstrom"

position = """
C -0.17850765 0.47097651 0.05115046
O 1.04100223 0.44269123 0.05319921
C -0.99386496 -0.82046198 0.05112240
H -2.08893435 -0.66023920 0.04912070
H -0.71070372 -1.42278052 -0.83613481
H -0.71368292 -1.42092813 0.94057875
C -0.95788519 1.77488512 0.04855271
H -1.62113333 1.82526581 -0.84133350
H -1.62396101 1.82708534 0.93621906
H -0.26289640 2.63427119 0.04877995
"""
```

#### Triplet：精确已验证输入

```toml
[ctrl]
print_level = 1
num_threads = 30

xc = "scan"

basis_path = "cc-pVDZ"
auxbas_path = "def2-SV(P)-JKFIT"

eri_type = "ri_v"
use_ri_symm = true

charge = 0.0
spin = 1.0
spin_polarization = false


[quasiparticle_methods]

gw_or_bse = "bse"

gw_scheme = "extrapolated"

use_low_rank_contour = true


bse_spin = "triplet"

bse_tda = true

bse_davidson_solver = true

davidson_target_excitations = 5

davidson_maximum_subspace_size = 50

davidson_restart_dimensions = 10



[geom]

name = "CH3COCH3"

unit = "angstrom"

position = """
C -0.17850765 0.47097651 0.05115046
O 1.04100223 0.44269123 0.05319921
C -0.99386496 -0.82046198 0.05112240
H -2.08893435 -0.66023920 0.04912070
H -0.71070372 -1.42278052 -0.83613481
H -0.71368292 -1.42092813 0.94057875
C -0.95788519 1.77488512 0.04855271
H -1.62113333 1.82526581 -0.84133350
H -1.62396101 1.82708534 0.93621906
H -0.26289640 2.63427119 0.04877995
"""
```

### 11.4 C₆H₆ (benzene) — 高对称 π→π* / 近简并 solver stress test

**为什么放进 Skill：** 本批唯一出现 triplet Davidson 难收敛并通过扩大 roots/subspace 解决的案例，最适合训练 Agent 区分“物理设置错误”和“数值 solver 困难”。

#### Singlet：精确已验证输入

```toml
[ctrl]
print_level = 1
num_threads = 30

xc = "scan"

basis_path = "cc-pVDZ"
auxbas_path = "def2-SV(P)-JKFIT"

eri_type = "ri_v"
use_ri_symm = true

charge = 0.0
spin = 1.0
spin_polarization = false


[quasiparticle_methods]

gw_or_bse = "bse"

gw_scheme = "extrapolated"

use_low_rank_contour = true


bse_spin = "singlet"

bse_tda = true

bse_davidson_solver = true

davidson_target_excitations = 5

davidson_maximum_subspace_size = 50

davidson_restart_dimensions = 10



[geom]

name = "C6H6"

unit = "angstrom"

position = """
C -0.97981444 0.50345020 0.00006312
C 0.42492240 0.50258670 0.00050944
C 1.12749384 1.71893729 -0.00004334
C 0.42449110 2.93511535 -0.00104890
C -0.98021276 2.93559862 -0.00149615
C -1.68312892 1.71940840 -0.00094104
H -1.53020384 -0.45023568 0.00049390
H 0.97505186 -0.45127886 0.00130093
H 2.22862628 1.71911662 0.00030003
H 0.97494734 3.88877536 -0.00148122
H -1.53039910 3.88941952 -0.00228443
H -2.78427157 1.71929817 -0.00129030
"""
```

#### Triplet：精确已验证输入

```toml
[ctrl]
print_level = 1
num_threads = 30

xc = "scan"

basis_path = "cc-pVDZ"
auxbas_path = "def2-SV(P)-JKFIT"

eri_type = "ri_v"
use_ri_symm = true

charge = 0.0
spin = 1.0
spin_polarization = false


[quasiparticle_methods]

gw_or_bse = "bse"

gw_scheme = "extrapolated"

bse_spin = "triplet"

bse_tda = true

bse_davidson_solver = true

davidson_target_excitations = 10

davidson_maximum_subspace_size = 60

davidson_restart_dimensions = 15



[geom]

name = "C6H6"

unit = "angstrom"

position = """
C -0.97981444 0.50345020 0.00006312
C 0.42492240 0.50258670 0.00050944
C 1.12749384 1.71893729 -0.00004334
C 0.42449110 2.93511535 -0.00104890
C -0.98021276 2.93559862 -0.00149615
C -1.68312892 1.71940840 -0.00094104
H -1.53020384 -0.45023568 0.00049390
H 0.97505186 -0.45127886 0.00130093
H 2.22862628 1.71911662 0.00030003
H 0.97494734 3.88877536 -0.00148122
H -1.53039910 3.88941952 -0.00228443
H -2.78427157 1.71929817 -0.00129030
"""
```

### 11.5 p-nitroaniline (PNA) — push–pull charge-transfer 测试

**为什么放进 Skill：** 供体–受体共轭使低能态对基组弥散性、starting point 和环境更敏感。它是 workflow CT 案例，不应被包装成 cc-pVDZ 的最终定量答案。

#### Singlet：精确已验证输入

```toml
[ctrl]
print_level = 1
num_threads = 30

xc = "scan"

basis_path = "cc-pVDZ"
auxbas_path = "def2-SV(P)-JKFIT"

eri_type = "ri_v"
use_ri_symm = true

charge = 0.0
spin = 1.0
spin_polarization = false


[quasiparticle_methods]

gw_or_bse = "bse"

gw_scheme = "extrapolated"

use_low_rank_contour = true


bse_spin = "singlet"

bse_tda = true

bse_davidson_solver = true

davidson_target_excitations = 5

davidson_maximum_subspace_size = 50

davidson_restart_dimensions = 10



[geom]

name = "PNA_p-nitroaniline"

unit = "angstrom"

position = """
C -2.09985604 0.07339622 0.01521403
C -0.69848184 0.06870414 0.01563245
C -0.02441714 1.29668811 0.01509792
C -0.71100898 2.51672925 0.01411922
C -2.11284068 2.49923864 0.01368334
C -2.82697237 1.28424134 0.01424298
H -2.64672721 -0.88281302 0.01565616
H -0.13378851 -0.87506654 0.01640946
H -0.15587971 3.46606060 0.01364849
H -2.68841967 3.43631720 0.01285135
N 1.45730738 1.30235877 0.01557465
O 2.01066852 1.30416794 1.11203635
O 2.01124922 1.30444543 -1.08060058
N -4.26344039 1.33768859 0.01372649
H -4.63076331 0.82971233 -0.80234628
H -4.63128950 0.83326900 0.83177015
"""
```

#### Triplet：精确已验证输入

```toml
[ctrl]
print_level = 1
num_threads = 30

xc = "scan"

basis_path = "cc-pVDZ"
auxbas_path = "def2-SV(P)-JKFIT"

eri_type = "ri_v"
use_ri_symm = true

charge = 0.0
spin = 1.0
spin_polarization = false


[quasiparticle_methods]

gw_or_bse = "bse"

gw_scheme = "extrapolated"

use_low_rank_contour = true


bse_spin = "triplet"

bse_tda = true

bse_davidson_solver = true

davidson_target_excitations = 5

davidson_maximum_subspace_size = 50

davidson_restart_dimensions = 10



[geom]

name = "PNA_p-nitroaniline"

unit = "angstrom"

position = """
C -2.09985604 0.07339622 0.01521403
C -0.69848184 0.06870414 0.01563245
C -0.02441714 1.29668811 0.01509792
C -0.71100898 2.51672925 0.01411922
C -2.11284068 2.49923864 0.01368334
C -2.82697237 1.28424134 0.01424298
H -2.64672721 -0.88281302 0.01565616
H -0.13378851 -0.87506654 0.01640946
H -0.15587971 3.46606060 0.01364849
H -2.68841967 3.43631720 0.01285135
N 1.45730738 1.30235877 0.01557465
O 2.01066852 1.30416794 1.11203635
O 2.01124922 1.30444543 -1.08060058
N -4.26344039 1.33768859 0.01372649
H -4.63076331 0.82971233 -0.80234628
H -4.63128950 0.83326900 0.83177015
"""
```

### 11.6 coumarin — 较大共轭发色团 / 性能与光学联合测试

**为什么放进 Skill：** 本集合 AO 数最多，既能测试 RI/GW/BSE 的规模增长，也能检查多个低能光学态、亮态和较真实发色团行为。

#### Singlet：精确已验证输入

```toml
[ctrl]
print_level = 1
num_threads = 30

xc = "scan"

basis_path = "cc-pVDZ"
auxbas_path = "def2-SV(P)-JKFIT"

eri_type = "ri_v"
use_ri_symm = true

charge = 0.0
spin = 1.0
spin_polarization = false


[quasiparticle_methods]

gw_or_bse = "bse"

gw_scheme = "extrapolated"

use_low_rank_contour = true


bse_spin = "singlet"

bse_tda = true

bse_davidson_solver = true

davidson_target_excitations = 5

davidson_maximum_subspace_size = 50

davidson_restart_dimensions = 10



[geom]

name = "coumarin"

unit = "angstrom"

position = """
C -7.10073387 -0.32984527 0.00031797
C -5.70519837 -0.35669243 0.00015019
C -4.96023962 0.84771790 0.00025124
C -5.66232796 2.08422244 0.00052888
C -7.06867980 2.11381885 0.00069476
C -7.77825493 0.90849652 0.00058913
H -2.94806157 -0.03510472 -0.00013592
H -7.67168481 -1.26995262 0.00023921
H -5.16231714 -1.31492699 -0.00006281
C -3.51887016 0.90790518 0.00008628
H -7.57622417 3.08889021 0.00090452
H -8.87871555 0.93028868 0.00072001
C -3.59449180 3.38114915 0.00050310
C -2.87109984 2.10972039 0.00020213
H -1.77527076 2.18974403 0.00008190
O -5.00442345 3.27419713 0.00064381
O -3.11438457 4.49245602 0.00064404
"""
```

#### Triplet：精确已验证输入

```toml
[ctrl]
print_level = 1
num_threads = 30

xc = "scan"

basis_path = "cc-pVDZ"
auxbas_path = "def2-SV(P)-JKFIT"

eri_type = "ri_v"
use_ri_symm = true

charge = 0.0
spin = 1.0
spin_polarization = false


[quasiparticle_methods]

gw_or_bse = "bse"

gw_scheme = "extrapolated"

use_low_rank_contour = true


bse_spin = "triplet"

bse_tda = true

bse_davidson_solver = true

davidson_target_excitations = 5

davidson_maximum_subspace_size = 50

davidson_restart_dimensions = 10



[geom]

name = "coumarin"

unit = "angstrom"

position = """
C -7.10073387 -0.32984527 0.00031797
C -5.70519837 -0.35669243 0.00015019
C -4.96023962 0.84771790 0.00025124
C -5.66232796 2.08422244 0.00052888
C -7.06867980 2.11381885 0.00069476
C -7.77825493 0.90849652 0.00058913
H -2.94806157 -0.03510472 -0.00013592
H -7.67168481 -1.26995262 0.00023921
H -5.16231714 -1.31492699 -0.00006281
C -3.51887016 0.90790518 0.00008628
H -7.57622417 3.08889021 0.00090452
H -8.87871555 0.93028868 0.00072001
C -3.59449180 3.38114915 0.00050310
C -2.87109984 2.10972039 0.00020213
H -1.77527076 2.18974403 0.00008190
O -5.00442345 3.27419713 0.00064381
O -3.11438457 4.49245602 0.00064404
"""
```


---

## 12. 六个案例分别在测试什么

### 12.1 H₂O：smoke test + Rydberg 警示

**[VERIFIED-RUN]**

- AO: 24
- QP gap: 16.1099 eV
- S1: 6.9549 eV
- T1: 6.1395 eV
- ΔE_ST: 0.8154 eV

**Agent 应学到：**

1. H₂O 应当是新环境第一批测试之一；
2. 如果连它都无法完成，优先检查安装、input syntax、basis path、library；
3. “算通”后仍要把 diffuse-basis caveat 写出来；
4. 不要因为小体系就跳过 QP/BSE/roots 完整性检查。

### 12.2 NH₃：第二个独立快速回归点

**[VERIFIED-RUN]**

- AO: 29
- QP gap: 14.5961 eV
- S1: 7.0365 eV
- T1: 6.1442 eV
- ΔE_ST: 0.8923 eV

如果 H₂O 与 NH₃ 都通过，而 PNA/coumarin 失败，更可能是：

- 规模/内存；
- BSE dimension；
- RI tensor；
- Davidson；
- GW 轨道窗口；

而不是最基本的软件安装失败。

### 12.3 CH₃COCH₃：最低态不等于最亮态

**[VERIFIED-RUN]**

- AO: 86
- QP gap: 10.8984 eV
- S1: 3.3838 eV
- T1: 2.7121 eV
- ΔE_ST: 0.6718 eV
- 本批前 5 个 singlet 中 brightest state 为 S2，而不是 S1

这是让 Agent 学会区分：

```text
lowest excitation
vs
optically dominant excitation
```

的关键案例。

默认报告至少同时给：

- S1；
- brightest state；
- f；
- dominant transition；
- 若需要，吸收谱 broadening。

### 12.4 C₆H₆：高对称、近简并与 Davidson

**[VERIFIED-RUN]**

- AO: 114
- QP gap: 10.6339 eV
- S1: 4.7204 eV
- T1: 3.5802 eV
- ΔE_ST: 1.1402 eV
- brightest singlet: S4，约 7.1321 eV，f ≈ 0.751110
- triplet 最终请求 10 roots
- GW orbital #23 出现 Newton warning，但任务完成

最重要的规则：

- singlet 与 triplet ground-state reference 相同；
- 不要改 `spin=3`；
- solver failure 不等于“没有 triplet 态”；
- 先扩大 Davidson roots / subspace；
- 本次成功不需要破坏苯的几何对称性。

### 12.5 PNA：CT 敏感性

**[VERIFIED-RUN]**

- AO: 170
- QP gap: 9.4950 eV
- S1: 2.5759 eV
- T1: 1.9275 eV
- ΔE_ST: 0.6484 eV

在当前 6 个体系中，PNA 的 S1/T1 最低。

科研解释时要主动提示：

- gas-phase fixed geometry；
- 非增强型 cc-pVDZ；
- CT 对 diffuse basis 敏感；
- G₀W₀ 对 starting point 敏感；
- 溶剂可显著改变 CT 稳定性；
- 构象也可能影响 donor–acceptor coupling。

### 12.6 Coumarin：规模与真实发色团

**[VERIFIED-RUN]**

- AO: 184（本集合最大）
- QP gap: 7.7742 eV
- S1: 3.3055 eV
- T1: 2.1554 eV
- ΔE_ST: 1.1501 eV
- singlet/triplet 总时间约 88.797 / 85.788 s

它适合同时监控：

- RI tensor construction；
- QP spectrum；
- BSE roots；
- Davidson iterations；
- runtime / memory scaling；
- absorption-like spectrum。

另外它也是“HOMO/LUMO 不能靠 QP 正负号判断”的回归案例。

---

## 13. 如何解析 REST GW–BSE 输出

### 13.1 Level 0：文件完整性

先检查：

- 文件存在；
- 文件非空；
- 没有只写到 Davidson 中途；
- 尾部有最终统计与 mission status；
- 若作业调度器日志另有 stderr，要一并检查。

### 13.2 Level 1：SCF

最低检查：

```text
SCF is converged
```

并提取：

- final SCF energy；
- iteration count；
- density change；
- eigenvalue change；
- total energy change；
- SCF time；
- Mulliken charges。

**singlet/triplet QA：**

若两个任务使用：

- 同一 geometry；
- 同一 `charge`；
- 同一 `spin`；
- 同一 `xc/basis`；

则 ground-state SCF 应一致到数值噪声。

如果显著不同，先找输入差异，而不是直接分析 BSE。

### 13.3 Level 2：GW

检查：

```text
One round of GW by extrapolated scheme has finished.
```

提取：

- explicit QP indices；
- `(calculated)` QP energy；
- `(extrapolated)` QP energy；
- `Fermi Surface`；
- HOMO；
- LUMO；
- QP gap；
- Newton / root-solving warnings。

### 13.4 正确的 HOMO/LUMO 解析算法

伪代码：

```text
for each QP energy line:
    if before "Fermi Surface":
        occupied_qp.append(...)
    else:
        virtual_qp.append(...)

HOMO = occupied_qp[-1]
LUMO = virtual_qp[0]
QP_gap = LUMO - HOMO
```

不要使用：

```text
energy < 0 => occupied
energy > 0 => virtual
```

### 13.5 Level 3：BSE 类型

必须检查：

```text
BSE Type:singlet
```

或：

```text
BSE Type:triplet
```

并和输入的 `bse_spin` 对比。

输入/输出不一致时，任务应该标成 configuration mismatch。

### 13.6 Level 4：Davidson

提取：

- iteration；
- residuals；
- search-space size；
- restart；
- final residual；
- requested roots；
- obtained roots。

危险信号：

```text
First 0 excitations:
```

```text
requested 5, printed <5
```

```text
residual oscillates / stagnates
```

```text
output ends during Davidson
```

### 13.7 Level 5：每个 excited state

至少结构化：

```yaml
state_index:
energy_Ha:
energy_eV:
wavelength_nm:
transition_dipole_x:
transition_dipole_y:
transition_dipole_z:
dipole_square:
oscillator_strength:
dominant_transitions:
  - from_orbital:
    to_orbital:
    amplitude:
```

### 13.8 轨道编号是 0-based

例如 benzene：

```text
HOMO = #20
LUMO = #21
```

所以：

```text
#20 -> #21
```

就是 HOMO→LUMO。

如果用户习惯 1-based，Agent 可以额外显示：

```text
REST index #20 (human 1-based orbital 21)
```

但内部数据必须保留 REST 原始 index。

### 13.9 不只输出 S1：必须找 brightest state

本批验证清楚表明：

```text
benzene: S4 brightest
acetone: S2 brightest
H2O:     S3 brightest
NH3:     S5 brightest
PNA:     S5 brightest (within requested roots)
coumarin:S4 brightest
```

因此默认科研摘要应至少同时有：

```text
lowest singlet
lowest triplet
ΔEST
brightest singlet
brightest energy
oscillator strength
dominant transition
```

### 13.10 能量与波长换算

与 REST 当前常量保持一致时：

\[
1\ \mathrm{Ha}\approx 27.2113845\ \mathrm{eV}.
\]

\[
E(\mathrm{eV}) = E(\mathrm{Ha})\times 27.2113845.
\]

波长近似：

\[
\lambda(\mathrm{nm}) \approx \frac{1239.84}{E(\mathrm{eV})}.
\]

报告里应保留原始 Hartree 或足够位数的 eV，避免多次舍入后再反算。

---

## 14. Davidson 收敛与 C₆H₆ triplet 故障案例

### 14.1 失败属于哪一层？

C₆H₆ 历史失败发生在：

```text
SCF: success
GW:  success
BSE kernel: entered
Davidson: failed to return valid roots
```

曾出现类似：

```text
First 0 excitations:
```

因此它不是：

- 基组读不到；
- SCF 不收敛；
- GW 完全失败；
- “物理上没有 triplet”。

### 14.2 正确修复

最终成功设置：

```toml
davidson_target_excitations = 10
davidson_maximum_subspace_size = 60
davidson_restart_dimensions = 15
```

而 ground-state 仍然：

```toml
spin = 1.0
spin_polarization = false
```

BSE 通道：

```toml
bse_spin = "triplet"
```

### 14.3 这个案例应该固化到 Agent 的诊断规则

```text
IF:
    SCF converged
    AND GW finished
    AND BSE entered
    AND roots missing / Davidson stalls
THEN:
    diagnose eigensolver/subspace first
    NOT ground-state multiplicity
```

### 14.4 为什么高对称更容易给 solver 压力？

高对称体系常出现：

- degeneracy；
- near-degeneracy；
- 多个相近 particle–hole configurations；
- root ordering 对细小数值变化敏感。

迭代 eigensolver 需要同时保持多个相邻 root 的子空间信息，所以：

- 多求几个 root；
- 给更大的 search space；
- restart 时保留更多有用方向；

可能明显改善稳定性。

### 14.5 什么时候才考虑轻微破坏对称性？

只有在：

- 已验证 solver 参数；
- 已排除代码/版本问题；
- 仍怀疑精确/近简并导致 root tracking 难题；

时，才可作为**诊断实验**。

且必须：

- 保存原始 geometry；
- 保存 perturbation magnitude；
- 报告结果不能和原始对称结构混为同一个计算。

本次 benzene 成功**不需要**这样做。

---

## 15. 科研级收敛测试

### 15.1 Ground-state starting point

G₀W₀ 具有 starting-point dependence。

定量研究至少考虑：

```text
SCAN baseline
vs
另一种合理 DFT 起点
```

若使用 hybrid / evGW，则方法已经改变，必须重新定义 regression。

关注：

- QP HOMO/LUMO；
- QP gap；
- S1/T1；
- state ordering；
- oscillator strength；
- dominant transition character。

### 15.2 主基组

至少看：

```text
double-zeta → triple-zeta
```

Rydberg / CT：

```text
non-augmented → diffuse/augmented
```

### 15.3 辅助基组

检查：

- RI fitting error；
- 更大/更适合的 aux basis 后 QP 与 excitation 是否稳定。

### 15.4 GW explicit-QP window

逐步扩大 `threshold`，直到关键量稳定：

- QP gap；
- 关键 QP levels；
- 目标 BSE roots；
- 关键 participating orbitals 是否 explicit。

### 15.5 BSE virtual-space cutoff

逐步增加 `bse_cutoff_energy`，检查：

- S1/T1；
- brightest state；
- oscillator strength；
- dominant transition；
- 高能 spectrum。

### 15.6 Davidson

收敛变量不只一个：

- target roots；
- max subspace；
- restart dimension；
- tolerance；
- max iteration（若版本暴露）；
- initial guess / preconditioner（若版本可配）。

### 15.7 TDA vs full BSE

科研级任务若关心 TDA 误差，应比较：

```text
bse_tda = true
vs
bse_tda = false
```

但 full BSE 的 solver 路径可能随 REST 版本不同，不能把旧 TDA Davidson 经验完全照搬。

### 15.8 Geometry 与环境

本文是 gas-phase、fixed-geometry vertical excitation 回归。

实验对比时，尤其 PNA/coumarin，可能需要考虑：

- solvent；
- dielectric environment；
- conformer；
- excited-state relaxation；
- vibronic structure；
- temperature；
- SOC。

---

## 16. Rydberg、CT、暗态、亮态、triplet 的特殊处理

### 16.1 Rydberg

Agent 在看到：

- 小分子；
- 高度弥散虚轨道；
- 较高 excitation；
- 明显 Rydberg character；

时应自动提示：

```text
cc-pVDZ workflow result may be qualitatively useful,
but diffuse-basis convergence is required for quantitative Rydberg energies.
```

### 16.2 Charge transfer

CT 态不应仅靠“轨道编号跨度大”判断。

更可靠的诊断可组合：

- dominant transition；
- occupied / virtual orbital spatial localization；
- donor/acceptor fragment；
- transition density；
- electron–hole separation（若可得到）；
- dipole change；
- solvent sensitivity。

当前基础输出只有 orbital transition amplitudes 时，可以先做“候选 CT”判断，不要过度宣称。

### 16.3 暗态

`f ≈ 0` 不代表坏结果。

可能原因：

- symmetry forbidden；
- n→π* 弱允许；
- spin forbidden；
- transition dipole cancellation。

所以 Agent 不能用 oscillator strength 是否非零当作通用成功判据。

### 16.4 亮态

光谱任务一定要区分：

```text
first state
brightest state
first bright state
```

三者可能不同。

### 16.5 Triplet

本文无 SOC 流程下：

- triplet oscillator strength 可为 0；
- T1 仍然是有效电子激发根；
- 若关心 phosphorescence / intersystem crossing，需要 SOC 等额外理论，不在当前回归范围。

---

## 17. 常见错误与自动诊断规则

### 错误 A：triplet → `spin=3`

**错误。**

正确：

```toml
spin = 1
spin_polarization = false
bse_spin = "triplet"
```

适用于“闭壳层 singlet ground state 上的 triplet BSE excitation”。

只有当用户明确要三重态作为 SCF reference 时才讨论 `spin=3`。

### 错误 B：把 GW `threshold` 当成 Davidson tolerance

**错误。**

```text
GW threshold:
    explicit quasiparticle energy window

Davidson threshold:
    eigensolver convergence
```

作用阶段、单位、意义都不同。

### 错误 C：按 QP energy 正负判断占据/虚轨道

**错误。**

看：

```text
Fermi Surface
```

### 错误 D：triplet f=0 → failed

**错误。**

在当前 closed-shell/no-SOC spin-adapted BSE 中是正常结果。

### 错误 E：`First 0 excitations` → “没有激发态”

**错误。**

优先标记为：

```text
Davidson / root convergence failure
```

### 错误 F：只看 `Mission accomplished`

不足。

还要看：

- requested roots 是否齐全；
- BSE type；
- warnings；
- QP warning；
- 输出是否截断；
- 输入回显是否匹配。

### 错误 G：把 cc-pVDZ 的 Rydberg/CT 值当最终基组极限

**错误。**

应主动提示 diffuse/basis convergence。

### 错误 H：升级 REST 后仍用旧默认值做强制判断

**错误。**

版本变化可能包括：

- GW/BSE kernel；
- UBSE；
- Davidson；
- full BSE solver；
- contour；
- keyword spelling/default。

### 错误 I：把 `use_ri_symm` 当分子点群开关

**错误。**

这是 RI 实现层面的优化语义，不等价于几何点群约束。

### 错误 J：把 solver 参数变化解释成“物理方法变化”

需分类：

```text
numerical solver settings:
    roots / subspace / restart / tolerance

physical/method settings:
    ground-state multiplicity / xc / basis / GW self-consistency / TDA/full BSE
```

二者要在报告中分开。

---

## 18. Agent 端到端工作流

### Step 1：识别任务意图

分类：

```text
GW-only
BSE singlet
BSE triplet
both singlet + triplet
absorption spectrum
ΔEST
method convergence
debug failed job
regression after REST upgrade
```

### Step 2：确定 ground-state reference

必须知道：

- geometry；
- charge；
- ground-state multiplicity；
- closed-shell/open-shell；
- XC；
- basis；
- auxiliary basis。

若 charge/multiplicity 不确定，不应静默猜。

### Step 3：做电子数一致性检查

至少检查：

```text
electron count parity
vs
requested multiplicity
```

若不相容，先提示用户/修正化学定义。

### Step 4：生成输入

对本文类型的 neutral closed-shell molecule：

```text
same [ctrl] ground-state reference
+ singlet BSE card
+ triplet BSE card
```

### Step 5：首次安装/版本升级先跑 Tier 1

```text
H2O singlet
H2O triplet
NH3 singlet
NH3 triplet
```

通过后再进入 C6H6/PNA/coumarin。

### Step 6：执行后进行机器 QA

最少：

```text
file complete?
SCF converged?
GW finished?
BSE type correct?
requested roots obtained?
Davidson converged?
QP warning?
Mission accomplished?
input/output parameter echo consistent?
```

### Step 7：解析物理结果

输出：

```text
SCF energy
QP HOMO / LUMO / gap
S1 / T1
ΔEST
brightest singlet
oscillator strength
dominant transitions
wavelength
warnings
```

### Step 8：判定“workflow success”还是“scientific convergence”

Agent 的措辞要区分：

```text
“任务运行成功”
```

和：

```text
“该数值已对 basis/GW window/TDA 等达到收敛”
```

除非真的做了收敛扫描，否则只允许宣称前者。

### Step 9：保存 provenance

至少：

```text
REST version / commit
input hash
geometry source
basis / aux basis
thread count
date
output path
warnings
```

---

## 19. 推荐结果数据结构

建议内部标准化为：

```yaml
system:
  name:
  formula:
  charge:
  ground_state_multiplicity:
  spin_polarized:
  geometry_source:
  geometry_unit:

software:
  rest_version:
  rest_commit:
  libxc_version:
  executable:
  host:
  threads:

method:
  xc:
  basis:
  auxiliary_basis:
  eri_type:
  gw_scheme:
  gw_threshold_Ha:
  low_rank_contour:
  gw_self_consistency:
  bse_spin:
  bse_tda:
  bse_cutoff_energy_Ha:
  requested_roots:
  davidson_max_subspace:
  davidson_restart_dimension:
  davidson_tolerance:

status:
  scf_converged:
  gw_finished:
  bse_started:
  bse_finished:
  mission_accomplished:
  complete_root_count:
  output_truncated:
  warnings: []

ground_state:
  scf_energy_Ha:
  scf_iterations:
  mulliken_charges: []

gw:
  explicit_qp_orbitals: []
  extrapolated_qp_orbitals: []
  homo_index_0based:
  homo_qp_Ha:
  lumo_index_0based:
  lumo_qp_Ha:
  qp_gap_eV:
  qp_warnings: []

bse:
  davidson_iterations:
  max_search_space:
  restart_count:
  final_residuals: []
  states:
    - index:
      energy_Ha:
      energy_eV:
      wavelength_nm:
      oscillator_strength:
      transition_dipole: [x, y, z]
      dipole_square:
      dominant_transitions:
        - from_index_0based:
          to_index_0based:
          amplitude:

derived:
  S1_eV:
  T1_eV:
  delta_EST_eV:
  brightest_singlet_state:
  brightest_singlet_energy_eV:
  brightest_singlet_f:

performance:
  scf_s:
  total_s:
  ri_ov_s:
  ri_vv_s:
  ri_oo_s:
  w_operator_calls:
  w_operator_s:
  coulomb_operator_calls:
  coulomb_operator_s:
```

### 19.1 为什么要把“原始量”和“派生量”分开？

例如：

```text
raw:
    S1 = parser 从输出读到

derived:
    ΔEST = S1 - T1
```

这样：

- parser bug 容易定位；
- 可重新计算；
- 不会把派生值误当成 REST 原生输出。

---

## 20. 建议的自动 QA / 回归判据

### 20.1 同一构建、同一输入

至少要求：

- root count 相同；
- BSE spin 相同；
- SCF energy 高度一致；
- QP spectrum 高度一致；
- S1/T1 在很小数值误差内一致；
- oscillator-strength pattern 不发生无解释巨变；
- warning 数量/轨道可追踪。

### 20.2 singlet vs triplet cross-check

对本文 closed-shell reference：

```text
geometry: identical
SCF reference: identical
QP spectrum: identical / numerical noise
BSE kernel: different spin channel
excitation energies: different
```

如果 singlet/triplet 的 SCF 或 QP 明显不一致，优先认为输入 reference 不同。

### 20.3 升级 REST 后

不要要求 bitwise identical。

流程：

1. 跑 H₂O/NH₃；
2. 比较 SCF/QP/BSE；
3. 查 changelog；
4. 再跑 C₆H₆；
5. 最后 PNA/coumarin；
6. 若确认算法变更，建立新 golden reference；
7. 旧 reference 仍保留版本标签。

### 20.4 回归 tolerance 不应永久硬编码

不同：

- 编译器；
- BLAS；
- CPU；
- 线程调度；
- solver 改版；

可能造成最后几位差异。

Skill 可以有默认工程 tolerance，但必须允许按版本重标定。

---

## 21. 尚未由这批数据验证的范围

当前 12 个 golden runs **没有**覆盖：

- open-shell UBSE；
- ROHF/reference-specific BSE；
- full BSE (`bse_tda=false`)；
- evGW；
- rsGW / renormalized-singles；
- solvent/environment GW-BSE；
- SOC 与 singlet–triplet mixing；
- phosphorescence rate；
- excited-state geometry optimization；
- adiabatic excitation；
- 0–0 energy；
- vibronic spectrum；
- periodic GW-BSE；
- core/X-ray excitation；
- very diffuse anions；
- strongly multireference systems。

REST 的新版本已经继续扩展 UGW/UBSE、统一 Davidson/非 TDA 求解等能力，但这些都应该建立**新的最小回归体系**，不能直接把本文 12 个结果当作验证。

---

## 22. REST 版本兼容策略

### 22.1 为什么必须 version-aware？

REST GW/BSE 属于持续活跃开发区域。不同版本可能改变：

- keyword spelling；
- default values；
- Davidson API；
- residual 判据；
- full BSE solver；
- UBSE；
- contour integration；
- low-rank implementation；
- auxiliary basis 默认值。

### 22.2 建议每个任务保存

```text
REST executable path
REST version
git commit (if available)
Libxc version
basis paths
hostname
thread count
input SHA256
output SHA256
```

### 22.3 本批回归能确认什么？

当前日志能确认包括：

- Libxc version（当前日志中可见 7.0.0）；
- 方法和 basis 回显；
- 任务成功。

但日志不一定直接给出完整 REST commit，因此：

> 仅凭这批 out 不能反推出唯一源代码提交。

### 22.4 当旧输入与新文档出现差异

例如：

```text
tested input: "ri_v"
current docs:  "ri-v"
```

处理规则：

```text
reproduce old calculation:
    preserve exact old input

generate for new installed version:
    follow installed-version documentation

never silently rewrite and then call it the same regression input
```

---

## 23. 如何并入 Skill

推荐目录：

```text
rest-electronic-structure/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── references/
│   └── rest_gwbse.md
└── scripts/
    ├── analyze_gwbse.py
    └── run_analysis.sh
```

**为什么把本文件放 `references/` 而不是全部塞 `SKILL.md`？**

Skill 应采用 progressive loading：

- `SKILL.md`：控制面，短、硬规则、触发条件、执行顺序；
- `references/rest_gwbse.md`：长篇理论、参数说明、案例、golden inputs；
- `scripts/`：确定性的解析/统计/绘图。

这样只有真正遇到 GW/BSE 请求时，Agent 才加载本文件。

### 23.1 `SKILL.md` 中建议写的路由提示

```text
Read references/rest_gwbse.md when the request involves:
- REST GW or G0W0
- quasiparticle energies
- BSE excited states
- singlet/triplet BSE
- GW-BSE input generation
- BSE Davidson convergence
- QP gap / optical gap
- oscillator strengths
- dominant BSE transitions
- "First 0 excitations"
- GW/BSE regression after REST upgrade
```

### 23.2 脚本与文档的职责划分

```text
Agent:
    choose physical method
    explain settings
    decide convergence strategy
    diagnose physics vs numerics

script:
    parse outputs
    compute tables
    generate plots
    check root counts
    flag warnings
    compare singlet/triplet references
```

不要让 LLM 每次手工用正则“临时解析”几千行 out；稳定字段应交给测试过的 parser。

---

## 24. 可直接复制进 `SKILL.md` 的控制规则

```text
For REST GW/BSE tasks:

1. Read references/rest_gwbse.md before generating, debugging, or interpreting GW/BSE input/output.

2. Separate ground-state multiplicity (`spin`) from excited-state BSE spin (`bse_spin`).
   For a neutral closed-shell singlet reference, keep spin=1 and
   spin_polarization=false for BOTH singlet and triplet BSE calculations.
   Select the triplet channel with bse_spin="triplet".
   Never change spin=1 to spin=3 merely because a user requests triplet excitation.

3. Treat gw_scheme="extrapolated" as a quasiparticle approximation that explicitly
   solves selected orbitals near the Fermi surface and extrapolates the remaining
   corrections. Never confuse its GW `threshold` with Davidson convergence tolerance.

4. Determine HOMO and LUMO from the REST "Fermi Surface" separator, not from the
   sign of quasiparticle energies. Preserve REST orbital indices as 0-based internally.

5. For the regression examples, preserve the exact tested input cards in
   references/rest_gwbse.md. Do not silently modernize keyword spelling or defaults.

6. Validate every completed job by checking:
   - SCF convergence
   - GW completion
   - requested BSE spin
   - Davidson/root completion
   - requested vs obtained root count
   - warnings
   - output truncation
   - final "REST: Mission accomplished" status

7. Do not treat zero triplet oscillator strength as a failure in the closed-shell,
   spin-adapted, no-SOC workflow unless other evidence shows the calculation failed.

8. If Davidson returns zero/incomplete roots or stalls after SCF and GW succeeded,
   diagnose the eigensolver first. Increase target roots, maximum subspace, and
   restart retained dimensions as appropriate before changing physical spin or geometry.

9. Treat H2O and NH3 as smoke/regression tests, C6H6 as a high-symmetry Davidson
   stress test, PNA as a charge-transfer sensitivity test, and coumarin as the
   larger chromophore/performance test.

10. Distinguish workflow success from scientific convergence. For quantitative
    Rydberg or charge-transfer states, recommend diffuse/basis, starting-point,
    GW-window, BSE-cutoff, and TDA/full-BSE convergence checks as appropriate.

11. Report at least:
    method, basis, auxiliary basis, charge, ground-state multiplicity, GW scheme,
    BSE spin/TDA, QP HOMO/LUMO/gap, S1 or T1, brightest singlet and oscillator
    strength where relevant, dominant transitions, convergence status, warnings,
    and runtime.

12. Keep REST-version provenance. After a REST upgrade, rerun the H2O/NH3 regression
    before trusting larger or scientifically sensitive calculations.
```

---

## 25. 推荐的 Agent 输出模板

### 25.1 成功任务

```text
REST GW-BSE result
==================

System
- Molecule:
- Geometry:
- Charge:
- Ground-state multiplicity:

Method
- XC:
- Basis:
- Auxiliary basis:
- ERI:
- GW scheme:
- BSE spin:
- TDA:
- Requested roots:
- Davidson max subspace / restart:

Ground state
- SCF converged: yes/no
- SCF energy:
- SCF iterations:

GW
- Explicit QP orbitals:
- HOMO index / QP energy:
- LUMO index / QP energy:
- QP gap:
- QP warnings:

BSE
- S1 or T1:
- Brightest singlet:
- Oscillator strength:
- Dominant transitions:
- Davidson iterations:
- Final residual:
- Requested/obtained roots:

QA
- BSE type matches input:
- Mission accomplished:
- Output complete:
- Notes:

Performance
- SCF time:
- Total time:
```

### 25.2 失败任务

不要只说：

```text
REST failed.
```

应分类：

```text
Failure stage:
  input parsing
  basis loading
  SCF
  GW
  BSE kernel construction
  Davidson eigensolver
  truncated/aborted output
```

并给：

```text
Evidence:
Most likely numerical cause:
Physical settings that should NOT be changed yet:
Next minimal diagnostic:
```

---

## 26. 参考资料

### 26.1 REST

1. REST documentation — About / features / citation  
   https://rest-doc.readthedocs.io/en/about.html

2. REST unified Davidson / Krylov solver documentation  
   https://rest-doc.readthedocs.io/en/contributor/solvers.html

3. REST changelog  
   https://rest-doc.readthedocs.io/en/changelog.html

4. REST project/group  
   https://gitee.com/restgroup/

5. REST paper（当前 REST 文档列出的引用）：  
   Zhiyun Li, Tianyi Gao, Shirong Wang, Sheng Bi, Rulin Feng, Zhenyu Zhu, Yilin Zhao, Wenjie Yan, Lingyue Yu, Qirui Gao, Zihan Lin, Jianming Wu, Igor Ying Zhang, Xin Xu.  
   *REST: Embracing the Rust Programming Language for Modern Electronic Structure Theory.*  
   Chinese Journal of Chemical Physics.  
   DOI: `10.1063/1674-0068/cjcp2510156`

### 26.2 GW / BSE 理论

6. L. Hedin,  
   *New Method for Calculating the One-Particle Green's Function with Application to the Electron-Gas Problem.*  
   Phys. Rev. 139, A796 (1965).  
   DOI: `10.1103/PhysRev.139.A796`

7. G. Onida, L. Reining, A. Rubio,  
   *Electronic excitations: density-functional versus many-body Green's-function approaches.*  
   Rev. Mod. Phys. 74, 601 (2002).  
   DOI: `10.1103/RevModPhys.74.601`

8. M. Rohlfing, S. G. Louie,  
   *Electron-hole excitations and optical spectra from first principles.*  
   Phys. Rev. B 62, 4927 (2000).  
   DOI: `10.1103/PhysRevB.62.4927`

9. BerkeleyGW GW tutorial  
   https://berkeleygw.org/documentation/tutorial/tutorial-sigma/

10. BerkeleyGW BSE tutorial  
    https://berkeleygw.org/documentation/tutorial/tutorial-bethe-salpeter-equation/

### 26.3 SCAN

11. J. Sun, A. Ruzsinszky, J. P. Perdew,  
    *Strongly Constrained and Appropriately Normed Semilocal Density Functional.*  
    Phys. Rev. Lett. 115, 036402 (2015).  
    DOI: `10.1103/PhysRevLett.115.036402`

---

## 27. 最终定位

这 6 个分子应该被你的 Agent 理解成一套**分层的 REST GW–BSE regression + 教学 + 故障诊断集合**，而不是 6 个孤立输入。

一个真正具备 GW–BSE 能力的 Agent，至少应做到：

1. 正确区分 ground-state spin 与 BSE excited-state spin；
2. 理解 SCF → GW → BSE 的物理层次；
3. 能生成 singlet/triplet 卡而不错误修改闭壳层 reference；
4. 能解释 G₀W₀ starting-point dependence；
5. 能解释 QP gap 与 optical excitation 的区别；
6. 能判断 TDA 与 full BSE 是方法选择，不是单纯“精度按钮”；
7. 能根据体系特征选择 roots/subspace/cutoff/basis 收敛策略；
8. 能从 REST out 正确识别 Fermi surface、0-based orbital、QP warning；
9. 能区分 S1 与 brightest state；
10. 能识别 triplet f=0 的正常物理含义；
11. 能把 `First 0 excitations` 识别为 solver failure 而不是“无激发态”；
12. 能把 C₆H₆ triplet 作为 Davidson stress regression；
13. 能提醒 H₂O Rydberg / PNA CT 的 diffuse-basis 风险；
14. 能对每个结果做 provenance 与 QA；
15. 能明确区分“workflow 已跑通”和“科研数值已收敛”。

### 一句话总纲

> **对闭壳层分子，REST GW–BSE 的正确工作流是：先固定并验证 singlet ground-state SCF reference，再用 GW 得到准粒子能量，并在同一 reference 上分别通过 `bse_spin="singlet"` 与 `"triplet"` 求电子–空穴激发；数值不收敛时优先调整 Davidson 与轨道空间，而不是篡改 ground-state 自旋。**
