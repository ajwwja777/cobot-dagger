# Cobot DAgger

```text
cobot-dagger/
├── src/capture_core/          # 录制、HDF5、标签、历史、ROS采样
├── src/segmented_capture/     # 开始/暂停/继续/节点、HIL、mask、转换
├── configs/domain-migration.json # 迁移前文件SHA256
├── scripts/                  # 安装、只读数据检查、同步
├── tests/                    # 格式、采样、标签与写入契约
└── docs/                     # 部署与迁移记录
```

主仓库：/data/LFT-W02_data/jiaan/jiaan/projects/cobot-dagger
现场：/home/agilex/jiaan/project/cobot-dagger
GitHub：https://github.com/ajwwja777/cobot-dagger

本项目负责采集领域能力；控制权与ROS接口由 cobot-control 提供，HTTP与网页由 cobot-web 提供，训练交给 vla-platform / rl-platform。本项目不发布机械臂动作。

2026-09-29：35个领域模块从web迁入，保留 capture_core / segmented_capture 原导入名称；web只留HTTP API与兼容包入口。数据字段、HIL/mask、动作与算法没有随迁移改变。

从 [DEPLOYMENT](docs/DEPLOYMENT.md) 开始，变更见 [MIGRATION](docs/MIGRATION.md)。
