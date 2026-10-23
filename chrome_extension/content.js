(() => {
  const BTN_ID = "ioh-agy-native-pptx-btn";
  const TOAST_ID = "ioh-agy-native-pptx-toast";

  function parseSessionFromUrl() {
    const m = window.location.pathname.match(/\/session\/(\d+)/);
    const params = new URLSearchParams(window.location.search);
    return {
      session: m ? m[1] : "",
      csesidx: params.get("csesidx") || ""
    };
  }

  function showToast(text, isError = false) {
    let toast = document.getElementById(TOAST_ID);
    if (!toast) {
      toast = document.createElement("div");
      toast.id = TOAST_ID;
      Object.assign(toast.style, {
        position: "fixed",
        top: "58px",
        right: "18px",
        zIndex: "2147483647",
        padding: "10px 14px",
        borderRadius: "8px",
        fontFamily: "'Plus Jakarta Sans', 'Segoe UI', system-ui, sans-serif",
        fontSize: "12px",
        fontWeight: "600",
        boxShadow: "0 10px 25px rgba(15, 23, 42, 0.22)",
        transition: "opacity 0.2s ease",
        maxWidth: "380px",
        lineHeight: "1.4"
      });
      document.body.appendChild(toast);
    }
    toast.style.backgroundColor = isError ? "#FEF2F2" : "#0F172A";
    toast.style.color = isError ? "#991B1B" : "#F8FAFC";
    toast.style.border = isError ? "1px solid #FCA5A5" : "1px solid #334155";
    toast.textContent = text;
    toast.style.opacity = "1";

    clearTimeout(window.__iohToastTimer);
    window.__iohToastTimer = setTimeout(() => {
      if (toast) toast.style.opacity = "0";
    }, 5500);
  }

  function ensureButton() {
    let btn = document.getElementById(BTN_ID);
    const { session } = parseSessionFromUrl();

    if (!btn) {
      btn = document.createElement("button");
      btn.id = BTN_ID;
      btn.type = "button";
      Object.assign(btn.style, {
        position: "fixed",
        top: "12px",
        right: "140px",
        zIndex: "2147483647",
        display: "inline-flex",
        alignItems: "center",
        gap: "6px",
        padding: "7px 13px",
        borderRadius: "7px",
        border: "1px solid rgba(255,255,255,0.16)",
        backgroundColor: "#4840E6",
        color: "#FFFFFF",
        fontFamily: "'Plus Jakarta Sans', 'Segoe UI', system-ui, sans-serif",
        fontSize: "12px",
        fontWeight: "700",
        letterSpacing: "0.01em",
        cursor: "pointer",
        boxShadow: "0 4px 12px rgba(72, 64, 230, 0.32)",
        transition: "all 0.15s ease"
      });

      btn.addEventListener("mouseenter", () => {
        if (!btn.disabled) btn.style.backgroundColor = "#3B33D1";
      });
      btn.addEventListener("mouseleave", () => {
        if (!btn.disabled) btn.style.backgroundColor = "#4840E6";
      });

      btn.addEventListener("click", async () => {
        const info = parseSessionFromUrl();
        if (!info.session) {
          showToast("Open an Agentspace chat session first (/r/session/<id>) to export slides.", true);
          return;
        }

        btn.disabled = true;
        const originalText = btn.textContent;
        btn.textContent = "⏳ Compiling Native PPTX...";
        btn.style.backgroundColor = "#334155";
        btn.style.cursor = "wait";

        try {
          const res = await chrome.runtime.sendMessage({
            type: "EXPORT_NATIVE_PPTX",
            session: info.session,
            csesidx: info.csesidx
          });

          if (res && res.ok) {
            const modeLabel =
              res.compiler === "native_python_pptx_lxml"
                ? "python-pptx + lxml"
                : "Playwright DOM Compiler";
            showToast(`✅ Downloaded ${res.filename} (${modeLabel})`);
          } else {
            showToast(`❌ ${res ? res.error : "Export failed"}`, true);
          }
        } catch (err) {
          showToast(`❌ Extension error: ${String(err)}`, true);
        } finally {
          btn.disabled = false;
          btn.style.backgroundColor = "#4840E6";
          btn.style.cursor = "pointer";
          btn.textContent = originalText;
        }
      });

      document.body.appendChild(btn);
    }

    if (session) {
      btn.textContent = "⬇ Native PPTX";
      btn.title = `Compile & download native PPTX for session ${session} (python-pptx + lxml / DOM compiler)`;
      btn.style.opacity = "1";
    } else {
      btn.textContent = "⬇ Native PPTX";
      btn.title = "Open a session with slides or native python-pptx code to download";
      btn.style.opacity = "0.75";
    }
  }

  ensureButton();
  const observer = new MutationObserver(() => {
    if (!document.getElementById(BTN_ID)) {
      ensureButton();
    }
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });
  window.addEventListener("popstate", ensureButton);
  setInterval(ensureButton, 1500);
})();
