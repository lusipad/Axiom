export type LabId =
  | "benchmark"
  | "point"
  | "five-axis-f1"
  | "five-axis-f2"
  | "five-axis-f3"
  | "five-axis-f4"
  | "machine-r3"
  | "physical-r4"
  | "intelligence-r5"
  | "intelligence-r5b"
  | "optimization-r6"
  | "control-r7"
  | "control-r7b"
  | "control-r7c"
  | "control-r7d"
  | "field-evidence";

export interface LabGuide {
  stage: string;
  stageIndex: number;
  stageQuestion: string;
  purpose: string;
  steps: string[];
  reads: string[];
  boundaryZh: string;
}

export interface StageInfo {
  name: string;
  question: string;
}

export const LAB_SHORT: Record<LabId, string> = {
  benchmark: "A/B 对比",
  point: "Point Lab",
  "five-axis-f1": "F1 几何",
  "five-axis-f2": "F2 运动学",
  "five-axis-f3": "F3 时间",
  "five-axis-f4": "F4 门禁",
  "machine-r3": "R3 画像",
  "physical-r4": "R4 物理",
  "intelligence-r5": "R5-A 合成",
  "intelligence-r5b": "R5-B 真实门",
  "optimization-r6": "R6 推荐",
  "control-r7": "R7-A 影子",
  "control-r7b": "R7-B 就绪",
  "control-r7c": "R7-C 传输",
  "control-r7d": "R7-D 厂商",
  "field-evidence": "R7-E 现场",
};

export const PIPELINE_ORDER: LabId[] = [
  "benchmark",
  "point",
  "five-axis-f1",
  "five-axis-f2",
  "five-axis-f3",
  "five-axis-f4",
  "machine-r3",
  "physical-r4",
  "intelligence-r5",
  "intelligence-r5b",
  "optimization-r6",
  "control-r7",
  "control-r7b",
  "control-r7c",
  "control-r7d",
  "field-evidence",
];

export const GUIDE_STAGES: StageInfo[] = [
  { name: "基础实验", question: "两个算法在同一输入下谁更好？" },
  { name: "数学参考", question: "路径与运动在数学上成立吗？" },
  { name: "设备画像", question: "从机床拿到的数据本身可信吗？" },
  { name: "物理验证", question: "仿真模型和真实运动一致吗？" },
  { name: "学习能力", question: "模型学到的是真规律吗？" },
  { name: "参数优化", question: "该调哪些参数、调多少？" },
  { name: "控制闭环", question: "敢不敢把算法放到真机旁运行？" },
  { name: "现场证据", question: "真实现场数据支持结论吗？" },
];

