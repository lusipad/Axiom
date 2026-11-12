# Axiom CNC 三层灰盒物理建模、正交误差解耦与跨刀路零样本推荐系统规范

> 文档状态：Accepted v2.0（替代 v1.0 纯黑盒 `ElasticNet` 初筛草案，见 [ADR-0030](架构决策记录/ADR-0030-三层灰盒物理建模与跨刀路零样本推荐.md)）
> 适用代码基线：`src/axiom/benchmark.py`、`src/axiom/greybox_model.py`、`src/axiom/parameter_space.py`、`src/axiom/parameter_learner.py`、`src/axiom/parameter_recommender.py`、`src/axiom/cnc_governance.py`
> 关联规范：`CNC-BENCHMARK.md`、`Axiom 通用评估框架规范.md`、`物理模型与现实对齐规范.md`、`数据集与学习模型规范.md`、`受约束优化与安全闭环规范.md`

## 1. 核心问题与为什么放弃纯黑盒 `ElasticNet`

在 32 维 CNC 路径规划（G1）、运动学滤波（G2）与伺服控制环（G3）参数调优中，纯黑盒多项式代理模型（如 `ElasticNet` 线性 + 纯二次项回归）在真实工业控制器上存在四项根本性物理失配：

1. **硬取小包络（Hard-Min Envelope）死区失真**：CNC 前瞻速度、单轴投影限幅与圆弧向心限速严格服从分段硬取小算子 $v(s) = \min(v_{\text{prog}}, v_{\text{axis}}, v_{\text{curv}}, v_{\text{la}})$。当某一参数高于当前活跃瓶颈时，真实系统处于**完全平坦的饱和死区**；二阶多项式在死区内必然产生伪抛物线翘尾与虚假拐点。
2. **高维欠定幻觉（Underdetermined Hallucination）**：32 维全二阶响应面含 $1 + 32 + \frac{32 \times 33}{2} = 561$ 个待定系数。在小样本（10～30 组试验）下，纯统计相关性会把物理上完全解耦的参数（例如纯 2D XY 平面刀路上的 Z 轴限幅 `g2.axis_vel_limit_z`）误判为活跃主导因子。
3. **法向误差矢量抵消盲区**：规划滤波引起的圆弧/拐角内缩（指向曲率中心内侧）与伺服惯量滞后引起的拐角外摆（指向曲率中心外侧）在局部 Frenet 法向空间内发生**带符号相消或叠加**，纯标量回归无法刻画符号翻转边界。
4. **单刀路死绑定（Zero Cross-Case Transfer）**：黑盒模型学习的权重把当前测试刀路的弧长、转角和曲率硬编码进了回归系数，更换新零件 NC 程序即完全失效。

为此，v2.0 采用 **“第一层白盒解析物理核 + 第二层受约束灰盒机理标定 + 第三层低维最大边缘似然 ARD-GP 残差 + R0–R7 统一安全治理桥接”** 架构。

## 2. 轨迹正交误差解耦与频谱特征提取（`benchmark.py`）

在进入建模前，单次轨迹评估核 `evaluate_cnc_export` 通过 $O(N + M)$ 单调弧长进度游标建立局部 Frenet 标架 $(\mathbf{t}(s), \mathbf{n}(s), \mathbf{b}(s))$，将原始跟随误差与采样噪声拆解为可辨识的物理分量：

