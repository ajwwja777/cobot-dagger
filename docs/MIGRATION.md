# Cobot 采集、HIL 与 DAgger：迁移记录

日期：2026-09-27。当前批次：**入口初始化**，尚未开始业务迁移。

## 已有位置与成果

以下是已读项目记录与前序目录核验的入口清单，不表示本轮重新完整验证每项资产。执行某批迁移前须核对实际目录、符号链接、Git 状态和使用者。

| 机器 | 旧位置／已有依赖 | 保留事项 |
|---|---|---|
| Cobot | `/home/agilex/cobot_magic/task3/jiaan` | 旧采集、模型部署与兼容入口。 |
| Cobot | `/home/agilex/cobot_magic/task5/jiaan` | HIL／DAgger 旧实现与部署资产。 |
| A6000 | `/data/LFT-W02_data/jiaan/projects/proj-20260829-cobot-realworld-vla/external/pi05-dagger-round001-backup` | 独立 Git 备份；保留原有历史，待迁移批次选择接入方式，不由本次新仓库替代。 |
| Cobot | `/media/agilex/Getea1/jiaan/projects/cobot-platform/app/backend/task5_hil` | 当前网页后端使用的 HIL 实现，先核验实际 import 与部署路径。 |

## 首个候选验收范围

先迁移一份数据格式说明、样例校验与转换入口，以现有一条成功保存的 episode 做离线对照，不改变现场录制服务。

验收要求：观测、动作、时间戳、HIL 来源及 mask 语义一致；保存未标注、成功、失败及彻底放弃的语义明确；转换结果可被既有训练读取。

## 逐批迁移约定

一次只处理一个明确范围，记录来源、目标、依赖、版本／校验值和回退入口；先复制与验证，再切换，最后清理对应旧文件。未验收不切换，仍被依赖或缺少可靠备份的原件不清理。共有目录按文件实际归属处理，保留其他对话的未提交修改及共享资产。

迁移批次记录至少包括：范围、来源与目标、验证结果、切换状态、可清理清单及实际清理结果。初始化完成仅表示入口与 Git 可接管，不代表运行环境或业务功能已验收。

本轮没有迁移／删除旧文件，没有安装项目运行环境、启动训练、加载模型或控制机器人，也没有变更当前网页服务。

## 初始化发布记录

- 2026-09-27：项目目录与维护入口已建立，基础提交已 push 并核对远端 main 一致。
- 仓库：https://github.com/ajwwja777/cobot-dagger（独立仓库，非 GitHub fork）。
- 首次发布提交：`16a9f37c9381596244bc4f4a5db1677d31f851a8`。
- 本记录在首次发布验证后追加并单独提交；最新版本以 main 为准。
- 运行状态：源码／文档基础已发布，业务迁移、环境安装及新位置运行验收尚未开展。

## 2026-09-28 20:00：迁移中遇到 Getea1 USB 掉线

已完成主体 12,059 条目、351,844,176,546 字节及 6 个恢复验证资产、117,047,594 字节的迁移、SHA 校验、运行验收和对应源文件清理。Warmup 与在线模型在新路径加载/释放通过；在线状态 5000/2500/2567，正式权重和 Replay 的 SHA 不变，未启动 Episode 或真机运动。历史读取、92 条有效评测和媒体通过；主副本清理后再次读通。系统盘当时剩余约 404 GiB。

剩余 FluxVLA 环境复制到 libcublasLt.so.12 时出现 I/O error。内核在 19:59:53 将 sda 下线，随后 USB 设备枚举失败；20:00 检查已无 Getea1 块设备和挂载。不能把它归因于单个 Python 包或仅网页错误，也不能仅凭这些日志判定是线缆、供电、硬盘盒或盘本体。

所有迁移进程已退出；正式网页 PID 366090 正常停止，无 GPU 模型进程，临时 ROS master 已停止。本轮未做运动。尚未验收的 FluxVLA 旧目录、暂存副本未清理，**Getea1/jiaan 仅保留 data/model 的目标尚未完成**。已验证结果仅代表掉线前状态，恢复连接后仍须核对文件系统并按迁移收据重新校验新资产，不能直接继续删除或开始在线训练。

证据：相邻 rl-platform/outputs/migrations/20260928-getea-storage/cobot/，现场同目录不带 cobot/。包括 retirement.json、validation/retirement.json、cutover-verification.json、extras/copy-status.json、disk-disconnect.json 和 disk-disconnect-kernel.log。源码和证据位于系统盘/A6000，本轮没有新增 A6000 数据/权重备份。

## 2026-09-28 20:56：Getea1 存储迁移完成

本批已完成复制、哈希与运行验收、切换和对应旧文件清理。Getea1/jiaan 只保留 data、model；旧系统盘数据/模型目录移除。数据按场景/用途/方法归类，位姿与动作回放归 data/motion；模型按项目/模型/场景/版本归类。代码/环境/日志/PID 留在 /home/agilex/jiaan/project/<项目>。

