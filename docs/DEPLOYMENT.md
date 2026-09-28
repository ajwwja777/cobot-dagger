# 部署与验证

结构见 ../README.md。材料：本项目 Git、cobot-control Git；网页录制另需 cobot-web。Python3.8依赖由 uv.lock 锁定；ROS Noetic的 rospy/cv_bridge 按control说明准备，不需要本项目GPU环境。

```bash
cd /home/agilex/jiaan/project/cobot-dagger
./scripts/install.sh
PYTHONPATH=src .venv/bin/python -m pytest -q
.venv/bin/python scripts/inspect_data.py /media/agilex/Getea1/jiaan/data/datasets/test
```

inspect_data只读元数据，不开启录制。完整录制由web现有HTTP入口提供，只有一个 recorder owner；不为拆项目再开启第二套录制服务。HTTP代码仍在 cobot-web/app/backend/{capture_core,segmented_capture}/api.py，调用本项目领域模块。

命令协议见 cobot-web/docs/COMMAND_LINE.md。UUID/generation、HIL控制源、训练mask不因页面或模型选择变化而重置。放弃不保留episode或标签记录；未标注保存不伪造成功/失败奖励。

换机器人需实现control的ROS topic/状态接口与segmented_capture/ports.py的采样约定，核对相机顺序、关节单位、夹爪字段、时间戳与handover。数据继续在 /media/agilex/Getea1/jiaan/data，代码/环境/日志/PID留项目目录。

验证：独立uv环境安装、75项录制/采样/标签测试通过；web回归覆盖跨项目调用。真实设备时序、操作者示教与HIL按钮仍需现场验收。

## 配置与可读入口

本项目没有另建一套机器配置文件。RecorderConfig和采样接口由调用方注入；网页调用时读取 cobot-web/configs/local.json 的目录、ROS设置，硬件话题来自 cobot-control/src/cobot_control/ros_topics.py。不同现场只替换该配置和control机器映射，不把用户名或硬盘路径写回领域模块。

原始录制、节点、HIL/mask与标签实现分别查看 src/capture_core/recorder.py、src/segmented_capture、src/capture_core/labels.py。训练转换由对应方法调用；这里不合并VLA与RL的训练循环或奖励。网页按钮和对应HTTP命令统一记录于 /home/agilex/jiaan/project/cobot-web/docs/COMMAND_LINE.md。