| 指标 ID | 物理定义与计算方法 | 解决的工程痛点 |
| :--- | :--- | :--- |
| `tangentialLagMaxMm` | $|\langle \mathbf{q}_{\text{cmd}} - \mathbf{q}_{\text{act}}, \mathbf{t}(s^*) \rangle|$ 峰值 | 剥离不直接损伤零件几何轮廓的纯切向时间延迟 |
| `normalServoErrorMaxMm` | $\|\mathbf{e}_{\perp}\| = \|(\mathbf{I} - \mathbf{t}\mathbf{t}^\top)(\mathbf{q}_{\text{cmd}} - \mathbf{q}_{\text{act}})\|$ 峰值 | 精准提取真正造成过切/欠切的法向伺服轮廓误差 |
| `signedRadialOffsetMeanMm` | 圆弧段 $\mathbb{E}[\|\mathbf{q}_{\text{act}} - \mathbf{c}\| - R]$ | 区分滤波/低增益导致的**径向内缩（$<0$）**与惯量过冲导致的**外扩（$>0$）** |
| `quadrantGlitchMaxMm` | 轴速度过零换向 ±5 采样内实测轮廓误差最大值（原口径，保持可比） | 过象限突跳总量 |
| `quadrantGlitchExcessMm` | 换向约 15 ms 窗口内实测轮廓误差减去指令偏差 | 剥离规划偏差后的伺服过象限突出量（灰盒模型使用） |
| `smoothedJerkRmsMmS3` | 7 点三次 Savitzky-Golay 正则化三阶导数 RMS | 抑制编码器分辨率量化在 $\Delta^3 q / T^3$ 上放大的高频伪白噪声 |
| `dominantResonanceFreqHz` | 有符号法向残差经 Hanning 窗与 $[45, 450]\text{ Hz}$ 频权寻峰 | 避免无符号模值整流导致的倍频失真，精准定位机械结构谐振主频 |
| `resonanceBandRmsMm` | 主谐振峰 $\pm 15\text{ Hz}$ 频带积分有效值 | 定量评估 FIR 频谱零点与伺服陷波器对机械颤振的抑制效果 |

## 3. 三层灰盒物理 + 残差混合建模数学体系（`greybox_model.py`）

对任一质量指标 $m$、任意参考刀路几何画像 $\mathcal{G}(\text{Case})$ 与 32 维参数向量 $\boldsymbol{\theta} = (\boldsymbol{\theta}_{G1}, \boldsymbol{\theta}_{G2}, \boldsymbol{\theta}_{G3})$，预测模型统一表述为：

$$\hat{y}_m(\boldsymbol{\theta}; \mathcal{G}) = \underbrace{f_m^{\text{GB}}\!\left(\boldsymbol{\theta}, \mathcal{G}; \hat{\boldsymbol{\phi}}\right)}_{\text{Layer 1+2: 解析物理核 + 灰盒标定常数}} + \underbrace{\hat{r}_m^{\text{GP}}\!\left(\mathbf{z}_m(\boldsymbol{\theta}, \mathcal{G})\right)}_{\text{Layer 3: 3D-6D 物理特征残差 ARD-GP}}$$

### 3.1 第一层：零轨迹白盒解析物理主干 $f_m^{\text{GB}}$

`extract_case_geometry_profile(case)` 仅读取 `CncBenchmarkCase` 的参考几何（直线、三维螺旋/平面圆弧、拐角顶角与角平分线方向、微线段簇特征弦长），无需运行仿真即可计算：

1. **分段硬取小稳态速度包络**（严格保留死区平台）：
   $$v_k = \min\!\left(\eta_{\text{feed}} F_{\text{prog}},\; \min_{i \in \{x,y,z\}} \frac{V_{\max,i}}{|u_{k,i}|},\; \eta_{\text{curv}}\sqrt{A_n R_k},\; \sqrt{2 \phi_{\text{la}} a_{\text{eff},k} N_{\text{la}} \bar{\ell}_k}\right)$$
2. **拐角内切样条有效曲率半径与滤波后谷值速度卷积**：
   $$R_{\text{eff},c} = \phi_{\text{spl}}(p_{\text{deg}}) \cdot \frac{\varepsilon_{\text{cor}} \cos(\theta_c / 2)}{1 - \cos(\theta_c / 2)}, \qquad v_{c,\text{post}} = \eta_{\text{scurve}} \left(v_c + \phi_{\text{valley}} a_{\text{eff}} \frac{\max(0, \tau_{\text{eff}} - \frac{1}{2} t_{\text{blend}})^2}{4 \tau_{\text{eff}}}\right)$$
3. **前后向加减速速度传播与运动总时长**：
   沿几何段序列执行前向可达速度递推 $v_{k+1} \le \sqrt{v_k^2 + 2 a_{\text{eff},k} L_k}$ 与后向制动回溯，叠加钟形加减速平滑裕度 $\phi_{\text{bell}} \beta_{\text{bell}}$、S 曲线加加速尾项 $\phi_j a_{\text{eff}} / J_t$ 以及因果滤波器群延迟 $\tau_{\text{FIR}} + \sqrt{2}/\omega_{\text{LP}}$。