export const LAB_GUIDE: Record<LabId, LabGuide> = {
  benchmark: {
    stage: "基础实验",
    stageIndex: 0,
    stageQuestion: GUIDE_STAGES[0]!.question,
    purpose: "同一案例下比较两版 CNC 算法的轨迹质量",
    steps: [
      "导入或「载入回归示例」填入案例、基线 A、候选 B 三份 JSON",
      "点「比较 A / B」，等待报告生成",
      "先看结论徽章，再看差异表定位退步指标与超限样本",
    ],
    reads: [
      "结论徽章：改善 / 退步 / 存在取舍 / 候选超限，基于采样范围内的指标差异",
      "「约束检查与最差位置」表给出超限发生在哪个样本、哪一秒、哪个轴",
    ],
    boundaryZh: "只评估采样轨迹，不代表实机加工效果",
  },
  point: {
    stage: "基础实验",
    stageIndex: 0,
    stageQuestion: GUIDE_STAGES[0]!.question,
    purpose: "同一输入跑两个 Subject，严格比较输出与证据",
    steps: [
      "在左侧查看共享输入点序列与参数，可修改后点「运行实验」",
      "「几何轨迹」页签看两臂输出与参考的贴合程度",
      "「指标比较」页签看数值差异，右侧证据区核对声明与哈希",
    ],
    reads: [
      "结论徽章 Passed / Failed 由硬门槛决定，阈值在左侧可调",
      "右侧「声明」是两臂各自发布的主张，带证据等级，可下载封存",
    ],
    boundaryZh: "仅数学验证，未接触真实机床",
  },
  "five-axis-f1": {
    stage: "数学参考",
    stageIndex: 1,
    stageQuestion: GUIDE_STAGES[1]!.question,
    purpose: "验证五轴路径几何：分段连续、不越界、无碰撞",
    steps: [
      "左侧选择内置场景（正规场景或碰撞 / 容差违规场景）",
      "切换场景即自动评估，也可点「重新评估 F1」",
      "中间页签依次看几何轨迹、M0→M2 谱系、碰撞上下文",
    ],
    reads: [
      "结论徽章 GeometryValid / TaskGeometryCollisionFree 表示几何与碰撞两层判定",
      "「碰撞与过程」页签里的包围盒图：路径与 stock / fixture 是否相交一眼可见",
    ],
    boundaryZh: "仅数学验证，未接触真实机床",
  },
  "five-axis-f2": {
    stage: "数学参考",
    stageIndex: 1,
    stageQuestion: GUIDE_STAGES[1]!.question,
    purpose: "把刀尖路径换算成五个关节的连续运动",
    steps: [
      "左侧选择机床构型场景（双摆头 / 双转台 / 摆头转台）",
      "切换场景即自动验证运动学链",
      "中间图表看五轴坐标随路径进度 σ 的变化曲线",
    ],
    reads: [
      "每条曲线是一个关节角，范围标签给出最小 / 最大值与单位",
      "悬停图表可读任一进度处的五轴取值，越限会在结论徽章中体现",
    ],
    boundaryZh: "仅数学验证，未接触真实机床",
  },
  "five-axis-f3": {
    stage: "数学参考",
    stageIndex: 1,
    stageQuestion: GUIDE_STAGES[1]!.question,
    purpose: "给连续路径加上时间与采样，检查 V/A/J 约束",
    steps: [
      "左侧选择时域场景（含 dwell、停止类节点、ZOH 不支持等反例）",
      "切换场景即自动评估，σ（t） 图展示时间分段",
      "中间看采样重建记录与轴利用率条",
    ],
    reads: [
      "σ（t） 曲线上的竖线是运动节点（start / move / dwell / stop），颜色区分类型",
      "结论徽章反映采样与约束判定；「样本不足」类结论意味着证据不够下结论",
    ],
    boundaryZh: "仅数学验证，未接触真实机床",
  },
  "five-axis-f4": {
    stage: "数学参考",
    stageIndex: 1,
    stageQuestion: GUIDE_STAGES[1]!.question,
    purpose: "把前三层的数学结论收束为一道门禁判定",
    steps: [
      "左侧选择门禁场景（正规 / 求解器 / 哈希不匹配等）",
      "点「执行 F4 门禁」",
      "中间 verdict 区看门禁通过与否及各层证据引用",
    ],
    reads: [
      "F4 的判定依赖 F1–F3 的上游证据，右侧执行链显示依赖是否齐",
      "哈希不匹配场景演示：输入被改动时门禁必须拒绝",
    ],
    boundaryZh: "仅数学验证，未接触真实机床",
  },
  "machine-r3": {
    stage: "设备画像",
    stageIndex: 2,
    stageQuestion: GUIDE_STAGES[2]!.question,
    purpose: "检查机床观测数据：只读、成对、时钟对齐",
    steps: [
      "左侧选择观测场景（只读配对 / 乱序缺口 / 越权操作等）",
      "点「导入观测并评估」",
      "中间看遥测轨迹与判定，右侧核对冻结身份与声明",
    ],
    reads: [
      "结论区分数据本身的问题（乱序、缺时钟）与越界操作，两者性质不同",
      "「禁止声明」清单列出此数据源永远不能被引用的结论类型",
    ],
    boundaryZh: "只读采集，不修改设备任何状态",
  },
  "physical-r4": {
    stage: "物理验证",
    stageIndex: 3,
    stageQuestion: GUIDE_STAGES[3]!.question,
    purpose: "对比指令、仿真、实测三条信号，给物理模型打分",
    steps: [
      "左侧选择验证场景（标定泄露 / 激励不足 / 模型失配等）",
      "切换场景即自动评估",
      "中间信号图看三条曲线的贴合与分叉位置",
    ],
    reads: [
      "command / simulation / observation 三线重合度就是模型质量的可视化",
      "残差分解表给出各频段误差来源，结论徽章区分模型问题与数据问题",
    ],
    boundaryZh: "模型级验证，未证明真实加工安全",
  },
  "intelligence-r5": {
    stage: "学习能力",
    stageIndex: 4,
    stageQuestion: GUIDE_STAGES[4]!.question,
    purpose: "审查学习证据：防数据泄露、防时间穿越、防篡改",
    steps: [
      "左侧选择审查场景（组泄露 / 时间倒序 / 证书篡改等）",
      "切换场景即自动审查",
      "中间看双出口判定：contract 与 reality 各自独立给结论",
    ],
    reads: [
      "合成数据上的通过只说明合约成立，不代表真实泛化（那是 R5-B 的事）",
      "每个篡改场景演示一类失效模式，右侧声明给出证据等级",
    ],
    boundaryZh: "合成数据上的学习评估，真实泛化未决",
  },
  "intelligence-r5b": {
    stage: "学习能力",
    stageIndex: 4,
    stageQuestion: GUIDE_STAGES[4]!.question,
    purpose: "用真实留出集判定模型能否走出合成世界",
    steps: [
      "左侧选择就绪场景，查看 contract / reality / runtime 三芯片",
      "点「执行内置 Open 场景」",
      "中间大字结论即真实泛化门当前状态",
    ],
    reads: [
      "当前仓库未内置真实 holdout，门保持 Open——这是事实声明而非失败",
      "导入真实导出后可重跑，门会从 Open 变为判定结果",
    ],
    boundaryZh: "真实泛化门保持开放，尚不能用于设备",
  },
  "optimization-r6": {
    stage: "参数优化",
    stageIndex: 5,
    stageQuestion: GUIDE_STAGES[5]!.question,
    purpose: "在约束内搜索参数微调方案，给三档 Pareto 推荐",
    steps: [
      "左侧查看目标与约束，或导入外部请求",
      "点「搜索 Pareto 候选」",
      "中间看三档推荐及各自改变的参数与预期效果",
    ],
    reads: [
      "三档推荐是不同激进程度的取舍，权衡说明写明了代价",
      "所有推荐只是离线建议，是否采纳由人在更上层决定",
    ],
    boundaryZh: "离线建议，不直接作用于任何设备",
  },
  "control-r7": {
    stage: "控制闭环",
    stageIndex: 6,
    stageQuestion: GUIDE_STAGES[6]!.question,
    purpose: "在影子模式下重放控制合同，验证权限边界",
    steps: [
      "左侧选择合同场景（含越权请求被拦的反例）",
      "点「重放 Shadow 合同」",
      "中间看合同重放轨迹与 verdict",
    ],
    reads: [
      "Shadow 模式只有观察权，任何越权请求都应被合同拒绝——被拒是对的",
      "「无设备权限」行是设计目标而非缺陷",
    ],
    boundaryZh: "影子运行：能看不能动，无设备权限",
  },
  "control-r7b": {
    stage: "控制闭环",
    stageIndex: 6,
    stageQuestion: GUIDE_STAGES[6]!.question,
    purpose: "评估真实接入前的就绪度：合同、现实、运行三芯片",
    steps: [
      "左侧选择就绪场景，查看三芯片状态",
      "执行内置场景或导入外部证据",
      "中间 hero 展示当前就绪判定",
    ],
    reads: [
      "三芯片分别看：合同齐不齐、现实缺口在哪、运行环境行不行",
      "厂商未定时所有结论都是 Open，不替你做选型决定",
    ],
    boundaryZh: "就绪性评估，不修改设备",
  },
  "control-r7c": {
    stage: "控制闭环",
    stageIndex: 6,
    stageQuestion: GUIDE_STAGES[6]!.question,
    purpose: "验收 Windows OPC UA 传输链路（虚拟）",
    steps: [
      "左侧选择传输场景",
      "执行内置场景或导入 。NET 传输证据",
      "中间看传输验收结论与边界",
    ],
    reads: [
      "虚拟传输验证只证明链路与格式，不证明真实设备行为",
      "「VENDOR OPEN」表示厂商侧证据仍缺",
    ],
    boundaryZh: "虚拟传输验证，厂商证据未齐",
  },
  "control-r7d": {
    stage: "控制闭环",
    stageIndex: 6,
    stageQuestion: GUIDE_STAGES[6]!.question,
    purpose: "把「支持 OPC UA」收紧为 Beckhoff 厂商事实",
    steps: [
      "左侧选择厂商边界场景",
      "执行开放基线或导入厂商证据包",
      "中间 hero 展示厂商门当前判定",
    ],
    reads: [
      "判定基于可审计的厂商证据，不是产品宣传页",
      "REALITY OPEN 表示仍待真实运行数据补全",
    ],
    boundaryZh: "厂商门评估，只读",
  },
  "field-evidence": {
    stage: "现场证据",
    stageIndex: 7,
    stageQuestion: GUIDE_STAGES[7]!.question,
    purpose: "把现场采集的数据投影为可审计的验收证据",
    steps: [
      "左侧选择双证据场景",
      "点「运行双证据验收」",
      "中间看现场证据的整体判定与各子项",
    ],
    reads: [
      "现场数据只读采集，结论注明哪些仍未覆盖（如连续加工质量）",
      "与 R7 系列联动：现场证据是控制闭环的最终输入",
    ],
    boundaryZh: "现场只读采集，不修改设备状态",
  },
};
