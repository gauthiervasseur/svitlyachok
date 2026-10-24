"use strict";

// The GitHub repository that publishes the releases. Change this if the repo has another name.
const REPO = "gauthiervasseur/svitlyachok";
const ASSETS = { mac: "Svitlyachok-macOS.dmg", win: "Svitlyachok-Windows-Setup.exe" };

const latest = (asset) => `https://github.com/${REPO}/releases/latest/download/${asset}`;
document.getElementById("dl-mac").href = latest(ASSETS.mac);
document.getElementById("dl-win").href = latest(ASSETS.win);
document.getElementById("source-link").href = `https://github.com/${REPO}`;
document.getElementById("releases-link").href = `https://github.com/${REPO}/releases`;

// Highlight the visitor's platform.
const platform = (navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || navigator.userAgent;
const os = /mac/i.test(platform) ? "mac" : /win/i.test(platform) ? "win" : null;
if (os) document.querySelector(`.cart[data-os="${os}"]`).classList.add("mine");

// Version and sizes from the latest release (works for public repositories).
fetch(`https://api.github.com/repos/${REPO}/releases/latest`)
  .then((response) => (response.ok ? response.json() : Promise.reject(response.status)))
  .then((release) => {
    const date = new Date(release.published_at).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
    document.getElementById("release").textContent = `LATEST: ${release.tag_name.toUpperCase()} · ${date.toUpperCase()}`;
    for (const el of document.querySelectorAll("[data-asset]")) {
      const asset = release.assets.find((a) => a.name === el.dataset.asset);
      if (asset) el.textContent = `${el.textContent} · ${(asset.size / 1e6).toFixed(0)} MB`;
    }
  })
  .catch(() => { /* private repo, rate limit or offline: keep the static labels */ });

// Ambient fireflies.
const sky = document.querySelector(".sky");
for (let i = 0; i < 22; i++) {
  const f = document.createElement("i");
  f.style.left = `${Math.random() * 100}%`;
  f.style.top = `${20 + Math.random() * 80}%`;
  f.style.setProperty("--dx", `${Math.round(Math.random() * 120 - 60)}px`);
  f.style.setProperty("--dy", `${Math.round(-40 - Math.random() * 140)}px`);
  f.style.setProperty("--d", `${10 + Math.random() * 14}s`);
  f.style.setProperty("--delay", `${-Math.random() * 20}s`);
  sky.append(f);
}
