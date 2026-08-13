# ADR-0025：Beckhoff 见证采用控制器锁存与离线部署预检

- 状态：Accepted
- 日期：2026-08-13
- 决策范围：R7-E Beckhoff Shadow Witness 部署准备

## 背景

R7-E 已能按 `sampleIndex` 通知执行七节点 batch Read，但仓库此前没有控制器侧模板来保证 command hash、索引和五轴回读来自同一 PLC 周期，也没有把真实 namespace/NodeId 编译成 Bound Witness Profile 的工具。直接依赖 OPC UA publishing/sampling interval 会把非实时协议误当成控制周期证据；从符号名猜 NodeId 则无法跨 PLC 工程复现。

## 决策

1. 提供可导入的 `FB_AxiomShadowWitness.TcPOU`。功能块只消费权威 M5 identity、sample index 和五轴回读；关闭观测窗口时公开索引保持 `16#FFFFFFFF`，重新开窗后先锁存 hash/axes，最后发布 witness sample index。窗口内 command identity 变化同样保持 sentinel，必须关闭并重新打开窗口，不能把两个从索引 0 开始的命令混在同一触发序列中。
2. 七个输出使用 Beckhoff `OPC.UA.DA` 与 `OPC.UA.DA.Access := '1'`，生产设计不包含轴写入、设备启停或 Method Call。
3. NodeId、vendor runtime 和 M5 command 必须通过 `axiom.control.beckhoff-shadow-witness-deployment-request@1` 显式提交；七个 NodeId 还必须附带与同一 runtime 内容身份绑定的 vendor-runtime 属性证据，逐项证明 BrowseName、Variable NodeClass、DataType 以及只读 AccessLevel/UserAccessLevel。离线评估器只在声明与运行时证据逐项闭合后生成 Bound Witness Profile。
4. 节点检查器必须核对 config 与实际连接服务器的 endpoint、证书和 Application URI；生产采集必须重新装载节点证据，同时匹配 runtime hash、Profile hash 和七节点身份，并在同一采集 session 创建订阅前再次读取七节点属性，不能只信任 Bound Profile 或陈旧证据。
5. 部署评估是应用层工具，不创建 R7-F DomainPack，不重写 R7-E Claim，也不连接或配置 PLC。
6. `capturePreparationStatus=Passed` 不能升级 capture authorization、Deployment Shadow、Reality、Controlled Trial、Closed Loop、DeviceSafe 或 ProcessSafe。

## 后果

- 控制器侧快照协议与主机侧采集协议形成可审计闭环，NodeId 声明与导入的运行时属性证据可由 Python、CLI、HTTP 和网页一致重放。
- 实际 NodeId、TMC/符号生成、TF6100 ACL、TwinCAT 编译和现场运行仍由部署责任人完成并留证。
- OPC UA 通知仍只是触发器；最终一致性和完整覆盖继续由读回 sample index、M5 索引集合、quality/timestamp 与 receipt 共同判定。

## 被拒绝的方案

- 仅提高 OPC UA publishing/sampling 频率：协议不提供实时保证，不能证明逐 M5 样本覆盖。
- 在客户端依次读取未锁存的实时轴变量：七个读取值可能跨 PLC 周期，无法证明一帧的一致性。
- 由 Axiom 自动部署 PLC 对象或修改 ACL：需要设备写入和现场权限，超出 Shadow 上限。
- 从变量名推导 NodeId：namespace 与实例路径由现场工程决定，结果不可复现。
