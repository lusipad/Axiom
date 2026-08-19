# Axiom 数学基础 v1.0

> 文档类型：理论基础与规范上位约束  
> 状态：Draft / Proposed  
> 适用范围：Axiom v1 的实验、评价、模型验证、证据与决策语义  
> 当前结论：本文件建立可实现、可证伪的数学骨架；它不是对真实设备安全性的证明  
> 更新日期：2026-08-19

## 1. 文档目的

Axiom v1 不再以“输入数据后计算若干指标”为理论中心，而以**不同表示层之间的有界声明迁移**为中心：

```text
理想数学对象
→ 数值求解结果
→ 固定周期离散命令
→ Orion / 物理模型响应
→ 真实控制器与机床响应
→ 测量与采集结果
→ 有限适用域内的工程声明
```

每一次转换都可能引入数值误差、离散化误差、时间与坐标对齐误差、模型结构误差、测量误差和统计不确定性。Axiom 的根本任务是回答：

> 在什么明确条件下，一个关于数学模型、仿真或有限试验的结论，能够迁移为关于真实 CNC 的有限范围结论？

本文件给出：

1. CNC 的混合系统与几何语义；
2. 多通道 Trace、距离与性质鲁棒度；
3. 可信度证书及其组合代数；
4. 数值、离散、模型、测量和统计误差的统一边界；
5. 声明迁移、算法排序迁移和连续区间证明的核心定理；
6. 每种正向 Claim 必须关闭的 Proof Obligations；
7. 能够推翻当前结论的反例和失败条件。

## 2. 核心研究问题

设算法或系统版本为 \(A,B\)，离线或仿真评价指标为 \(\widehat J\)，真实设备评价指标为 \(J\)。Axiom 的核心科学问题不是：

> 仿真曲线与实机曲线看起来是否接近？

而是：

> 当 Axiom 依据数学或仿真证据判定 \(B\) 优于 \(A\) 时，这一排序在声明的设备、控制器、轨迹族和工况范围内是否仍成立？

形式化地，若越小越好：

\[
\widehat\Delta
=
\widehat J(B)-\widehat J(A),
\qquad
\Delta
=
J(B)-J(A)
\]

Axiom 只有在证明或验证：

\[
\widehat\Delta + B_{\mathrm{transfer}} < -\delta_{\min}
\]

时，才允许产生“真实系统至少改善 \(\delta_{\min}\)”的正向 Claim。其中 \(B_{\mathrm{transfer}}\) 是从模型、离散、对齐、测量和统计不确定度组合得到的保守上界。

## 3. Axiom Margin Principle

Axiom v1 的第一原则是：

\[
\boxed{
\text{没有超过总不确定度的裕量，就没有可迁移的正向结论。}
}
\]

对于性质 \(arphi\)，设模型或观测 Trace 的鲁棒裕量为 \(ho_\varphi(\widehat\tau)\)，端到端迁移界为 \(B\)。只有当：

\[
\rho_\varphi(\widehat\tau)>B
\]

时，才能把该性质迁移到目标真实 Trace。若只知道 \(ho_\varphi(\widehat\tau)>0\)，但不知道它是否大于迁移误差，则结论只能是 `Inconclusive`。

## 4. 基本对象与符号

### 4.1 适用域

一个适用域定义为：

\[
D
\subseteq
D_{machine}
\times D_{controller}
\times D_{trajectory}
\times D_{process}
\times D_{environment}
\times D_{measurement}
\]

它至少冻结：

- 机床、机构、驱动和固件身份；
- 控制器版本与插补周期；
- 轨迹族、速度和加速度范围；
- 负载、工艺和夹具条件；
- 温度、暖机与环境范围；
- 采集、计量、时钟和坐标配置。

不存在脱离适用域的 `ModelValidated=true`。所有 Claim 都必须携带 \(D\)。

### 4.2 CNC 的随机混合系统语义

一个 CNC、PLC、伺服与机床组合建模为：

\[
\mathcal H=
(
\mathcal M,
\{X_m\}_{m\in\mathcal M},
U,W,\Theta,
F,G,R,H,\mu_0
)
\]

其中：

- \(\mathcal M\)：离散模式，例如 `Idle`、`Run`、`Hold`、`Stopping`、`Fault`；
- \(X_m\)：模式 \(m\) 下的连续状态空间；
- \(U\)：控制输入；
- \(W\)：扰动；
- \(\Theta\)：设备与模型参数；
- \(F\)：连续动力学；
- \(G\)：模式转换 Guard；
- \(R\)：离散跳变 Reset；
- \(H\)：观测映射；
- \(\mu_0\)：初始状态分布。

连续演化可写为：

\[
dx_t=f_m(x_t,u_t,\theta,c)dt+\Sigma_m(x_t,u_t,\theta,c)dW_t
\]

事件 \(e\) 触发时：

