# Zotero 插件调试说明

这个目录是 Zotero 7/8/9.0 插件的开发版外壳。插件会在 Zotero 条目右键菜单里加入 `生成/更新 PDF 大纲`，然后调用当前项目里的 Python 识别引擎，给选中的 PDF 附件原地写入标准 PDF 书签大纲。

## 打包

在项目根目录双击：

```bat
BUILD_ZOTERO_PLUGIN.bat
```

输出文件：

```text
dist\pdf-outline-builder-for-zotero.xpi
```

每次移动项目目录、重建虚拟环境或修改插件 JS/Python 后，都重新运行这个 bat。它会自动刷新：

- `.venv\Scripts\python.exe`
- `zotero-plugin\native\run_outline.py`
- `src`

## 安装到 Zotero

1. 打开 Zotero。
2. 菜单进入 `Tools` -> `Plugins`。有些版本里仍显示为 `Add-ons`。
3. 点击齿轮按钮，选择 `Install Plugin From File...` 或 `Install Add-on From File...`。
4. 选择 `dist\pdf-outline-builder-for-zotero.xpi`。
5. 重启 Zotero。

## 使用

在 Zotero 主列表里：

- 右键一个带 PDF 附件的论文条目，点 `生成/更新 PDF 大纲`。
- 或者直接右键 PDF 附件。
- 可以多选多个条目，插件会批量处理所有 PDF 附件。

处理成功后，关闭并重新打开 Zotero PDF 阅读器标签，就能看到新的 PDF 大纲。

## 调试

### 看插件日志

Zotero 里打开：

```text
Help -> Debug Output Logging -> View Output
```

插件日志前缀是：

```text
[PDF Outline Builder]
```

### 常见问题

- 右键菜单没出现：确认选中的是论文条目或 PDF 附件，并重启 Zotero。
- 处理失败并提示文件无法替换：先关闭 Zotero 里打开的 PDF 阅读器标签，再重试。
- 提示 Python/helper/config 相关错误：重新运行 `BUILD_ZOTERO_PLUGIN.bat`。
- 识别效果不对：先用网页调试 UI 或 CLI 复现，因为 Zotero 插件调用的是同一套 Python 引擎。

## 当前限制

这是开发版插件，XPI 里保存的是当前项目的绝对路径。要发给别人用，下一步应该把 Python 引擎打成独立 exe，或者在插件设置页里让用户选择 Python/引擎路径。
