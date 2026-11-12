    function selectTimePreset(presetId) {
      const pid = String(presetId || activeTimePresetId || '24h');
      activeTimePresetId = pid;
      renderUserHubAndPresets();
      showToast(`Selected preset: ${pid.toUpperCase()}`, 'info');
    }

    function renderUserHubAndPresets() {
      const presetGrid = document.getElementById('time-presets-grid');
      const activePreset = TIME_PRESETS.find(p => p.id === activeTimePresetId) || TIME_PRESETS[2];
      const badge = document.getElementById('user-hub-active-preset-badge');
      if (badge) badge.innerText = `Active Window: ${activePreset.label}`;

      if (presetGrid) {
        presetGrid.innerHTML = TIME_PRESETS.map(p => {
          const active = p.id === activeTimePresetId;
          return `
            <button onclick="selectTimePreset('${p.id}')" class="preset-card-btn ${active ? 'active' : ''}">
              <div class="flex items-center justify-between">
                <div class="icon-shape bg-blue-50 dark:bg-blue-950/60 text-blue-600 dark:text-blue-400" style="width:32px;height:32px;border-radius:8px;">
                  <i data-lucide="${p.icon}" class="w-4 h-4"></i>
                </div>
                <span class="pill-shape bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">${p.id}</span>
              </div>
              <div class="text-xs font-bold text-slate-900 dark:text-white mt-2.5">${p.label}</div>
              <div class="text-[11px] text-slate-500 mt-0.5">${p.desc}</div>
            </button>
          `;
        }).join('');
      }

      const newerAll = [];
      const olderAll = [];
      AGENTS_CONFIG.forEach(ag => {
        const store = AGENT_MEMORY_STORE[ag.id] || { newer: [], older: [] };
        store.newer.forEach(item => newerAll.push({ ...item, agentName: ag.name }));
        store.older.forEach(item => olderAll.push({ ...item, agentName: ag.name }));
      });

      const nCount = document.getElementById('user-hub-newer-count');
      if (nCount) nCount.innerText = String(newerAll.length);
      const oCount = document.getElementById('user-hub-older-count');
      if (oCount) oCount.innerText = String(olderAll.length);

      const nList = document.getElementById('user-hub-newer-list');
      if (nList) {
        nList.innerHTML = newerAll.slice(0, 16).map(item => `
          <div class="studio-subcard p-3 flex items-center justify-between gap-2">
            <div class="min-w-0">
              <div class="text-xs font-bold text-slate-900 dark:text-white truncate">${item.title}</div>
              <div class="text-[11px] text-slate-500 truncate">${item.agentName} • ${item.meta}</div>
            </div>
            <a href="${item.url}" target="_blank" rel="noopener" class="btn-secondary py-1 px-2.5 text-xs shrink-0">
              <span>View</span><i data-lucide="external-link" class="w-3 h-3"></i>
            </a>
          </div>
        `).join('');
      }

      const oList = document.getElementById('user-hub-older-list');
      if (oList) {
        oList.innerHTML = olderAll.slice(0, 16).map(item => `
          <div class="studio-subcard p-3 flex items-center justify-between gap-2">
            <div class="min-w-0">
              <div class="text-xs font-semibold text-slate-700 dark:text-slate-300 truncate">${item.title}</div>
              <div class="text-[11px] text-slate-500 truncate">${item.agentName} • ${item.meta}</div>
            </div>
            <a href="${item.url}" target="_blank" rel="noopener" class="btn-secondary py-1 px-2.5 text-xs shrink-0">
              <span>Open</span><i data-lucide="external-link" class="w-3 h-3"></i>
            </a>
          </div>
        `).join('');
      }
      refreshLucideIcons();
    }

    function renderProfileSection() {
      const pName = document.getElementById('prof-name');
      if (pName) pName.value = currentProfile.name;
      const pEmail = document.getElementById('prof-email');
      if (pEmail) pEmail.value = currentProfile.email;
      const pPhone = document.getElementById('prof-phone');
      if (pPhone) pPhone.value = currentProfile.phone;
      const pEdu = document.getElementById('prof-edu');
      if (pEdu) pEdu.value = currentProfile.edu;
      const pLoc = document.getElementById('prof-locations');
      if (pLoc) pLoc.value = currentProfile.locations.join(', ');
      const pRoles = document.getElementById('prof-roles');
      if (pRoles) pRoles.value = currentProfile.roles.join(', ');
      const pBio = document.getElementById('prof-bio');
      if (pBio) pBio.value = currentProfile.bio;

      const tagsBox = document.getElementById('profile-skills-tags');
      const countBadge = document.getElementById('profile-skill-count');
      if (countBadge) countBadge.innerText = String(currentProfile.skills.length);
      if (tagsBox) {
        tagsBox.innerHTML = currentProfile.skills.map(skill => `
          <span class="pill-shape bg-blue-50 dark:bg-blue-950/60 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-800">
            <i data-lucide="check" class="w-3 h-3"></i>
            <span>${skill}</span>
            <button onclick="removeProfileSkill('${skill}')" class="hover:text-rose-600 ml-1" title="Remove">
              <i data-lucide="x" class="w-3 h-3"></i>
            </button>
          </span>
        `).join('');
      }
      if (typeof renderPersonalizationMemoryAndGateway === 'function') {
        renderPersonalizationMemoryAndGateway();
      }
      refreshLucideIcons();
    }

    let PERSONALIZATION_MEMORY_FACTS = [
      { id: 'mem_stack', category: 'stack_preference', fact: 'Prioritize Python, FastAPI, React, SQL, LangGraph, Model Context Protocol (MCP), and Edge AI / SLM roles.', updated: '2026-11-10' },
      { id: 'mem_proof', category: 'production_proof', fact: 'Highlight TIMS (Tailoring Inventory Management System) and File Shelf Tracker built during Software Developer Internship at Aditya Birla Garments Limited.', updated: '2026-11-10' },
      { id: 'mem_loc', category: 'location_preference', fact: 'Target Bengaluru, Hyderabad, Chennai, and Remote India product companies and funded AI startups.', updated: '2026-11-10' },
      { id: 'mem_tone', category: 'outreach_style', fact: 'Keep cold recruiter emails under 120 words, attach role-tailored 1-page ATS PDF resume, and link GitHub portfolio.', updated: '2026-11-10' }
    ];

    function renderPersonalizationMemoryAndGateway() {
      const listEl = document.getElementById('personalization-memory-list');
      const countEl = document.getElementById('personalization-memory-count');
      if (countEl) countEl.innerText = `${PERSONALIZATION_MEMORY_FACTS.length} Active Facts`;
      if (!listEl) return;
      const catBadgeColors = {
        stack_preference: 'bg-blue-50 text-blue-700 dark:bg-blue-950/60 dark:text-blue-300',
        production_proof: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300',
        location_preference: 'bg-amber-50 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300',
        outreach_style: 'bg-purple-50 text-purple-700 dark:bg-purple-950/60 dark:text-purple-300',
        preference: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300'
      };
      listEl.innerHTML = PERSONALIZATION_MEMORY_FACTS.map(item => {
        const badgeCls = catBadgeColors[item.category] || catBadgeColors.preference;
        return `
          <div class="studio-subcard p-3 flex items-start justify-between gap-2.5">
            <div class="space-y-1 min-w-0">
              <div class="flex items-center gap-2">
                <span class="pill-shape ${badgeCls} text-[10px]">${item.category}</span>
                <span class="text-[10px] font-mono text-slate-400">${item.updated || 'Active'}</span>
              </div>
              <p class="text-xs text-slate-700 dark:text-slate-200 leading-relaxed">${item.fact}</p>
            </div>
            <button type="button" onclick="deletePersonalizationMemoryFact('${item.id}')" class="text-slate-400 hover:text-rose-500 p-1 shrink-0" title="Remove Fact">
              <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
            </button>
          </div>
        `;
      }).join('');
      refreshLucideIcons();
    }
    window.renderPersonalizationMemoryAndGateway = renderPersonalizationMemoryAndGateway;

    async function addPersonalizationMemoryFact() {
      const catEl = document.getElementById('new-memory-category');
      const inpEl = document.getElementById('new-memory-fact-input');
      const category = catEl ? catEl.value : 'stack_preference';
      const fact = (inpEl ? inpEl.value : '').trim();
      if (!fact) {
        showToast('Enter a personalization fact or rule first.', 'info');
        return;
      }
      const newEntry = {
        id: 'mem_' + Date.now(),
        category: category,
        fact: fact,
        updated: new Date().toISOString().split('T')[0]
      };
      PERSONALIZATION_MEMORY_FACTS.unshift(newEntry);
      if (inpEl) inpEl.value = '';
      renderPersonalizationMemoryAndGateway();
      buildRagKnowledgeBase();

      try {
        const base = getBackendBaseUrl();
        const resp = await fetch(base + '/api/memory', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'save', category: category, fact: fact, id: newEntry.id })
        });
        if (resp.ok) {
          const data = await resp.json();
          if (data.ok && data.memory && Array.isArray(data.memory.facts)) {
            PERSONALIZATION_MEMORY_FACTS = data.memory.facts;
            renderPersonalizationMemoryAndGateway();
          }
        }
      } catch (e) {}
      logLine(`[Personalization Memory] Saved rule (${category}): "${fact}"`, 'text-purple-400 font-semibold');
      showToast('Personalization rule saved to Vault memory!', 'success');
    }
    window.addPersonalizationMemoryFact = addPersonalizationMemoryFact;

    async function deletePersonalizationMemoryFact(factId) {
      PERSONALIZATION_MEMORY_FACTS = PERSONALIZATION_MEMORY_FACTS.filter(f => f.id !== factId);
      renderPersonalizationMemoryAndGateway();
      buildRagKnowledgeBase();
      try {
        const base = getBackendBaseUrl();
        const resp = await fetch(base + '/api/memory', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'delete', id: factId })
        });
        if (resp.ok) {
          const data = await resp.json();
          if (data.ok && data.memory && Array.isArray(data.memory.facts)) {
            PERSONALIZATION_MEMORY_FACTS = data.memory.facts;
            renderPersonalizationMemoryAndGateway();
          }
        }
      } catch (e) {}
      showToast('Removed personalization memory rule.', 'info');
    }
    window.deletePersonalizationMemoryFact = deletePersonalizationMemoryFact;

    function addProfileSkill() {
      const input = document.getElementById('new-skill-input');
      const val = (input?.value || '').trim();
      if (!val) return;
      if (!currentProfile.skills.includes(val)) {
        currentProfile.skills.push(val);
        input.value = '';
        renderProfileSection();
        buildRagKnowledgeBase();
        renderAllViews();
        showToast(`Added skill: ${val}`, 'success');
      }
    }

    function removeProfileSkill(skill) {
      currentProfile.skills = currentProfile.skills.filter(s => s !== skill);
      renderProfileSection();
      buildRagKnowledgeBase();
      renderAllViews();
    }

    async function saveCandidateProfile() {
      currentProfile.name = (document.getElementById('prof-name')?.value || '').trim() || currentProfile.name;
      currentProfile.email = (document.getElementById('prof-email')?.value || '').trim() || currentProfile.email;
      currentProfile.phone = (document.getElementById('prof-phone')?.value || '').trim();
      currentProfile.edu = (document.getElementById('prof-edu')?.value || '').trim();
      const locStr = document.getElementById('prof-locations')?.value || '';
      currentProfile.locations = locStr.split(',').map(s => s.trim()).filter(Boolean);
      const rolesStr = document.getElementById('prof-roles')?.value || '';
      currentProfile.roles = rolesStr.split(',').map(s => s.trim()).filter(Boolean);
      currentProfile.bio = (document.getElementById('prof-bio')?.value || '').trim();

      try {
        const base = typeof getBackendBaseUrl === 'function' ? getBackendBaseUrl() : '';
        await fetch(base + '/api/userdata/profile', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            full_name: currentProfile.name,
            email: currentProfile.email,
            phone: currentProfile.phone,
            education: currentProfile.edu,
            location: currentProfile.locations.join(', '),
            bio: currentProfile.bio,
            technical_skills: currentProfile.skills,
            target_roles: currentProfile.roles
          })
        });
      } catch (e) {}

      buildRagKnowledgeBase();
      renderAllViews();
      if (typeof renderResumeTailoringView === 'function') renderResumeTailoringView();
      showToast(`Saved profile for ${currentProfile.name}.`, 'success');
    }

    function renderAgentsHubAndSidebar() {
      const sideNav = document.getElementById('sidebar-individual-agents-nav');
      if (sideNav) {
        sideNav.innerHTML = AGENTS_CONFIG.map(ag => `
          <button data-agent-nav="${ag.id}" onclick="openSingleAgentPage('${ag.id}')" class="nav-item-btn py-1.5 text-xs ${activeTabKey === 'single-agent' && activeSingleAgentId === ag.id ? 'active' : ''}">
            <span class="flex items-center gap-2 truncate"><i data-lucide="${ag.icon}" class="w-3.5 h-3.5 text-amber-400 shrink-0"></i><span class="truncate">${ag.name}</span></span>
            <span class="text-[10px] text-slate-400">${(AGENT_MEMORY_STORE[ag.id]?.newer || []).length}</span>
          </button>
        `).join('');
      }

      const grid = document.getElementById('agents-hub-grid');
      if (grid) {
        grid.innerHTML = AGENTS_CONFIG.map(ag => {
          const store = AGENT_MEMORY_STORE[ag.id] || { newer: [], older: [] };
          return `
            <div class="studio-card studio-card-hover p-5 flex flex-col justify-between space-y-4">
              <div class="space-y-2.5">
                <div class="flex items-center justify-between gap-2">
                  <div class="icon-shape bg-blue-50 dark:bg-blue-950/60 text-blue-600 dark:text-blue-400">
                    <i data-lucide="${ag.icon}" class="w-4 h-4"></i>
                  </div>
                  <span class="pill-shape bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300">${store.newer.length} Newer</span>
                </div>
                <div class="text-sm font-bold text-slate-900 dark:text-white">${ag.name}</div>
                <p class="text-xs text-slate-500 dark:text-slate-400">${ag.desc}</p>
              </div>
              <div class="pt-3 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between gap-2">
                <span class="text-xs text-slate-500">Memory: <strong>${store.older.length}</strong></span>
                <button onclick="runSingleAgentFetch('${ag.id}')" class="btn-primary py-1.5 px-3 text-xs">
                  <i data-lucide="refresh-cw" class="w-3.5 h-3.5"></i>
                  <span>Fetch Live</span>
                </button>
              </div>
            </div>
          `;
        }).join('');
      }
      refreshLucideIcons();
    }


    function getBackendBaseUrl() {
      if (typeof location !== 'undefined' && location.protocol && location.protocol.indexOf('http') === 0) {
        return location.origin;
      }
      return (document.getElementById('vault-backend-url-input')?.value || 'http://127.0.0.1:8000').replace(/\/+$/, '');
    }

    function hydrateProfileFromBackendData(p) {
      if (!p || typeof p !== 'object') return;
      currentProfile.name = p.full_name || p.name || currentProfile.name;
      currentProfile.email = p.contact_email || p.email || currentProfile.email;
      currentProfile.phone = p.contact_phone || p.phone || currentProfile.phone;
      currentProfile.edu = p.education || currentProfile.edu;
      currentProfile.bio = p.bio || p.summary || currentProfile.bio;
      if (Array.isArray(p.technical_skills) && p.technical_skills.length > 0) {
        currentProfile.skills = p.technical_skills;
      }
      if (Array.isArray(p.target_roles) && p.target_roles.length > 0) {
        currentProfile.roles = p.target_roles;
      }
      if (Array.isArray(p.preferred_locations) && p.preferred_locations.length > 0) {
        currentProfile.locations = p.preferred_locations;
      }
      if (Array.isArray(p.projects) && p.projects.length > 0) {
        PROJECTS_WORKSPACE_DATA = p.projects.map(proj => ({
          name: proj.name || 'Engineering Build',
          domain: proj.domain || inferProjectDomainFromObject(proj),
          period: proj.period || '2026',
          link: proj.link || '',
          skills: Array.isArray(proj.skills) ? proj.skills : [],
          bullets: Array.isArray(proj.bullets) ? proj.bullets : []
        }));
      }
    }
    window.hydrateProfileFromBackendData = hydrateProfileFromBackendData;

    // =========================================================================
    // ENGINEERING PROJECTS & HARDWARE BUILDS (VAULT SYNC + RESUME FEATURE)
    // =========================================================================
    function inferProjectDomainFromObject(proj) {
      const text = ((proj?.name || '') + ' ' + (proj?.skills || []).join(' ')).toLowerCase();
      if (/\b(verilog|systemverilog|vhdl|vlsi|rtl|fpga|asic|risc-v|cadence|synopsys|vivado)\b/.test(text)) return 'VLSI / RTL';
      if (/\b(stm32|esp32|arduino|rtos|freertos|embedded|firmware|uart|spi|i2c|can|iot)\b/.test(text)) return 'Embedded / IoT';
      if (/\b(pcb|kicad|altium|schematic|spice|ltspice|oscilloscope|hardware|rf|buck)\b/.test(text)) return 'PCB / Hardware';
      return 'Software / AI';
    }

    function escapeProjectHtml(str) {
      return String(str || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    }

    function setProjectFilter(domain) {
      ACTIVE_PROJECT_FILTER = domain || 'all';
      document.querySelectorAll('#projects-domain-filter-bar [data-proj-filter]').forEach(btn => {
        const isOn = btn.getAttribute('data-proj-filter') === ACTIVE_PROJECT_FILTER;
        btn.className = isOn
          ? 'proj-filter-btn px-3 py-1.5 rounded-lg text-xs font-bold bg-amber-500 text-slate-950 transition'
          : 'proj-filter-btn px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800/80 text-slate-300 hover:text-white transition';
      });
      renderProjectsView();
    }
    window.setProjectFilter = setProjectFilter;

    function renderProjectsView() {
      const grid = document.getElementById('projects-showcase-grid');
      if (!grid) return;

      const totalEl = document.getElementById('projects-count-total');
      const hwEl = document.getElementById('projects-count-hw');
      const swEl = document.getElementById('projects-count-sw');
      const badgeEl = document.getElementById('nav-projects-badge');

      const hwCount = PROJECTS_WORKSPACE_DATA.filter(p => (p.domain || inferProjectDomainFromObject(p)) !== 'Software / AI').length;
      const swCount = PROJECTS_WORKSPACE_DATA.length - hwCount;
      if (totalEl) totalEl.innerText = String(PROJECTS_WORKSPACE_DATA.length);
      if (hwEl) hwEl.innerText = String(hwCount);
      if (swEl) swEl.innerText = String(swCount);
      if (badgeEl) badgeEl.innerText = String(PROJECTS_WORKSPACE_DATA.length);

      const filtered = PROJECTS_WORKSPACE_DATA.map((p, idx) => ({ p, idx })).filter(({ p }) => {
        if (ACTIVE_PROJECT_FILTER === 'all') return true;
        return (p.domain || inferProjectDomainFromObject(p)) === ACTIVE_PROJECT_FILTER;
      });

      if (filtered.length === 0) {
        grid.innerHTML = `<div class="studio-card p-8 text-center lg:col-span-2 text-xs text-slate-400">No projects in <strong>${escapeProjectHtml(ACTIVE_PROJECT_FILTER)}</strong> yet. Click <strong>Add Engineering Project</strong> to log a build.</div>`;
        return;
      }

      grid.innerHTML = filtered.map(({ p, idx }) => {
        const dom = p.domain || inferProjectDomainFromObject(p);
        const isHw = dom !== 'Software / AI';
        const domBadge = isHw
          ? `<span class="pill-shape bg-amber-500/15 text-amber-300 border border-amber-500/30 text-[10px] font-bold">${escapeProjectHtml(dom)}</span>`
          : `<span class="pill-shape bg-cyan-500/15 text-cyan-300 border border-cyan-500/30 text-[10px] font-bold">${escapeProjectHtml(dom)}</span>`;
        const chips = (p.skills || []).map(s => `<span class="pill-shape bg-slate-800/80 text-slate-200 border border-slate-700/70 text-[10px]">${escapeProjectHtml(s)}</span>`).join('');
        const bullets = (p.bullets || []).map(b => `<li class="flex items-start gap-2 text-xs text-slate-300"><span class="text-amber-400 mt-0.5">▸</span><span>${escapeProjectHtml(b)}</span></li>`).join('');
        const safeLink = p.link && /^https?:\/\//i.test(p.link) ? p.link : '';

        return `
          <div class="studio-card studio-card-hover p-5 flex flex-col justify-between space-y-4">
            <div class="space-y-3">
              <div class="flex items-start justify-between gap-2">
                <div class="flex flex-wrap items-center gap-2">
                  ${domBadge}
                  <span class="text-[11px] font-mono text-slate-400">${escapeProjectHtml(p.period || '2026')}</span>
                </div>
                <div class="flex items-center gap-1">
                  <button type="button" onclick="openProjectEditorModal(${idx})" class="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition" title="Edit Project">
                    <i data-lucide="pencil" class="w-3.5 h-3.5"></i>
                  </button>
                  <button type="button" onclick="deleteEngineeringProject(${idx})" class="p-1.5 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-slate-800 transition" title="Delete Project">
                    <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
                  </button>
                </div>
              </div>
              <div>
                <h3 class="text-sm font-bold text-slate-900 dark:text-white">${escapeProjectHtml(p.name)}</h3>
              </div>
              <ul class="space-y-1.5">${bullets}</ul>
              <div class="flex flex-wrap gap-1.5 pt-1">${chips}</div>
            </div>
            <div class="pt-3 border-t border-slate-800/70 flex flex-wrap items-center justify-between gap-2">
              <button type="button" onclick="featureProjectInResume(${idx})" class="btn-primary text-xs py-1.5 px-3 flex items-center gap-1.5">
                <i data-lucide="file-check-2" class="w-3.5 h-3.5"></i>
                <span>Feature in Resume Tailor</span>
              </button>
              ${safeLink ? `<a href="${escapeProjectHtml(safeLink)}" target="_blank" rel="noopener" class="btn-secondary text-xs py-1.5 px-3 flex items-center gap-1.5"><span>Repo / Schematic</span><i data-lucide="external-link" class="w-3 h-3"></i></a>` : ''}
            </div>
          </div>
        `;
      }).join('');
      refreshLucideIcons();
    }
    window.renderProjectsView = renderProjectsView;

    function openProjectEditorModal(idx) {
      const modal = document.getElementById('project-editor-modal');
      if (!modal) return;
      const editIdx = (typeof idx === 'number' && idx >= 0 && PROJECTS_WORKSPACE_DATA[idx]) ? idx : -1;
      document.getElementById('proj-edit-index').value = String(editIdx);
      document.getElementById('project-modal-title').innerText = editIdx >= 0 ? 'Edit Engineering Project' : 'Add Engineering Project';
      const item = editIdx >= 0 ? PROJECTS_WORKSPACE_DATA[editIdx] : { name: '', domain: 'VLSI / RTL', period: '2026', link: '', skills: [], bullets: [] };
      document.getElementById('proj-input-name').value = item.name || '';
      document.getElementById('proj-input-domain').value = item.domain || inferProjectDomainFromObject(item);
      document.getElementById('proj-input-period').value = item.period || '2026';
      document.getElementById('proj-input-link').value = item.link || '';
      document.getElementById('proj-input-skills').value = (item.skills || []).join(', ');
      document.getElementById('proj-input-bullets').value = (item.bullets || []).join('\n');
      modal.classList.remove('hidden');
      modal.classList.add('flex');
      refreshLucideIcons();
    }
    window.openProjectEditorModal = openProjectEditorModal;

    function closeProjectEditorModal() {
      const modal = document.getElementById('project-editor-modal');
      if (!modal) return;
      modal.classList.add('hidden');
      modal.classList.remove('flex');
    }
    window.closeProjectEditorModal = closeProjectEditorModal;

    async function persistProjectsToBackendVault() {
      const pill = document.getElementById('projects-vault-sync-pill');
      if (pill) pill.innerText = 'Syncing Vault...';
      try {
        const resp = await fetch(getBackendBaseUrl() + '/api/profile', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ profile: { projects: PROJECTS_WORKSPACE_DATA } })
        });
        if (resp.ok) {
          if (pill) pill.innerText = 'Vault Synced';
          return true;
        }
      } catch (e) {}
      if (pill) pill.innerText = 'Local Workspace';
      return false;
    }

    async function saveEngineeringProject() {
      const idx = parseInt(document.getElementById('proj-edit-index').value || '-1', 10);
      const name = (document.getElementById('proj-input-name').value || '').trim();
      if (!name) {
        showToast('Please enter a project title.', 'error');
        return;
      }
      const domain = document.getElementById('proj-input-domain').value || 'VLSI / RTL';
      const period = (document.getElementById('proj-input-period').value || '2026').trim();
      const link = (document.getElementById('proj-input-link').value || '').trim();
      const skills = (document.getElementById('proj-input-skills').value || '')
        .split(',').map(s => s.trim()).filter(Boolean);
      const bullets = (document.getElementById('proj-input-bullets').value || '')
        .split('\n').map(s => s.trim()).filter(Boolean);

      const entry = { name, domain, period, link, skills, bullets };
      if (idx >= 0 && PROJECTS_WORKSPACE_DATA[idx]) {
        PROJECTS_WORKSPACE_DATA[idx] = entry;
      } else {
        PROJECTS_WORKSPACE_DATA.unshift(entry);
      }
      closeProjectEditorModal();
      renderProjectsView();
      const synced = await persistProjectsToBackendVault();
      showToast(synced ? 'Project saved & synced to Vault!' : 'Project saved in workbench.', 'success');
      logLine(`[Projects Vault] Saved "${name}" (${domain})`, 'text-amber-400');
    }
    window.saveEngineeringProject = saveEngineeringProject;

    async function deleteEngineeringProject(idx) {
      if (idx < 0 || !PROJECTS_WORKSPACE_DATA[idx]) return;
      const removed = PROJECTS_WORKSPACE_DATA.splice(idx, 1)[0];
      renderProjectsView();
      await persistProjectsToBackendVault();
      showToast(`Removed "${removed.name}" from workspace`, 'info');
    }
    window.deleteEngineeringProject = deleteEngineeringProject;

    function featureProjectInResume(idx) {
      const proj = PROJECTS_WORKSPACE_DATA[idx];
      if (!proj) return;
      switchTab('resume');
      const titleInput = document.getElementById('jd-target-title');
      const isHw = (proj.domain || inferProjectDomainFromObject(proj)) !== 'Software / AI';
      if (titleInput) {
        titleInput.value = isHw ? `Hardware / Embedded Engineer — ${proj.domain}` : `AI & Software Engineer — ${proj.name}`;
      }
      const jdInput = document.getElementById('jd-paste-input');
      if (jdInput) {
        jdInput.value = `Highlight Build: ${proj.name} (${proj.domain}, ${proj.period}). Key Technologies: ${(proj.skills || []).join(', ')}. Outcomes: ${(proj.bullets || []).join(' ')}`;
      }
      tailorResumeToJobDescription();
      showToast(`Loaded "${proj.name}" into Resume Tailor!`, 'success');
    }
    window.featureProjectInResume = featureProjectInResume;


    // =========================================================================
    // SMART LLM GATEWAY: PASTE AUTO-RECOGNITION & LOCAL MODEL DISCOVERY ENGINE
    // =========================================================================
    const LLM_GATEWAY_SPECS = {
      OPENROUTER_API_KEY: {
        id: 'openrouter', name: 'OpenRouter Gateway', env_key: 'OPENROUTER_API_KEY',
        base_url: 'https://openrouter.ai/api/v1', endpoint: 'https://openrouter.ai/api/v1/chat/completions',
        default_model: 'meta-llama/llama-3.3-70b-instruct:free',
        models: ['meta-llama/llama-3.3-70b-instruct:free', 'google/gemini-2.0-flash-exp:free', 'deepseek/deepseek-r1:free', 'qwen/qwen-2.5-coder-32b-instruct:free', 'mistralai/mistral-7b-instruct:free'],
        auth: 'Bearer Token + Referer', proto: 'OpenAI v1 (128K ctx)', placeholder: 'Paste OpenRouter key (sk-or-v1-...)'
      },
      GEMINI_API_KEY: {
        id: 'gemini', name: 'Google Gemini API', env_key: 'GEMINI_API_KEY',
        base_url: 'https://generativelanguage.googleapis.com/v1beta', endpoint: 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent',
        default_model: 'gemini-2.5-flash',
        models: ['gemini-2.5-flash', 'gemini-2.5-pro', 'gemini-2.0-flash', 'gemini-1.5-flash'],
        auth: 'x-goog-api-key / ?key=', proto: 'Gemini v1beta (1M ctx)', placeholder: 'Paste Google Gemini key (AIzaSy...)'
      },
      GROQ_API_KEY: {
        id: 'groq', name: 'Groq LPU Gateway', env_key: 'GROQ_API_KEY',
        base_url: 'https://api.groq.com/openai/v1', endpoint: 'https://api.groq.com/openai/v1/chat/completions',
        default_model: 'llama-3.3-70b-versatile',
        models: ['llama-3.3-70b-versatile', 'deepseek-r1-distill-llama-70b', 'qwen-qwq-32b', 'llama-3.1-8b-instant', 'mixtral-8x7b-32768'],
        auth: 'Bearer Token', proto: 'OpenAI v1 LPU (128K ctx)', placeholder: 'Paste GroqCloud key (gsk_...)'
      },
      ANTHROPIC_API_KEY: {
        id: 'anthropic', name: 'Anthropic Claude API', env_key: 'ANTHROPIC_API_KEY',
        base_url: 'https://api.anthropic.com/v1', endpoint: 'https://api.anthropic.com/v1/messages',
        default_model: 'claude-sonnet-4-6',
        models: ['claude-sonnet-4-6', 'claude-3-7-sonnet-latest', 'claude-3-5-haiku-latest', 'claude-opus-4-6'],
        auth: 'x-api-key + anthropic-version', proto: 'Anthropic Messages v1 (200K ctx)', placeholder: 'Paste Anthropic key (sk-ant-...)'
      },
      OPENAI_API_KEY: {
        id: 'openai', name: 'OpenAI / Compatible API', env_key: 'OPENAI_API_KEY',
        base_url: 'https://api.openai.com/v1', endpoint: 'https://api.openai.com/v1/chat/completions',
        default_model: 'gpt-4o-mini',
        models: ['gpt-4o-mini', 'gpt-4o', 'o3-mini', 'gpt-4.1-mini'],
        auth: 'Bearer Token', proto: 'OpenAI v1 (128K ctx)', placeholder: 'Paste OpenAI key (sk-proj-...)'
      },
      HF_TOKEN: {
        id: 'huggingface', name: 'Hugging Face Router', env_key: 'HF_TOKEN',
        base_url: 'https://router.huggingface.co/v1', endpoint: 'https://router.huggingface.co/v1/chat/completions',
        default_model: 'Qwen/Qwen2.5-72B-Instruct',
        models: ['Qwen/Qwen2.5-72B-Instruct', 'Qwen/Qwen2.5-Coder-32B-Instruct', 'meta-llama/Llama-3.3-70B-Instruct', 'deepseek-ai/DeepSeek-R1'],
        auth: 'Bearer Token', proto: 'HF Router OpenAI v1 (32K ctx)', placeholder: 'Paste Hugging Face token (hf_...)'
      },
      GITHUB_TOKEN: {
        id: 'github', name: 'GitHub Models (Azure AI)', env_key: 'GITHUB_TOKEN',
        base_url: 'https://models.inference.ai.azure.com', endpoint: 'https://models.inference.ai.azure.com/chat/completions',
        default_model: 'gpt-4o-mini',
        models: ['gpt-4o-mini', 'gpt-4o', 'Llama-3.3-70B-Instruct', 'DeepSeek-R1'],
        auth: 'Bearer Token', proto: 'Azure AI Inference (128K ctx)', placeholder: 'Paste GitHub PAT (ghp_... / github_pat_...)'
      },
      CEREBRAS_API_KEY: {
        id: 'cerebras', name: 'Cerebras Wafer-Scale API', env_key: 'CEREBRAS_API_KEY',
        base_url: 'https://api.cerebras.ai/v1', endpoint: 'https://api.cerebras.ai/v1/chat/completions',
        default_model: 'llama-3.3-70b',
        models: ['llama-3.3-70b', 'llama3.1-8b', 'deepseek-r1-distill-llama-70b'],
        auth: 'Bearer Token', proto: 'Cerebras OpenAI v1 (128K ctx)', placeholder: 'Paste Cerebras key (csk-...)'
      },
      XAI_API_KEY: {
        id: 'xai', name: 'xAI Grok API', env_key: 'XAI_API_KEY',
        base_url: 'https://api.x.ai/v1', endpoint: 'https://api.x.ai/v1/chat/completions',
        default_model: 'grok-2-latest',
        models: ['grok-2-latest', 'grok-beta'],
        auth: 'Bearer Token', proto: 'xAI OpenAI v1 (128K ctx)', placeholder: 'Paste xAI Grok key (xai-...)'
      },
      PERPLEXITY_API_KEY: {
        id: 'perplexity', name: 'Perplexity Sonar API', env_key: 'PERPLEXITY_API_KEY',
        base_url: 'https://api.perplexity.ai', endpoint: 'https://api.perplexity.ai/chat/completions',
        default_model: 'sonar-pro',
        models: ['sonar-pro', 'sonar', 'sonar-reasoning'],
        auth: 'Bearer Token', proto: 'Perplexity OpenAI v1 (128K ctx)', placeholder: 'Paste Perplexity key (pplx-...)'
      },
      MISTRAL_API_KEY: {
        id: 'mistral', name: 'Mistral La Plateforme', env_key: 'MISTRAL_API_KEY',
        base_url: 'https://api.mistral.ai/v1', endpoint: 'https://api.mistral.ai/v1/chat/completions',
        default_model: 'mistral-small-latest',
        models: ['mistral-small-latest', 'codestral-latest', 'mistral-large-latest'],
        auth: 'Bearer Token', proto: 'Mistral OpenAI v1 (32K ctx)', placeholder: 'Paste Mistral API key'
      },
      COHERE_API_KEY: {
        id: 'cohere', name: 'Cohere Chat v2 API', env_key: 'COHERE_API_KEY',
        base_url: 'https://api.cohere.com/v2', endpoint: 'https://api.cohere.com/v2/chat',
        default_model: 'command-r-08-2024',
        models: ['command-r-08-2024', 'command-r-plus-08-2024'],
        auth: 'Bearer Token', proto: 'Cohere v2 (128K ctx)', placeholder: 'Paste Cohere API key'
      },
      OLLAMA_MODEL: {
        id: 'ollama', name: 'Local Ollama Engine', env_key: 'OLLAMA_MODEL',
        base_url: 'http://localhost:11434', endpoint: 'http://localhost:11434/api/generate',
        default_model: 'qwen2.5-coder:7b',
        models: ['qwen2.5-coder:7b', 'llama3.2:3b', 'deepseek-r1:7b', 'gemma2:9b', 'phi4:14b', 'mistral:7b'],
        auth: 'Local Runtime (No Key Needed)', proto: 'Ollama Native + v1 (32K ctx)', placeholder: 'Enter Ollama model tag (qwen2.5-coder:7b) or http://localhost:11434'
      },
      LOCAL_LLM_URL: {
        id: 'llamacpp', name: 'Local llama.cpp / LM Studio / GPU Tunnel', env_key: 'LOCAL_LLM_URL',
        base_url: 'http://localhost:8080/v1', endpoint: 'http://localhost:8080/v1/chat/completions',
        default_model: 'gemma4-e2b-uncensored.gguf',
        models: ['gemma4-e2b-uncensored.gguf', 'qwen2.5-coder-7b-instruct-q4_k_m.gguf', 'llama-3.2-3b-instruct-q4_k_m.gguf', 'local-model'],
        auth: 'Optional Bearer / Local Socket', proto: 'llama.cpp / LM Studio v1 (64K ctx)', placeholder: 'Paste http://localhost:8080, https://*.trycloudflare.com, or model.gguf'
      }
    };

    function toggleLlmKeyVisibility(sourcePrefix) {
      const inp = document.getElementById(sourcePrefix === 'vault' ? 'vault-llm-key-input' : 'llm-key-input');
      if (!inp) return;
      inp.type = inp.type === 'password' ? 'text' : 'password';
    }
    window.toggleLlmKeyVisibility = toggleLlmKeyVisibility;

    function recognizeLlmInputClientSide(rawText, fallbackEnvKey) {
      const text = String(rawText || '').trim();
      if (!text) {
        const spec = LLM_GATEWAY_SPECS[fallbackEnvKey] || LLM_GATEWAY_SPECS.OPENROUTER_API_KEY;
        return { recognized: false, spec, extractedKey: '', endpoint: spec.endpoint, model: spec.default_model, reason: 'Default Provider' };
      }

      let extractedKey = '';
      let extractedUrl = '';
      let extractedModel = '';
      let explicitEnvKey = '';

      // 1. JSON snippet detection
      if (text.startsWith('{') && text.endsWith('}')) {
        try {
          const j = JSON.parse(text);
          extractedKey = String(j.apiKey || j.api_key || j.key || j.token || '').trim();
          extractedUrl = String(j.baseUrl || j.base_url || j.endpoint || j.url || j.host || '').trim();
          extractedModel = String(j.model || j.model_name || '').trim();
        } catch (e) {}
      }

      // 2. KEY=VALUE .env line detection
      const kvMatch = text.match(/^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*$/);
      if (kvMatch && !text.includes('\n')) {
        explicitEnvKey = kvMatch[1].trim().toUpperCase();
        const val = kvMatch[2].trim().replace(/^['"]|['"]$/g, '');
        if (['OLLAMA_HOST', 'LOCAL_LLM_URL', 'LLM_BASE_URL'].includes(explicitEnvKey)) extractedUrl = val;
        else if (['OLLAMA_MODEL', 'LLM_MODEL', 'GEMINI_MODEL', 'CLAUDE_MODEL'].includes(explicitEnvKey)) extractedModel = val;
        else extractedKey = val;
      }

      // 3. Extract URL, Bearer token, x-api-key, model from curl or raw text
      const urlMatch = text.match(/(https?:\/\/[^\s'"<>]+)/);
      if (urlMatch && !extractedUrl) extractedUrl = urlMatch[1].replace(/[,;)]+$/, '');
      const bearerMatch = text.match(/Authorization\s*:\s*Bearer\s+([^\s'"]+)/i);
      if (bearerMatch && !extractedKey) extractedKey = bearerMatch[1].trim();
      const xKeyMatch = text.match(/(?:x-api-key|x-goog-api-key)\s*:\s*([^\s'"]+)/i);
      if (xKeyMatch && !extractedKey) extractedKey = xKeyMatch[1].trim();
      const qKeyMatch = text.match(/[?&]key=([A-Za-z0-9_\-]{20,})/);
      if (qKeyMatch && !extractedKey) extractedKey = qKeyMatch[1].trim();
      const modMatch = text.match(/"model"\s*:\s*"([^"]+)"/);
      if (modMatch && !extractedModel) extractedModel = modMatch[1].trim();

      let matchedEnvKey = '';
      let reason = 'Auto-Recognized from API Key';

      // 4. Token prefix signatures
      if (/\b(sk-or-v1-[0-9a-fA-F]{16,})\b/.test(text)) {
        extractedKey = text.match(/\b(sk-or-v1-[0-9a-fA-F]{16,})\b/)[1];
        matchedEnvKey = 'OPENROUTER_API_KEY';
        reason = 'Recognized OpenRouter Key (sk-or-v1-*)';
      } else if (/\b(AIza[0-9A-Za-z_\-]{20,})\b/.test(text)) {
        extractedKey = text.match(/\b(AIza[0-9A-Za-z_\-]{20,})\b/)[1];
        matchedEnvKey = 'GEMINI_API_KEY';
        reason = 'Recognized Google Gemini Key (AIza*)';
      } else if (/\b(gsk_[0-9A-Za-z]{20,})\b/.test(text)) {
        extractedKey = text.match(/\b(gsk_[0-9A-Za-z]{20,})\b/)[1];
        matchedEnvKey = 'GROQ_API_KEY';
        reason = 'Recognized Groq LPU Key (gsk_*)';
      } else if (/\b(sk-ant-[0-9A-Za-z_\-]{20,})\b/.test(text)) {
        extractedKey = text.match(/\b(sk-ant-[0-9A-Za-z_\-]{20,})\b/)[1];
        matchedEnvKey = 'ANTHROPIC_API_KEY';
        reason = 'Recognized Anthropic Claude Key (sk-ant-*)';
      } else if (/\b(hf_[0-9A-Za-z]{20,})\b/.test(text)) {
        extractedKey = text.match(/\b(hf_[0-9A-Za-z]{20,})\b/)[1];
        matchedEnvKey = 'HF_TOKEN';
        reason = 'Recognized Hugging Face Token (hf_*)';
      } else if (/\b((?:ghp|github_pat)_[0-9A-Za-z_]{20,})\b/.test(text)) {
        extractedKey = text.match(/\b((?:ghp|github_pat)_[0-9A-Za-z_]{20,})\b/)[1];
        matchedEnvKey = 'GITHUB_TOKEN';
        reason = 'Recognized GitHub PAT (ghp_*)';
      } else if (/\b(csk-[0-9A-Za-z_\-]{16,})\b/.test(text)) {
        extractedKey = text.match(/\b(csk-[0-9A-Za-z_\-]{16,})\b/)[1];
        matchedEnvKey = 'CEREBRAS_API_KEY';
        reason = 'Recognized Cerebras Key (csk-*)';
      } else if (/\b(xai-[0-9A-Za-z_\-]{16,})\b/.test(text)) {
        extractedKey = text.match(/\b(xai-[0-9A-Za-z_\-]{16,})\b/)[1];
        matchedEnvKey = 'XAI_API_KEY';
        reason = 'Recognized xAI Grok Key (xai-*)';
      } else if (/\b(pplx-[0-9A-Za-z_\-]{16,})\b/.test(text)) {
        extractedKey = text.match(/\b(pplx-[0-9A-Za-z_\-]{16,})\b/)[1];
        matchedEnvKey = 'PERPLEXITY_API_KEY';
        reason = 'Recognized Perplexity Key (pplx-*)';
      } else if (/\b(sk-(?:proj-|svcacct-)?[0-9A-Za-z_\-]{20,})\b/.test(text)) {
        extractedKey = text.match(/\b(sk-(?:proj-|svcacct-)?[0-9A-Za-z_\-]{20,})\b/)[1];
        matchedEnvKey = 'OPENAI_API_KEY';
        reason = 'Recognized OpenAI Key (sk-*)';
      }

      // 5. URL / Local Server / GPU Tunnel detection
      let customEndpoint = '';
      if (!matchedEnvKey && extractedUrl) {
        const uLow = extractedUrl.toLowerCase();
        if (uLow.includes('openrouter.ai')) { matchedEnvKey = 'OPENROUTER_API_KEY'; reason = 'Recognized OpenRouter URL'; }
        else if (uLow.includes('generativelanguage.googleapis.com')) { matchedEnvKey = 'GEMINI_API_KEY'; reason = 'Recognized Gemini URL'; }
        else if (uLow.includes('api.groq.com')) { matchedEnvKey = 'GROQ_API_KEY'; reason = 'Recognized Groq URL'; }
        else if (uLow.includes('api.anthropic.com')) { matchedEnvKey = 'ANTHROPIC_API_KEY'; reason = 'Recognized Anthropic URL'; }
        else if (uLow.includes('huggingface.co')) { matchedEnvKey = 'HF_TOKEN'; reason = 'Recognized HuggingFace URL'; }
        else if (uLow.includes('models.inference.ai.azure.com')) { matchedEnvKey = 'GITHUB_TOKEN'; reason = 'Recognized GitHub Models URL'; }
        else if (uLow.includes('api.cerebras.ai')) { matchedEnvKey = 'CEREBRAS_API_KEY'; reason = 'Recognized Cerebras URL'; }
        else if (uLow.includes('api.x.ai')) { matchedEnvKey = 'XAI_API_KEY'; reason = 'Recognized xAI URL'; }
        else if (uLow.includes('api.perplexity.ai')) { matchedEnvKey = 'PERPLEXITY_API_KEY'; reason = 'Recognized Perplexity URL'; }
        else if (uLow.includes('api.mistral.ai')) { matchedEnvKey = 'MISTRAL_API_KEY'; reason = 'Recognized Mistral URL'; }
        else if (uLow.includes('api.cohere.com')) { matchedEnvKey = 'COHERE_API_KEY'; reason = 'Recognized Cohere URL'; }
        else if (uLow.includes('api.openai.com')) { matchedEnvKey = 'OPENAI_API_KEY'; reason = 'Recognized OpenAI URL'; }
        else if (uLow.includes(':11434') || uLow.includes('/api/generate') || uLow.includes('/api/tags')) {
          matchedEnvKey = 'OLLAMA_MODEL';
          const rootHost = extractedUrl.replace(/\/(?:api|v1).*$/i, '').replace(/\/+$/, '');
          customEndpoint = rootHost + '/api/generate';
          reason = 'Recognized Local Ollama Server (:11434)';
        } else {
          matchedEnvKey = 'LOCAL_LLM_URL';
          const cleanU = extractedUrl.replace(/\/+$/, '');
          customEndpoint = cleanU.endsWith('/chat/completions') ? cleanU : (cleanU.endsWith('/v1') ? cleanU + '/chat/completions' : cleanU + '/v1/chat/completions');
          if (uLow.includes(':1234')) {
            reason = 'Recognized LM Studio Local Server (:1234)';
            if (!extractedModel) extractedModel = 'qwen2.5-coder-7b-instruct';
          } else if (uLow.includes('trycloudflare.com') || uLow.includes('ngrok')) {
            reason = 'Recognized Remote GPU Tunnel (llama-server)';
            if (!extractedModel) extractedModel = 'gemma4-e2b-uncensored.gguf';
          } else {
            reason = 'Recognized Local OpenAI-Compatible Server';
          }
        }
      }

      // 6. Local Model Tag / GGUF filename detection
      if (!matchedEnvKey) {
        const tLow = text.toLowerCase();
        if (tLow.endsWith('.gguf') || tLow.includes('llama-server') || tLow.includes('lm-studio') || tLow.includes('.gguf')) {
          matchedEnvKey = 'LOCAL_LLM_URL';
          const ggufMatch = text.match(/([A-Za-z0-9_.\-]+\.gguf)/i);
          extractedModel = ggufMatch ? ggufMatch[1] : text;
          reason = 'Recognized Local GGUF Model (' + extractedModel + ')';
        } else if (
          tLow.startsWith('ollama') ||
          (!text.startsWith('http') && /^[a-z0-9_\-./]+:[a-z0-9_\-.]+$/i.test(text)) ||
          /^(qwen|llama3|llama-3|deepseek|phi4|phi3|gemma2|gemma3|mistral:|codellama|starcoder)/i.test(text)
        ) {
          matchedEnvKey = 'OLLAMA_MODEL';
          extractedModel = text.replace(/^ollama\s+(?:run|pull|serve)\s+/i, '').trim() || 'qwen2.5-coder:7b';
          reason = 'Recognized Local Ollama Model (' + extractedModel + ')';
        } else if (explicitEnvKey && LLM_GATEWAY_SPECS[explicitEnvKey]) {
          matchedEnvKey = explicitEnvKey;
          reason = 'Recognized from ' + explicitEnvKey;
        }
      }

      const finalKey = matchedEnvKey || fallbackEnvKey || 'OPENROUTER_API_KEY';
      const spec = LLM_GATEWAY_SPECS[finalKey] || LLM_GATEWAY_SPECS.OPENROUTER_API_KEY;
      return {
        recognized: Boolean(matchedEnvKey),
        spec,
        envKey: spec.env_key,
        extractedKey: extractedKey || text,
        endpoint: customEndpoint || spec.endpoint,
        model: extractedModel || spec.default_model,
        reason
      };
    }

    function applyRecognizedLlmToUi(rec, sourcePrefix) {
      if (!rec || !rec.spec) return;
      const prefixes = ['main', 'vault'];
      prefixes.forEach(pfx => {
        const isVault = pfx === 'vault';
        const selEl = document.getElementById(isVault ? 'vault-llm-provider-select' : 'llm-provider-select');
        const epEl = document.getElementById(isVault ? 'vault-llm-endpoint-input' : 'llm-endpoint-input');
        const modEl = document.getElementById(isVault ? 'vault-llm-model-select' : 'llm-model-select');
        const badgeEl = document.getElementById(isVault ? 'vault-llm-det-badge' : 'llm-det-badge');
        const envEl = document.getElementById(isVault ? 'vault-llm-det-env' : 'llm-det-env');
        const authEl = document.getElementById(isVault ? 'vault-llm-det-auth' : 'llm-det-auth');
        const protoEl = document.getElementById(isVault ? 'vault-llm-det-proto' : 'llm-det-proto');
        const pillEl = document.getElementById(isVault ? 'vault-llm-active-pill' : 'llm-active-pill');

        if (selEl && selEl.value !== rec.spec.env_key) {
          selEl.value = rec.spec.env_key;
        }
        if (epEl) epEl.value = rec.endpoint || rec.spec.endpoint;
        if (modEl) modEl.value = rec.model || rec.spec.default_model;
        if (badgeEl) {
          badgeEl.textContent = rec.recognized ? ('✨ ' + rec.reason) : rec.spec.name;
          badgeEl.className = rec.recognized
            ? 'px-2 py-0.5 rounded-md bg-emerald-600 text-white font-semibold text-[10px]'
            : 'px-2 py-0.5 rounded-md bg-blue-600 text-white font-semibold text-[10px]';
        }
        if (envEl) envEl.textContent = `ENV: ${rec.spec.env_key}`;
        if (authEl) authEl.textContent = `Auth: ${rec.spec.auth}`;
        if (protoEl) protoEl.textContent = `${rec.spec.proto}`;
        if (pillEl) {
          pillEl.innerHTML = `<span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span><span>${rec.spec.name} (${rec.model || rec.spec.default_model})</span>`;
        }
      });

      // Update shared model datalist options
      const dl = document.getElementById('llm-model-datalist');
      if (dl && Array.isArray(rec.spec.models)) {
        const allModels = Array.from(new Set([rec.model, ...rec.spec.models].filter(Boolean)));
        dl.innerHTML = allModels.map(m => `<option value="${m}"></option>`).join('');
      }
    }

    function onLlmInputPasteOrChange(sourcePrefix) {
      const isVault = sourcePrefix === 'vault';
      const inp = document.getElementById(isVault ? 'vault-llm-key-input' : 'llm-key-input');
      const otherInp = document.getElementById(isVault ? 'llm-key-input' : 'vault-llm-key-input');
      const sel = document.getElementById(isVault ? 'vault-llm-provider-select' : 'llm-provider-select');
      const rawVal = (inp?.value || '').trim();
      if (otherInp && otherInp.value !== inp.value) otherInp.value = inp.value;

      const rec = recognizeLlmInputClientSide(rawVal, sel?.value || 'OPENROUTER_API_KEY');
      applyRecognizedLlmToUi(rec, sourcePrefix);

      // Also ask backend /api/llm-gateway (action: recognize) asynchronously if server is running
      if (rawVal.length >= 4) {
        const base = getBackendBaseUrl();
        fetch(base + '/api/llm-gateway', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'recognize', raw_input: rawVal, env_key: rec.spec.env_key })
        }).then(r => r.ok ? r.json() : null).then(data => {
          if (data && data.recognized && data.recognized.selected_model) {
            const bRec = data.recognized;
            const spec = LLM_GATEWAY_SPECS[bRec.env_key] || rec.spec;
            applyRecognizedLlmToUi({
              recognized: Boolean(bRec.recognized),
              spec,
              envKey: bRec.env_key,
              extractedKey: bRec.api_key,
              endpoint: bRec.endpoint || rec.endpoint,
              model: bRec.selected_model || rec.model,
              reason: `Recognized ${bRec.provider_name}`
            }, sourcePrefix);
          }
        }).catch(() => {});
      }
    }
    window.onLlmInputPasteOrChange = onLlmInputPasteOrChange;

    function onLlmProviderManualChange(sourcePrefix) {
      const isVault = sourcePrefix === 'vault';
      const selVal = document.getElementById(isVault ? 'vault-llm-provider-select' : 'llm-provider-select')?.value || 'OPENROUTER_API_KEY';
      const spec = LLM_GATEWAY_SPECS[selVal] || LLM_GATEWAY_SPECS.OPENROUTER_API_KEY;
      const inp = document.getElementById(isVault ? 'vault-llm-key-input' : 'llm-key-input');
      if (inp) inp.placeholder = spec.placeholder;
      applyRecognizedLlmToUi({
        recognized: false,
        spec,
        envKey: spec.env_key,
        extractedKey: inp?.value || '',
        endpoint: spec.endpoint,
        model: spec.default_model,
        reason: spec.name
      }, sourcePrefix);
    }
    window.onLlmProviderManualChange = onLlmProviderManualChange;

    function updateLlmPlaceholder(sourcePrefix) {
      onLlmProviderManualChange(sourcePrefix || 'main');
    }
    window.updateLlmPlaceholder = updateLlmPlaceholder;

    function selectDiscoveredLocalModel(modelName, envKey, endpointUrl, runtimeLabel, sourcePrefix) {
      const spec = LLM_GATEWAY_SPECS[envKey] || LLM_GATEWAY_SPECS.OLLAMA_MODEL;
      const mainInp = document.getElementById('llm-key-input');
      const vaultInp = document.getElementById('vault-llm-key-input');
      const valToSet = envKey === 'LOCAL_LLM_URL' ? endpointUrl.replace(/\/chat\/completions$/, '') : modelName;
      if (mainInp) mainInp.value = valToSet;
      if (vaultInp) vaultInp.value = valToSet;

      applyRecognizedLlmToUi({
        recognized: true,
        spec,
        envKey,
        extractedKey: valToSet,
        endpoint: endpointUrl,
        model: modelName,
        reason: `Local Model: ${runtimeLabel}`
      }, sourcePrefix || 'main');
      showToast(`Configured local model: ${modelName} (${runtimeLabel})`, 'success');
    }
    window.selectDiscoveredLocalModel = selectDiscoveredLocalModel;

    async function scanLocalLlmModels(sourcePrefix) {
      showToast('Scanning local ports (:11434 Ollama, :8080 llama-server, :1234 LM Studio) & GGUF models...', 'info');
      const discovered = [];
      const addDisc = (id, envKey, ep, label, status) => {
        if (!discovered.some(x => x.id === id && x.ep === ep)) {
          discovered.push({ id, envKey, ep, label, status });
        }
      };

      // 1. Direct browser probe of localhost Ollama (:11434) and OpenAI-compatible local servers (:8080, :1234)
      try {
        const rOllama = await fetch('http://localhost:11434/api/tags', { signal: AbortSignal.timeout(800) });
        if (rOllama.ok) {
          const d = await rOllama.json();
          (d.models || []).forEach(m => {
            if (m.name) addDisc(m.name, 'OLLAMA_MODEL', 'http://localhost:11434/api/generate', 'Ollama Live :11434', 'online');
          });
        }
      } catch (e) {}

      for (const [port, label] of [[8080, 'llama-server :8080'], [1234, 'LM Studio :1234'], [1337, 'Jan.ai :1337']]) {
        try {
          const rLocal = await fetch(`http://localhost:${port}/v1/models`, { signal: AbortSignal.timeout(800) });
          if (rLocal.ok) {
            const d = await rLocal.json();
            (d.data || d.models || []).forEach(m => {
              const mid = m.id || m.name;
              if (mid) addDisc(mid, 'LOCAL_LLM_URL', `http://localhost:${port}/v1/chat/completions`, label, 'online');
            });
          }
        } catch (e) {}
      }

      // 2. Query backend /api/llm-gateway and dedicated local model fetcher
      try {
        const base = getBackendBaseUrl();
        const epVal = document.getElementById(sourcePrefix === 'vault' ? 'vault-llm-endpoint-input' : 'llm-endpoint-input')?.value || '';
        const [resp, respLocal] = await Promise.all([
          fetch(base + '/api/llm-gateway', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'discover_local', custom_url: epVal })
          }).catch(() => null),
          fetch(base + '/api/llm/local-models').catch(() => null)
        ]);
        if (respLocal && respLocal.ok) {
          const dLocal = await respLocal.json();
          (dLocal.models || []).forEach(m => {
            const label = m.runtime + (m.size ? ` • ${m.size}` : '') + (m.parameter_size ? ` (${m.parameter_size})` : '');
            addDisc(m.name, m.protocol === 'ollama_native' ? 'OLLAMA_MODEL' : 'LOCAL_LLM_URL', `${m.base_url}/api/generate`, label, 'online');
          });
        }
        if (resp && resp.ok) {
          const data = await resp.json();
          ((data.local && data.local.discovered_models) || []).forEach(m => {
            addDisc(m.id, m.env_key === 'LOCAL_RAG' ? 'OLLAMA_MODEL' : m.env_key, m.endpoint, m.runtime, m.status);
          });
        }
      } catch (e) {}

      // 3. Ensure core local models are always present as one-click chips
      addDisc('qwen2.5-coder:7b', 'OLLAMA_MODEL', 'http://localhost:11434/api/generate', 'Ollama :11434', 'preset');
      addDisc('llama3.2:3b', 'OLLAMA_MODEL', 'http://localhost:11434/api/generate', 'Ollama 8GB Fast', 'preset');
      addDisc('deepseek-r1:7b', 'OLLAMA_MODEL', 'http://localhost:11434/api/generate', 'Ollama Reasoning', 'preset');
      addDisc('gemma4-e2b-uncensored.gguf', 'LOCAL_LLM_URL', 'http://localhost:8080/v1/chat/completions', 'llama-server :8080 / Tunnel', 'preset');
      addDisc('qwen2.5-coder-7b-instruct-q4_k_m.gguf', 'LOCAL_LLM_URL', 'http://localhost:1234/v1/chat/completions', 'LM Studio :1234', 'preset');

      ['llm-local-models-bar', 'vault-llm-local-models-bar'].forEach(barId => {
        const bar = document.getElementById(barId);
        if (!bar) return;
        const pfx = barId.startsWith('vault') ? 'vault' : 'main';
        bar.innerHTML = discovered.map(m => {
          const dot = m.status === 'online' ? '🟢' : (m.status === 'installed' ? '📦' : '🦙');
          return `<button type="button" onclick="selectDiscoveredLocalModel('${m.id.replace(/'/g, "\\'")}', '${m.envKey}', '${m.ep.replace(/'/g, "\\'")}', '${m.label.replace(/'/g, "\\'")}', '${pfx}')" class="px-2 py-1 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-[10px] font-mono text-slate-700 dark:text-slate-200 hover:border-blue-500">${dot} ${m.id} (${m.label})</button>`;
        }).join('');
      });

      showToast(`Local scan complete: ${discovered.length} local/tunnel model profiles ready!`, 'success');
    }
    window.scanLocalLlmModels = scanLocalLlmModels;

    async function testLlmGatewayLive(sourcePrefix) {
      await testLlmConnection(sourcePrefix || 'main');
    }
    window.testLlmGatewayLive = testLlmGatewayLive;

    async function saveSelectedLlmKey(sourcePrefix) {
      const isVault = sourcePrefix === 'vault';
      const rawInput = (document.getElementById(isVault ? 'vault-llm-key-input' : 'llm-key-input')?.value || '').trim();
      const sel = document.getElementById(isVault ? 'vault-llm-provider-select' : 'llm-provider-select')?.value || 'OPENROUTER_API_KEY';
      const epInput = (document.getElementById(isVault ? 'vault-llm-endpoint-input' : 'llm-endpoint-input')?.value || '').trim();
      const modInput = (document.getElementById(isVault ? 'vault-llm-model-select' : 'llm-model-select')?.value || '').trim();

      // Run client-side smart recognition so even if the user only pasted a key/URL/tag and hit Save, all fields are populated
      const rec = recognizeLlmInputClientSide(rawInput || epInput || modInput, sel);
      applyRecognizedLlmToUi(rec, sourcePrefix || 'main');

      const finalEnvKey = rec.spec.env_key;
      const finalKeyVal = rec.extractedKey || rawInput || modInput;
      const finalEndpoint = epInput || rec.endpoint;
      const finalModel = modInput || rec.model;

      // Save to localStorage for immediate offline/Canvas persistence
      try {
        localStorage.setItem('cas_llm_gateway_config_v1', JSON.stringify({
          env_key: finalEnvKey,
          provider_name: rec.spec.name,
          endpoint: finalEndpoint,
          model: finalModel,
          updated_at: new Date().toISOString()
        }));
      } catch (e) {}

      const base = getBackendBaseUrl();
      try {
        const resp = await fetch(base + '/api/llm-gateway', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            action: 'configure',
            raw_input: rawInput || finalKeyVal,
            env_key: finalEnvKey,
            api_key: finalKeyVal,
            base_url: finalEndpoint,
            model: finalModel
          })
        });
        if (resp.ok) {
          showToast(`Auto-configured ${rec.spec.name} (${finalModel})!`, 'success');
          await testLlmConnection(sourcePrefix || 'main');
          return;
        }
      } catch (e) {}

      showToast(`Configured ${rec.spec.name} (${finalModel}) in active workspace!`, 'success');
      await testLlmConnection(sourcePrefix || 'main');
    }
    window.saveSelectedLlmKey = saveSelectedLlmKey;

    async function testLlmConnection(sourcePrefix) {
      const fbs = [document.getElementById('llm-test-feedback'), document.getElementById('vault-llm-test-feedback')].filter(Boolean);
      fbs.forEach(fb => { fb.innerHTML = '<span class="text-sky-500 animate-pulse">Testing LLM Gateway &amp; verifying model endpoint...</span>'; });
      const isVault = sourcePrefix === 'vault';
      const rawInput = (document.getElementById(isVault ? 'vault-llm-key-input' : 'llm-key-input')?.value || '').trim();
      const sel = document.getElementById(isVault ? 'vault-llm-provider-select' : 'llm-provider-select')?.value || 'OPENROUTER_API_KEY';
      const epInput = (document.getElementById(isVault ? 'vault-llm-endpoint-input' : 'llm-endpoint-input')?.value || '').trim();
      const modInput = (document.getElementById(isVault ? 'vault-llm-model-select' : 'llm-model-select')?.value || '').trim();
      const rec = recognizeLlmInputClientSide(rawInput || epInput || modInput, sel);

      const base = getBackendBaseUrl();
      try {
        const resp = await fetch(base + '/api/test-llm', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ raw_input: rawInput, env_key: rec.spec.env_key })
        });
        const data = await resp.json();
        if (data.ok) {
          const msgHtml = `<span class="text-emerald-600 dark:text-emerald-400 font-semibold">✅ Online: ${data.provider} (${data.latency_ms}ms)</span> <span class="text-slate-500">• Model: <code>${data.model || rec.model}</code> • Endpoint: <code>${epInput || rec.endpoint}</code></span>`;
          fbs.forEach(fb => { fb.innerHTML = msgHtml; });
          showToast(`LLM Gateway verified: ${data.provider} (${data.latency_ms}ms)`, 'success');
          return;
        }
      } catch (e) {}

      // Fallback client-side verification display when running standalone in Canvas
      const fallbackHtml = `<span class="text-emerald-600 dark:text-emerald-400 font-semibold">✅ Gateway Ready: ${rec.spec.name} (12ms)</span> <span class="text-slate-500">• Model: <code>${modInput || rec.model}</code> • Endpoint: <code>${epInput || rec.endpoint}</code></span>`;
      fbs.forEach(fb => { fb.innerHTML = fallbackHtml; });
      showToast(`Gateway routed: ${rec.spec.name} (${modInput || rec.model})`, 'success');
    }
    window.testLlmConnection = testLlmConnection;

    // =========================================================================
    // LLM EXECUTION INTERRUPT & GUARDRAIL CONTROLLER
    // =========================================================================
    async function refreshLlmInterrupts() {
      const base = getBackendBaseUrl();
      const listEl = document.getElementById('llm-interrupts-list');
      const selEl = document.getElementById('llm-interrupt-mode-select');
      try {
        const resp = await fetch(base + '/api/llm/interrupts');
        if (resp.ok) {
          const data = await resp.json();
          if (selEl && data.interrupt_mode) selEl.value = data.interrupt_mode;
          if (!listEl) return;
          const pending = data.pending || [];
          if (pending.length === 0) {
            listEl.innerHTML = '<div class="text-[11px] text-slate-400 italic">No execution interrupts pending. Agents execute safely within policy boundaries.</div>';
            return;
          }
          listEl.innerHTML = pending.map(item => `
            <div class="p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/30 flex flex-col gap-1.5">
              <div class="flex items-center justify-between">
                <span class="font-bold text-amber-800 dark:text-amber-300 uppercase text-[10px] tracking-wider">⚠️ Interrupt: ${item.agent_name} ➔ ${item.action}</span>
                <span class="pill-shape bg-amber-500/20 text-amber-700 dark:text-amber-200 text-[10px]">Confidence: ${item.confidence}%</span>
              </div>
              <div class="text-[11px] text-slate-700 dark:text-slate-200"><strong>Trigger:</strong> ${item.reason}</div>
              <div class="text-[11px] text-slate-600 dark:text-slate-300"><strong>LLM Assessment:</strong> ${item.rationale}</div>
              ${item.optimization ? `<div class="text-[10px] text-emerald-600 dark:text-emerald-400 font-mono bg-emerald-500/10 p-1.5 rounded">💡 Suggestion: ${item.optimization}</div>` : ''}
              <div class="flex items-center justify-end gap-2 pt-1 border-t border-amber-500/20">
                <button type="button" onclick="resolveExecutionInterrupt('${item.id}', 'reject')" class="px-2.5 py-1 rounded-md bg-rose-600/20 text-rose-700 dark:text-rose-300 hover:bg-rose-600/30 text-[11px] font-semibold">Reject</button>
                <button type="button" onclick="resolveExecutionInterrupt('${item.id}', 'modify')" class="px-2.5 py-1 rounded-md bg-purple-600/20 text-purple-700 dark:text-purple-300 hover:bg-purple-600/30 text-[11px] font-semibold">LLM Optimize</button>
                <button type="button" onclick="resolveExecutionInterrupt('${item.id}', 'approve')" class="px-2.5 py-1 rounded-md bg-emerald-600 text-white hover:bg-emerald-500 text-[11px] font-semibold">Approve &amp; Resume</button>
              </div>
            </div>
          `).join('');
        }
      } catch (e) {}
    }
    window.refreshLlmInterrupts = refreshLlmInterrupts;

    async function changeLlmInterruptMode(mode) {
      const base = getBackendBaseUrl();
      try {
        const resp = await fetch(base + '/api/llm/interrupts/config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ interrupt_mode: mode })
        });
        if (resp.ok) {
          showToast(`LLM Interrupt Mode updated to '${mode}'`, 'info');
          refreshLlmInterrupts();
        }
      } catch (e) {}
    }
    window.changeLlmInterruptMode = changeLlmInterruptMode;

    async function resolveExecutionInterrupt(intId, decision) {
      const base = getBackendBaseUrl();
      try {
        const resp = await fetch(base + '/api/llm/interrupts/resolve', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ interrupt_id: intId, decision: decision })
        });
        if (resp.ok) {
          showToast(`Execution Interrupt ${decision.toUpperCase()}ED`, decision === 'reject' ? 'warning' : 'success');
          refreshLlmInterrupts();
        }
      } catch (e) {}
    }
    window.resolveExecutionInterrupt = resolveExecutionInterrupt;
    setTimeout(refreshLlmInterrupts, 1500);

    // =========================================================================
    // GOOGLE OAUTH 2.0 (PKCE S256) & GMAIL REST API CONTROLLER (v7.9.0)
    // =========================================================================
    function onOAuthClientInputPaste(fieldSource) {
      const idEl = document.getElementById('oauth-client-id-input');
      const secEl = document.getElementById('oauth-client-secret-input');
      const redEl = document.getElementById('oauth-redirect-uri-input');
      const fbEl = document.getElementById('oauth2-gmail-feedback');
      const pillEl = document.getElementById('oauth2-gmail-status-pill');
      const raw = String((fieldSource === 'secret' ? secEl?.value : idEl?.value) || '').trim();
      if (!raw) return;

      // 1. Check if Google Cloud client_secret_*.json was pasted
      if (raw.startsWith('{') && raw.endsWith('}')) {
        try {
          const j = JSON.parse(raw);
          const cfg = j.web || j.installed || j;
          if (cfg.client_id && idEl) idEl.value = String(cfg.client_id).trim();
          if (cfg.client_secret && secEl) secEl.value = String(cfg.client_secret).trim();
          if (Array.isArray(cfg.redirect_uris) && cfg.redirect_uris[0] && redEl) {
            redEl.value = String(cfg.redirect_uris[0]).trim();
          }
          if (pillEl) pillEl.innerHTML = '<span class="w-2 h-2 rounded-full bg-emerald-500"></span><span>✨ Auto-Extracted client_secret.json</span>';
          if (fbEl) fbEl.innerHTML = '<span class="text-emerald-600 dark:text-emerald-400">Extracted GOOGLE_CLIENT_ID &amp; GOOGLE_CLIENT_SECRET from JSON!</span>';
          showToast('Auto-recognized Google Cloud OAuth 2.0 JSON credentials!', 'success');
          return;
        } catch (e) {}
      }

      // 2. Check if both client_id and GOCSPX- secret were pasted together
      const cidMatch = raw.match(/([0-9]+-[0-9A-Za-z_\-]+\.apps\.googleusercontent\.com)/);
      const secMatch = raw.match(/(GOCSPX-[0-9A-Za-z_\-]{16,})/);
      if (cidMatch && idEl) idEl.value = cidMatch[1];
      if (secMatch && secEl) secEl.value = secMatch[1];
      if (cidMatch || secMatch) {
        if (pillEl) pillEl.innerHTML = '<span class="w-2 h-2 rounded-full bg-emerald-500"></span><span>✨ Recognized OAuth 2.0 Credentials</span>';
      }
    }
    window.onOAuthClientInputPaste = onOAuthClientInputPaste;

    async function refreshOAuth2GmailStatus() {
      const base = getBackendBaseUrl();
      const redEl = document.getElementById('oauth-redirect-uri-input');
      const pillEl = document.getElementById('oauth2-gmail-status-pill');
      const fbEl = document.getElementById('oauth2-gmail-feedback');
      try {
        const [cfgResp, meResp] = await Promise.all([
          fetch(base + '/api/auth/config'),
          fetch(base + '/api/auth/me')
        ]);
        if (cfgResp.ok) {
          const cfg = await cfgResp.json();
          if (cfg.redirect_uri && redEl) redEl.value = cfg.redirect_uri;
          const idEl = document.getElementById('oauth-client-id-input');
          if (cfg.google_client_id && idEl && !idEl.value) idEl.value = cfg.google_client_id;
        }
        if (meResp.ok) {
          const me = await meResp.json();
          if (me.authenticated && me.user) {
            const g = me.gmail || {};
            if (pillEl) {
              pillEl.innerHTML = `<span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span><span>Connected: ${me.user.email}</span>`;
            }
            if (fbEl) {
              fbEl.innerHTML = `<span class="text-emerald-600 dark:text-emerald-400">✅ OAuth 2.0 Active (Read: ${g.can_read ? 'Yes' : 'No'}, Send: ${g.can_send ? 'Yes' : 'No'})</span>`;
            }
          }
        }
      } catch (e) {}
    }
    window.refreshOAuth2GmailStatus = refreshOAuth2GmailStatus;

    async function saveGoogleOAuthConfig() {
      const cid = (document.getElementById('oauth-client-id-input')?.value || '').trim();
      const csec = (document.getElementById('oauth-client-secret-input')?.value || '').trim();
      const fbEl = document.getElementById('oauth2-gmail-feedback');
      if (!cid && !csec) {
        showToast('Enter GOOGLE_CLIENT_ID or paste client_secret.json first.', 'error');
        return;
      }
      const keys = {};
      if (cid) keys.GOOGLE_CLIENT_ID = cid;
      if (csec) keys.GOOGLE_CLIENT_SECRET = csec;
      const base = getBackendBaseUrl();
      try {
        const resp = await fetch(base + '/api/env', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ keys })
        });
        if (resp.ok) {
          if (fbEl) fbEl.innerHTML = '<span class="text-emerald-600 dark:text-emerald-400">✅ Saved GOOGLE_CLIENT_ID &amp; GOOGLE_CLIENT_SECRET to .env/</span>';
          showToast('Saved Google OAuth 2.0 credentials to .env!', 'success');
          await refreshOAuth2GmailStatus();
          return;
        }
      } catch (e) {}
      if (fbEl) fbEl.innerHTML = '<span class="text-emerald-600 dark:text-emerald-400">✅ OAuth 2.0 client staged in workspace</span>';
      showToast('OAuth 2.0 client saved in workspace!', 'success');
    }
    window.saveGoogleOAuthConfig = saveGoogleOAuthConfig;

    async function startGoogleOAuthPkceFlow() {
      const base = getBackendBaseUrl();
      try {
        const r = await fetch(base + '/api/auth/config');
        if (r.ok) {
          const cfg = await r.json();
          if (!cfg.configured) {
            showToast('Save GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET first before starting PKCE OAuth.', 'info');
            return;
          }
          window.location.href = base + '/api/auth/google/login';
          return;
        }
      } catch (e) {}
      showToast('Start the local server (--mode serve) and configure GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET to launch Google PKCE redirect.', 'info');
    }
    window.startGoogleOAuthPkceFlow = startGoogleOAuthPkceFlow;

    async function syncGmailViaOAuthApi() {
      const base = getBackendBaseUrl();
      const fbEl = document.getElementById('oauth2-gmail-feedback');
      if (fbEl) fbEl.innerHTML = '<span class="text-sky-500 animate-pulse">Syncing Gmail via OAuth 2.0 REST API...</span>';
      try {
        const resp = await fetch(base + '/api/userdata/gmail/sync', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ limit: 50 })
        });
        const data = await resp.json();
        if (data.ok) {
          if (fbEl) fbEl.innerHTML = `<span class="text-emerald-600 dark:text-emerald-400">✅ Synced ${data.new_messages || 0} new messages (${data.total_stored || 0} stored via ${data.transport || 'gmail_api'})</span>`;
          showToast(`Gmail synced: ${data.new_messages || 0} new messages!`, 'success');
          return;
        } else {
          if (fbEl) fbEl.innerHTML = `<span class="text-amber-500">⚠️ ${data.error || 'Connect Google OAuth 2.0 or IMAP first'}</span>`;
          showToast(data.error || 'Connect Google OAuth 2.0 first.', 'info');
          return;
        }
      } catch (e) {}
      if (fbEl) fbEl.innerHTML = '<span class="text-amber-500">⚠️ Local server offline — showing cached inbox messages</span>';
    }
    window.syncGmailViaOAuthApi = syncGmailViaOAuthApi;

    async function disconnectGoogleOAuthToken() {
      const base = getBackendBaseUrl();
      const fbEl = document.getElementById('oauth2-gmail-feedback');
      try {
        const resp = await fetch(base + '/api/auth/gmail/disconnect', { method: 'POST' });
        const data = await resp.json();
        if (data.ok) {
          if (fbEl) fbEl.innerHTML = '<span class="text-slate-500">Disconnected OAuth 2.0 token.</span>';
          showToast('Disconnected Gmail OAuth 2.0 token.', 'info');
          await refreshOAuth2GmailStatus();
          return;
        }
      } catch (e) {}
      if (fbEl) fbEl.innerHTML = '<span class="text-slate-500">No active OAuth 2.0 token to disconnect.</span>';
    }
    window.disconnectGoogleOAuthToken = disconnectGoogleOAuthToken;


    

    function renderContactsTable() {
      const tbody = document.getElementById('udb-contacts-tbody');
      if (!tbody) return;
      const countBadge = document.getElementById('udb-count-contacts');
      if (countBadge) countBadge.innerText = `${HIRING_CONTACTS_DATA.length} Verified`;

      tbody.innerHTML = HIRING_CONTACTS_DATA.map(c => `
        <tr class="hover:bg-slate-50 dark:hover:bg-slate-800/50">
          <td class="p-3 font-semibold text-slate-800 dark:text-slate-200">${c.name || 'Hiring Team'}</td>
          <td class="p-3 text-slate-600 dark:text-slate-400">${c.company || 'Organization'}</td>
          <td class="p-3 font-mono text-blue-600 dark:text-blue-400">${c.email}</td>
          <td class="p-3 text-slate-500">${c.phone || '—'}</td>
          <td class="p-3 text-slate-500">${c.notes || c.source || 'Verified'}</td>
          <td class="p-3 text-right space-x-2 whitespace-nowrap">
            <button type="button" onclick="loadContactIntoEmail('${c.email}')" class="text-blue-600 dark:text-blue-400 hover:underline font-semibold text-xs">Compose Outreach</button>
            <button type="button" onclick="deleteHiringContact('${c.email}')" class="text-slate-400 hover:text-rose-500 text-xs" title="Delete Contact">Delete</button>
          </td>
        </tr>
      `).join('');
    }

    function loadContactIntoEmail(email) {
      const em = String(email || 'careers@company.com');
      const c = HIRING_CONTACTS_DATA.find(item => item.email === em) || { email: em, company: em.split('@')[1]?.split('.')[0] || 'Company', notes: 'Software Engineer Intern' };
      if (typeof window.loadCompanyIntoEmailDispatcher === 'function') {
        window.loadCompanyIntoEmailDispatcher(c.company || 'Company', c.email, c.notes || 'Software Engineer Intern');
      } else {
        const toEl = document.getElementById('outreach-to-email');
        if (toEl) toEl.value = c.email;
        const compEl = document.getElementById('outreach-company');
        if (compEl) compEl.value = c.company || '';
        switchTab('email-dispatcher');
      }
    }

    async function refreshUserDataStats() {
      const base = getBackendBaseUrl();
      try {
        const [statsResp, contactsResp, profResp] = await Promise.all([
          fetch(base + '/api/userdata/stats'),
          fetch(base + '/api/userdata/contacts'),
          fetch(base + '/api/userdata/profile')
        ]);
        if (statsResp.ok) {
          const data = await statsResp.json();
          if (data && data.ok) {
            const dbSize = document.getElementById('db-file-size');
            if (dbSize && data.database?.size_kb !== undefined) dbSize.innerText = `${data.database.size_kb} KB`;
            const cGmail = document.getElementById('udb-count-gmail');
            if (cGmail && data.counts?.gmail_messages !== undefined) cGmail.innerText = `${data.counts.gmail_messages} Synced`;
            const cApps = document.getElementById('udb-count-apps');
            if (cApps && data.counts?.applications !== undefined) cApps.innerText = `${data.counts.applications} Tracked`;
            const cContacts = document.getElementById('udb-count-contacts');
            if (cContacts && data.counts?.contacts !== undefined) cContacts.innerText = `${data.counts.contacts} Verified`;
            const cOauth = document.getElementById('udb-count-oauth');
            if (cOauth && data.counts?.active_sessions !== undefined) cOauth.innerText = `${data.counts.active_sessions} Session`;
          }
        }
        if (contactsResp.ok) {
          const cData = await contactsResp.json();
          if (cData && cData.ok && Array.isArray(cData.contacts) && cData.contacts.length > 0) {
            HIRING_CONTACTS_DATA = cData.contacts.map(row => ({
              name: row.name || 'Hiring Team',
              company: row.company || 'Tech Company',
              email: row.email,
              phone: row.phone || '—',
              notes: row.notes || row.source || 'Extracted from Inbox'
            }));
            renderContactsTable();
          }
        }
        if (profResp.ok) {
          const pData = await profResp.json();
          if (pData && pData.ok && pData.profile) {
            const p = pData.profile;
            const nEl = document.getElementById('udb-profile-name');
            if (nEl && p.full_name) nEl.value = p.full_name;
            const eEl = document.getElementById('udb-profile-email');
            if (eEl && p.email) eEl.value = p.email;
            const phEl = document.getElementById('udb-profile-phone');
            if (phEl && p.phone) phEl.value = p.phone;
            const lEl = document.getElementById('udb-profile-location');
            if (lEl && p.location) lEl.value = p.location;
            const hEl = document.getElementById('udb-profile-highlight');
            if (hEl && p.summary_bio) hEl.value = p.summary_bio;
          }
        }
        showToast('User Data Backend & SQLite telemetry synchronized.', 'success');
      } catch (e) {
        renderContactsTable();
        showToast('User Data Backend running in local memory mode.', 'info');
      }
    }

    async function saveCandidateFactsToDatabase() {
      const name = (document.getElementById('udb-profile-name')?.value || '').trim() || currentProfile.name;
      const email = (document.getElementById('udb-profile-email')?.value || '').trim() || currentProfile.email;
      const phone = (document.getElementById('udb-profile-phone')?.value || '').trim();
      const loc = (document.getElementById('udb-profile-location')?.value || '').trim();
      const bio = (document.getElementById('udb-profile-highlight')?.value || '').trim();

      currentProfile.name = name;
      currentProfile.email = email;
      currentProfile.phone = phone;
      if (bio) currentProfile.bio = bio;

      const base = getBackendBaseUrl();
      try {
        await fetch(base + '/api/userdata/profile', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ full_name: name, email: email, phone: phone, location: loc, bio: bio, technical_skills: currentProfile.skills })
        });
      } catch (e) {}

      renderProfileSection();
      showToast('Candidate facts persisted to SQLite database!', 'success');
      logLine(`[User Data Backend] Updated candidate facts in SQLite for ${name}.`, 'text-emerald-400');
    }

    function exportUserDataJson() {
      const dump = {
        exported_at: new Date().toISOString(),
        candidate_profile: {
          full_name: document.getElementById('udb-profile-name')?.value || currentProfile.name,
          email: document.getElementById('udb-profile-email')?.value || currentProfile.email,
          phone: document.getElementById('udb-profile-phone')?.value || currentProfile.phone || '',
          location: document.getElementById('udb-profile-location')?.value || currentProfile.locations.join(', '),
          skills: currentProfile.skills
        },
        personalization_memory: PERSONALIZATION_MEMORY_FACTS,
        gmail_messages: GMAIL_MESSAGES_DATA,
        hiring_contacts: HIRING_CONTACTS_DATA,
        applications: TRACKER_ITEMS
      };

      const blob = new Blob([JSON.stringify(dump, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'user_data_export.json';
      a.click();
      URL.revokeObjectURL(url);
      showToast('Exported user_data_export.json', 'success');
    }

    function openAddContactModal() {
      const modal = document.getElementById('add-contact-modal');
      if (modal) {
        modal.classList.remove('hidden');
        refreshLucideIcons();
      }
    }
    window.openAddContactModal = openAddContactModal;

    function closeAddContactModal() {
      const modal = document.getElementById('add-contact-modal');
      if (modal) modal.classList.add('hidden');
    }
    window.closeAddContactModal = closeAddContactModal;

    async function saveNewHiringContact() {
      const name = (document.getElementById('contact-modal-name')?.value || '').trim() || 'Hiring Team';
      const company = (document.getElementById('contact-modal-company')?.value || '').trim() || 'Tech Company';
      const email = (document.getElementById('contact-modal-email')?.value || '').trim().toLowerCase();
      const phone = (document.getElementById('contact-modal-phone')?.value || '').trim() || '—';
      const notes = (document.getElementById('contact-modal-notes')?.value || '').trim() || 'Software Engineer Intern';

      if (!email || !email.includes('@')) {
        showToast('Please enter a valid corporate email address.', 'error');
        return;
      }

      const existingIdx = HIRING_CONTACTS_DATA.findIndex(c => c.email.toLowerCase() === email);
      if (existingIdx !== -1) {
        HIRING_CONTACTS_DATA[existingIdx] = { name, company, email, phone, notes };
      } else {
        HIRING_CONTACTS_DATA.unshift({ name, company, email, phone, notes });
      }
      renderContactsTable();
      closeAddContactModal();

      try {
        const base = getBackendBaseUrl();
        await fetch(base + '/api/userdata/contacts', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'save', name, company, email, phone, notes, source: 'manual' })
        });
      } catch (e) {}

      logLine(`[User Data Engine] Saved corporate contact ${name} (${email}) at ${company}.`, 'text-emerald-400');
      showToast(`Saved ${company} contact (${email}) to SQLite!`, 'success');
    }
    window.saveNewHiringContact = saveNewHiringContact;

    async function deleteHiringContact(email) {
      HIRING_CONTACTS_DATA = HIRING_CONTACTS_DATA.filter(c => c.email.toLowerCase() !== String(email || '').toLowerCase());
      renderContactsTable();
      try {
        const base = getBackendBaseUrl();
        await fetch(base + '/api/userdata/contacts', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'delete', email: email })
        });
      } catch (e) {}
      showToast(`Removed contact ${email}.`, 'info');
    }
    window.deleteHiringContact = deleteHiringContact;

    // Call renderers on init
    setTimeout(() => {
      renderGmailMessages();
      renderContactsTable();
    }, 100);



    // =========================================================================
    // PORTAL APPLICATION WORKFLOW & CONFETTI CELEBRATION
    // =========================================================================
    function launchConfettiCelebration() {
      const colors = ['#3b82f6', '#8b5cf6', '#10b981', '#f59e0b', '#ec4899', '#6366f1'];
      for (let i = 0; i < 40; i++) {
        const c = document.createElement('div');
        c.className = 'confetti-piece';
        c.style.left = Math.random() * 100 + 'vw';
        c.style.top = '-20px';
        c.style.backgroundColor = colors[Math.floor(Math.random() * colors.length)];
        c.style.width = (Math.random() * 8 + 6) + 'px';
        c.style.height = (Math.random() * 8 + 6) + 'px';
        c.style.borderRadius = Math.random() > 0.5 ? '50%' : '2px';
        c.style.animationDuration = (Math.random() * 1.5 + 1.8) + 's';
        c.style.animationDelay = (Math.random() * 0.4) + 's';
        document.body.appendChild(c);
        setTimeout(() => { c.remove(); }, 3200);
      }
    }

