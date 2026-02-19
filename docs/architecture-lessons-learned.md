# 架构设计经验教训

## 项目概述

eroasmr-scraper + telegram-upload-service 是一个视频下载和上传到 Telegram 频道的系统。

## 遇到的问题

### 1. 路径映射问题

**问题描述：**
- eroasmr-scraper 和 telegram-upload-service 使用不同的下载目录
- Docker 容器只能访问挂载的卷内文件
- 上传请求发送的文件路径无法被容器访问

**具体表现：**
```
File not found: /root/eroasmr-scraper/data/downloads/xxx.mp4
```

**解决方案：**
1. 统一下载目录到 `/root/telegram-upload-service/data/downloads/`
2. Docker 卷挂载：`./data:/app/data`
3. 配置路径映射：`file_path_map` 将主机路径映射为容器路径

**经验教训：**
- 在涉及 Docker 的系统中，文件路径需要统一规划
- 所有服务应该使用同一个数据目录
- 路径映射配置要清晰文档化

---

### 2. 上传并发不足

**问题描述：**
- 默认只有 3 个上传工作线程
- 下载速度远超上传速度，导致文件积压
- 磁盘空间被待上传文件占满

**解决方案：**
- 增加上传并发数从 3 到 6
- 增加 `upload_queue_size` 从 20 到 30

**经验教训：**
- 下载和上传速度需要平衡
- 监控队列积压情况，及时调整并发数
- 考虑网络带宽限制

---

### 3. 数据库记录缺失

**问题描述：**
- `upload_pending.py` 脚本上传文件但未记录到数据库
- Dashboard 显示的上传数量不准确
- 无法追踪已上传文件的消息 ID

**具体表现：**
- 326 条下载记录没有对应的上传记录
- 10 个文件已上传但无数据库记录

**解决方案：**
1. 修改 `upload_pending.py` 在上传成功后调用 `storage.add_storage_location()`
2. 从 telegram-upload-service 的 jobs 表恢复缺失记录
3. 通过消息 ID 顺序和 job 历史匹配 slug

**经验教训：**
- 所有数据变更操作必须记录到数据库
- 上传服务有自己的 job 数据库，可用于恢复
- Dashboard 统计依赖准确的数据库记录

---

### 4. 磁盘空间管理

**问题描述：**
- 下载速度快于上传，磁盘空间不足
- 原有设计在磁盘空间不足时会停止整个管道
- 需要暂停下载但继续上传

**解决方案：**
1. 添加暂停文件机制（`.pause_downloads`）
2. 管道检查暂停文件，暂停下载但上传继续
3. 创建独立的 `upload_pending.py` 脚本处理积压文件
4. 磁盘监控脚本自动创建/删除暂停文件

**关键代码：**
```python
def _is_paused(self) -> bool:
    return self._get_pause_file().exists()

# 在下载生产者中检查
while self._is_paused():
    logger.info("Downloads paused via pause file. Waiting...")
    await asyncio.sleep(10)
```

**经验教训：**
- 下载和上传应该是可独立控制的
- 磁盘空间监控要提前预警
- 文件生命周期管理：下载 → 上传 → 删除

---

### 5. 暂停文件路径不一致

**问题描述：**
- 磁盘监控脚本使用 `$SCRIPT_DIR/.pause_downloads`
- 管道使用 `output_dir.parent / ".pause_downloads"`
- 两个路径不一致导致暂停机制失效

**解决方案：**
- 统一暂停文件路径为 `/root/telegram-upload-service/data/.pause_downloads`
- 更新磁盘监控脚本中的 `PAUSE_FILE` 变量

**经验教训：**
- 跨进程通信的文件路径必须明确定义
- 使用绝对路径而非相对路径
- 配置应该集中管理

---

### 6. 多目录文件混乱

**问题描述：**
- 文件同时存在于两个目录：
  - `/root/eroasmr-scraper/data/downloads/` (63 文件)
  - `/root/telegram-upload-service/data/downloads/` (260 文件)
- Docker 容器无法访问 eroasmr-scraper 目录

**解决方案：**
- 统一使用一个目录
- 移动所有文件到 telegram-upload-service 目录
- 更新 `run_continuous.sh` 的 `OUTPUT_DIR`

**经验教训：**
- 避免多个服务维护各自的数据目录
- 数据目录应该集中管理
- 定期清理临时文件

---

## 架构改进建议

### 短期改进

1. **统一配置管理**
   - 将所有路径配置集中到一个配置文件
   - 环境变量覆盖默认值

2. **增加监控指标**
   - 下载/上传队列长度
   - 磁盘空间使用率
   - 上传成功率/失败率

3. **日志聚合**
   - 统一日志格式
   - 集中日志存储

### 长期改进

1. **消息队列**
   - 使用 Redis 或 RabbitMQ 管理任务队列
   - 下载和上传作为独立消费者

2. **断点续传**
   - 记录下载/上传进度
   - 支持从中断点恢复

3. **分布式存储**
   - 使用 S3 或 MinIO 存储文件
   - 避免本地磁盘限制

---

## 当前系统配置

```
eroasmr-scraper/
├── data/videos.db          # 视频元数据和上传记录
├── upload_pending.py       # 独立上传脚本
└── run_continuous.sh       # 批处理管道

telegram-upload-service/
├── data/
│   ├── app.db              # 上传服务数据库（jobs, tenants）
│   └── downloads/          # 下载文件目录
│       └── .pause_downloads # 暂停文件
└── docker-compose.yml      # Docker 配置

tmux sessions:
├── pipeline               # 下载/上传管道（可暂停下载）
├── upload-pending         # 独立上传脚本
└── eroasmr-dashboard      # Web 监控面板
```

---

## 关键命令

```bash
# 暂停下载
touch /root/telegram-upload-service/data/.pause_downloads

# 恢复下载
rm /root/telegram-upload-service/data/.pause_downloads

# 运行独立上传
uv run python upload_pending.py

# 查看上传进度
tmux attach -t upload-pending

# 检查数据库统计
uv run python -c "
from eroasmr_scraper.storage import VideoStorage
storage = VideoStorage()
stats = storage.get_download_stats()
print(stats)
"
```

---

## 文档更新记录

- 2026-02-19: 初始版本，记录实际运行中遇到的问题
