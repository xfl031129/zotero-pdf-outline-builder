var PDFOutlineBuilderPlugin = class {
  constructor({ id, version, rootURI }) {
    this.id = id;
    this.version = version;
    this.rootURI = rootURI;
    this.menuItem = null;
    this.menuPopup = null;
    this.onPopupShowing = this.onPopupShowing.bind(this);
    this.onCommand = this.onCommand.bind(this);
  }

  async startup() {
    this.window = Zotero.getMainWindow();
    this.document = this.window.document;
    await this.prepareBundledHelper();
    this.addMenuItem();
    Zotero.debug("[PDF Outline Builder] Started");
  }

  async shutdown() {
    if (this.menuPopup) {
      this.menuPopup.removeEventListener("popupshowing", this.onPopupShowing);
    }
    if (this.menuItem) {
      this.menuItem.removeEventListener("command", this.onCommand);
      this.menuItem.remove();
    }
    this.menuItem = null;
    this.menuPopup = null;
    Zotero.debug("[PDF Outline Builder] Stopped");
  }

  addMenuItem() {
    const doc = this.document;
    const popup = doc.getElementById("zotero-itemmenu") || doc.getElementById("zotero-itemmenu-popup");
    if (!popup) {
      Zotero.debug("[PDF Outline Builder] Could not find Zotero item context menu");
      return;
    }

    const menuItem = doc.createXULElement ? doc.createXULElement("menuitem") : doc.createElement("menuitem");
    menuItem.id = "pdf-outline-builder-generate";
    menuItem.setAttribute("label", "生成/更新 PDF 大纲");
    menuItem.setAttribute("tooltiptext", "为选中的 Zotero 条目或 PDF 附件生成标准 PDF 书签大纲");
    menuItem.addEventListener("command", this.onCommand);

    const separator = doc.createXULElement ? doc.createXULElement("menuseparator") : doc.createElement("menuseparator");
    separator.id = "pdf-outline-builder-separator";
    popup.appendChild(separator);
    popup.appendChild(menuItem);
    popup.addEventListener("popupshowing", this.onPopupShowing);

    this.menuPopup = popup;
    this.menuItem = menuItem;
    this.menuSeparator = separator;
  }

  async onPopupShowing() {
    if (!this.menuItem) {
      return;
    }
    const attachments = await this.getSelectedPDFAttachments();
    const disabled = attachments.length === 0;
    this.menuItem.hidden = disabled;
    if (this.menuSeparator) {
      this.menuSeparator.hidden = disabled;
    }
    this.menuItem.setAttribute("disabled", disabled ? "true" : "false");
    this.menuItem.setAttribute(
      "label",
      attachments.length > 1 ? `生成/更新 ${attachments.length} 个 PDF 大纲` : "生成/更新 PDF 大纲",
    );
  }

  async onCommand() {
    try {
      const attachments = await this.getSelectedPDFAttachments();
      if (!attachments.length) {
        this.alert("没有找到 PDF 附件", "请选中带 PDF 附件的文献条目，或直接选中 PDF 附件。");
        return;
      }
      await this.runForAttachments(attachments);
    } catch (error) {
      Zotero.debug(`[PDF Outline Builder] ${error.stack || error}`);
      this.alert("生成 PDF 大纲失败", String(error.message || error));
    }
  }

  async getSelectedPDFAttachments() {
    const pane = Zotero.getActiveZoteroPane();
    const selected = pane.getSelectedItems();
    const attachments = [];
    const seen = new Set();

    for (const item of selected) {
      const pdfs = await this.getPDFsForItem(item);
      for (const pdf of pdfs) {
        if (!seen.has(pdf.id)) {
          seen.add(pdf.id);
          attachments.push(pdf);
        }
      }
    }
    return attachments;
  }

  async getPDFsForItem(item) {
    if (!item) {
      return [];
    }

    if (item.isAttachment && item.isAttachment()) {
      return this.isPDFAttachment(item) ? [item] : [];
    }

    if (!item.getAttachments) {
      return [];
    }
    const childIDs = item.getAttachments();
    const children = Zotero.Items.get(childIDs);
    return children.filter((child) => this.isPDFAttachment(child));
  }

  isPDFAttachment(item) {
    if (!item || !item.isAttachment || !item.isAttachment()) {
      return false;
    }
    if (item.isPDFAttachment && item.isPDFAttachment()) {
      return true;
    }
    const contentType = item.attachmentContentType || "";
    return contentType.toLowerCase() === "application/pdf";
  }

  async runForAttachments(attachments) {
    this.validateConfig();
    const failures = [];
    let successCount = 0;

    for (let index = 0; index < attachments.length; index++) {
      const attachment = attachments[index];
      const label = attachment.getField("title") || attachment.attachmentFilename || `PDF ${index + 1}`;
      Zotero.debug(`[PDF Outline Builder] Processing ${index + 1}/${attachments.length}: ${label}`);

      try {
        const filePath = await attachment.getFilePathAsync();
        if (!filePath) {
          throw new Error("无法获取 PDF 文件路径");
        }
        const result = await this.runHelper(filePath);
        if (!result.ok) {
          throw new Error(result.error || "未知错误");
        }
        successCount++;
        Zotero.debug(`[PDF Outline Builder] Generated ${result.count} entries for ${filePath}`);
      } catch (error) {
        failures.push(`${label}: ${error.message || error}`);
      }
    }

    if (failures.length) {
      this.alert(
        "PDF 大纲生成完成，但有失败",
        `成功：${successCount}\n失败：${failures.length}\n\n${failures.slice(0, 8).join("\n")}`,
      );
    } else {
      this.alert("PDF 大纲生成完成", `已处理 ${successCount} 个 PDF。重新打开 PDF 阅读器标签后即可看到大纲。`);
    }
  }

  validateConfig() {
    const config = PDFOutlineBuilderConfig;
    if (!config) {
      throw new Error("插件配置不存在，请重新安装插件。");
    }
    if (config.useBundledHelper) {
      if (!config.helperExecutablePath) {
        throw new Error("内置 helper 未准备好，请重启 Zotero 后重试。");
      }
      return;
    }
    if (!config.pythonPath || !config.helperScript || !config.projectSrc) {
      throw new Error("插件配置不完整，请重新运行 BUILD_ZOTERO_PLUGIN.bat。");
    }
  }

  async runHelper(pdfPath) {
    const config = PDFOutlineBuilderConfig;
    const jsonPath = await this.makeTempJSONPath();
    const jobPath = await this.makeTempJSONPath("job");
    const logPath = await this.makeTempJSONPath("log");
    const job = {
      input: pdfPath,
      json_out: jsonPath,
      min_confidence: config.minConfidence || 0.30,
      force: config.force !== false,
    };
    let executablePath = config.helperExecutablePath;
    let args = ["--job", jobPath];
    if (!config.useBundledHelper) {
      job.helper_script = config.helperScript;
      job.project_src = config.projectSrc;
      const launcher = [
        "import json, runpy, sys",
        "job = json.load(open(sys.argv[1], encoding='utf-8-sig'))",
        "sys.argv = [job['helper_script'], '--job', sys.argv[1]]",
        "runpy.run_path(job['helper_script'], run_name='__main__')",
      ].join("; ");
      executablePath = config.pythonPath;
      args = ["-c", launcher, jobPath];
    }
    await IOUtils.writeUTF8(jobPath, JSON.stringify(job));

    const exitCode = await this.runProcess(executablePath, args, logPath);
    let payload = null;
    try {
      payload = JSON.parse(await IOUtils.readUTF8(jsonPath));
      await IOUtils.remove(jsonPath, { ignoreAbsent: true });
    } catch (error) {
      const logText = await this.readTextIfExists(logPath);
      payload = {
        ok: false,
        error: `helper 没有写出结果 JSON，exit=${exitCode}: ${error.message || error}\n\n${logText}`,
      };
    }
    await IOUtils.remove(jobPath, { ignoreAbsent: true });
    await IOUtils.remove(logPath, { ignoreAbsent: true });
    if (exitCode !== 0 && payload.ok) {
      payload.ok = false;
      payload.error = `helper exit code ${exitCode}`;
    }
    return payload;
  }

  async prepareBundledHelper() {
    const config = PDFOutlineBuilderConfig;
    if (!config || !config.useBundledHelper) {
      return;
    }
    if (!config.bundledHelper) {
      throw new Error("插件配置缺少 bundledHelper。");
    }

    const targetDir = PathUtils.join(PathUtils.profileDir, "pdf-outline-builder");
    const targetPath = PathUtils.join(targetDir, "outline-helper.exe");
    await IOUtils.makeDirectory(targetDir, { ignoreExisting: true });

    const response = await fetch(this.rootURI + config.bundledHelper);
    if (!response.ok) {
      throw new Error(`无法读取内置 helper: ${response.status}`);
    }
    const bytes = new Uint8Array(await response.arrayBuffer());
    await IOUtils.write(targetPath, bytes);
    config.helperExecutablePath = targetPath;
    Zotero.debug(`[PDF Outline Builder] Bundled helper ready: ${targetPath}`);
  }

  async makeTempJSONPath(kind = "result") {
    const extension = kind === "log" ? "txt" : "json";
    const name = `zotero-pdf-outline-${kind}-${Date.now()}-${Math.random().toString(16).slice(2)}.${extension}`;
    return PathUtils.join(PathUtils.tempDir, name);
  }

  async readTextIfExists(path) {
    try {
      return await IOUtils.readUTF8(path);
    } catch (error) {
      return "";
    }
  }

  runProcess(executablePath, args, logPath = null) {
    return new Promise((resolve, reject) => {
      try {
        const file = Components.classes["@mozilla.org/file/local;1"].createInstance(Components.interfaces.nsIFile);
        file.initWithPath(executablePath);
        const process = Components.classes["@mozilla.org/process/util;1"].createInstance(Components.interfaces.nsIProcess);
        process.init(file);
        if (logPath && process.startHidden !== undefined) {
          process.startHidden = true;
        }
        process.runAsync(
          args,
          args.length,
          {
            observe(subject, topic) {
              if (topic === "process-finished" || topic === "process-failed") {
                resolve(process.exitValue);
              }
            },
          },
          false,
        );
      } catch (error) {
        reject(error);
      }
    });
  }

  alert(title, message) {
    Services.prompt.alert(this.window, title, message);
  }
};
