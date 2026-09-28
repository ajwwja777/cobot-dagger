# Cobot 采集、HIL 与 DAgger

统一人工与模型辅助采集、HIL 事件、数据格式、训练 mask、质量校验和 DAgger 迭代流程，训练通过 vla-platform 接入。

## 入口与位置

- 先读统一框架：`/data/LFT-W02_data/jiaan/jiaan/agent-guide/AGENTS.md`。
- A6000 主工作区：`/data/LFT-W02_data/jiaan/jiaan/projects/cobot-dagger`。
- 笔记本对话入口：`D:\Code\jiaan_workspace\cobot-dagger`。
- 自有独立仓库：`https://github.com/ajwwja777/cobot-dagger`（目标分支 `main`）。
- Cobot 目标部署位置：`/home/agilex/jiaan/project/cobot-dagger`，本轮尚未部署。
- 当前阶段：入口与仓库初始化；旧业务代码、环境、模型和数据尚未迁移，现有服务入口未切换。

## 负责什么

录制与 episode 生命周期、时间对齐、人工接管与动作来源记录、训练数据转换、DAgger 数据聚合与轮次来源。训练 mask、控制权、相机有效性掩码分别定义。

示教按钮和设备控制权状态来自 cobot-control；模型加载和训练调用 vla-platform；RL 成功失败标签及 replay 接入与 rl-platform 对齐；网页只呈现同一采集接口。

## 机器与资产

A6000 负责主代码、Git、维护文档、主要开发验证环境、数据处理和离线评测；训练按资源需要在 A6000／已授权训练机进行。Cobot 只部署本项目现场实际需要的硬件、采集、推理、网页或维护组件，不复制仿真资产和完整训练环境。

Cobot 采集及评测数据统一规划在 `/home/agilex/jiaan/data/`。模型放所属项目的 `models/`（上游已有 `checkpoints/` 等目录时保留其源码布局，由配置明确实际权重位置）；同一资产跨项目引用，避免重复复制。现场服务日志、PID 和状态归实际负责项目；网页编排任务使用 `cobot-web/runtime/`；训练 checkpoint、配置和指标保留在所属项目 `outputs/<实验>/`。环境、模型、大数据与 runtime 不入 Git。

## 项目协作

缺帧、节点、标签和 mask 由本项目负责；物理示教状态交 cobot-control；模型训练执行和归一化交 vla-platform。

先读本次任务涉及的依赖项目入口和接口说明，再修改相关边界；接口变更要记录受影响调用方与验证方式。常用项目：`cobot-control`、`cobot-dagger`、`vla-platform`、`rl-platform`、`cobot-web`，主工作区均在 `/data/LFT-W02_data/jiaan/jiaan/projects/`。需要专题对话时仍共享所属项目，不因此重复建立业务仓库。

## 下一步

先迁移一份数据格式说明、样例校验与转换入口，以现有一条成功保存的 episode 做离线对照，不改变现场录制服务。

旧位置、验收条件和切换／清理规则见迁移记录。

来源：2026-09-27 用户确认的项目划分、机器职责与逐批迁移方案；本轮范围仅初始化。

## 保留事项

π0.5 in_the_pot 保留原始 2,000 步与 DAgger 续训 3,000 步的来源关系，不能因暴露的 checkpoint 名称不同而混淆总训练历程。

2026-09-27 归属更新：独立 ops 项目已取消；本次仅修正协作与 runtime 归属，不代表本项目旧业务资产已迁移。

## 现有数据位置与共享方式（2026-09-28）

用户确认原始采集与现场评测只在Cobot，当前部署checkpoint也归Cobot；训练中间checkpoint和停止部署的历史模型归A6000，同一资产不跨机器长期重复保存。场景数据可供多个模型使用，训练子集/mask/转换版本通过manifest关联。

现有in_the_pot原始DAgger rollout在/home/agilex/cobot_magic/task5/jiaan/hil_realworld_rl/data/raw_rollouts/in_the_pot（6.07GiB）；对应LeRobot产物在同一data下lerobot/in_the_pot（0.47GiB）。task3旧数据在/home/agilex/cobot_magic/task3/jiaan/datasets/in_the_pot（0.40GiB）和/home/agilex/cobot_magic/task3/jiaan/realworld_rl/data/task5-rlt-r1/in_the_pot（1.16GiB）。不同格式的产物不能仅凭共同来源视为重复。

当前新采集根为/home/agilex/jiaan/data/，场景命名目标in_the_pot/、plug_insertion/尚未切换；录制实现仍在cobot-web，数据位置登记不代表本项目业务代码迁移已完成。完整路径/空间清单见同级cobot-web/docs/STORAGE.md。