4. **圆弧解析滤波内缩（FIR `sinc` $\times$ 二阶 Butterworth）**：
   $$\Delta R_{\text{cmd}}(v, R) = R \left[1 - \operatorname{sinc}\!\left(\frac{v \tau_{\text{FIR}}}{2 R}\right) \cdot \frac{1}{\sqrt{1 + (v / (R \omega_{\text{LP}}))^4}}\right]$$
5. **级联 P-PI 伺服跟踪误差与二阶曲率-延迟带符号法向叠加**：
   对单轴级联位置-速度环（速度环等效带宽 $\omega_{v,i} = \psi_{v,i} K_{p,i}$），低频渐近展开给出精确一阶速度滞后系数 $c_{v,i} = \frac{1 - k_{vf,i}}{K_{p,i}}$ 与二阶加速度滞后系数 $c_{a,i} = \frac{1 - k_{af,i}}{\psi_{v,i} K_{p,i}^2} - \frac{1 - k_{vf,i}}{K_{p,i}^2}$。在曲率半径 $R$ 上，包含切向延迟沿曲线二阶弯曲补偿项后的**净向内法向伺服偏移**为：
   $$\delta_{n,\text{inward}}^{\text{servo}} = -\left(\bar{c}_a + \frac{1}{2}\bar{c}_v^2\right) a_{\text{norm}}$$
   当 $k_{vf}=1, k_{af}<1$ 时 $\delta_{n,\text{inward}}^{\text{servo}} < 0$（伺服惯量外摆抵消部分内切削角 $|e_{\text{cmd}} + \delta_{n,\text{inward}}^{\text{servo}}|$）；当 $k_{vf}<1$ 时切向滞后二阶项占优导致向内收缩叠加，同时叠加双轴增益失配项 $v |c_{v,x} - c_{v,y}| b_x b_y$。
6. **过象限静摩擦突跳与结构谐振频域调制**：
   $$\hat{e}_{\text{quad}} = \max_{i \in \{x,y\}} \left|\phi_{\text{stick},i}\frac{60}{K_{p,i}}\sqrt{\frac{a_{\text{rev}}}{2500}} - A_{\text{fric},i}\right|, \quad \hat{e}_{\text{vib}} \propto \left|\operatorname{sinc}(\pi f_{\text{res}} \tau_{\text{FIR}})\right| \cdot |H_{\text{LP}}(j 2\pi f_{\text{res}})| \cdot \left(1 - 0.85 e^{-\frac{(f_{\text{notch}} - f_{\text{res}})^2}{2 \sigma_n^2}}\right)$$

### 3.2 第二层：小样本受约束灰盒参数标定（`calibrate_greybox_constants`）

- **闭式时序最小二乘辨识伺服内环**：利用实采轨迹指令与反馈序列，通过有界线性最小二乘 `scipy.optimize.lsq_linear` 直接从时序信号 $e_i(t) - c_{v,i}\dot{q}_i + \frac{1-k_{vf,i}}{K_{p,i}^2}\ddot{q}_i = \frac{1}{\psi_{v,i}}\frac{1-k_{af,i}}{K_{p,i}^2}\ddot{q}_i$ 辨识各轴速度环带宽比 $\psi_{v,i} \in [0.8, 15]$，无需消耗额外试验组数。
- **有界信赖域反射标定**：通过 `scipy.optimize.least_squares(..., method="trf")` 在严格物理上下界内联合标定样条曲率系数、前瞻安全裕度、拐角谷值平滑系数、Stribeck 脱开基准与谐振柔度增益。

### 3.3 第三层：低维最大边缘似然 ARD Matérn-5/2 GP 残差与留一验证

- 对灰盒剥离后的残差 $r_m = y_m^{\text{obs}} - f_m^{\text{GB}}$，仅在物理因果筛选出的 **3～6 维活跃特征与物理无量纲桥接特征**（如 `derived.kp_xy_mismatch`、`phys.firResonanceGain`、`phys.notchSuppression`）上，通过 `L-BFGS-B` 最大化精确对数边缘似然（Log Marginal Likelihood）拟合各向异性 Matérn-5/2 高斯过程。
- 结合留一法（LOO）异方差自适应 Split Conformal 校准半径 $q_{1-\alpha} \cdot (0.45 + 0.55 \sigma_{\text{GP}} / \sigma_0)$ 输出保守安全上界。
- 当传入 $\ge 2$ 条校准刀路时，自动执行 **跨刀路留一交叉验证（LOCO，`CrossToolpathValidationSummary`）**，输出未见刀路上的零样本时长 MAPE 与轮廓误差 RMSE。

