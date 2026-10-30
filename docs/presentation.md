# 展示素材与复现

## 页面布局参考

查看并参考了 GitHub 的 [Best-README-Template](https://github.com/othneildrew/Best-README-Template)，采用简介、核心能力、截图、快速开始和文档入口的组织方式。该参考模板采用 [Unlicense](https://github.com/othneildrew/Best-README-Template/blob/master/LICENSE.txt)。未引入其示例按钮、社交链接、占位徽章或第三方应用代码；本项目的样式和内容按实际业务编写。

当前产品为命令行工具和本地模拟 API，暂不需要引入管理后台模板。新增的 HTML 为展示运行结果的只读静态报告，不提供按钮，也不宣称存在交互后台。

## 截图来源

- `assets/demo-report.png`：Chromium 对静态报告的真实截图。报告数据来自一次全新数据库的完整 demo 及其 Excel 对账结果。
- `assets/demo-run.png`：Chromium 对实际标准输出排版后的截图。不是终端模拟执行动画，内容取自真实运行结果。
- `assets/demo-report.html`：可独立打开的只读报告，数据为生成时的快照，不会实时刷新。
- `assets/run-evidence.txt`：本次 demo 和 Pytest 的原始标准输出。

所有业务数据为虚构样例，截图未使用真实账号或客户信息。

## 重新生成

在已安装项目依赖的虚拟环境中额外安装截图工具（业务运行不需要）：

```bash
python -m pip install playwright
python -m playwright install chromium
python scripts/capture_demo.py
```

脚本优先使用系统 Chromium，没有系统浏览器时使用 Playwright 安装的 Chromium。脚本需要本地端口权限，会运行完整 demo 和全部测试；任一步失败都会中止。它使用临时数据库，不清空已有业务数据库；更新 outputs 下的演示报表与 docs/assets 下的展示素材。

更新截图后应检查图片文字和表格，并核对 README 中的测试数量。不要用手写的成功数字替代命令输出。