USB 掉线重连后已完成已迁移资产的全量收据复核；尚不能据此认定硬件链路根因已消除。RLT 新路径暂停加载、在线状态恢复与历史媒体通过；FluxVLA 固定版本离线 baseline/prefix-RTC 通过；π0.5 两入口只做 dry-run。本批未启动真实 Episode 或机器人动作。

完整路径、占用、各项验证边界及回执见实际 cobot-web/docs/STORAGE.md。证据位于 rl-platform/outputs/migrations/20260928-getea-storage/cobot/（Cobot 去掉末尾 cobot/）。同批源码与项目记录已按各自仓库发布；guide Git 保持由其他会话管理。

## 2026-09-29：职责边界与部署材料

按实际源码、只读现场状态整理，代码先在A6000开发。结构、安装、依赖来源及验证界限见docs/DEPLOYMENT.md；跨项目关系见cobot-web/docs/ARCHITECTURE.md。数据/模型实体未迁移或删除；公共厂商工作区未删除、硬件未重启。guide只写事实、不提交其Git。现场切换与版本见后续发布回执。

## 2026-09-29：正式切换、清理及交付验收

35个采集/HIL/mask领域模块已归本项目，首次发布69ddc94。独立Python3.8 uv环境75项契约测试通过；正式8015使用本项目源码，web只保留API和兼容入口。111条既有RLT历史及首帧JPEG在模型offline时读取通过。

现场验收后清除了web中33个与迁移收据SHA一致的旧领域文件；另两个兼容包入口仍保留。原始数据、标签、HIL/mask和动作参数没有变更；真实按键/示教时序待现场。

主代码位于 /data/LFT-W02_data/jiaan/jiaan/projects/cobot-dagger；现场副本 /home/agilex/jiaan/project/cobot-dagger。后续收尾版本以Git main和现场.release.json为准。guide仅更新事实摘要，不提交其Git。

## 2026-09-29：实时录制预检时钟竞态

源自用户反馈RLT加载后重复录制偶发recorder_not_ready。LatestMessageCache.snapshot新增clock callable用法，在同一缓存锁内复制后采时，避免先采时再等待锁期间的新callback被误判为负age/不新鲜；传浮点时间的既有采样语义不改，真正未来时间仍拒绝。RolloutRecorder.check_ready提供不创建Episode、不驱动机器人的流/写目录/空间预检，start使用同一实现。

HTTP/API和页面恢复归cobot-web，模型不释放，RL算法不改。254项相关Python通过、1项既有跳过；cache确定性竞态与未来时钟回归通过。没有放宽流过期阈值、修改HIL/mask或训练数据。该竞态并非所有既有503的已证实唯一根因；现场结果见cobot-web/docs/MIGRATION.md对应批次。


现场发布与写入验收：dagger dffc3f1 / web 8dd6983 已push并核验远端，同步45/198文件SHA一致；空闲时只重载8015，模型PID1436537及start_ticks9136435、机械臂PID1318293、相机PID1317979保持。正式预检/恢复API均成功，新静态资源SHA与A6000一致。

Session始终stopped/policy_paused，模型保持加载，在独立 datasets/test/recorder_recovery_check_<UUID> 下连续3次直接录制，每次12帧HDF5成功提交；逐轮通过UUID绑定的discard接口删除，无剩余数据/标签/目录。未向Session发start/resume、未归位、未新增Replay，Session generation10及chunk_count18不变。最终模型ready、recorder idle、Session stopped，可手动开始Session；在线Learner仍5090、Actor2545。该验收证明当前录制器可连续写入，不冒充完整推理/HIL轮次或长期稳定性测试。

回执：A6000 /data/LFT-W02_data/jiaan/jiaan/projects/cobot-web/outputs/rlt-recorder-recovery-20260929/{release.json,passive-recording.json,final.json}；Cobot /home/agilex/jiaan/project/cobot-web/runtime/verification/rlt-recorder-recovery-20260929/。详细恢复方式见web/docs/WEB_RECOVERY.md。

## 2026-09-29：混用目录的历史未标注记录阻塞 RLT

现场 RLT 开始失败的明确原因是 Task5 latest episode labels are incomplete：选择的 demonstrations/legacy_test 包含其他模型的已完成、未标注人工示范。旧 RLT orphan 恢复只接受同模型/轮次身份，不能处理该示范；旧恢复按钮只预检输入/写入，没有检查目录历史，所以错误重复。

统一录制的 flat 目录允许已有 finalized 未标注记录，保留其标签完整性事实，不自动写 aborted/success/failure，不向 Replay 加数据。legacy 独立接口仍默认要求标签；真正 incomplete、损坏或身份无效的末条记录仍拦截。采集领域提供显式 require_labels 参数；web 挂载接口选择策略，不重复维护数据判断。

网页“检查录制 / 恢复录制（保留模型）”使用同一个目录检查入口，显示检查路径、具体完整性错误与处理建议，新故障清除旧通过提示。不开始推理、不卸载模型、不删除历史数据。64项Python相关回归通过，45项前端通过。现场切换及版本另记；不能将离线测试当作真实推理验收。
