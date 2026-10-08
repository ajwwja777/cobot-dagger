# 2026-10-08 Recorder backpressure follow-up

结论：确定的采样调度错误已修复；原始 Online 154 ms 控制停顿和 HDF5 长积压的唯一根因仍证据不足。不能据此宣布真机 Online 验收通过。修复没有增加队列、放宽控制 deadline、改 FPS、改模型/Replay/算法或隐式发布 Actor。

## 证据与边界

|结论|状态|直接证据与边界|
|---|---|---|
|采样线程迟到后补采“当前缓存”，并不能补回过去观测|已验证|旧 127b3f3 的确定性回归失败：阻塞 1 s 后立即继续采样；候选跳过错过的采样时刻、保留时间戳缺口。不是已证明的本次唯一根因。|
|采样时间存在先采时后等待缓存锁的竞态|已验证|旧 acquisition 传入 clock()；preflight 已用 clock callable。候选采样同样在缓存锁内采时，真正未来时间仍不放宽。|
|故障录制队列溢出|失败|实际 episode_000010.hdf5.incomplete，UUID bbf2aa91-1d12-4013-9f6f-5983cf134f3e，error writer_queue_overflow；523 sampled / 267 written，差值256。原文件只读，未重标、恢复为完整或提交 Replay。|
|控制超时由磁盘写入直接引起|证据不足|原 trace 154.3 ms 区间缺少写入结束时刻；queue overflow 晚于控制失败。不能把相关性当因果。前轮 RLT 排队写 trace 修复见 rl-platform/docs/audits/2026-10-08-recurrent-publication-timeout.md。|
|现有外置盘始终无法维持10 Hz|证据不足|同现场环境独立合成480帧、三路640×480RGB，各盘约1.328GB：NVMe append p99 18.58/max24.46 ms；外置盘 p99 41.64/max61.49 ms。无模型/训练/现场并发，不代表高负载长尾已通过。|
|候选完整录制器的短时合成写入和HIL字段保存|已验证|同现场Python3.8、候选源码、外置盘：480/480帧、队列峰值1、最大append55.03ms、missed ticks0；100帧模拟HIL/控制来源逐项验证。不是实际HIL动作、模型泛化或真机评测。|

数据身份：原录制路径 `/media/agilex/Getea1/jiaan/data/datasets/plug_insertion/recordings/rl-platform/rlt/online/supported_mc30/episode_000010.hdf5.incomplete`。数据集划分不适用于合成基础设施测试；未使用训练/开发/测试 Episode 计算模型指标。图仅描述单次时序，不将帧作为独立样本推断成功率或置信区间。

## 实现

- dagger recorder：错过时刻不补采重复当前状态；缓存锁内确定采样时刻；有界数值诊断包含队列深度/峰值、写入在途时长/最大耗时、采样与磁盘检查耗时、missed ticks；错误日志保留诊断。满队列仍撤销发布，失败文件不可成为完整数据。
- web API：仅暴露白名单内有限非负数值，不泄露路径/原异常。既有调用方无 timing 时保持兼容。
- 缓存 HDF5 writer 已是实际默认，本轮没有重复修复句柄缓存，也没有修改文件 schema。

## 验证

- A6000 Python3.8：采集领域80 passed；相关 API/恢复/录制/门控/生命周期78 passed。
- 旧基线确定性回归1 failed（预期），候选通过。
- Cobot 实际 web Python：两个独立故障回归通过、480帧完整合成链路通过。该环境没有pytest；未安装或改环境，不能称现场80项pytest通过。
- 初次隔离运行缺少跨项目导入路径，修正 PYTHONPATH 后通过；日志保留，包括失败尝试。
- 独立合成HDF5逐项校验后删除，仅保留小JSON/日志；没有复制原数据或权重。

## 下一步与停止条件

候选源码同步不重载现有进程；正式8015仍使用已导入旧模块，现场生效待维护窗口重载和只读状态核验。模型已由操作者释放，本任务不启动模型/机器人/硬件/服务，不抢占GPU。

生效后先做无动作录制与控制链路的一致性验收，确认 timing 可见、队列不持续增长、无 lost/重复补采、trace 队列可排空，再考虑短轮冻结真机。真实模型并发与50Hz发布的长尾仍待验证；出现控制timeout、writer overflow、不断增长的队列或错误不完整文件即停止本轮，保留证据，不自动继续训练/发布。不得用本次合成测试证明任务成功率或 Online 越训越好。

回退：仅恢复本批两个源码文件至同步备份；若尚未重载则运行模块本就未变。保留上一轮RLT trace修复、模型/配置/归一化/Replay和不完整证据，禁止用恢复标签掩盖失败。

产物：`/data/LFT-W02_data/jiaan/jiaan/projects/cobot-dagger/outputs/recorder-backpressure-20261008/`，包括原现场元数据、实际命令/测试日志、storage-benchmark.json、full-recorder-benchmark.json、01-recorder-backpressure.png、源码/同步收据及进度。完整命令由测试命令JSON和可重跑基准脚本记录；合成脚本仅对独立路径操作。