\[
m^+=\Gamma_e(m^-),
\qquad
x^+=R_e(x^-,u^-,\theta)
\]

设备观测为：

\[
z_k=h_m(x(t_k),\eta,c)+\nu_k
\]

本语义要求连续信号、离散事件、运行模式和时钟同时成为一等对象；任何仅使用点序列的领域包都只是该语义的一个投影。

### 4.3 配置空间和任务空间

对 \(n_l\) 个直线轴和 \(n_r\) 个旋转轴：

\[
Q=\mathbb R^{n_l}\times\mathbb T^{n_r}
\]

考虑机械限位和有效配置后：

\[
Q_{adm}\subset Q
\]

刀具相对工件的位姿属于 \(SE(3)\)，正向运动学是：

\[
F:Q_{adm}\rightarrow SE(3)
\]

其微分：

\[
dF_q:T_qQ\rightarrow T_{F(q)}SE(3)
\]

在局部坐标中表示为雅可比 \(J(q)\)。奇异集合为：

\[
\Sigma=
\{q\in Q_{adm}:\operatorname{rank}J(q)<r\}
\]

这里 \(r\) 是当前任务所需的局部维数，不应无条件固定为 6。

### 4.4 约束路径提升

给定任务空间路径：

\[
\gamma:[0,1]\rightarrow SE(3)
\]

其五轴可行性不是“每个离散点都存在逆解”，而是存在连续提升：

\[
q:[0,1]\rightarrow Q_{adm}
\]

满足：

\[
F(q(s))=\gamma(s),
\quad
q(s)\notin\Sigma,
\quad
q(s)\in Q_{free}
\]

路径提升集合定义为：

\[
\mathcal L(\gamma)=
\left\{
q\in W^{3,\infty}([0,1],Q_{adm})
\mid
F(q(s))=\gamma(s),
q(s)\in Q_{free},
q(0)\in B_0
\right\}
\]

运动学可行性是：

\[
\mathcal L(\gamma)\neq\varnothing
\]

它同时要求分支连续、远离奇异集合、满足配置空间碰撞和轴限位，并具有后续 Jerk 时间参数化所需的正则性。

## 5. Trace 空间

### 5.1 多通道 TraceBundle

一个运行观测不是单一 Artifact，而是：

\[
\mathcal T=
(
\{\tau_c\}_{c\in C},
\mathcal K,
\mathcal F,
\mathcal E,
P
)
\]

其中：

- \(C\)：通道集合；
- \(	au_c:[0,T_c]\rightarrow Y_c\)：通道 Trace；
- \(\mathcal K\)：ClockGraph；
- \(\mathcal F\)：FrameGraph；
- \(\mathcal E\)：事件与模式 Trace；
- \(P\)：Provenance。

每个值空间 \(Y_c\) 必须声明单位、类型和度量 \(d_c\)。典型通道包括：

- `SignalTrace<T>`：位置、速度、电流、温度；
- `EventTrace`：启动、停止、报警、Reset、控制权请求；
- `ModeTrace`：CNC、PLC、轴和设备模式区间；
- `TrajectoryTrace`：任务空间或轴空间轨迹；
- `MeasurementTrace`：外部计量数据与不确定度。

### 5.2 Trace 距离

Axiom 不定义一个跨所有领域的万能距离。每个 Comparator 必须声明：

\[
(\mathcal T,d_{\mathcal T})
\]

对于允许有限时间扭曲的连续或分段连续 Trace，可使用 Skorokhod 型距离：

\[
d_{Sk}(\tau_1,\tau_2)
=
\inf_{\lambda\in\Lambda}
\max
\left\{
\|\lambda-id\|_\infty,
\sup_t d_Y(\tau_1(t),\tau_2(\lambda(t)))
\right\}
\]

其中 \(\Lambda\) 为严格单调、端点保持的时间重参数化集合。若评价的是控制器固定采样语义，则必须限制或禁用重参数化，避免把真实超时“对齐掉”。

多通道距离可以定义为：

\[
d_{bundle}(\mathcal T_1,\mathcal T_2)
=
\max_{c\in C}w_c d_c(\tau_{1c},\tau_{2c})
\]

但权重 \(w_c\) 只能在单位、业务含义和 Claim 中显式声明；默认情况下，线性轴、旋转轴、事件和状态不得被压缩为一个标量总分。

## 6. 性质、鲁棒度和 Claim

### 6.1 性质鲁棒度

一个性质 \(arphi\) 对 Trace 的定量语义为：

\[
\rho_\varphi:\mathcal T\rightarrow\mathbb R
\]

约定：

- \(ho_\varphi(\tau)>0\)：满足；
- \(ho_\varphi(\tau)<0\)：违反；
- \(|\rho_\varphi(\tau)|\)：到性质边界的裕量。

例如跟随误差约束：

\[
\varphi_{fe}
=
\mathbf G_{[0,T]}(|e_f(t)|\le e_{max})
\]

控制权唯一性：

