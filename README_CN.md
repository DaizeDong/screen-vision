# screen-vision

截取桌面窗口，通过无障碍数据和 OCR 读取带物理像素坐标的界面元素，并按需执行经过身份校验的动作。

[![Claude Code Skill](https://img.shields.io/badge/Claude%20Code-Skill-orange?style=flat)](https://docs.anthropic.com/en/docs/claude-code)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Accessibility-first](https://img.shields.io/badge/Reads-UIA%20%2B%20OCR-green?style=flat)](skills/screen-vision/reference/backends.md)
[![Read-only default](https://img.shields.io/badge/Click-opt--in%20%2F%20dry--run-green?style=flat)](skills/screen-vision/reference/schema.md)
[![Languages](https://img.shields.io/badge/Languages-EN%20%2F%20CN-blue?style=flat)](#语言)
[![Roadmap](https://img.shields.io/badge/Roadmap-v0.1.1-purple?style=flat)](ROADMAP.md)

[English](README.md) | [中文版](README_CN.md)

---

## 设计理念

Windows UI Automation 会为参与无障碍接口的控件提供名称、状态和几何位置。直接读取这些结构，
可以减少从像素猜测控件属性的误差。OCR 只补充尚未覆盖的文字区域，OCR 框本身不能授权点击。
自绘控件和不完整的无障碍树仍是明确的限制。

坐标必须和当前界面对应。工具先核实实际生效的 DPI 感知状态，记录控件所属进程和窗口，
再在执行动作前重新查找保存的 UIA 身份。布局变化或截图过期后，可能需要重新截图。
拒绝过期目标，可以避免将动作施加到另一个控件。

截图和动作使用独立命令。屏幕像素可能包含个人信息，因此截图前先验证 PRIVATE 输出位置；
动作默认只预览，需显式确认才执行。合成检查验证这些判断，真实输入、显示器缩放和平台权限
仍需单独进行桌面验收。

[完整设计理念](PHILOSOPHY.md)。

## 适用范围

这个 CLI skill 每次完成截图、解析和返回，无需常驻 MCP 服务。它提供三个命令：

- `probe.py`：报告 DPI、显示器几何信息和可用后端。
- `capture.py`：生成截图、带物理像素坐标的元素列表，以及可选的 Set-of-Mark 标注。
- `click.py`：按元素 ID 预览或显式执行动作，优先使用 UIA `Invoke`，物理点击也需通过身份校验。

适用于桌面、原生、Win32、WinUI、Electron、游戏和远程桌面窗口。
网页 DOM 访问使用 Playwright，图像生成或编辑使用相应图像工具。

Windows 的 GDI 截图和 PNG 写出使用标准库。实际点击还需要 `uiautomation` 验证最新的控件身份；WinOCR 读取图像需要同时安装 winocr 和 Pillow，OCR 也可使用 RapidOCR；标注另需 Pillow。截图前还需要 Git 和已登录的 `gh` 验证私有输出仓。

## 安装

```
/plugin install github:DaizeDong/screen-vision
```

或手动克隆：

```bash
git clone --recurse-submodules https://github.com/DaizeDong/screen-vision.git ~/.claude/plugins/screen-vision
```

推荐后端（可选，缺了也能降级运行）:

```bash
pip install uiautomation mss pillow            # 元素 + 快速截图 + 标注
pip install winocr pillow                      # OCR(Windows 原生，需要 Pillow)，或:
pip install rapidocr-onnxruntime               # OCR(跨平台)
```


## 配置

将 `SCREEN_VISION_CONFIG` 指向已有的 PRIVATE 伴生仓，或用
`SCREEN_VISION_DATA_DIR` 指定其中准确的 `data/` 目录，并登录 `gh`。
存储只按显式设置查找：DATA_DIR、CONFIG、CONFIG_DIR；切换 CONFIG 前清除继承的
DATA_DIR。安装后可以保持未初始化。

截图需要伴生仓已有提交、当前 PRIVATE 路由证明，以及已声明且可纳入 Git 管理的
产物路径。每次运行使用 `data/captures/` 的一个新建直接子目录。
[DATA.md](DATA.md) 规定初始化、传输限制、产物写入检查和 JSON 暂存失败后的恢复。

## 快速开始

> "用 screen-vision 读屏幕上的按钮，然后点 Save。"

```bash
python skills/screen-vision/scripts/probe.py
python skills/screen-vision/scripts/capture.py --target 'window:Calculator' --clickable-only
python skills/screen-vision/scripts/click.py --elements-json <path> --id 30            # dry-run
python skills/screen-vision/scripts/click.py --elements-json <path> --id 30 --confirm  # 实点
```

## 如何触发

触发词：*截图并读按钮、屏幕上有哪些 UI 元素、找到 X 按钮并给坐标、点击这个桌面应用里的 OK 按钮、读屏幕、浏览器之外的 GUI 自动化。*

## 示例输出

每次捕获生成 `screen.png`、可选的 `annotated.png`、`elements.json` 和 `capture.json`。
清单记录请求范围、实际范围、时间和文件路径；[合成示例](tests/fixtures/element.json)由生成器生成。

目标无效时不会自动截取全屏；只有显式指定 `--allow-full-screen-fallback` 才能扩大范围。
按标题查找窗口时，所有可见窗口的标题都必须成功读取；枚举不完整、读取失败或标题发生变化都会中止查找。

点击仍默认预览。实际动作要求捕获未超过 60 秒，并重新核对进程创建时间、窗口、UIA 运行时身份、
元素属性和几何位置。坐标兜底也必须通过身份和命中检查。`recapture_required` 表示需重新检查并截图；
`action_outcome_unknown` 表示动作结果不明，先查看应用状态，再决定是否重试。

默认 `python -m pytest` 和 `python tests/run_gate.py --json` 不读桌面。
前者的四项桌面读取检查需加 `--interactive-desktop`。
后者只有加 `--interactive` 才会创建专用测试窗口、执行动作并清理自己创建的进程。
未运行的桌面检查不代表真实能力已经验收。

## 局限

- 当前实现以 **Windows 为主**。macOS 使用原生 Screen Recording 权限预检和 MSS 显示器信息，不要求 X11 环境变量；Linux 仍需显示会话和 MSS。macOS/Linux 的真实截图、OCR 和权限兼容性尚需单独验收，原生无障碍层也未接入。Wayland 可能阻止静默截图。
- UIA 盲区（未加 `--force-renderer-accessibility` 的 Chromium/Electron、Qt、Canvas、游戏）需 OCR 兜底；重型视觉后端（OmniParser / grounding VLM）是延后的、用户自取的 stub（AGPL 权重不随仓打包，见[后端说明](skills/screen-vision/reference/backends.md)）。
- 读取提权（UAC）窗口需同样以管理员身份运行 Python。

## 语言

中文 (`README_CN.md`) · English (`README.md`, 权威版)

## Roadmap · 贡献 · 许可

见 [ROADMAP.md](ROADMAP.md) · [CONTRIBUTING.md](CONTRIBUTING.md) · [LICENSE](LICENSE)(MIT)。
