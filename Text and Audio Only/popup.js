const radios = document.querySelectorAll('input[name="mode"]');

function setMode(mode) {
  chrome.runtime.sendMessage({ type: "setMode", mode });
}

chrome.storage.sync.get("mode", (d) => {
  const m = d.mode || "normal";
  [...radios].find(r => r.value === m).checked = true;
});

radios.forEach(r => r.addEventListener("change", () => setMode(r.value)));
