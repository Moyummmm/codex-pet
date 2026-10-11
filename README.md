# Codex Pet ⚡

一个实时显示 **Codex / ChatGPT Plus** 配额余额的 Windows 桌面小工具。

**默认模式(任务栏文字条)**:在任务栏托盘左侧显示一行紧凑文字,如 `● Codex 29% · 2h15m`,
状态圆点随剩余量变色(绿 → 橙 → 红),不占用桌面空间。全屏看视频/游戏时自动隐藏(与任务栏行为一致)。

**可选模式(桌面宠物)**:一只"电量条"史莱姆小人,身体填充高度 = 5 小时主窗口剩余配额,
表情随余额变化(充足眯眼笑 / 紧张冒汗 / 快耗尽闪烁),可在托盘菜单一键切换。

![文字条](shots/bar_mid.png) ![宠物](shots/pet_full.png)

## 功能

- **实时余额**:通过官方 `codex app-server` 协议获取,自动跟随推送更新 + 5 分钟兜底轮询
- **两种显示模式**:任务栏文字条(默认)/ 桌面宠物,托盘菜单一键切换,选择写入配置
- **全屏自动隐藏**:检测到全屏应用时自动隐藏,退出全屏恢复(同任务栏行为)
- **详情面板**:点击显示条/宠物弹出,显示套餐类型、两个窗口的进度条与重置倒计时
- **系统托盘**:迷你电量图标 + 悬停提示
- **零凭证接触**:不读取 `~/.codex/auth.json`,鉴权完全由 Codex CLI 自己管理
- **离线兜底**:codex 未安装/未登录时显示离线状态,进程崩溃自动退避重启

## 环境要求

- Windows 10/11
- 已安装并登录 [Codex CLI](https://developers.openai.com/codex)(即 `codex` 命令可用,ChatGPT Plus 订阅)
- [uv](https://docs.astral.sh/uv/)(Python 环境管理)

## 运行

**方式一**:从 [Releases](../../releases) 下载 `CodexPet.exe`,双击即可,无需 Python 环境。

**方式二**:源码运行

```bash
cd codex-pet
uv run codex-pet
```

首次运行会自动解析 `codex` 可执行文件位置并后台拉起 `codex app-server`。

## 交互

| 操作 | 效果 |
| --- | --- |
| 左键点击显示条/宠物 | 弹出/收起详情面板 |
| 按住拖拽 | 微调位置(自动记忆;任务栏挪动时跟随锚定) |
| 右键 | 菜单:立即刷新 / 重置位置 / 退出 |
| 托盘图标 | 单击显示/隐藏;菜单可切换显示模式 |

## 配置

`~/.codex-pet/config.json`(自动生成):

```jsonc
{
  "display": "bar",        // "bar" = 任务栏文字条,"pet" = 桌面宠物
  "bar_offset": [0, 0],    // 显示条相对任务栏托盘左侧锚点的偏移
  "pos": [2200, 1100]      // 宠物模式的位置
}
```

## 打包成 exe(可选)

```bash
uv run --with pyinstaller pyinstaller --onefile --windowed \
    --name CodexPet --paths src launcher.py --noconfirm
```

产物在 `dist/CodexPet.exe`(约 36MB),双击即可运行,无需 Python 环境。

## 开发自检脚本

```bash
uv run python test_smoke.py    # 端到端冒烟测试(离屏,验证真实数据链路)
uv run python test_render.py   # 渲染宠物各状态截图到 shots/
```

## 项目结构

```
src/codex_pet/
├── __main__.py      # 入口:装配各组件、双模式切换
├── codex_client.py  # codex app-server JSONL 客户端(QProcess + JSON-RPC 2.0)
├── taskbar_bar.py   # 任务栏文字条(Win32 任务栏/托盘探测 + 全屏检测)
├── pet_window.py    # 宠物模式:无边框透明置顶窗口、拖拽、位置持久化
├── pet_widget.py    # QPainter 自绘电量宠物
├── detail_panel.py  # 点击弹出的配额详情浮层
├── tray.py          # 系统托盘
└── config.py        # 配置读写(~/.codex-pet/config.json)
```

## 数据来源说明

配额数据来自 Codex CLI 文档化的 app-server JSONL 协议
(`initialize` → `account/rateLimits/read`,并订阅 `account/rateLimits/updated` 推送),
返回 `primary`(5 小时窗口)与 `secondary`(周窗口)的 `usedPercent` / `resetsAt` 等。

注:`CODEX_PET_DEBUG=1` 环境变量可让文字条渲染成品红实心块,用于诊断定位问题。
另:半透明(layered)窗口在部分环境下不会被 GDI 截屏捕获,截图验证时需注意。

## License

[MIT](LICENSE)
