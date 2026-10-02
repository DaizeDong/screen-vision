# screen-vision

截屏任意桌面窗口，把按钮 + 文本读成像素级精确、可点击的 JSON, 无障碍树优先，视觉作兜底。

[![Claude Code Skill](https://img.shields.io/badge/Claude%20Code-Skill-orange?style=flat)](https://docs.anthropic.com/en/docs/claude-code)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Accessibility-first](https://img.shields.io/badge/Reads-UIA%20%2B%20OCR-green?style=flat)](skills/screen-vision/reference/backends.md)
[![Read-only default](https://img.shields.io/badge/Click-opt--in%20%2F%20dry--run-green?style=flat)](skills/screen-vision/reference/schema.md)
[![Languages](https://img.shields.io/badge/Languages-EN%20%2F%20CN-blue?style=flat)](#语言)
[![Roadmap](https://img.shields.io/badge/Roadmap-v0.1.1-purple?style=flat)](ROADMAP.md)

[English](README.md) | [中文版](README_CN.md)

---

## ⭐ 先读这里, 设计理念

大多数"让 agent 看屏幕"的工具，从一张截图出发去问视觉模型"按钮在哪"。这是反的。操作系统本身已经暴露了**结构化的无障碍树**（UI Automation）：每个控件的名称、类型、状态、精确矩形都是**事实**,不靠模型、不靠猜、不受缩放与抗锯齿干扰。所以 screen-vision 只立一条原则：

> **先读无障碍树；只在它读不到的地方用视觉（OCR / 图标模型）兜底；绝不点击一个你无法验证的坐标。**

由此直接派生三条决策，也是它在像素匹配类工具会碎的地方依然可靠的原因：

1. **UIA 是真值，视觉是兜底。** 结构化元素带 confidence 1.0 和可直接触发的 `Invoke` pattern,**完全不靠坐标**即可点击。OCR 使用经过裁剪和遮罩的图像，只处理 UIA Text 控件尚未提供文字的像素。窗口、面板的名称和 AutomationId 不算文字覆盖；重叠过滤也采用同一组文本矩形。这正是微软 UFO² 的混合检测路线。
2. **先确认 DPI 感知，再使用坐标。** Windows 的坐标虚拟化可能导致截图和点击位置对不上。脚本在 `import` 时尝试设置 Per-Monitor-V2，使用坐标前再查询实际生效的状态。未确认、不感知 DPI 或仅系统级感知时，截图和操作都会停止。离线测试验证这些判断；真实显示器的缩放效果需要单独开启桌面测试验证。
3. **默认只读；点击是显式的、先 dry-run 的 opt-in。** 看屏幕安全，动屏幕不安全。登录 / 付款 / 验证码留给人工。

📜 **[完整设计理念 → PHILOSOPHY.md](PHILOSOPHY.md)**（每条原则都给出"打补丁 vs 改根因"的对照与它产出的真实决策）。

---

## 它是什么（不是什么）

它是一个 **CLI 脚本 skill**（不是 MCP server,截屏→解析→返回是无状态一次性能力，无需常驻 socket/token 开销），给 agent 三个动词：

- **`probe.py`**, 这台机器到底能干什么（DPI、显示器、装了哪些后端）？
- **`capture.py`**, 截图 + 结构化元素列表，坐标全为**物理像素**（`screen.png` + Set-of-Mark `annotated.png` + `elements.json`）。
- **`click.py`**, 可选、默认 dry-run 的点击，按 `id` 定位（优先 UIA `Invoke`，物理点击仅作兜底）。

**适用于** 桌面 / 原生 / Win32 / WinUI / Electron / 游戏 / 远程桌面窗口,一切**浏览器之外**的界面。

**不适用于** 网页,网页有实时 DOM，请走 **Playwright**。也不是图像生成/编辑工具（那是 `pixel-art` / 图像工具）。

Windows 的 GDI 截图和 PNG 写出使用标准库。实际点击还需要 `uiautomation` 验证最新的控件身份；WinOCR 读取图像需要同时安装 winocr 和 Pillow，OCR 也可使用 RapidOCR；标注另需 Pillow。截图前还需要 Git 和已登录的 `gh` 验证私有输出仓。

## 安装

```
/plugin install github:DaizeDong/screen-vision
```

或手动克隆:

```bash
git clone --recurse-submodules https://github.com/DaizeDong/screen-vision.git ~/.claude/plugins/screen-vision
```

推荐后端（可选,缺了也能降级运行）:

```bash
pip install uiautomation mss pillow            # 元素 + 快速截图 + 标注
pip install winocr pillow                      # OCR(Windows 原生，需要 Pillow)，或:
pip install rapidocr-onnxruntime               # OCR(跨平台)
```


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

先创建私有伴生仓，用 `git clone https://github.com/OWNER/REPOSITORY.git` 克隆，再将 `SCREEN_VISION_CONFIG` 指向该目录，创建其中的 `data/`，并登录 `gh`。每次截图前会检查所有配置及实际生效的拉取、推送地址，并确认各仓库为 PRIVATE。目前只接受 GitHub HTTPS 的默认端口或 443；SSH 尚未验证，暂不支持。URL 重写、代理、TLS 信任覆盖和 Git 路由环境覆盖也会被拒绝。
目标无效时不会自动截取全屏；只有显式指定 `--allow-full-screen-fallback` 才能扩大范围。

点击仍默认预览。实际动作要求捕获未超过 60 秒，并重新核对进程创建时间、窗口、UIA 运行时身份、
元素属性和几何位置。坐标兜底也必须通过身份和命中检查。`recapture_required` 表示需重新检查并截图；
`action_outcome_unknown` 表示动作结果不明，先查看应用状态，再决定是否重试。

默认 `python -m pytest` 和 `python tests/run_gate.py --json` 不读桌面。
后者只有加 `--interactive` 才会创建专用测试窗口、执行动作并清理自己创建的进程。
未运行的桌面检查不代表真实能力已经验收。

## 局限

- 当前实现以 **Windows 为主**。macOS 使用原生 Screen Recording 权限预检和 MSS 显示器信息，不要求 X11 环境变量；Linux 仍需显示会话和 MSS。macOS/Linux 的真实截图、OCR 和权限兼容性尚需单独验收，原生无障碍层也未接入。Wayland 可能阻止静默截图。
- UIA 盲区（未加 `--force-renderer-accessibility` 的 Chromium/Electron、Qt、Canvas、游戏）需 OCR 兜底；重型视觉后端（OmniParser / grounding VLM）是延后的、用户自取的 stub（AGPL 权重不随仓打包,见 `reference/backends.md`）。
- 读取提权（UAC）窗口需同样以管理员身份运行 Python。

## 语言

中文 (`README_CN.md`) · English (`README.md`, 权威版)

## Roadmap · 贡献 · 许可

见 [ROADMAP.md](ROADMAP.md) · [CONTRIBUTING.md](CONTRIBUTING.md) · [LICENSE](LICENSE)(MIT)。
