# Paper-Feed: 自动化文献精准筛选与推送系统

[![GitHub Actions](https://img.shields.io/badge/Actions-Automated-blue.svg)](https://github.com/features/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

### 系统概述
本工具是一个基于 GitHub Actions 的全自动文献监测系统。它旨在解决科研工作中的信息筛选效率问题，功能逻辑如下：
1.  **抓取**：定时从指定的期刊 RSS 源获取最新发表的论文。
2.  **筛选**：根据预设的关键词逻辑（支持 `AND` 组合）对标题和摘要进行匹配。
3.  **分发**：将命中的论文重组为标准化的 RSS 订阅源，供 Zotero 等阅读器订阅。

---

## 🛠 功能特性

*   **全自动运行**：无需服务器，利用 GitHub Actions 每 6 小时自动执行一次检索。
*   **多维度检索**：支持简单的关键词匹配及 `Keyword A AND Keyword B` 的组合逻辑检索。
*   **数据清洗**：内置 XML 字符清洗程序，自动移除非法字符，确保订阅源的兼容性与稳定性。
*   **隐私保护**：支持通过 GitHub Secrets 注入配置，隐藏用户的研究领域与关注列表。
*   **通用兼容**：生成的 `filtered_feed.xml` 遵循 RSS 2.0 标准，适配所有主流 RSS 阅读器。

---

## 🚀 部署流程

### 1. 初始化项目
1.  点击本页面右上角的 **Fork**，将仓库复制到你的账号下。
2.  在你的仓库中，删除根目录下的 `filtered_feed.xml` 文件（清除示例数据）。

### 2. 配置参数
提供两种配置方式，**涉及未发表 Idea 或敏感方向建议使用方式 B**。

> 提示：当前默认的 `journals.dat` 已按 **CCF A类（软件工程/系统软件/程序设计语言）期刊/会议** + **信息安全顶会（S&P/CCS/USENIX Security/NDSS）**（含 EuroS&P/RAID/ACSAC） + **AI 顶会（AAAI/NeurIPS/ACL/ICML/IJCAI）** + **arXiv（cs.CR/cs.SE/cs.PL/cs.AI/cs.LG/cs.CL/cs.IR/stat.ML）** 给了一套起步订阅源，并补充了部分中科院 1 区/常见顶级期刊（如 TDSC/TIFS/TOPS/CSUR/ESE/ASE/IST/JSS/SCP/IEEE S&P 等）；原材料/物理方向的示例 RSS 列表保存在 `journals.dat`。

#### 文件配置（公开可见）
直接编辑仓库中的以下文件：
*   `journals.dat`：填入期刊 RSS 链接，一行一个。
*   `keywords.dat`：填入筛选关键词，一行一个。
    *   示例：`Perovskite AND Stability`


### 3. 启动服务
1.  **配置 Pages**：
    *   进入 **Settings** -> **Pages**。
    *   **Build and deployment** 下，Source 选择 `Deploy from a branch`。
    *   Branch 选择 `main` 分支的 `/(root)` 目录。
    *   点击 **Save**。
2.  **激活 Workflow**：
    *   进入 **Actions** 页面。
    *   若提示 "Workflows aren't being run..."，点击绿色按钮 **I understand my workflows, go ahead and enable them**。
    *   选中左侧 **Auto RSS Fetch** -> **Run workflow** 手动触发首次运行。

---

## 📈 客户端接入 (以 Zotero 为例)

1.  **获取订阅链接**：
    `https://{你的GitHub用户名}.github.io/{仓库名}/filtered_feed.xml`
2.  **添加订阅**：
    *   Zotero 菜单栏：`文件` -> `新建文献库` -> `新建订阅` -> `从网址`。
    *   粘贴上述链接。
3.  **设置同步频率**：
    *   建议在 Zotero 订阅设置中将更新时间设为 **6小时** 或更短，以匹配后端的更新频率。

---

## ⚠️ 维护说明

1.  **关键词优化**：若订阅源中无关论文过多，请检查 `keywords.dat` 是否过于宽泛；若漏掉重要论文，请检查是否拼写错误或逻辑过严。
2.  **活跃度维持**：GitHub 可能会暂停长期无代码提交仓库的 Actions 定时任务。若发现停止更新，请进入 Actions 页面手动启用或提交一次空的 Commit。(真的吗，AI说的我也不知道)
3.  **解析失败**：部分期刊 RSS 格式不规范。若遇到特定期刊抓取失败，请检查其 RSS XML 结构的合法性。