\[
\varphi_{owner}
=
\mathbf G
\left(
\sum_{s\in Sources}owner(axis,s)\le1
\right)
\]

紧停后进入安全停止模式：

\[
\varphi_{stop}
=
\mathbf G
\left(
EmergencyStop
\rightarrow
\mathbf F_{[0,T_s]}SafeStopped
\right)
\]

### 6.2 Claim

一个 Claim 定义为：

\[
C=(\phi,D,I,K,A)
\]

其中：

- \(\phi\)：命题；
- \(D\)：适用域；
- \(I\)：预期用途；
- \(K\)：可信度描述；
- \(A\)：依赖的 Argument。

Claim 的结论状态只允许：

```text
Supported
Refuted
Inconclusive
```

`Supported` 不等于全局真理，只表示在 \(D\)、\(I\)、冻结假设和当前证据下，Argument 已满足声明的接受规则。

## 7. 可信度证书

### 7.1 定义

从表示层 \(X\) 到 \(Y\) 的可信度证书定义为：

\[
\mathcal C_{X\to Y}
=
(
D,
R,
d,
\varepsilon,
\alpha,
A,
M,
P
)
\]

其中：

- \(D\)：适用域；
- \(R\subseteq X\times Y\)：对应关系；
- \(d\)：比较距离；
- \(arepsilon\ge0\)：误差界；
- \(\alpha\in[0,1]\)：界失效风险上界；
- \(A\)：成立所需假设；
- \(M\)：证明、验证、测量或统计方法；
- \(P\)：Provenance。

语义为：对 \(D\) 内的有效输入，有：

\[
\Pr[d(x,y)\le\varepsilon]\ge1-\alpha
\]

演绎证明可取 \(\alpha=0\)，但仍必须记录证明依赖、数值类型和模型假设；真实观测证书通常有 \(\alpha>0\)，且必须记录测量模型。

### 7.2 证书种类

`methodKind` 至少区分：

```text
Deductive
IntervalCertified
NumericallyVerified
StatisticallyValidated
DirectlyObserved
```

这些类别不是从强到弱的单一等级。一个针对简化方程的演绎证明和一个独立外部计量结果支持的是不同命题，不能用 `Exact > Observed` 的线性枚举比较。

### 7.3 证书偏序

对相同关系、距离和假设族，定义：

\[
\mathcal C_1\succeq\mathcal C_2
\]

当且仅当：

\[
D_1\supseteq D_2,
\qquad
\varepsilon_1\le\varepsilon_2,
\qquad
\alpha_1\le\alpha_2
\]

并且 \(\mathcal C_1\) 的假设不比 \(\mathcal C_2\) 更强。该关系是偏序，不是总序；大量证书彼此不可比较。

## 8. 八条基础公理

### AX-01 预期用途公理

模型、指标和证书只能相对于明确的 Intended Use 评价，不存在无条件“有效模型”。

### AX-02 类型与量纲公理

任何比较、组合和阈值必须在类型、单位、Frame、Clock 和重建语义兼容后进行；禁止依赖数组形状推断语义。

### AX-03 Raw 不可变公理

插值、滤波、对齐、单位转换、坐标转换和异常剔除都产生新的 Derived Trace 和内容身份，不得改写原始观测。

### AX-04 独立证据公理

Subject 自身生成的结论不能作为独立验证证据；Reference、Verifier、Calibration 和 Validation 的身份边界必须可审计。

### AX-05 裕量公理

正向 Claim 的鲁棒裕量必须严格大于组合迁移界，否则结论为 `Inconclusive`。

### AX-06 显式变换公理

跨层和跨领域变换必须有版本化 Adapter、源/目标身份、保留语义、丢弃语义和误差证书。

### AX-07 有限外推公理

真实证据只能支持其覆盖的适用域及经证明的邻域，不能因模型形式或学习器表达能力而自动外推。

### AX-08 权限分离公理

Optimizer 提出候选、Evaluator 评价候选、DecisionPolicy 处置候选、设备权限方执行候选；四者不得由一个未经独立约束的角色合并。

## 9. 核心定理

### 定理 T1：证书域限制单调性

