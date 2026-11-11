/* Career Agent System v7.8.0 — 5-Stage Data Processing & Multi-Page Coordinator */
(function () {
  window.CA_TAB_STAGE_MAP = {
    "profile": 1, "user-hub": 1, "user-data-engine": 1,
    "agents": 2, "single-agent": 2, "rag-engine": 2,
    "jobs": 3, "certs": 3, "contests": 3, "feeds": 3, "materials": 3, "tech-updates": 3,
    "resume": 4, "direct-apply": 4,
    "dashboard": 5, "email-dispatcher": 5, "gmail-inbox": 5, "tracker": 5, "terminal": 5, "vault": 5, "theme-studio": 5
  };

  window.CA_STAGE_DEFAULT_TAB = {
    1: "profile",
    2: "agents",
    3: "jobs",
    4: "resume",
    5: "dashboard"
  };

  window.CA_FILE_TO_TAB = {
    "index.html": { tab: "dashboard", stage: 5 },
    "user_hub.html": { tab: "user-hub", stage: 1 },
    "profile.html": { tab: "profile", stage: 1 },
    "agents.html": { tab: "agents", stage: 2 },
    "agent_greenhouse.html": { tab: "single-agent", agentId: "jobglove", stage: 2 },
    "agent_remotive.html": { tab: "single-agent", agentId: "jobspy", stage: 2 },
    "agent_arbeitnow.html": { tab: "single-agent", agentId: "jobglove", stage: 2 },
    "agent_hn.html": { tab: "single-agent", agentId: "hackernews_api", stage: 2 },
    "agent_ashby.html": { tab: "single-agent", agentId: "browser_use", stage: 2 },
    "agent_ai_news.html": { tab: "single-agent", agentId: "github_api", stage: 2 },
    "agent_youtube.html": { tab: "single-agent", agentId: "imap_smtp_mime", stage: 2 },
    "agent_contests.html": { tab: "single-agent", agentId: "kaggle_datasets", stage: 2 },
    "agent_certs.html": { tab: "single-agent", agentId: "classcentral", stage: 2 },
    "jobs.html": { tab: "jobs", stage: 3 },
    "contests.html": { tab: "contests", stage: 3 },
    "certs.html": { tab: "certs", stage: 3 },
    "feeds.html": { tab: "feeds", stage: 3 },
    "resume.html": { tab: "resume", stage: 4 },
    "tracker.html": { tab: "tracker", stage: 5 },
    "terminal.html": { tab: "terminal", stage: 5 },
    "vault.html": { tab: "vault", stage: 5 }
  };

  window.CA_TAB_TO_FILE = {
    "dashboard": "index.html",
    "user-hub": "user_hub.html",
    "user-data-engine": "profile.html",
    "profile": "profile.html",
    "agents": "agents.html",
    "rag-engine": "agents.html",
    "jobs": "jobs.html",
    "contests": "contests.html",
    "certs": "certs.html",
    "feeds": "feeds.html",
    "materials": "feeds.html",
    "tech-updates": "feeds.html",
    "resume": "resume.html",
    "direct-apply": "resume.html",
    "email-dispatcher": "index.html",
    "gmail-inbox": "index.html",
    "tracker": "tracker.html",
    "terminal": "terminal.html",
    "vault": "vault.html",
    "theme-studio": "index.html"
  };

  window.CA_AGENT_TO_FILE = {
    "jobspy": "agent_remotive.html",
    "jobglove": "agent_greenhouse.html",
    "classcentral": "agent_certs.html",
    "aihawk": "resume.html",
    "browser_use": "agent_ashby.html",
    "imap_smtp_mime": "agent_youtube.html",
    "github_api": "agent_ai_news.html",
    "hackernews_api": "agent_hn.html",
    "kaggle_datasets": "agent_contests.html"
  };

  window.syncPipelineStageBar = function (tabName) {
    var stageNum = (window.CA_TAB_STAGE_MAP && window.CA_TAB_STAGE_MAP[tabName]) || 5;
    document.querySelectorAll("[data-pipeline-stage]").forEach(function (el) {
      var s = parseInt(el.getAttribute("data-pipeline-stage"), 10);
      var isCurrent = s === stageNum;
      el.classList.toggle("active", isCurrent);
      el.setAttribute("aria-current", isCurrent ? "step" : "false");
    });
    var badge = document.getElementById("active-html-file-badge");
    if (badge) {
      badge.textContent = "Stage " + stageNum + " • " + (tabName || "dashboard");
    }
  };

  window.switchPipelineStage = function (stageNum) {
    var targetTab = (window.CA_STAGE_DEFAULT_TAB && window.CA_STAGE_DEFAULT_TAB[stageNum]) || "dashboard";
    if (typeof window.switchTab === "function") {
      window.switchTab(targetTab);
    }
  };
})();