## 4. `R0–R7` 统一安全治理桥接（`cnc_governance.py`）

为彻底消除 CNC 参数优化工作流与 `Axiom` 核心证据框架之间的架构断层，`cnc_governance.py` 将三层灰盒闭环接入通用 `DomainPack` 与 `RunBundle` 主干：

1. **领域包注册**：公开注册 `cnc-greybox.domain-pack@1` 与 `DomainRuntimeBinding`，可通过公共 `axiom.evaluate_run(run_spec)` 直接复算并封存 SHA-256 `RunBundle`。
2. **显式 Artifact 转换与 R3 只读遥测接入**：
   - 注册 `cnc.export-to-ordered-point@1` 适配器，完整记录保留语义与丢弃语义哈希；
   - 提供 `adapt_r3_telemetry_to_cnc_export`，将 R3 只读 `MachineTelemetryTrace` 确定性投影为 `controller-trace` 导出，若检测到非 `file-import` 写操作或序号断裂则立即阻断。
3. **四层标准声明（Claims）与权限天花板**：
   - `cnc-greybox.sampled-limits-claim@1`（L0 采样硬限门禁）；
   - `cnc-greybox.r4-calibration-claim@1`（R4 灰盒物理标定有效性）；
   - `cnc-greybox.r5-epistemic-claim@1`（R5 适用域包络与 Split Conformal 保守上界闭合）；
   - `cnc-greybox.r7-zero-write-advisory-claim@1`（R6/R7 锁定 `OfflineAdvisory`、`deviceWriteAllowed=False`，并保持 `DeploymentShadow / ControlledTrial / ClosedLoop = Open`、`DeviceSafe = NotAssessed`）。

## 5. CLI、HTTP API 与跨刀路零样本推荐工作流

### 5.1 最小正交灰盒定参 + 跨刀路零样本推荐（CLI）

```powershell
# 1. 生成五条 V1 标准校准刀路（直线、整圆、90°拐角、密集小线段、S曲线）
axiom benchmark-standard-cases --out-dir v1 --feed 3000 --period 0.002

# 2. 生成正交物理激励试验表（仅需 10 组离线 + 6 组控制器实采即可完成全参数物理标定）
axiom param-doe --mode orthogonal-greybox --offline-count 10 --controller-count 6 --out doe_plan.json

# 3. 多刀路联合标定三层灰盒模型（自动输出物理辨识常数与跨刀路 LOCO 留一验证报告）
axiom param-learn `
  --case v1/line.case.json `
  --case v1/circle.case.json `
  --case v1/corner90.case.json `
  --case v1/micro200.case.json `
  --case v1/scurve.case.json `
  --export exports/run_01.json --export exports/run_02.json `
  --out-model machine_greybox_model.json --format table

# 4. 针对任意未采集过的新零件刀路（unseen_part.case.json）直接零样本推荐 Top-4 稀疏微调参数
axiom param-recommend `
  --model machine_greybox_model.json `
  --target-case unseen_part.case.json `
  --max-changed-params 4 `
  --max-actual-path-deviation-mm 0.035 `
  --format table

# 5. 一键体验多工况灰盒标定闭环或输出 R0-R7 封存治理证书
axiom param-demo --multi-case --format table
axiom param-governance --multi-case
```

### 5.2 FastAPI 端点一览

- `POST /api/v1/benchmarks/cnc/evaluate`：单次双源轨迹 Frenet 正交误差解耦、抗噪 Jerk 与 FFT 谐振诊断。
- `GET /api/v1/benchmarks/cnc/param-doe?mode=orthogonal-greybox`：生成物理正交激励定参试验表。
- `POST /api/v1/benchmarks/cnc/param-learn`：支持单 `case` 或多 `cases` 联合灰盒标定与 LOCO 验证。
- `POST /api/v1/benchmarks/cnc/param-recommend`：支持传入新零件 `targetCase` 执行跨刀路零样本三档 Pareto 稀疏推荐。
- `GET /api/v1/benchmarks/cnc/param-demo?multiCase=true`：端到端 32 维参数多工况灰盒闭环演示。
- `GET /api/v1/benchmarks/cnc/param-governance` & `POST /api/v1/benchmarks/cnc/param-governance`：执行 `cnc-greybox.domain-pack@1` 并返回封存 `RunBundle` 与四层治理声明。
