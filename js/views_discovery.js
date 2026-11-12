    function renderDirectApplyCards() {
      const container = document.getElementById('direct-apply-cards-container');
      if (!container) return;
      const list = JOBS_DATA.filter(j => ACTIVE_DOMAIN === 'all' || inferJobDomain(j) === ACTIVE_DOMAIN);
      container.innerHTML = list.map(job => {
        const sc = scoreJob(job);
        const dom = inferJobDomain(job);
        const domBadge = dom === 'hardware'
          ? '<span class="pill-shape bg-amber-500/15 text-amber-400 border border-amber-500/30 text-[10px]">ECE / HW</span>'
          : '<span class="pill-shape bg-cyan-500/15 text-cyan-400 border border-cyan-500/30 text-[10px]">SW / AI</span>';
        return `
          <div class="studio-card studio-card-hover p-5 flex flex-col justify-between space-y-4">
            <div class="space-y-3">
              <div class="flex items-center justify-between gap-2">
                <div class="flex items-center gap-1.5">
                  <span class="pill-shape bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300">
                    <i data-lucide="check-circle" class="w-3.5 h-3.5"></i><span>LLM Decision: Apply</span>
                  </span>
                  ${domBadge}
                </div>
                <span class="pill-shape ats-pill-high">${sc.pct}% Match</span>
              </div>
              <div>
                <div class="text-sm font-bold text-slate-900 dark:text-white">${job.title}</div>
                <div class="text-xs text-slate-500 mt-0.5">${job.company} • ${job.location}</div>
              </div>
              <div class="p-3 rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 space-y-1">
                <div class="text-[11px] font-semibold text-slate-500">Corporate Hiring Department Inbox</div>
                <div class="text-xs font-mono font-bold text-blue-600 dark:text-blue-400 truncate">${job.hiringEmail}</div>
              </div>
              <div class="flex flex-wrap gap-1.5">
                ${sc.matched.map(s => `<span class="pill-shape bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300">${s}</span>`).join('')}
              </div>
            </div>
            <div class="pt-3 border-t border-slate-100 dark:border-slate-800 flex items-center gap-2">
              <button onclick="sendRecruiterEmail('${job.id}', '${job.company}', '${job.hiringEmail}', '${job.title}')" class="btn-primary flex-1 text-xs py-2 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white shadow-md flex items-center justify-center gap-1.5">
                <i data-lucide="mail" class="w-3.5 h-3.5"></i>
                <span>Send Gmail to Recruiter</span>
              </button>
              <button onclick="applyForJobWithPortalAnimation('${job.id}')" class="btn-secondary py-2 px-2.5 text-xs" title="Open Job Portal">
                <i data-lucide="external-link" class="w-3.5 h-3.5"></i>
                <span>Portal</span>
              </button>
              <button onclick="loadJobIntoResumeTailor('${job.id}')" class="btn-secondary py-2 px-2.5 text-xs" title="Tailor Resume">
                <i data-lucide="file-check-2" class="w-3.5 h-3.5 text-purple-600"></i>
              </button>
            </div>
          </div>
        `;
      }).join('');
      refreshLucideIcons();
    }

    function renderTechUpdatesAndApis() {
      const apiGrid = document.getElementById('free-apis-grid-container');
      if (apiGrid) {
        apiGrid.innerHTML = FREE_APIS_DATA.map(item => `
          <div class="studio-card studio-card-hover p-5 flex flex-col justify-between space-y-3.5">
            <div class="space-y-2">
              <div class="flex items-center justify-between">
                <span class="pill-shape bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300">${item.category}</span>
                <span class="text-xs font-semibold text-blue-600">${item.quota}</span>
              </div>
              <div class="text-sm font-bold text-slate-900 dark:text-white">${item.name}</div>
              <div class="space-y-1 text-xs text-slate-600 dark:text-slate-300">
                ${item.features.map(f => `<div class="flex items-center gap-1.5"><i data-lucide="check" class="w-3 h-3 text-emerald-600"></i><span>${f}</span></div>`).join('')}
              </div>
            </div>
            <a href="${item.url}" target="_blank" rel="noopener" class="btn-primary w-full py-1.5 text-xs">
              <span>Get Free API Key</span>
              <i data-lucide="external-link" class="w-3.5 h-3.5"></i>
            </a>
          </div>
        `).join('');
      }

      const projGrid = document.getElementById('tech-projects-grid-container');
      if (projGrid) {
        projGrid.innerHTML = TECH_PROJECTS_DATA.map(item => `
          <div class="studio-card studio-card-hover p-5 flex flex-col justify-between space-y-3.5">
            <div class="space-y-2">
              <div class="flex items-center justify-between">
                <span class="pill-shape bg-blue-50 dark:bg-blue-950 text-blue-700 dark:text-blue-300">${item.roleTrack}</span>
              </div>
              <div class="text-sm font-bold text-slate-900 dark:text-white">${item.title}</div>
              <p class="text-xs text-slate-500 leading-relaxed">${item.desc}</p>
              <div class="flex flex-wrap gap-1.5">
                ${item.stack.map(s => `<span class="pill-shape bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">${s}</span>`).join('')}
              </div>
            </div>
            <a href="${item.url}" target="_blank" rel="noopener" class="btn-secondary w-full py-1.5 text-xs">
              <span>View Project Reference</span>
              <i data-lucide="arrow-up-right" class="w-3.5 h-3.5"></i>
            </a>
          </div>
        `).join('');
      }
      refreshLucideIcons();
    }


    function scoreJob(job) {
      if (!job || typeof job !== 'object') return { score: 0, pct: 0, matched: [], missing: [] };
      const userSkillsLower = (currentProfile.skills || []).map(s => s.toLowerCase());
      const matched = job.skills.filter(s => userSkillsLower.includes(s.toLowerCase()));
      const missing = job.skills.filter(s => !userSkillsLower.includes(s.toLowerCase()));
      const pct = Math.min(99, Math.max(60, Math.round((matched.length / Math.max(1, job.skills.length)) * 100)));
      return { pct, matched, missing };
    }

    function renderJobsList() {
      const q = (document.getElementById('job-search-input')?.value || '').toLowerCase().trim();
      const src = document.getElementById('job-source-filter')?.value || 'all';
      const filtered = JOBS_DATA.filter(j => {
        const domOk = ACTIVE_DOMAIN === 'all' || inferJobDomain(j) === ACTIVE_DOMAIN;
        const srcOk = src === 'all' || j.source === src;
        const qOk = !q || j.title.toLowerCase().includes(q) || j.company.toLowerCase().includes(q) || j.location.toLowerCase().includes(q) || j.skills.some(s => s.toLowerCase().includes(q));
        return domOk && srcOk && qOk;
      });

      const sumEl = document.getElementById('jobs-count-summary');
      if (sumEl) sumEl.innerText = `${filtered.length} Roles Available (${ACTIVE_DOMAIN.toUpperCase()}) for ${currentProfile.name}`;

      const container = document.getElementById('jobs-feed-container');
      if (container) {
        container.innerHTML = filtered.map(j => {
          const sc = scoreJob(j);
          const dom = inferJobDomain(j);
          const domBadge = dom === 'hardware'
            ? '<span class="pill-shape bg-amber-500/15 text-amber-400 border border-amber-500/30 text-[10px]">ECE / HW</span>'
            : '<span class="pill-shape bg-cyan-500/15 text-cyan-400 border border-cyan-500/30 text-[10px]">SW / AI</span>';
          return `
            <div class="studio-card studio-card-hover p-5 space-y-3.5">
              <div class="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <div class="flex items-center gap-2">
                    <div class="text-sm font-bold text-slate-900 dark:text-white">${j.title}</div>
                    ${domBadge}
                  </div>
                  <div class="text-xs text-slate-500 mt-0.5">${j.company} • ${j.location} • ${j.source} • ${j.posted}</div>
                </div>
                <span class="pill-shape ats-pill-high">${sc.pct}% Match</span>
              </div>
              <div class="flex flex-wrap gap-1.5">
                ${sc.matched.map(s => `<span class="pill-shape bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300"><i data-lucide="check" class="w-3 h-3"></i>${s}</span>`).join('')}
                ${sc.missing.map(s => `<span class="pill-shape bg-amber-50 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300"><i data-lucide="plus" class="w-3 h-3"></i>${s}</span>`).join('')}
              </div>
              <div class="pt-2.5 border-t border-slate-100 dark:border-slate-800 flex flex-wrap items-center justify-between gap-2">
                <div class="flex items-center gap-2">
                  <button onclick="applyForJobWithPortalAnimation('${j.id}')" class="btn-primary py-1.5 px-3 text-xs flex items-center gap-1.5 shadow-sm">
                    <i data-lucide="send" class="w-3.5 h-3.5"></i>
                    <span>Direct Apply</span>
                  </button>
                  <button onclick="loadJobIntoResumeTailor('${j.id}')" class="btn-secondary py-1.5 px-3 text-xs">
                    <i data-lucide="file-check-2" class="w-3.5 h-3.5 text-blue-600"></i>
                    <span>Tailor Resume</span>
                  </button>
                </div>
                <a href="${j.url}" target="_blank" rel="noopener" class="btn-secondary py-1.5 px-3 text-xs">
                  <span>Portal</span>
                  <i data-lucide="external-link" class="w-3.5 h-3.5"></i>
                </a>
              </div>
            </div>
          `;
        }).join('');
      }

      const dashJobs = document.getElementById('dashboard-top-jobs');
      if (dashJobs) {
        dashJobs.innerHTML = JOBS_DATA.slice(0, 4).map(j => {
          const sc = scoreJob(j);
          return `
            <div class="studio-subcard p-3.5 flex items-center justify-between gap-3 hover:border-blue-500/40 transition">
              <div class="min-w-0">
                <div class="text-xs font-bold text-slate-900 dark:text-white truncate">${j.title}</div>
                <div class="text-[11px] text-slate-500 truncate mt-0.5">${j.company} • ${j.location} • ${j.hiringEmail}</div>
              </div>
              <div class="flex items-center gap-2 shrink-0">
                <span class="pill-shape ats-pill-high">${sc.pct}% Match</span>
                <button onclick="applyForJobWithPortalAnimation('${j.id}')" class="btn-primary py-1.5 px-3 text-xs flex items-center gap-1.5 shadow-sm">
                  <i data-lucide="send" class="w-3 h-3"></i><span>Apply</span>
                </button>
              </div>
            </div>
          `;
        }).join('');
      }

      const gapSide = document.getElementById('jobs-side-gap-summary');
      if (gapSide) {
        gapSide.innerHTML = MATERIALS_DATA.slice(0, 4).map(m => `
          <div class="studio-subcard p-3.5 space-y-1.5">
            <div class="text-xs font-bold text-slate-900 dark:text-white">${m.title}</div>
            <div class="text-[11px] text-slate-500">${m.category} • ${m.author}</div>
            <a href="${m.url}" target="_blank" rel="noopener" class="text-[11px] font-semibold text-blue-600 dark:text-blue-400 hover:underline inline-flex items-center gap-1">
              <span>Read Guide</span><i data-lucide="arrow-right" class="w-3 h-3"></i>
            </a>
          </div>
        `).join('');
      }
      refreshLucideIcons();
    }

    function renderContestsGrid() {
      const pf = document.getElementById('contest-platform-filter')?.value || 'all';
      const list = CONTESTS_DATA.filter(c => pf === 'all' || c.platform === pf);
      const grid = document.getElementById('contests-grid-container');
      if (!grid) return;
      grid.innerHTML = list.map(c => `
        <div class="studio-card studio-card-hover p-5 flex flex-col justify-between space-y-4">
          <div class="space-y-2.5">
            <div class="flex items-center justify-between">
              <span class="pill-shape bg-amber-50 dark:bg-amber-950 text-amber-700 dark:text-amber-300">${c.platform}</span>
              <span class="text-xs font-semibold text-emerald-600">${c.deadline}</span>
            </div>
            <div class="text-sm font-bold text-slate-900 dark:text-white">${c.title}</div>
            <div class="text-xs font-semibold text-blue-600 dark:text-blue-400">${c.prize}</div>
            <div class="flex flex-wrap gap-1.5">
              ${(c.tags || c.skills || ['Python', 'AI']).map(t => `<span class="pill-shape bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">${t}</span>`).join('')}
            </div>
          </div>
          <a href="${c.url}" target="_blank" rel="noopener" class="btn-primary w-full py-2 text-xs">
            <span>Register</span>
            <i data-lucide="external-link" class="w-3.5 h-3.5"></i>
          </a>
        </div>
      `).join('');
      refreshLucideIcons();
    }

    function renderCertsGrid() {
      const cat = document.getElementById('cert-category-filter')?.value || 'all';
      const list = CERTS_DATA.filter(c => cat === 'all' || c.category === cat);
      const grid = document.getElementById('certs-grid-container');
      if (!grid) return;
      grid.innerHTML = list.map(c => `
        <div class="studio-card studio-card-hover p-5 flex flex-col justify-between space-y-4">
          <div class="space-y-2.5">
            <div class="flex items-center justify-between">
              <span class="pill-shape bg-blue-50 dark:bg-blue-950 text-blue-700 dark:text-blue-300">${c.provider}</span>
              <span class="text-xs font-semibold text-emerald-600">${c.cost}</span>
            </div>
            <div class="text-sm font-bold text-slate-900 dark:text-white">${c.title}</div>
            <div class="flex flex-wrap gap-1.5">
              ${(c.skills || c.covers || ['Python', 'AI']).map(s => `<span class="pill-shape bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">${s}</span>`).join('')}
            </div>
          </div>
          <a href="${c.url}" target="_blank" rel="noopener" class="btn-primary w-full py-2 text-xs">
            <span>Start Course</span>
            <i data-lucide="external-link" class="w-3.5 h-3.5"></i>
          </a>
        </div>
      `).join('');
      refreshLucideIcons();
    }

    function renderMaterialsGrid() {
      const grid = document.getElementById('materials-grid-container');
      if (!grid) return;
      grid.innerHTML = MATERIALS_DATA.map(m => `
        <div class="studio-card studio-card-hover p-5 flex flex-col justify-between space-y-4">
          <div class="space-y-2.5">
            <div class="flex items-center justify-between">
              <span class="pill-shape bg-indigo-50 dark:bg-indigo-950 text-indigo-700 dark:text-indigo-300">${m.category}</span>
              <span class="text-xs font-medium text-slate-500">${m.author}</span>
            </div>
            <div class="text-sm font-bold text-slate-900 dark:text-white">${m.title}</div>
            <p class="text-xs text-slate-500 leading-relaxed">${m.desc}</p>
            <div class="flex flex-wrap gap-1.5">
              ${(m.tags || ['Python', 'Open Source']).map(t => `<span class="pill-shape bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">${t}</span>`).join('')}
            </div>
          </div>
          <a href="${m.url}" target="_blank" rel="noopener" class="btn-primary w-full py-2 text-xs">
            <span>Open Repository</span>
            <i data-lucide="external-link" class="w-3.5 h-3.5"></i>
          </a>
        </div>
      `).join('');
      refreshLucideIcons();
    }

    function renderFeedsSection() {
      const nList = document.getElementById('feeds-news-list');
      const nCount = document.getElementById('feeds-news-count');
      if (nCount) nCount.innerText = String(AI_NEWS_DATA.length);
      if (nList) {
        nList.innerHTML = AI_NEWS_DATA.map(n => `
          <div class="studio-subcard p-4 flex items-center justify-between gap-3">
            <div class="min-w-0">
              <div class="text-xs font-bold text-slate-900 dark:text-white">${n.title}</div>
              <div class="text-[11px] text-slate-500 mt-0.5">${n.source} • ${n.time}</div>
            </div>
            <a href="${n.url}" target="_blank" rel="noopener" class="btn-secondary py-1.5 px-3 text-xs shrink-0">
              <span>Read</span><i data-lucide="external-link" class="w-3 h-3"></i>
            </a>
          </div>
        `).join('');
      }

      const vList = document.getElementById('feeds-video-list');
      const vCount = document.getElementById('feeds-video-count');
      if (vCount) vCount.innerText = String(YOUTUBE_VIDEOS_DATA.length);
      if (vList) {
        vList.innerHTML = YOUTUBE_VIDEOS_DATA.map(v => `
          <div class="studio-subcard p-3.5 space-y-2.5">
            <div class="media-16-9 bg-slate-900 text-white p-3.5 flex flex-col justify-between border border-slate-800">
              <div class="flex items-center justify-between text-[11px]">
                <span class="pill-shape bg-rose-600 text-white">${v.channel}</span>
                <span class="pill-shape bg-slate-800 text-slate-300">${v.duration}</span>
              </div>
              <div class="text-xs font-bold leading-snug">${v.title}</div>
              <div class="flex items-center justify-between text-[11px] text-slate-400">
                <span>Watch Tutorial</span>
                <i data-lucide="play-circle" class="w-5 h-5 text-rose-400"></i>
              </div>
            </div>
            <a href="${v.url}" target="_blank" rel="noopener" class="btn-secondary w-full py-1.5 text-xs">
              <span>Open Channel (${v.channel})</span>
              <i data-lucide="external-link" class="w-3.5 h-3.5"></i>
            </a>
          </div>
        `).join('');
      }
      refreshLucideIcons();
    }

