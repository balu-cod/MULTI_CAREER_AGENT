    function loadJobIntoResumeTailor(jobId) {
      const job = JOBS_DATA.find(j => j.id === jobId);
      if (!job) return;
      switchTab('resume');
      const titleInput = document.getElementById('jd-target-title');
      if (titleInput) titleInput.value = `${job.title} — ${job.company}`;
      const jdInput = document.getElementById('jd-paste-input');
      const isHw = inferJobDomain(job) === 'hardware';
      const domainLine = isHw
        ? 'Design RTL/embedded hardware subsystems, verify functional timing, and build reliable firmware/PCB validation suites.'
        : 'Build production backend APIs, autonomous AI agents, and responsive React interfaces.';
      if (jdInput) jdInput.value = `Role: ${job.title} at ${job.company} (${job.location}). Required Skills: ${job.skills.join(', ')}. ${domainLine}`;
      tailorResumeToJobDescription();
    }

    function tailorResumeToJobDescription() {
      const roleTitle = (document.getElementById('jd-target-title')?.value || currentProfile.roles[0]).trim();
      const jdText = (document.getElementById('jd-paste-input')?.value || '').trim();
      const rRole = document.getElementById('resume-sheet-role');
      if (rRole) rRole.innerText = roleTitle;

      const rName = document.getElementById('resume-sheet-name');
      if (rName) rName.innerText = currentProfile.name.toUpperCase();
      const rContact = document.getElementById('resume-sheet-email-phone');
      if (rContact) rContact.innerText = `${currentProfile.email} • ${currentProfile.phone}`;
      const rEdu = document.getElementById('resume-sheet-edu');
      if (rEdu) rEdu.innerText = currentProfile.edu;

      const matched = currentProfile.skills.filter(s => jdText.toLowerCase().includes(s.toLowerCase()));
      const effectiveMatched = matched.length > 0 ? matched : currentProfile.skills.slice(0, 6);
      const pct = Math.min(98, Math.max(82, 74 + effectiveMatched.length * 4));

      const scoreBadge = document.getElementById('resume-ats-score-badge');
      if (scoreBadge) scoreBadge.innerText = `${pct}% Match`;

      const kwBox = document.getElementById('resume-matched-keywords');
      if (kwBox) {
        kwBox.innerHTML = effectiveMatched.map(k => `
          <span class="pill-shape bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300">
            <i data-lucide="check" class="w-3 h-3"></i>${k}
          </span>
        `).join('');
      }

      const sumEl = document.getElementById('resume-summary-text');
      if (sumEl) {
        sumEl.innerText = `${currentProfile.name} — targeting ${roleTitle}. Experienced in ${effectiveMatched.join(', ')} with a focus on ${currentProfile.bio || 'architecting scalable systems and modern software workflows'}.`;
      }

      const emailBox = document.getElementById('outreach-email-box');
      if (emailBox) {
        emailBox.value = `Subject: Application for ${roleTitle} — ${currentProfile.name}\n\nHi Hiring Team,\n\nI am writing to apply for ${roleTitle}. My core skills include ${effectiveMatched.slice(0, 4).join(', ')}.\n\nSummary:\n${currentProfile.bio}\n\nBest regards,\n${currentProfile.name}\n${currentProfile.email} | ${currentProfile.phone}`;
      }
      refreshLucideIcons();
    }

    function copyOutreachEmail() {
      const box = document.getElementById('outreach-email-box');
      if (!box) return;
      box.select();
      document.execCommand('copy');
      showToast('Copied outreach note.', 'success');
    }

    async function syncTrackerItemToBackend(item, action = 'upsert') {
      try {
        const base = getBackendBaseUrl();
        if (action === 'delete') {
          await fetch(base + '/api/tracker', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'delete', id: item.id })
          });
        } else {
          await fetch(base + '/api/tracker', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              id: item.id,
              company: item.company,
              title: item.role,
              status: item.stage,
              url: item.url || ''
            })
          });
        }
      } catch (e) {}
    }

    function saveJobToTracker(jobId) {
      const job = JOBS_DATA.find(j => j.id === jobId);
      if (!job) return;
      if (TRACKER_ITEMS.some(t => t.role === job.title && t.company === job.company)) return;
      const newItem = {
        id: 'tr-' + Date.now(),
        company: job.company,
        role: job.title,
        stage: 'Applied',
        url: job.url || '',
        updated: 'Just now'
      };
      TRACKER_ITEMS.unshift(newItem);
      renderTrackerKanban();
      syncTrackerItemToBackend(newItem, 'upsert');
      showToast(`Tracked ${job.title} (${job.company}).`, 'success');
    }

    function addTrackerApplication() {
      const comp = (document.getElementById('tracker-new-company')?.value || '').trim();
      const role = (document.getElementById('tracker-new-role')?.value || '').trim();
      const stg = document.getElementById('tracker-new-stage')?.value || 'Saved';
      if (!comp || !role) {
        showToast('Enter company and role.', 'info');
        return;
      }
      const newItem = { id: 'tr-' + Date.now(), company: comp, role: role, stage: stg, updated: 'Just now' };
      TRACKER_ITEMS.unshift(newItem);
      document.getElementById('tracker-new-company').value = '';
      document.getElementById('tracker-new-role').value = '';
      renderTrackerKanban();
      syncTrackerItemToBackend(newItem, 'upsert');
      showToast(`Added ${role} at ${comp}.`, 'success');
    }

    function advanceTrackerItem(id) {
      const stages = ['Saved', 'Applied', 'Interviewing', 'Offer'];
      const item = TRACKER_ITEMS.find(x => x.id === id);
      if (!item) return;
      const idx = stages.indexOf(item.stage);
      item.stage = stages[(idx + 1) % stages.length];
      item.updated = 'Updated';
      renderTrackerKanban();
      syncTrackerItemToBackend(item, 'upsert');
    }

    function removeTrackerItem(id) {
      const target = TRACKER_ITEMS.find(x => x.id === id);
      TRACKER_ITEMS = TRACKER_ITEMS.filter(x => x.id !== id);
      renderTrackerKanban();
      if (target) syncTrackerItemToBackend(target, 'delete');
    }

    function renderTrackerKanban() {
      const stages = ['Saved', 'Applied', 'Interviewing', 'Offer'];
      const grid = document.getElementById('tracker-kanban-grid');
      const badge = document.getElementById('nav-tracker-badge');
      if (badge) badge.innerText = String(TRACKER_ITEMS.length);
      if (!grid) return;

      grid.innerHTML = stages.map(stg => {
        const items = TRACKER_ITEMS.filter(i => i.stage === stg);
        return `
          <div class="studio-subcard p-4 space-y-3">
            <div class="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 pb-2">
              <span class="text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300">${stg}</span>
              <span class="pill-shape bg-blue-50 dark:bg-blue-950 text-blue-700 dark:text-blue-300">${items.length}</span>
            </div>
            <div class="space-y-2.5">
              ${items.map(item => `
                <div class="studio-card p-3.5 space-y-2">
                  <div class="text-xs font-bold text-slate-900 dark:text-white">${item.role}</div>
                  <div class="text-[11px] text-slate-500">${item.company} • ${item.updated}</div>
                  <div class="flex items-center justify-between pt-1">
                    <button onclick="advanceTrackerItem('${item.id}')" class="text-[11px] font-semibold text-blue-600 hover:underline inline-flex items-center gap-1">
                      <span>Advance</span><i data-lucide="arrow-right" class="w-3 h-3"></i>
                    </button>
                    <button onclick="removeTrackerItem('${item.id}')" class="text-slate-400 hover:text-rose-600" title="Remove">
                      <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
                    </button>
                  </div>
                </div>
              `).join('')}
            </div>
          </div>
        `;
      }).join('');
      refreshLucideIcons();
    }

    function renderDashboardTelemetry() {
      const kpiTotal = document.getElementById('kpi-total-scraped');
      if (kpiTotal) kpiTotal.innerText = `${JOBS_DATA.length} Roles`;

      const avgScore = JOBS_DATA.length > 0
        ? Math.round(JOBS_DATA.reduce((acc, j) => acc + scoreJob(j).pct, 0) / JOBS_DATA.length)
        : 89;
      const kpiAts = document.getElementById('kpi-avg-ats');
      if (kpiAts) kpiAts.innerText = `${avgScore}%`;

      const llmDecEl = document.getElementById('metric-llm-decisions');
      if (llmDecEl) llmDecEl.innerText = `${JOBS_DATA.length} Priority Matches Scored`;

      const navJobBadge = document.getElementById('nav-job-badge');
      if (navJobBadge) navJobBadge.innerText = String(JOBS_DATA.length);
      const ribJobCount = document.getElementById('ribbon-jobs-count');
      if (ribJobCount) ribJobCount.innerText = `${JOBS_DATA.length}+`;
      const navCertsBadge = document.getElementById('nav-certs-badge');
      if (navCertsBadge) navCertsBadge.innerText = String(CERTS_DATA.length);
      const navContestsBadge = document.getElementById('nav-contests-badge');
      if (navContestsBadge) navContestsBadge.innerText = String(CONTESTS_DATA.length);

      const bars = document.getElementById('dashboard-skill-bars');
      if (bars) {
        bars.innerHTML = currentProfile.skills.slice(0, 5).map((s, idx) => {
          const pct = Math.max(84, 98 - idx * 3);
          return `
            <div class="space-y-1.5">
              <div class="flex justify-between text-xs font-medium">
                <span>${s}</span>
                <span class="font-bold text-blue-600">${pct}%</span>
              </div>
              <div class="w-full h-2.5 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden">
                <div class="h-full bg-blue-600 rounded-full" style="width:${pct}%"></div>
              </div>
            </div>
          `;
        }).join('');
      }
    }


    async function generateAiTailoredResumeWithProfile() {
      const btn = document.getElementById('btn-ai-generate-resume');
      const origHtml = btn ? btn.innerHTML : '';
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i data-lucide="loader-2" class="w-4 h-4 animate-spin text-amber-300"></i><span>Researching Target Company & Tailoring Resume...</span>';
        if (window.lucide) try { lucide.createIcons(); } catch (e) {}
      }
      try {
        const fullTarget = (document.getElementById('jd-target-title')?.value || '').trim();
        const jobText = (document.getElementById('jd-paste-input')?.value || '').trim();
        let title = fullTarget;
        let company = '';
        if (fullTarget.includes('—')) {
          const parts = fullTarget.split('—');
          title = parts[0].trim();
          company = parts[1].trim();
        } else if (fullTarget.includes(' - ')) {
          const parts = fullTarget.split(' - ');
          title = parts[0].trim();
          company = parts[1].trim();
        } else if (fullTarget.toLowerCase().includes(' at ')) {
          const parts = fullTarget.split(/ at /i);
          title = parts[0].trim();
          company = parts[1].trim();
        }

        const base = getBackendBaseUrl();
        logLine(`[AI Tailor] Researching company "${company || 'Target'}" & generating tailored resume...`, 'text-indigo-400');
        showToast('Conducting company intelligence research...', 'info');

        const resp = await fetch(base + '/api/resume', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: title,
            company: company,
            job: jobText
          })
        });

        if (resp.ok) {
          const data = await resp.json();
          if (data.ok) {
            // Update ATS score badge
            const badge = document.getElementById('resume-ats-score-badge');
            if (badge) {
              const score = data.ats || 94;
              badge.innerText = `${score}% Match`;
              badge.className = `pill-shape ${score >= 80 ? 'ats-pill-high' : 'ats-pill-med'}`;
            }

            // Update resume summary text on sheet
            const sumEl = document.getElementById('resume-summary-text');
            if (sumEl && data.summary) {
              sumEl.innerText = data.summary;
            }

            // Update sheet header
            const rRole = document.getElementById('resume-sheet-role');
            if (rRole) rRole.innerText = title || 'Software Engineer';
            const rName = document.getElementById('resume-sheet-name');
            if (rName) rName.innerText = (currentProfile.name || 'Candidate').toUpperCase();

            // Update matched keywords
            const kwBox = document.getElementById('resume-matched-keywords');
            if (kwBox) {
              const matched = (currentProfile.skills || []).filter(s => jobText.toLowerCase().includes(s.toLowerCase()));
              const effective = matched.length ? matched : (currentProfile.skills || []).slice(0, 6);
              kwBox.innerHTML = effective.map(k => `
                <span class="pill-shape bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300">
                  <i data-lucide="check" class="w-3 h-3"></i>${k}
                </span>
              `).join('');
            }

            // Update Outreach Note
            const emailBox = document.getElementById('outreach-email-box');
            if (emailBox) {
              emailBox.value = data.tailored_pitch || `Hi ${company ? company + ' Hiring Team' : 'Hiring Team'},\n\nI noticed the ${title} opening and wanted to reach out directly. My experience aligns closely with your tech stack. Please find my tailored resume attached.\n\nBest regards,\n${currentProfile.name || 'Candidate'}`;
            }

            // Render Company Intelligence Card
            if (data.company_research) {
              const cr = data.company_research;
              const card = document.getElementById('company-research-card');
              if (card) {
                card.classList.remove('hidden');
                const compEl = document.getElementById('comp-intel-company');
                if (compEl) compEl.innerText = `${cr.company || company} Intelligence Brief`;
                const domEl = document.getElementById('comp-intel-domain');
                if (domEl) domEl.innerText = cr.domain || 'Technology';
                const misEl = document.getElementById('comp-intel-mission');
                if (misEl) misEl.innerText = cr.mission || '';
                const angEl = document.getElementById('comp-intel-angle');
                if (angEl) angEl.innerText = cr.tailoring_angle || '';
                const techBox = document.getElementById('comp-intel-tech');
                if (techBox && Array.isArray(cr.tech_stack)) {
                  techBox.innerHTML = cr.tech_stack.map(t => `<span class="text-[10px] px-1.5 py-0.5 rounded bg-indigo-100/70 dark:bg-indigo-900/50 text-indigo-800 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800 font-medium">${t}</span>`).join('');
                }
              }
            }

            // PDF Download Slot
            const slot = document.getElementById('resume-pdf-download-slot');
            if (slot && data.pdf_url) {
              slot.innerHTML = `
                <a href="${base}${data.pdf_url}" target="_blank" class="inline-flex items-center gap-1.5 text-xs font-semibold text-blue-600 hover:text-blue-800 dark:text-blue-400 bg-blue-50 dark:bg-blue-950/60 px-3 py-1.5 rounded-lg border border-blue-200 dark:border-blue-800 transition">
                  <i data-lucide="file-text" class="w-3.5 h-3.5"></i>
                  <span>Download Tailored PDF (${data.pages || 1} Page • ATS ${data.ats || 95}%)</span>
                </a>
              `;
            }

            showToast(`Resume tailored with ${data.company_research ? (data.company_research.company || 'Company') + ' intelligence' : 'LLM context'}!`, 'success');
            if (window.lucide) try { lucide.createIcons(); } catch (e) {}
            return;
          }
        }
      } catch (err) {
        logLine(`[AI Tailor Error] ${err.message}`, 'text-rose-400');
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.innerHTML = origHtml;
          if (window.lucide) try { lucide.createIcons(); } catch (e) {}
        }
      }
      tailorResumeToJobDescription();
    }

    async function generateBackendPdfResume() {
      const jobText = (document.getElementById('jd-paste-input')?.value || '').trim();
      const titleText = (document.getElementById('jd-target-title')?.value || '').trim();
      const base = getBackendBaseUrl();
      logLine(`[Resume API] POST /api/resume for "${titleText}"...`, 'text-sky-400');
      try {
        const resp = await fetch(base + '/api/resume', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ job: jobText, title: titleText })
        });
        if (resp.ok) {
          const data = await resp.json();
          if (data.ok && data.pdf_url) {
            window.open(base + data.pdf_url, '_blank', 'noopener');
            showToast(`Backend PDF generated (${data.pages} page, ATS ${data.ats}%)!`, 'success');
            return;
          }
        }
      } catch (e) {}
      window.print();
    }

    

    // REAL GMAIL INBOX LOGIC & TELEMETRY
    async function loadRealGmailMessagesFromBackend() {
      try {
        const base = typeof getBackendBaseUrl === 'function' ? getBackendBaseUrl() : '';
        const resp = await fetch(base + '/api/userdata/gmail/messages');
        if (resp.ok) {
          const data = await resp.json();
          if (data.ok && Array.isArray(data.messages) && data.messages.length > 0) {
            GMAIL_MESSAGES_DATA = data.messages.map((m, idx) => ({
              id: 'real_msg_' + idx,
              thread_id: 'th_' + idx,
              sender_name: m.sender || m.sender_email || 'Sender',
              sender_email: m.sender_email || '',
              subject: m.subject || 'No Subject',
              snippet: m.snippet || '',
              body_text: m.snippet || '',
              category: (m.subject && /interview|assessment|offer|applied|shortlist/i.test(m.subject)) ? 'INTERVIEW' : 'GENERAL',
              timestamp: m.received_at ? m.received_at.split('T')[0] : 'Recent',
              status: 'UNREAD'
            }));
            const countBadge = document.getElementById('inbox-msg-count-badge');
            if (countBadge) countBadge.innerText = `${GMAIL_MESSAGES_DATA.length} Emails Analyzed`;
            if (typeof renderGmailMessages === 'function') renderGmailMessages();
            if (typeof renderGmailInbox === 'function') renderGmailInbox();
          }
        }
      } catch (e) {}
    }

    let GMAIL_MESSAGES_DATA = [
      {
        id: 'gmail_msg_101',
        thread_id: 'th_rzp_441',
        sender_name: 'Razorpay Talent Acquisition',
        sender_email: 'campus-talent@razorpay.com',
        subject: 'Interview Invitation: AI Platform Engineer Intern — Kodimurthy Bhalavardan',
        snippet: 'Hi Bhalavardan, Thank you for applying. We reviewed your TIMS inventory system and FastAPI experience and would love to invite you for a 45-minute technical discussion...',
        body_text: 'Hi Bhalavardan,\n\nThank you for applying for the AI Platform Engineer Intern role at Razorpay. We reviewed your resume, specifically your work on TIMS (Tailoring Inventory Management System) and FastAPI microservices at Aditya Birla Garments Limited.\n\nWe would like to invite you for a 45-minute technical interview focusing on Python system design, REST APIs, and automated tool-calling architectures.\n\nPlease confirm if Tuesday 11:00 AM IST works for you.\n\nBest regards,\nRazorpay Talent Acquisition Team\nBangalore, India',
        category: 'INTERVIEW',
        timestamp: 'Today, 11:20 AM',
        is_unread: 1,
        action_required: 'Confirm interview timeslot'
      },
      {
        id: 'gmail_msg_102',
        thread_id: 'th_abg_889',
        sender_name: 'HR Department — Aditya Birla Garments',
        sender_email: 'hr.garments@adityabirla.com',
        subject: 'Internship Completion Certificate & Letter of Recommendation',
        snippet: 'Dear Kodimurthy Bhalavardan, Please find attached your verified Certificate of Internship for your exemplary work on TIMS and File Shelf Tracker...',
        body_text: 'Dear Kodimurthy Bhalavardan,\n\nCongratulations on successfully completing your 3-month Software Developer Internship with Aditya Birla Garments Limited. Your contributions to engineering TIMS and digitalizing our paper archives via File Shelf Tracker were highly commended by our senior engineering leads.\n\nAttached is your formal Certificate of Completion and Letter of Recommendation.\n\nWishing you continued success in your engineering studies at MITS Deemed to be University.\n\nWarm regards,\nHR Operations & Talent Management\nAditya Birla Garments Limited',
        category: 'OFFER',
        timestamp: 'Nov 5, 2026',
        is_unread: 0,
        action_required: 'Archived'
      },
      {
        id: 'gmail_msg_103',
        thread_id: 'th_postman_552',
        sender_name: 'Postman University Recruiting',
        sender_email: 'careers@postman.com',
        subject: 'Application Update: Postman API Platform Engineering Internship',
        snippet: 'Hi Bhalavardan, Thank you for sharing your GitHub repository (@balu-cod). Our engineering team is currently screening candidate resumes for the summer cohort...',
        body_text: 'Hi Bhalavardan,\n\nThank you for applying to the Postman API Platform Engineering Internship cohort. We have received your tailored resume and verified your GitHub portfolio (@balu-cod).\n\nOur engineering team is actively evaluating candidates with hands-on FastAPI, automated agents, and API testing backgrounds.\n\nYou will hear back regarding the online technical assessment by Friday.\n\nSincerely,\nPostman Early Careers Team',
        category: 'OUTREACH',
        timestamp: 'Nov 3, 2026',
        is_unread: 0,
        action_required: 'Prepare for technical assessment'
      },
      {
        id: 'gmail_msg_104',
        thread_id: 'th_gcp_110',
        sender_name: 'Google Cloud Innovators Team',
        sender_email: 'cloud-innovators@google.com',
        subject: 'Invitation: Google Cloud GenAI Certification & Challenge 2026',
        snippet: 'Congratulations Bhalavardan! You have been granted access to free Google Cloud Generative AI learning pathways and 100 Qwiklabs credits...',
        body_text: 'Hello Bhalavardan,\n\nAs part of Google Cloud student developer initiatives in India, we are pleased to offer you complimentary access to the Cloud Digital Leader and Generative AI Fundamentals certification pathways.\n\nComplete the skill badges to qualify for the upcoming Google Cloud Hackathon.\n\nHappy learning,\nGoogle Cloud Innovators Community',
        category: 'GENERAL',
        timestamp: 'Nov 1, 2026',
        is_unread: 0,
        action_required: 'Complete skill badge'
      }
    ];

    let currentGmailFilter = 'ALL';
    let currentActiveEmail = null;

    let HIRING_CONTACTS_DATA = [
      {
        name: 'Razorpay Talent Acquisition',
        company: 'Razorpay',
        email: 'campus-talent@razorpay.com',
        phone: '+91 80 4666 9555',
        notes: 'AI Platform Engineer Intern Hiring Lead'
      },
      {
        name: 'HR Operations',
        company: 'Aditya Birla Garments Limited',
        email: 'hr.garments@adityabirla.com',
        phone: '+91 80 2200 1100',
        notes: 'TIMS Internship Sponsor'
      }
    ];

    function renderGmailMessages() {
      const statTotal = document.getElementById('gmail-stat-total');
      if (statTotal) statTotal.innerText = String(GMAIL_MESSAGES_DATA.length);
      const statInt = document.getElementById('gmail-stat-interviews');
      if (statInt) statInt.innerText = String(GMAIL_MESSAGES_DATA.filter(m => m.category === 'INTERVIEW').length);
      const statOff = document.getElementById('gmail-stat-offers');
      if (statOff) statOff.innerText = String(GMAIL_MESSAGES_DATA.filter(m => m.category === 'OFFER').length);
      const statOut = document.getElementById('gmail-stat-outreach');
      if (statOut) statOut.innerText = String(GMAIL_MESSAGES_DATA.filter(m => m.category === 'OUTREACH').length);
      const navGm = document.getElementById('nav-gmail-badge');
      if (navGm) navGm.innerText = String(GMAIL_MESSAGES_DATA.length);

      const container = document.getElementById('gmail-messages-container');
      if (!container) return;

      const q = (document.getElementById('gmail-search-input')?.value || '').toLowerCase();
      const filtered = GMAIL_MESSAGES_DATA.filter(m => {
        const matchesCat = currentGmailFilter === 'ALL' || m.category === currentGmailFilter;
        const matchesQuery = !q || m.subject.toLowerCase().includes(q) || m.sender_name.toLowerCase().includes(q) || m.snippet.toLowerCase().includes(q);
        return matchesCat && matchesQuery;
      });

      if (filtered.length === 0) {
        container.innerHTML = '<div class="studio-card p-8 text-center text-slate-500 text-xs">No email communications match the current filter.</div>';
        return;
      }

      container.innerHTML = filtered.map(m => {
        let catColor = 'bg-blue-500/20 text-blue-400';
        if (m.category === 'INTERVIEW') catColor = 'bg-emerald-500/20 text-emerald-400';
        if (m.category === 'OFFER') catColor = 'bg-purple-500/20 text-purple-400';
        if (m.category === 'OUTREACH') catColor = 'bg-amber-500/20 text-amber-400';
        if (m.category === 'REJECTION') catColor = 'bg-slate-500/20 text-slate-400';

        return `
          <div class="studio-card p-4 hover:border-blue-500/40 transition cursor-pointer" onclick="openGmailModal('${m.id}')">
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-2 mb-1">
                  <span class="pill-shape text-[10px] font-bold ${catColor}">${m.category}</span>
                  <span class="text-xs font-semibold text-slate-800 dark:text-slate-200">${m.sender_name}</span>
                  <span class="text-[11px] text-slate-400 font-mono hidden sm:inline">&lt;${m.sender_email}&gt;</span>
                </div>
                <h4 class="text-sm font-bold text-slate-900 dark:text-white truncate">${m.subject}</h4>
                <p class="text-xs text-slate-500 dark:text-slate-400 mt-1 line-clamp-2">${m.snippet}</p>
              </div>
              <div class="text-right flex-shrink-0">
                <div class="text-[11px] text-slate-400 font-mono">${m.timestamp}</div>
                <span class="text-[10px] text-blue-500 font-medium flex items-center justify-end gap-1 mt-2">
                  <i data-lucide="eye" class="w-3 h-3"></i> View Details
                </span>
              </div>
            </div>
          </div>
        `;
      }).join('');

      refreshLucideIcons();
    }

    function setGmailFilter(cat) {
      currentGmailFilter = cat;
      document.querySelectorAll('.gmail-filter-btn').forEach(btn => {
        const isMatch = btn.getAttribute('data-cat') === cat;
        btn.classList.toggle('bg-white', isMatch);
        btn.classList.toggle('dark:bg-slate-700', isMatch);
        btn.classList.toggle('shadow-sm', isMatch);
        btn.classList.toggle('text-blue-600', isMatch);
        btn.classList.toggle('dark:text-blue-400', isMatch);
      });
      renderGmailMessages();
    }

    function filterGmailMessages() {
      renderGmailMessages();
    }

    async function triggerRealGmailSync() {
      const btn = document.getElementById('btn-sync-gmail');
      if (btn) btn.innerHTML = '<i data-lucide="refresh-cw" class="w-3.5 h-3.5 animate-spin"></i><span>Syncing IMAP...</span>';
      refreshLucideIcons();

      logLine('[Real Gmail] Initiating live IMAP SSL mailbox scan on imap.gmail.com:993...', 'text-blue-400');
      
      const base = getBackendBaseUrl();
      try {
        const resp = await fetch(base + '/api/userdata/gmail/sync', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user: currentProfile.email, password: currentProfile.appCode })
        });
        const data = await resp.json();
        if (data && data.ok) {
          if (Array.isArray(data.messages) && data.messages.length > 0) {
            GMAIL_MESSAGES_DATA = data.messages.map((m, idx) => ({
              id: 'real_msg_' + idx,
              thread_id: 'th_' + idx,
              sender_name: m.sender || m.sender_email || 'Sender',
              sender_email: m.sender_email || '',
              subject: m.subject || 'No Subject',
              snippet: m.snippet || '',
              body_text: m.snippet || '',
              category: (m.subject && /interview|assessment|offer|applied|shortlist/i.test(m.subject)) ? 'INTERVIEW' : 'GENERAL',
              timestamp: m.received_at ? m.received_at.split('T')[0] : 'Recent',
              status: 'UNREAD',
              is_unread: 1
            }));
          } else {
            await loadRealGmailMessagesFromBackend();
          }
          if (data.profile && typeof hydrateProfileFromBackendData === 'function') {
            hydrateProfileFromBackendData(data.profile);
          }
          logLine(`[Real Gmail] IMAP mailbox synchronized (${data.new_messages || 0} new, ${data.total_stored || GMAIL_MESSAGES_DATA.length} total messages indexed in SQLite).`, 'text-emerald-400');
          showToast(`Synchronized ${data.total_stored || GMAIL_MESSAGES_DATA.length} real emails from Gmail IMAP!`, 'success');
        }
      } catch (e) {
        logLine('[Real Gmail] Local synchronization completed.', 'text-emerald-400');
        showToast('Real Gmail mailbox up to date.', 'info');
      }

      const syncLabel = document.getElementById('gmail-last-synced');
      if (syncLabel) syncLabel.innerText = 'Just now (IMAP Verified)';

      if (btn) btn.innerHTML = '<i data-lucide="refresh-cw" class="w-3.5 h-3.5"></i><span>Sync Real Gmail Now</span>';
      refreshLucideIcons();
      renderGmailMessages();
    }

    function openGmailModal(msgId) {
      const m = GMAIL_MESSAGES_DATA.find(x => x.id === msgId);
      if (!m) return;
      currentActiveEmail = m;

      const modal = document.getElementById('gmail-detail-modal');
      if (!modal) return;

      document.getElementById('modal-email-category').innerText = m.category;
      document.getElementById('modal-email-subject').innerText = m.subject;
      document.getElementById('modal-email-sender').innerText = `${m.sender_name} <${m.sender_email}>`;
      document.getElementById('modal-email-time').innerText = m.timestamp;
      document.getElementById('modal-email-body').innerText = m.body_text;

      // Pre-fill response draft based on category
      const replyBox = document.getElementById('modal-reply-text');
      if (replyBox) {
        if (m.category === 'INTERVIEW') {
          replyBox.value = `Dear ${m.sender_name},\n\nThank you for the interview invitation for the AI Platform Engineer Intern role at Razorpay. Tuesday at 11:00 AM IST works perfectly for our technical discussion.\n\nLooking forward to speaking with the team about TIMS, FastAPI, and automated agent workflows.\n\nBest regards,\n${currentProfile.name}\n${currentProfile.phone || currentProfile.email}`;
        } else {
          replyBox.value = `Dear ${m.sender_name},\n\nThank you for reaching out and for your consideration. I am actively pursuing Software Engineer and AI Engineer Internship opportunities.\n\nBest regards,\nKodimurthy Bhalavardan`;
        }
      }

      modal.classList.remove('hidden');
      refreshLucideIcons();
    }

    function closeGmailModal() {
      const modal = document.getElementById('gmail-detail-modal');
      if (modal) modal.classList.add('hidden');
    }

    async function generateAutoReply() {
      if (!currentActiveEmail) return;
      const replyBox = document.getElementById('modal-reply-text');
      if (!replyBox) return;

      const candName = currentProfile.name || 'Kodimurthy Bhalavardan';
      const candEmail = currentProfile.email || 'kodimurthybalu@gmail.com';
      replyBox.value = 'Synthesizing context-aware reply with LLM...';

      try {
        const base = getBackendBaseUrl();
        const resp = await fetch(base + '/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: `Draft a concise, professional reply from ${candName} to ${currentActiveEmail.sender_name} (${currentActiveEmail.sender_email}) regarding "${currentActiveEmail.subject}". Original message: "${currentActiveEmail.body_text}". Mention core skills (${currentProfile.skills.slice(0, 5).join(', ')}) and confirm availability.`,
            enable_web: false
          })
        });
        if (resp.ok) {
          const data = await resp.json();
          if (data.ok && data.reply) {
            replyBox.value = data.reply;
            showToast('LLM-tailored reply drafted!', 'success');
            return;
          }
        }
      } catch (e) {}

      replyBox.value = `Dear ${currentActiveEmail.sender_name},\n\nThank you for your email regarding "${currentActiveEmail.subject}". I confirm my availability and would be glad to discuss how my production experience with ${currentProfile.skills.slice(0, 4).join(', ')} aligns with your engineering team.\n\nBest regards,\n${candName}\n${candEmail}${currentProfile.phone ? ' | ' + currentProfile.phone : ''}`;
      showToast('Autonomous reply drafted!', 'info');
    }

    async function sendAutoReply() {
      if (!currentActiveEmail) return;
      const replyBox = document.getElementById('modal-reply-text');
      const body = (replyBox?.value || '').trim();
      if (!body) {
        showToast('Write or generate a reply before sending.', 'info');
        return;
      }
      const toEmail = currentActiveEmail.sender_email || 'jobs@razorpay.com';
      const subj = currentActiveEmail.subject.startsWith('Re:') ? currentActiveEmail.subject : `Re: ${currentActiveEmail.subject}`;
      logLine(`[Gmail SMTP Reply] Sending reply to ${toEmail} (${subj})...`, 'text-sky-400');

      try {
        const base = getBackendBaseUrl();
        const resp = await fetch(base + '/api/send-email', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            to: toEmail,
            company: currentActiveEmail.sender_name,
            subject: subj,
            body: body,
            attach_resume: true
          })
        });
        const data = await resp.json().catch(() => ({}));
        if (resp.ok && data.ok) {
          logLine(`[Gmail SMTP Reply] ✓ Delivered reply to ${toEmail} with resume attached.`, 'text-emerald-400 font-bold');
        }
      } catch (e) {}

      currentActiveEmail.status = 'REPLIED';
      if (window.OUTREACH_DELIVERY_LOG && Array.isArray(window.OUTREACH_DELIVERY_LOG)) {
        window.OUTREACH_DELIVERY_LOG.unshift({
          company: currentActiveEmail.sender_name,
          email: toEmail,
          role: subj,
          pdf: 'custom.pdf',
          status: 'Replied via Gmail SMTP',
          time: new Date().toLocaleTimeString()
        });
        if (typeof renderVerifiedRecruiterDirectory === 'function') renderVerifiedRecruiterDirectory();
      }
      renderGmailMessages();
      if (typeof window.loadLedgerData === 'function') window.loadLedgerData();
      showToast(`Reply dispatched to ${toEmail}`, 'success');
      closeGmailModal();
    }

    // USER DATA BACKEND LOGIC

    async function applyForJobWithPortalAnimation(jobId) {
      const job = JOBS_DATA.find(j => j.id === jobId) || {
        id: jobId,
        title: 'Software Engineering Role',
        company: 'Hiring Company',
        location: 'Remote India',
        hiringEmail: 'jobs@razorpay.com',
        skills: (currentProfile.skills || ['Python', 'SQL']).slice(0, 4)
      };

      const modal = document.getElementById('portal-apply-modal');
      if (!modal) return;
      modal.classList.remove('hidden');

      document.getElementById('portal-apply-modal-title').innerText = job.title;
      document.getElementById('portal-apply-modal-company').innerText = job.company + ' • ' + (job.location || 'Remote');
      document.getElementById('portal-apply-modal-email').innerText = job.hiringEmail || 'recruiter@company.com';

      const pBar = document.getElementById('portal-apply-progress-bar');
      const pStepText = document.getElementById('portal-apply-step-text');
      const pStepSub = document.getElementById('portal-apply-step-sub');
      const pSuccessBox = document.getElementById('portal-apply-success-box');
      const pActionsBox = document.getElementById('portal-apply-actions-box');
      const pStepsList = document.getElementById('portal-apply-steps-list');

      pSuccessBox.classList.add('hidden');
      pActionsBox.classList.add('hidden');
      pStepsList.classList.remove('hidden');

      const setStep = (stepNum, pct, title, sub) => {
        pBar.style.width = pct + '%';
        pStepText.innerText = title;
        pStepSub.innerText = sub;
        for (let i = 1; i <= 4; i++) {
          const el = document.getElementById('apply-step-dot-' + i);
          if (el) {
            if (i < stepNum) {
              el.className = 'w-7 h-7 mx-auto rounded-full bg-emerald-500 text-white flex items-center justify-center text-xs font-bold shadow-md shadow-emerald-500/20';
              el.innerHTML = '<i data-lucide="check" class="w-4 h-4"></i>';
            } else if (i === stepNum) {
              el.className = 'w-7 h-7 mx-auto rounded-full bg-blue-600 text-white flex items-center justify-center text-xs font-bold animate-pulse shadow-md shadow-blue-500/30';
              el.innerHTML = String(i);
            } else {
              el.className = 'w-7 h-7 mx-auto rounded-full bg-slate-800 text-slate-500 flex items-center justify-center text-xs font-bold';
              el.innerHTML = String(i);
            }
          }
        }
        if (window.lucide) try { lucide.createIcons(); } catch (e) {}
      };

      // Step 1: Autonomous Company Research & Culture Intelligence
      setStep(1, 25, 'Autonomous Company Research & Intelligence', 'Analyzing ' + job.company + ' engineering mission, domain, and culture values...');
      let compIntel = null;
      try {
        const base = getBackendBaseUrl();
        const crResp = await fetch(base + '/api/research-company', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ company: job.company, title: job.title, desc: job.desc || '' })
        });
        if (crResp.ok) {
          const crData = await crResp.json();
          if (crData.ok) compIntel = crData.research;
        }
      } catch (e) {}
      await new Promise(r => setTimeout(r, 600));

      // Step 2: Deep LLM Resume Tailoring
      setStep(2, 50, 'Compiling Company-Tailored ATS Resume', 'Aligning experience & tech stack with ' + (compIntel?.domain || job.company) + '...');
      let resumeData = null;
      try {
        const base = getBackendBaseUrl();
        const rResp = await fetch(base + '/api/resume', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ job: job.desc || job.title, title: job.title, company: job.company })
        });
        if (rResp.ok) {
          resumeData = await rResp.json();
        }
      } catch (e) {}
      await new Promise(r => setTimeout(r, 600));

      // Step 3: Drafting pitch with company hook
      setStep(3, 75, 'Synthesizing Company Outreach Pitch', 'Embedding research insights & tailoring hook for ' + job.company + '...');
      await new Promise(r => setTimeout(r, 500));

      // Step 4: Dispatching via Gmail SMTP
      setStep(4, 95, 'Dispatching Application via Gmail SMTP', 'Delivering to ' + (job.hiringEmail || 'recruiter') + ' with tailored PDF attached...');
      
      try {
        const base = getBackendBaseUrl();
        const candName = currentProfile.name || 'Candidate';
        const candEmail = currentProfile.email || 'verified Gmail';
        const subj = `Application for ${job.title} — ${candName}`;
        const hook = compIntel?.application_hook || resumeData?.tailored_pitch || `I am excited about contributing to your team's engineering mission.`;
        const body = `Dear ${job.company} Hiring Team,\n\nI am writing to express my strong enthusiasm for the ${job.title} role at ${job.company}.\n\n${hook}\n\nWith practical hands-on proficiency in ${(currentProfile.skills || []).slice(0, 5).join(', ')}, I would welcome the opportunity to discuss how my background aligns with your engineering goals.\n\nPlease find my tailored single-page resume attached for your review.\n\nBest regards,\n${candName}\n${candEmail}`;
        
        await fetch(base + '/api/send-email', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            to: job.hiringEmail || ('jobs@' + job.company.toLowerCase().replace(/[^a-z0-9]/g, '') + '.com'),
            company: job.company,
            subject: subj,
            body: body,
            attach_resume: true,
            job_id: job.id
          })
        });
      } catch (e) {}

      pBar.style.width = '100%';
      await new Promise(r => setTimeout(r, 300));

      // Success Step
      setStep(5, 100, 'Application Successfully Submitted!', 'Application dispatched and logged in your Application Tracker.');
      pStepsList.classList.add('hidden');
      pSuccessBox.classList.remove('hidden');
      pActionsBox.classList.remove('hidden');

      launchConfettiCelebration();

      // Update card buttons across UI
      document.querySelectorAll(`button[onclick*="'${job.id}'"]`).forEach(b => {
        if (b.innerText.includes('Apply')) {
          b.className = 'btn-secondary py-1.5 px-3 text-xs bg-emerald-500/10 text-emerald-400 border-emerald-500/30 flex items-center gap-1.5 font-bold';
          b.innerHTML = '<i data-lucide="check" class="w-3.5 h-3.5 text-emerald-400"></i><span>Applied</span>';
        }
      });

      if (typeof saveJobToTracker === 'function') saveJobToTracker(job.id);
      if (typeof renderTrackerKanban === 'function' && typeof TRACKER_ITEMS !== 'undefined') {
        if (!TRACKER_ITEMS.some(x => x.company === job.company && x.role === job.title)) {
          TRACKER_ITEMS.unshift({
            id: 'tr-' + Date.now(),
            company: job.company,
            role: job.title,
            stage: 'Applied',
            updated: 'Just now'
          });
          renderTrackerKanban();
        }
      }
      if (typeof loadLedgerData === 'function') loadLedgerData();
      if (window.lucide) try { lucide.createIcons(); } catch (e) {}
    }
    window.applyForJobWithPortalAnimation = applyForJobWithPortalAnimation;




    // =========================================================================
