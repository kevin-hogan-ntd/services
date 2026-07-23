const MODES = { NORMAL: "normal", TEXT: "text", AUDIO: "audio" };
const STYLE_ID = "textModeStyle";

/* ── install default ───────────────────────────────────────────────────── */
chrome.runtime.onInstalled.addListener(() =>
  chrome.storage.sync.set({ mode: MODES.NORMAL }));

/* ── helpers ───────────────────────────────────────────────────────────── */
function cssFor(mode, host) {
  if (mode === MODES.TEXT) {
    return `
img,picture,svg,source,object,embed,iframe,video {display:none!important;}
*{background-image:none!important;}
`;
  }
  if (mode === MODES.AUDIO) {
    // keep Youglish transport buttons (.small / .big) visible
    if (host.endsWith("youglish.com")) {
      return `
img:not(.small):not(.big) {display:none!important;}
video,iframe {opacity:0!important;pointer-events:auto!important;}
*{background-image:none!important;}
`;
    }
    return `
img,picture,svg,source,object,embed {display:none!important;}
video,iframe {opacity:0!important;pointer-events:auto!important;}
*{background-image:none!important;}
`;
  }
  return ""; // NORMAL
}

function injectMode(tabId, mode) {
  chrome.scripting.executeScript({
    target: { tabId, allFrames: true },
    world: "MAIN",
    args: [mode],
    func: (mode) => {
      const STYLE_ID = "textModeStyle";

      /* -- insert / update style element -------------------------------- */
      let style = document.getElementById(STYLE_ID);
      if (!style) {
        style = document.createElement("style");
        style.id = STYLE_ID;
        document.head.appendChild(style);
      }

      const host = location.hostname;
      function cssFor(m, h) {
        if (m === "text") {
          return `
img,picture,svg,source,object,embed,iframe,video {display:none!important;}
*{background-image:none!important;}
`;
        }
        if (m === "audio") {
          if (h.endsWith("youglish.com")) {
            return `
img:not(.small):not(.big) {display:none!important;}
video,iframe {opacity:0!important;pointer-events:auto!important;}
*{background-image:none!important;}
`;
          }
          return `
img,picture,svg,source,object,embed {display:none!important;}
video,iframe {opacity:0!important;pointer-events:auto!important;}
*{background-image:none!important;}
`;
        }
        return ""; // NORMAL
      }
      style.textContent = cssFor(mode, host);

      /* -- TEXT-ONLY: kill all media now & in future -------------------- */
      if (mode === "text") {
        const killMedia = (root = document) => {
          root.querySelectorAll("video,audio").forEach((el) => {
            try { el.pause(); } catch {}
            try { el.currentTime = 0; } catch {}
            try { el.src = ""; } catch {}
            try { el.load(); } catch {}
          });
        };
        killMedia();

        /* also reach into iframes when same-origin and tell YouTube to pause */
        document.querySelectorAll("iframe").forEach((f) => {
          try { killMedia(f.contentDocument || f.contentWindow?.document); } catch {}
          try { f.contentWindow?.postMessage('{"event":"command","func":"pauseVideo","args":""}', "*"); } catch {}
        });

        /* observe for new media nodes */
        new MutationObserver((mutList) => {
          for (const m of mutList) {
            if (m.type === "childList") {
              m.addedNodes.forEach((n) => {
                if (!n) return;
                if (n.tagName === "VIDEO" || n.tagName === "AUDIO") {
                  killMedia(n.parentNode || document);
                } else if (n.querySelectorAll) {
                  killMedia(n);
                }
              });
            }
          }
        }).observe(document.body || document.documentElement, {
          childList: true,
          subtree: true
        });
      }
    }
  });
}

function refreshAllTabs(mode) {
  chrome.tabs.query({}, (tabs) => tabs.forEach((t) => injectMode(t.id, mode)));
}

/* ── storage & tab events ──────────────────────────────────────────────── */
chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === "setMode") {
    chrome.storage.sync.set({ mode: msg.mode }, () => refreshAllTabs(msg.mode));
  }
});

chrome.tabs.onUpdated.addListener((tabId, info) => {
  if (info.status === "complete") {
    chrome.storage.sync.get("mode", (d) => injectMode(tabId, d.mode || MODES.NORMAL));
  }
});

chrome.tabs.onActivated.addListener(({ tabId }) =>
  chrome.storage.sync.get("mode", (d) => injectMode(tabId, d.mode || MODES.NORMAL)));
