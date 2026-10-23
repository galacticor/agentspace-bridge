const BRIDGE_BASE = "http://127.0.0.1:18765";

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg && msg.type === "CHECK_BRIDGE_HEALTH") {
    (async () => {
      try {
        const resp = await fetch(`${BRIDGE_BASE}/health`, { method: "GET" });
        const data = await resp.json();
        sendResponse({ ok: Boolean(resp.ok && data && data.ok) });
      } catch (err) {
        sendResponse({ ok: false, error: String(err) });
      }
    })();
    return true;
  }

  if (msg && msg.type === "EXPORT_NATIVE_PPTX") {
    (async () => {
      try {
        const session = encodeURIComponent(msg.session || "");
        const csesidx = encodeURIComponent(msg.csesidx || "");
        const url = `${BRIDGE_BASE}/export?session=${session}&csesidx=${csesidx}&tag=chrome_ext`;

        const resp = await fetch(url, { method: "GET" });
        if (!resp.ok) {
          let errText = `HTTP ${resp.status}`;
          try {
            const errJson = await resp.json();
            if (errJson && errJson.error) errText = errJson.error;
          } catch (_) {}
          sendResponse({ ok: false, error: errText });
          return;
        }

        const disposition = resp.headers.get("Content-Disposition") || "";
        const compiler = resp.headers.get("X-PPTX-Compiler") || "native_pptx";
        const slidesCount = resp.headers.get("X-PPTX-Slides") || "";
        let filename = `agentspace_${msg.session || "deck"}_native.pptx`;
        const match = disposition.match(/filename="([^"]+)"/i);
        if (match && match[1]) {
          filename = match[1];
        }

        const buf = await resp.arrayBuffer();
        const bytes = new Uint8Array(buf);
        let binary = "";
        const chunkSize = 0x8000;
        for (let i = 0; i < bytes.length; i += chunkSize) {
          binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunkSize));
        }
        const dataUrl =
          "data:application/vnd.openxmlformats-officedocument.presentationml.presentation;base64," +
          btoa(binary);

        await chrome.downloads.download({
          url: dataUrl,
          filename: filename,
          saveAs: false
        });

        sendResponse({
          ok: true,
          filename: filename,
          compiler: compiler,
          slidesCount: slidesCount,
          bytes: bytes.length
        });
      } catch (err) {
        sendResponse({
          ok: false,
          error:
            "Local bridge not running on 127.0.0.1:18765. Run: python agentspace_cli.py --serve-chrome"
        });
      }
    })();
    return true;
  }
});