若证书 \(\mathcal C=(D,R,d,\varepsilon,\alpha,A,M,P)\) 成立，且 \(D'\subseteq D\)，则：

\[
\mathcal C|_{D'}=(D',R,d,\varepsilon,\alpha,A,M,P)
\]

仍成立。

**证明。** 原证书的概率界对 \(D\) 中所有有效输入成立，因此也对其子集 \(D'\) 中的所有输入成立。证毕。

该定理只允许收缩适用域，不允许在没有额外证据时扩大适用域。

### 定理 T2：证书链组合定理

设：

\[
x_0,x_1,\ldots,x_n\in(\mathcal T,d)
\]

且每一层证书满足：

\[
\Pr[d(x_{i-1},x_i)\le\varepsilon_i]\ge1-\alpha_i
\]

则：

\[
\Pr
\left[
 d(x_0,x_n)\le\sum_{i=1}^n\varepsilon_i
\right]
\ge
1-\min\left(1,\sum_{i=1}^n\alpha_i\right)
\]

适用域为各层证书适用域的交集。

**证明。** 令事件 \(E_i=\{d(x_{i-1},x_i)\le\varepsilon_i\}\)。在 \(\cap_iE_i\) 上，由三角不等式：

\[
d(x_0,x_n)
\le
\sum_i d(x_{i-1},x_i)
\le
\sum_i\varepsilon_i
\]

由 union bound：

\[
\Pr[\cap_iE_i]
=1-\Pr[\cup_iE_i^c]
\ge1-\sum_i\Pr[E_i^c]
\ge1-\sum_i\alpha_i
\]

并将下界截断到 \([0,1]\)。证毕。

除非明确证明独立性或其他联合分布结构，Axiom 默认使用该保守风险组合，不得擅自相乘概率。

### 定理 T3：Lipschitz 指标迁移定理

若 \(J:(\mathcal T,d)\rightarrow\mathbb R\) 是 \(L_J\)-Lipschitz：

\[
|J(x)-J(y)|\le L_Jd(x,y)
\]

且证书给出：

\[
\Pr[d(x,y)\le\varepsilon]\ge1-\alpha
\]

则：

\[
\Pr[|J(x)-J(y)|\le L_J\varepsilon]\ge1-\alpha
\]

**证明。** 在事件 \(d(x,y)\le\varepsilon\) 上，直接应用 Lipschitz 条件。证毕。

若指标不连续或无法给出局部连续模，则不得使用该定理迁移排序。

### 定理 T4：算法排序迁移定理

设越小越好，模型 Trace 为 \(\widehat\tau_A,\widehat\tau_B\)，真实 Trace 为 \(	au_A,	au_B\)。若：

\[
d(\tau_A,\widehat\tau_A)\le\varepsilon_A
\]

\[
d(\tau_B,\widehat\tau_B)\le\varepsilon_B
\]

且 \(J\) 为 \(L_J\)-Lipschitz，定义：

\[
\widehat\Delta
=J(\widehat\tau_B)-J(\widehat\tau_A)
\]

\[
\Delta
=J(\tau_B)-J(\tau_A)
\]

则：

\[
|\Delta-\widehat\Delta|
\le
L_J(\varepsilon_A+\varepsilon_B)
\]

因此，如果：

\[
\widehat\Delta
+L_J(\varepsilon_A+\varepsilon_B)
<-\delta
\]

则：

\[
\Delta<-\delta
\]

**证明。**

\[
\begin{aligned}
|\Delta-\widehat\Delta|
&=
|J(\tau_B)-J(\tau_A)-J(\widehat\tau_B)+J(\widehat\tau_A)|\\
&\le
|J(\tau_B)-J(\widehat\tau_B)|
+
|J(\tau_A)-J(\widehat\tau_A)|\\
&\le
L_J\varepsilon_B+L_J\varepsilon_A
\end{aligned}
\]

由上界重排即可得到充分条件。证毕。

若两个 Trace 证书风险分别为 \(\alpha_A,\alpha_B\)，则该排序结论的失效风险上界为 \(\alpha_A+\alpha_B\)。

### 定理 T5：鲁棒性质迁移定理

设性质鲁棒度 \(ho_\varphi\) 满足连续模：

\[
|\rho_\varphi(x)-\rho_\varphi(y)|
\le
\omega_\varphi(d(x,y))
\]

且：

\[
d(x,y)\le\varepsilon
\]

则：

\[
\rho_\varphi(x)
\ge
\rho_\varphi(y)-\omega_\varphi(\varepsilon)
\]

如果：

\[
\rho_\varphi(y)>
\omega_\varphi(\varepsilon)
\]

则 \(ho_\varphi(x)>0\)，即 \(x\) 满足 \(arphi\)。

**证明。** 由绝对值不等式：

\[
\rho_\varphi(y)-\rho_\varphi(x)
\le
|\rho_\varphi(x)-\rho_\varphi(y)|
\le
\omega_\varphi(\varepsilon)
\]

重排得到第一式，第二式随即成立。证毕。

### 定理 T6：共同坐标系左变换不变性

定义两个位姿的相对变换：

\[
E(T_1,T_2)=T_1^{-1}T_2
\]

对任意共同 Frame 变换 \(G\in SE(3)\)：

\[
E(GT_1,GT_2)=E(T_1,T_2)
\]

**证明。**

\[
E(GT_1,GT_2)
=(GT_1)^{-1}(GT_2)
=T_1^{-1}G^{-1}GT_2
=T_1^{-1}T_2
\]

证毕。

因此基于相对变换本身构造的误差在共同世界坐标系变换下保持不变。若进一步对 \(\log(E)\) 使用加权范数，权重和特征长度必须显式冻结；本定理不意味着 \(SE(3)\) 上存在适用于一切任务的默认标量距离。

### 定理 T7：分段线性重建误差界

设 \(q:[t_k,t_{k+1}]\rightarrow\mathbb R^n\) 二阶连续可微，区间长度 \(h=t_{k+1}-t_k\)，\(I_hq\) 为端点分段线性插值。则：

\[
\|q-I_hq\|_\infty
\le
\frac{h^2}{8}
\|q''\|_\infty
\]

其中向量范数和诱导的函数上确界范数必须一致。

**证明。** 对任一标量分量，线性插值余项可写为：

\[
q_i(t)-(I_hq_i)(t)
=
\frac{q_i''(\xi_t)}{2}(t-t_k)(t-t_{k+1})
\]

而：

\[
\max_{t\in[t_k,t_{k+1}]}
|(t-t_k)(t-t_{k+1})|
=\frac{h^2}{4}
\]

故每个分量误差不超过 \(h^2\|q_i''\|_\infty/8\)，组合到一致向量范数得到结论。证毕。

若控制器采用 ZOH，则必须改用对应的一阶界，例如：

\[
\|q-ZOH_h(q)\|_\infty
\le h\|\dot q\|_\infty
\]

不得把分段线性界套到 ZOH 语义上。

### 定理 T8：连续区间净空证书

设净空函数：

\[
c:Q\rightarrow\mathbb R
\]

满足 \(c(q)>0\) 表示无碰撞，并且是 \(L_c\)-Lipschitz：

\[
|c(q_1)-c(q_2)|\le L_c\|q_1-q_2\|
\]

若在区间 \([t_k,t_{k+1}]\) 有已证明的轨迹管界：

\[
\|q(t)-q_k\|\le r_k
\]

且：

\[
c(q_k)>L_cr_k
\]

则整个区间无碰撞。

**证明。** 对任意 \(t\)：

\[
c(q(t))
\ge
c(q_k)-|c(q(t))-c(q_k)|
\ge
c(q_k)-L_c\|q(t)-q_k\|
\ge
c(q_k)-L_cr_k
>0
\]

证毕。

这一定理说明“所有采样点无碰撞”本身不足以产生 `IntervalCertified`；还必须有区间轨迹管和净空连续性界。

### 定理 T9：鲁棒 Pareto 支配

考虑均为越小越好的 \(m\) 个目标。对候选 \(A,B\)，若真实目标分别位于区间：

\[
J_j(A)\in[\underline A_j,\overline A_j],
\qquad
J_j(B)\in[\underline B_j,\overline B_j]
\]

并且对所有 \(j\)：

\[
\overline B_j\le\underline A_j
\]

且至少一个目标严格小于，则 \(B\) 在所有与证书一致的真实取值上 Pareto 支配 \(A\)。

**证明。** 对任意允许取值：

\[
J_j(B)\le\overline B_j\le\underline A_j\le J_j(A)
\]

至少一个目标严格成立，因此根据 Pareto 支配定义得到结论。证毕。

若区间重叠，Axiom 只能报告可能支配或不可判定，不能靠任意权重制造确定排名。

### 定理 T10：有限数据不可无条件外推

设校准数据仅覆盖有限输入集合：

\[
S=\{x_1,\ldots,x_n\}\subset D
\]

且 \(x_*\in D\setminus S\)。在不施加连续性、光滑性、函数族或物理结构假设时，对于任意模型 \(f\) 和任意 \(M>0\)，都存在另一个函数 \(g\)，使：

\[
g(x_i)=f(x_i),\quad i=1,\ldots,n
\]

但：

\[
|g(x_*)-f(x_*)|>M
\]

**证明。** 构造一个在所有 \(x_i\) 上为 0、在 \(x_*\) 上为 1 的函数 \(b\)。令：

\[
g(x)=f(x)+(M+1)b(x)
\]

则 \(g\) 与 \(f\) 在全部校准点完全一致，但在 \(x_*\) 处相差 \(M+1\)。证毕。

因此，没有结构假设和覆盖证据时，训练误差或有限 holdout 不能证明任意未覆盖区域的现实可信度。

### 命题 T11：灵敏度秩亏的局部不可辨识性

设模型输出 \(y(\theta)\) 可微，灵敏度矩阵：

\[
S(\theta)=\frac{\partial y}{\partial\theta}
\]

若：

\[
\operatorname{rank}S(\theta)<\dim\theta
\]

则存在非零方向 \(v\)，满足：

\[
S(\theta)v=0
\]

并且：

\[
y(\theta+hv)=y(\theta)+o(h)
\]

即该参数方向在一阶近似下不可辨识。

**证明。** 秩亏意味着零空间中存在 \(v\neq0\)。由 Taylor 展开：

\[
y(\theta+hv)
=y(\theta)+hS(\theta)v+o(h)
=y(\theta)+o(h)
\]

证毕。

满秩通常只是局部可辨识的必要条件之一，不自动证明全局唯一性。

## 10. 时间参数化的数学契约

给定几何轴路径 \(q(s)\) 和时间律 \(s(t)\)：

\[
s(0)=0,
\quad
s(T)=1,
\quad
\dot s(t)\ge0
\]

轴导数必须按链式法则计算：

\[
\dot q=q'(s)\dot s
\]

\[
\ddot q=q''(s)\dot s^2+q'(s)\ddot s
\]

\[
\dddot q=q'''(s)\dot s^3+3q''(s)\dot s\ddot s+q'(s)\dddot s
\]

时间规划问题是：

\[
\min_{s(\cdot)}T
\]

subject to：

\[
|\dot q_i|\le v_i^{max},
\quad
|\ddot q_i|\le a_i^{max},
\quad
|\dddot q_i|\le j_i^{max}
\]

以及驱动力、奇异性、碰撞和工艺约束。Axiom 必须区分：

1. 找到一个数值时间律；
2. 离散节点满足约束；
3. 连续区间满足约束；
4. 参数扰动后仍鲁棒满足约束。

四者不得共用一个 `Passed`。

## 11. 物理模型、偏差与测量

真实观测应建模为：

\[
y^{obs}(u,c)
=
\mathcal M(u,\theta,c)
+
\delta(u,c)
+
\epsilon(u,c)
\]

其中：

- \(\mathcal M\)：Orion 或候选机床模型；
- \(	heta\)：可校准参数；
- \(\delta\)：模型结构偏差；
- \(\epsilon\)：测量误差。

禁止把全部 \(\delta\) 吸收到 \(	heta\) 并把低训练误差解释为物理参数已识别。当前逐轴一阶滞后模型应作为 Null Model：复杂模型只有在独立 holdout、残差诊断和不确定度覆盖上显著优于该基线时，才有资格增加复杂度。

测量模型写为：

\[
z=g(y,\eta)
\]

一阶不确定度传播为：

\[
\Sigma_z
\approx
J_g\Sigma_\eta J_g^\mathsf T
\]

实机 MetricResult 至少需要：

```text
measurand
estimate
standardUncertainty
coverageInterval
coverageProbability
uncertaintyBudget
measurementModelId
```

## 12. 配对算法比较规则

对场景 \(i\)、重复 \(j\)，定义配对差异：

\[
D_{ij}=J(\tau_{B,ij})-J(\tau_{A,ij})
\]

统计分析计划必须在读取 validation 结果前冻结。可以使用层次模型、配对 bootstrap、随机化检验或其他明确方法，但正向结论必须同时满足：

1. 数学和设备硬约束通过；
2. Calibration 与 Validation 无谱系重叠；
3. 差异的统计不确定度已量化；
4. 迁移界已加入；
5. 改善超过预声明的最小实际意义 \(\delta_{min}\)。

若差异置信集合为 \(\mathcal I_{1-\alpha}\)，越小越好，则充分接受规则为：

\[
\sup\mathcal I_{1-\alpha}
+
B_{transfer}
<
-\delta_{min}
\]

P 值不能替代效应量、实际意义、适用域和迁移误差。

## 13. Proof Obligation Catalog

| 编号 | 证明义务 | 最低输出 |
|---|---|---|
| PO-01 | 类型与 schema 一致性 | 有类型解析证据 |
| PO-02 | 单位一致性 | 量纲检查与转换谱系 |
| PO-03 | Frame 客观性 | FrameGraph 与不变性说明 |
| PO-04 | Clock 可比性 | 时钟源、偏置和抖动界 |
| PO-05 | 数值有限性 | NaN/Inf/overflow 排除 |
| PO-06 | 数值算法实现正确性 | 独立 Oracle 或证明 |
| PO-07 | 数值误差 | \(arepsilon_{num}\) |
| PO-08 | 路径正则性 | 连续性与导数条件 |
| PO-09 | 路径提升存在 | \(\mathcal L(\gamma)\neq\varnothing\) |
| PO-10 | IK 分支连续性 | 无未授权分支跳变 |
| PO-11 | 奇异性裕量 | \(\sigma_{min}(J)\ge\sigma_0\) 或等价证据 |
| PO-12 | 轴限位 | 连续区间限位证书 |
| PO-13 | 连续碰撞 | Clearance/tube 证书 |
| PO-14 | 连续速度约束 | 区间速度界 |
| PO-15 | 连续加速度约束 | 区间加速度界 |
| PO-16 | 连续 Jerk 约束 | 区间 Jerk 界 |
| PO-17 | 重建语义正确 | PWL/ZOH/控制器实际语义 |
| PO-18 | 离散重建误差 | \(arepsilon_{disc}\) |
| PO-19 | 采集完整性 | 序号、丢样和撕裂检测 |
| PO-20 | 时间对齐 | \(arepsilon_{time}\) |
| PO-21 | 坐标标定 | \(arepsilon_{frame}\) |
| PO-22 | 测量不确定度 | \(arepsilon_{meas},\alpha_{meas}\) |
| PO-23 | 激励覆盖 | 输入与频率覆盖报告 |
| PO-24 | 参数局部可辨识 | 灵敏度/FIM 诊断 |
| PO-25 | 残差结构 | 白噪声、相关性和异方差诊断 |
| PO-26 | Calibration/Validation 隔离 | 内容身份和时间窗证明 |
| PO-27 | 模型 holdout 一致性 | \(arepsilon_{model},\alpha_{model}\) |
| PO-28 | 适用域覆盖 | \(D_{claim}\subseteq D_{cert}\) |
| PO-29 | 性质鲁棒度 | \(ho_\varphi\) 与连续模 |
| PO-30 | 证书链组合 | 总 \(arepsilon\) 和总 \(\alpha\) |
| PO-31 | 排序迁移 | T4 的充分条件 |
| PO-32 | 决策权限 | Evaluator、Policy、Authority 分离 |

任何 ClaimDefinition 必须声明依赖哪些 PO。缺少任一必需 PO 时，不得静默降级为正向 Claim。

## 14. 典型 Claim 与证明依赖

### GeometryValid

至少依赖：PO-01、PO-02、PO-03、PO-05、PO-06、PO-07、PO-08。

### KinematicallyFeasible

至少依赖：GeometryValid 依赖项，加 PO-09、PO-10、PO-11、PO-12。

### IntervalCertified

至少依赖：PO-13 至 PO-18，且重建语义必须匹配实际执行器。

### ModelAdequateForOfflineRanking

至少依赖：PO-19 至 PO-31，并将 Intended Use 限定为“离线算法排序”。它不能推出 `DeviceSafe`。

### AlgorithmBImprovesRealMetric

至少依赖：

- A、B 相同 Protocol 的配对运行；
- 全部硬约束 Claim；
- 测量和模型证书；
- 统计差异区间；
- T4 排序迁移充分条件；
- 明确的 \(\delta_{min}\)。

## 15. 必须保留的反例

Axiom 的测试库必须包含以下最小反例：

1. 所有采样点无碰撞，但区间内部碰撞；
2. 每个点均有 IK 解，但不存在连续分支提升；
3. 毫米和弧度被直接相加后生成错误排名；
4. 训练误差极低，但 holdout 结构性偏差明显；
5. 时钟对齐算法把真实超时重参数化消除；
6. Calibration 与 Validation 文件名不同，但内容窗口重叠；
7. 一阶模型通过自生成数据自证；
8. 模型 A/B 排序优势小于迁移误差，却错误发布优胜方；
9. 同一坐标值在不同 Frame 下被错误比较；
10. FIM 秩亏却输出唯一物理参数；
11. PWL 误差界被错误用于 ZOH；
12. 单一总分掩盖一个硬约束失败。

## 16. 数学成熟度路线

| 阶段 | 数学目标 | 退出条件 |
|---|---|---|
| M0 | 类型、单位、Frame、Clock 语义 | PO-01 至 PO-05 闭合 |
| M1 | Trace 空间和 Comparator | 每个指标有明确空间与距离 |
| M2 | 数值和离散证书 | PO-06 至 PO-18 闭合 |
| M3 | 真实采集、辨识和测量 | PO-19 至 PO-26 闭合 |
| M4 | 模型一致性与性质迁移 | T2、T3、T5 可执行验证 |
| M5 | 算法排序迁移 | T4 条件在独立 holdout 上通过 |
| M6 | 跨工况和第二设备证伪 | 适用域扩展由新证据支持 |

`learning`、`optimization` 和 `controlled_runtime` 只能在 M5 通过后恢复为主线能力；在此之前保持 Experimental。

## 17. 与当前仓库的映射

### 保留

- 内容哈希与 Provenance；
- DomainPack 的显式类型和能力思想；
- 五轴 F1–F4 中的连续区间证据；
- Calibration/Validation 隔离；
- R3/R7-E 的只读采集和零写边界；
- 负例与 fail-closed 测试。

### 重构

- `OrderedPointSequence` 移出 Core，成为领域类型；
- 单一 `Observation` 升级为多通道 `TraceSet`；
- `Evidence.level` 拆成方法种类、适用域、误差、风险和独立性；
- `Claim` 增加 Argument、Assumption、Defeater；
- 一阶独立轴模型降级为 Null Model；
- R5–R7 先冻结为 Experimental；
- Core 不再依靠顶层导入副作用注册所有领域。

## 18. 限制和非声明

本文件没有证明：

- 任意五轴机床都能被当前模型覆盖；
- Skorokhod 距离适合所有 CNC 属性；
- 误差分量在统计上独立；
- 当前逐轴模型足以预测真实设备；
- 通过数学门的轨迹具备设备或工艺安全性；
- Axiom 可以承担 Safety PLC、设备写入或最终责任审批。

若某个定理的连续性、Lipschitz、可辨识、测量或适用域假设无法验证，结论必须降为 `Inconclusive`，而不是用经验阈值替代缺失证明。

## 19. 理论依据

### 模型可信度、验证与不确定性

1. NASA, *NASA-STD-7009B: Standard for Models and Simulations*.  
   https://standards.nasa.gov/standard/nasa/nasa-std-7009
2. NASA, *NASA-HDBK-7009B: An Implementation Guide for NASA-STD-7009B*, 2026.  
   https://standards.nasa.gov/standard/NASA/NASA-HDBK-7009
3. M. C. Kennedy and A. O’Hagan, “Bayesian Calibration of Computer Models,” *JRSS B*, 63(3), 425–464, 2001.  
   https://doi.org/10.1111/1467-9868.00294
4. M. J. Bayarri et al., “A Framework for Validation of Computer Models,” *Technometrics*, 49(2), 138–154, 2007.  
   https://doi.org/10.1198/004017007000000092
5. J. Brynjarsdóttir and A. O’Hagan, “Learning about Physical Parameters: The Importance of Model Discrepancy,” *Inverse Problems*, 30, 114007, 2014.  
   https://doi.org/10.1088/0266-5611/30/11/114007
6. JCGM, *Evaluation of Measurement Data — Guide to the Expression of Uncertainty in Measurement*, JCGM 100:2008.  
   https://doi.org/10.59161/JCGM100-2008E

### 系统辨识和试验设计

7. L. Ljung, “Prediction Error Estimation Methods,” *Circuits, Systems, and Signal Processing*, 21, 11–21, 2002.  
   https://doi.org/10.1007/BF01211648
8. H. Hjalmarsson, “From Experiment Design to Closed-Loop Control,” *Automatica*, 41(3), 393–438, 2005.  
   https://doi.org/10.1016/j.automatica.2004.11.021

### 混合系统、Trace 和时序逻辑

9. A. Platzer, “Differential Dynamic Logic for Hybrid Systems,” *Journal of Automated Reasoning*, 41, 143–189, 2008.  
   https://doi.org/10.1007/s10817-008-9103-8
10. G. E. Fainekos and G. J. Pappas, “Robustness of Temporal Logic Specifications for Continuous-Time Signals,” *Theoretical Computer Science*, 410(42), 4262–4291, 2009.  
    https://doi.org/10.1016/j.tcs.2009.06.021
11. A. Donzé and O. Maler, “Robust Satisfaction of Temporal Logic over Real-Valued Signals,” FORMATS 2010.  
    https://doi.org/10.1007/978-3-642-15297-9_9
12. J. V. Deshmukh, R. Majumdar, and V. S. Prabhu, “Quantifying Conformance Using the Skorokhod Metric,” *Formal Methods in System Design*, 50, 168–206, 2017.  
    https://doi.org/10.1007/s10703-016-0261-8

### 时间规划和 CNC

13. H. Pham and Q.-C. Pham, “A New Approach to Time-Optimal Path Parameterization Based on Reachability Analysis,” *IEEE Transactions on Robotics*, 2018.  
    https://arxiv.org/abs/1707.07239
14. K. Erkorkmaz and Y. Altintas, “High Speed CNC System Design. Part I: Jerk Limited Trajectory Generation and Quintic Spline Interpolation,” *International Journal of Machine Tools and Manufacture*, 41, 1323–1345, 2001.  
    https://doi.org/10.1016/S0890-6955(01)00002-5
15. K. Erkorkmaz and Y. Altintas, “High Speed CNC System Design. Part II: Modeling and Identification of Feed Drives,” *International Journal of Machine Tools and Manufacture*, 41, 1487–1509, 2001.  
    https://doi.org/10.1016/S0890-6955(01)00003-7
16. Y. Koren, “Cross-Coupled Biaxial Computer Control for Manufacturing Systems,” *Journal of Dynamic Systems, Measurement, and Control*, 102(4), 265–272, 1980.  
    https://doi.org/10.1115/1.3149612
17. ISO 230-4:2022, *Test Code for Machine Tools — Part 4: Circular Tests for Numerically Controlled Machine Tools*.  
    https://www.iso.org/standard/79155.html
18. ISO 10791-6:2014, *Test Conditions for Machining Centres — Part 6: Accuracy of Speeds and Interpolations*.  
    https://www.iso.org/standard/46440.html

## 20. 规范优先级

Axiom v1 后续项目规划、架构和实现必须满足本文件中的：

1. 八条基础公理；
2. 证书语义；
3. Margin Principle；
4. Proof Obligation Catalog；
5. 适用域与不确定度边界。

若现有 Roadmap、DomainPack、UI、优化或控制代码与本文件冲突，应先通过 ADR 明确取舍，不能让既有实现反向决定理论含义。
