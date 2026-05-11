# Publishing Checklist

## One-Time Setup

Create a GitHub repository:

```text
xfl031129/zotero-pdf-outline-builder
```

The stable Zotero add-on id is:

```text
zotero-pdf-outline-builder@xfl031129.github.io
```

Do not change this id after users install the plugin.

## Build Release

```bat
BUILD_WINDOWS_RELEASE.bat
```

Release assets are created in:

```text
dist/release/
```

Upload these two files to GitHub Release `v0.1.2`:

```text
zotero-pdf-outline-builder-windows-v0.1.2.xpi
updates.json
```

## Test Install

1. Remove any old development build from Zotero.
2. Install the release XPI.
3. Restart Zotero.
4. Right-click a Zotero item with a PDF attachment.
5. Run `生成/更新 PDF 大纲`.

## Submit To Zotero Chinese Plugin Index

Fork:

```text
https://github.com/syt2/zotero-addons-scraper
```

Add:

```text
addons/xfl031129@zotero-pdf-outline-builder
```

Content:

```json
{"tags": ["reader", "attachment", "utility"]}
```

Open a pull request.
