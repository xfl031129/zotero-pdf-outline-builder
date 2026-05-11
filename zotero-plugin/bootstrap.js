var Services;
try {
  Services = ChromeUtils.importESModule("resource://gre/modules/Services.sys.mjs").Services;
} catch (error) {
  Services = ChromeUtils.import("resource://gre/modules/Services.jsm").Services;
}

var plugin;

function install() {}

async function startup({ id, version, rootURI }) {
  Services.scriptloader.loadSubScript(rootURI + "chrome/content/config.js");
  Services.scriptloader.loadSubScript(rootURI + "chrome/content/outline-plugin.js");
  plugin = new PDFOutlineBuilderPlugin({ id, version, rootURI });
  await plugin.startup();
}

async function shutdown() {
  if (plugin) {
    await plugin.shutdown();
    plugin = null;
  }
}

function uninstall() {}
