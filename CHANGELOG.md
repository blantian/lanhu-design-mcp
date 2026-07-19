# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - 2026-07-19

### Changed
- 认证统一为 macOS 专用托管 Chrome Profile，不再读取 Cookie 文件、环境变量或默认浏览器数据库。
- MCP 启动方式统一为 stdio，并重写正式安装与使用文档。
- 所有生产代码函数和方法增加中文用途说明。

### Added
- 支持 Sketch、Figma、Photoshop 细粒度切图及多倍率资源地址。
- 增加 PyPI Trusted Publishing、会话有效性验证和 macOS 平台边界。

### Removed
- 删除旧 Cookie 配置链、HTTP 模式、本地辅助脚本和过时发布文档。

## [0.1.0] - 2026-07-09

### Added
- 初始发布
- 4 个 MCP 工具：
  - `lanhu_get_designs` - 获取项目设计列表
  - `lanhu_analyze_design` - 分析指定设计稿
  - `lanhu_get_design_assets` - 获取设计资源
  - `lanhu_export_ui_context` - 导出完整 UI 上下文
- 支持 4 种平台：web, android, ios, wechat_miniprogram
- Android 单位自动转换（px → dp）
- 浏览器 Cookie 自动获取功能（macOS Chrome/Safari）
- 交互式 Cookie 配置工具
- MCP stdio 和 HTTP 传输模式
- 完整的测试套件

### Features
- 🎉 自动从浏览器读取蓝湖 Cookie
- 📐 精确的平台单位转换
- 🔧 Agent 友好的 DesignIR 格式
- 🚀 FastMCP 框架集成
- 📋 完整的文档和示例

[0.1.0]: https://github.com/blantian/lanhu-design-mcp/releases/tag/v0.1.0
[0.1.1]: https://github.com/blantian/lanhu-design-mcp/releases/tag/v0.1.1
