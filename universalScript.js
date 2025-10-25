console.log("ResuMate script loaded:", location.href);

function scrapeProfile() {
  const name = document.querySelector(".pv-text-details__left-panel h1")?.innerText.trim() || "";
  const headline = document.querySelector(".pv-text-details__left-panel .text-body-medium")?.innerText.trim() || "";
  const about = document.querySelector(".pv-shared-text-with-see-more span[aria-hidden='true']")?.innerText.trim() || "";
  return { type: "profile", name, headline, about };
}

function scrapeJob() {
  const title = document.querySelector("h1.top-card-layout__title, h1.jobs-unified-top-card__job-title")?.innerText.trim() || "";
  const company = document.querySelector("a.topcard__org-name-link, a.jobs-unified-top-card__company-name")?.innerText.trim() || "";
  const desc = document.querySelector(".show-more-less-html__markup, .jobs-box__html-content, .jobs-description__content")?.innerText.trim() || "";
  return { type: "job", title, company, desc };
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "SCRAPE_PROFILE") {
    sendResponse({ ok: true, data: scrapeProfile() });
  }
  if (msg.type === "SCRAPE_JOB") {
    sendResponse({ ok: true, data: scrapeJob() });
  }
  return true;
});
