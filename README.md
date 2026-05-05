# sooon_learn

这是一个基于 `ps_2026-04-25_all.json` 整理出来的 Obsidian 学习仓库，用来做文章归档、主题阅读、关系梳理和阅读笔记。

仓库目前包含 `3274` 篇文章，以及围绕它们生成的主题阅读包、聚类分析和图谱配置。

## 目录结构

- [文章](文章): 按 `年份 / 月份` 归档的原始文章笔记
- [主题分类阅读模板](主题分类阅读模板): 按主题拆好的阅读包和总表
- [总览](总览): 聚类分析、关系分析、思想地图、说明文档
- [scripts](scripts): 生成和维护这些文件的脚本
- [.obsidian](.obsidian): Obsidian 图谱、配色和界面配置

## 主要内容

### 1. 文章库

每篇文章都是独立 Markdown 文件，统一包含：

- 标题
- 问题
- 回答
- 来源链接
- 引用网络

为了方便在手机或桌面端一键复制，文章里的 `标题 / 问题 / 回答` 已经都用 `text` 代码块包起来。

### 2. 主题阅读包

阅读包目录在 [主题分类阅读模板](主题分类阅读模板)。

特点：

- 按主题分包
- 有总表和分表
- 阅读顺序做过排序
- 短文和长文使用不同阅读模板
- 长文支持 AI 输入 / AI 输出区块

总入口见：

- [00-主题阅读模板总表.md](主题分类阅读模板/00-主题阅读模板总表.md)

### 3. 总览与分析

分析文档集中在 [总览](总览) 下，包括：

- [README.md](总览/README.md): 文章整理说明与月份统计
- [文章关系分析.md](总览/文章关系分析.md): 文章之间的关系分析
- [作者思想地图.md](总览/作者思想地图.md): 核心母题和思想脉络
- [文章总目录表.md](总览/文章总目录表.md): 主题总目录
- [sklearn聚类分析.md](总览/sklearn聚类分析.md): 基于聚类的主题分析

## 使用方式

推荐直接用 Obsidian 打开这个目录作为 vault。

比较常见的使用方式是：

- 从总表挑一个阅读包开始读
- 在分表里边读边写阅读卡
- 通过文章底部的引用网络继续跳读
- 在关系图里按主题浏览

如果你只想快速开始，优先看这几个位置：

- [主题分类阅读模板](主题分类阅读模板)
- [总览](总览)
- [文章](文章)

## Codex 续接说明

如果你是在新的 Codex 会话里重新打开这个仓库，需要注意：

- Codex 不会仅凭本地文件自动恢复成之前的原始对话线程
- 但可以先读取本地说明文件，再基于这些内容继续工作

推荐先让 Codex 阅读：

- [总览/Codex对话续接说明.md](总览/Codex对话续接说明.md)
- [总览/文章关系分析.md](总览/文章关系分析.md)
- [主题分类阅读模板/00-主题阅读模板总表.md](主题分类阅读模板/00-主题阅读模板总表.md)

你可以在新会话里直接对 Codex 说：

```text
先阅读 README.md 和 总览/Codex对话续接说明.md，再继续在这个仓库上工作。
```

这样虽然不是“自动加载原对话”，但通常已经足够恢复这个仓库的上下文。

## 脚本说明

这个仓库里保留了生成脚本，方便后续重跑或增量维护。主要包括：

- [build_reading_templates.py](scripts/build_reading_templates.py): 生成阅读包
- [build_catalog_and_references.py](scripts/build_catalog_and_references.py): 生成目录和引用关系
- [cluster_articles_sklearn.py](scripts/cluster_articles_sklearn.py): 聚类分析
- [enrich_article_relations.py](scripts/enrich_article_relations.py): 丰富文章关系
- [wrap_article_copy_blocks.py](scripts/wrap_article_copy_blocks.py): 给文章内容包上可复制代码块

## Git 说明

这个仓库适合做版本管理，但有两类文件通常不值得提交：

- 系统缓存文件
- Obsidian 的本地工作区状态文件

所以 `.gitignore` 里默认排除了：

- `.DS_Store`
- Python 缓存目录
- `.obsidian/workspace.json`
- `.obsidian/workspaces.json`

这样既保留了图谱和主题配置，又减少了无意义变更。
