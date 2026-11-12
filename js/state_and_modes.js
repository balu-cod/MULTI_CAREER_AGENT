    // =========================================================================
    // CANDIDATE PROFILE & AUTONOMOUS LLM STATE
    // =========================================================================
    let currentProfile = {
      name: '',
      email: '',
      phone: '',
      appCode: '',
      edu: '',
      locations: ['Bengaluru', 'Hyderabad', 'Remote India', 'Remote'],
      roles: ['Software Engineer Intern', 'AI Engineer Intern', 'Python Backend Developer', 'Full Stack Developer'],
      skills: ['Python', 'FastAPI', 'React', 'SQL', 'Git', 'REST APIs', 'Docker'],
      bio: '',
      inboxSummary: '',
      loggedPlatforms: [],
      detectedInterests: [],
      llmProvider: 'groq',
      llmModel: 'llama-3.3-70b-versatile'
    };

    let isAuthenticated = false;

    const VIEW_TITLES = {
      'gmail-inbox': 'Real Gmail Live Inbox',
      'email-dispatcher': 'Recruiter Email Dispatcher',
      'theme-studio': 'Theme Studio & Visual Design Gallery',
      'user-data-engine': 'User Data Engine',
      'dashboard': 'Overview',
      'rag-engine': 'LLM & RAG Knowledge',
      'user-hub': 'Time Presets & Memory',
      'profile': 'Candidate Profile',
      'projects': 'Engineering Projects & Hardware Builds',
      'direct-apply': 'Direct Job Applying',
      'tech-updates': 'Tech Updates & Free APIs',
      'agents': 'All Agents',
      'single-agent': 'Agent Workspace',
      'jobs': 'Jobs & Internships',
      'contests': 'Hackathons & Contests',
      'certs': 'Verified Certifications',
      'feeds': 'AI News & Videos',
      'materials': 'Required Materials',
      'resume': 'Resume Tailor',
      'tracker': 'Application Tracker',
      'terminal': 'Execution Logs',
      'vault': 'Email & Settings'
    };

    let ACTIVE_DOMAIN = 'all';
    let ACTIVE_PROJECT_FILTER = 'all';

    function inferJobDomain(job) {
      if (job && job.domain) return job.domain;
      const hay = ((job?.title || '') + ' ' + (job?.skills || []).join(' ')).toLowerCase();
      if (/\b(verilog|systemverilog|vhdl|vlsi|rtl|fpga|asic|embedded|firmware|stm32|esp32|pcb|kicad|altium|rtos|freertos|rf|dsp|iot|silicon|cadence|synopsys|vivado|hardware)\b/.test(hay)) {
        return 'hardware';
      }
      return 'software';
    }

    function setActiveDomain(domain) {
      ACTIVE_DOMAIN = domain || 'all';
      document.querySelectorAll('#header-domain-switcher [data-domain-btn]').forEach(btn => {
        const isOn = btn.getAttribute('data-domain-btn') === ACTIVE_DOMAIN;
        btn.className = isOn
          ? 'px-2 py-1 rounded-md bg-amber-500 text-slate-950 font-bold transition'
          : 'px-2 py-1 rounded-md text-slate-600 dark:text-slate-300 hover:text-white transition';
      });
      if (typeof renderAllViews === 'function') renderAllViews();
      if (typeof logLine === 'function') {
        logLine(`[Domain Switcher] Active engineering track set to: ${ACTIVE_DOMAIN.toUpperCase()}`, 'text-amber-400');
      }
    }
    window.setActiveDomain = setActiveDomain;

    let PROJECTS_WORKSPACE_DATA = [
      {
        name: '5-Stage Pipelined RISC-V (RV32I) Core in SystemVerilog',
        domain: 'VLSI / RTL',
        period: '2026',
        link: 'https://github.com/balu-cod/riscv-rv32i-rtl',
        skills: ['SystemVerilog', 'Verilog', 'RISC-V', 'Vivado', 'FPGA', 'Testbench'],
        bullets: [
          'Architected IF/ID/EX/MEM/WB pipeline with data forwarding and hazard detection unit.',
          'Synthesized and ran timing simulation targeting Xilinx Artix-7 FPGA using Vivado.'
        ]
      },
      {
        name: 'STM32 + FreeRTOS Edge Telemetry & CAN-Bus Node',
        domain: 'Embedded / IoT',
        period: '2025 - 2026',
        link: 'https://github.com/balu-cod/stm32-freertos-node',
        skills: ['Embedded C', 'STM32', 'FreeRTOS', 'SPI', 'I2C', 'UART', 'CAN'],
        bullets: [
          'Built real-time sensor fusion tasks on ARM Cortex-M4 with DMA-driven UART/SPI rings.',
          'Added low-power sleep wake interrupts and deterministic FreeRTOS queue pipelines.'
        ]
      },
      {
        name: '4-Layer KiCad ESP32-S3 Motor Control & Power PCB',
        domain: 'PCB / Hardware',
        period: '2025',
        link: 'https://github.com/balu-cod/kicad-esp32-controller',
        skills: ['KiCad', 'PCB Layout', 'ESP32', 'Buck Converter', 'EMI/EMC', 'Oscilloscope'],
        bullets: [
          'Routed 4-layer impedance-controlled PCB with isolated gate drivers and TPS5430 buck stage.',
          'Validated ripple, thermal profile, and PWM dead-time via bench oscilloscope testing.'
        ]
      },
      {
        name: 'Autonomous Multi-Agent Career & LLM Gateway Workbench',
        domain: 'Software / AI',
        period: '2026',
        link: 'https://github.com/balu-cod/career-agent-system',
        skills: ['Python', 'FastAPI', 'SQLite', 'Groq', 'Gemini', 'Ollama'],
        bullets: [
          'Built local+cloud LLM gateway with company research synthesis and ATS resume tailoring.',
          'Integrated Gmail OAuth 2.0 + SMTP dispatch and encrypted Vault artifact persistence.'
        ]
      }
    ];

    const AGENTS_CONFIG = [
      { id: 'jobspy', name: 'JobSpy Multi-Board Scraper (LinkedIn, Indeed, Glassdoor, Google, ZipRecruiter)', icon: 'radar', endpoint: 'https://remotive.com/api/remote-jobs?category=software-dev&limit=10', fallbackQuery: 'JobSpy+LinkedIn+Indeed+Python+engineer', desc: 'Aggregates LinkedIn, Indeed, Glassdoor, Google Jobs, ZipRecruiter & Naukri via python-jobspy.' },
      { id: 'jobglove', name: 'JobGlove Unified ATS Aggregator (Greenhouse, Lever, Ashby, Jobicy, Himalayas)', icon: 'layers', endpoint: 'https://www.arbeitnow.com/api/job-board-api', fallbackQuery: 'ATS+Greenhouse+Lever+Ashby+software+intern', desc: 'Deduplicates native ATS postings across Greenhouse, Lever, Ashby, Jobicy & Himalayas.' },
      { id: 'classcentral', name: 'ClassCentral.com Free Certificates & Courses Scraper', icon: 'award', endpoint: 'https://www.classcentral.com/report/free-certificates/', fallbackQuery: 'Class+Central+free+certificate+Python+AI+course', desc: 'Scrapes free university & developer certificates from classcentral.com matched to skill gaps.' },
      { id: 'aihawk', name: 'AIHawk Dynamic YAML Resume & Auto-Applier Engine', icon: 'file-check-2', endpoint: 'https://api.github.com/search/repositories?q=aihawk+resume+auto+apply&sort=updated', fallbackQuery: 'AIHawk+dynamic+resume+YAML+auto+apply', desc: 'Generates plain_text_resume.yaml and tailors single-page ATS PDFs per job application.' },
      { id: 'browser_use', name: 'Browser-Use + Playwright Chromium Autonomous Portal Agent', icon: 'globe', endpoint: 'https://api.github.com/search/repositories?q=browser-use+playwright+chromium&sort=stars', fallbackQuery: 'browser-use+playwright+chromium+agent', desc: 'Drives headless Chromium over CDP/Playwright to auto-fill Greenhouse, Lever & Ashby forms.' },
      { id: 'imap_smtp_mime', name: 'Gmail IMAP (993) + smtplib (465) + email.mime Engine', icon: 'mail-check', endpoint: 'https://hn.algolia.com/api/v1/search_by_date?tags=story&query=imap+smtp+email+mime+python&hitsPerPage=6', fallbackQuery: 'python+imaplib+smtplib+email+mime', desc: 'Syncs real Gmail INBOX over IMAP4_SSL and dispatches MIMEMultipart + PDF attachments via SMTP_SSL.' },
      { id: 'github_api', name: 'GitHub REST API v3 Repository & Topic Watcher', icon: 'git-branch', endpoint: 'https://api.github.com/search/repositories?q=topic:ai-agents+topic:mcp&sort=updated&order=desc&per_page=8', fallbackQuery: 'GitHub+API+AI+agents+FastAPI+MCP', desc: 'Queries api.github.com/search/repositories for trending AI agent, MCP, LangGraph & FastAPI repos.' },
      { id: 'hackernews_api', name: 'HackerNews Algolia & Firebase Live API', icon: 'terminal', endpoint: 'https://hn.algolia.com/api/v1/search_by_date?tags=story&query=hiring+python+AI+MCP&hitsPerPage=8', fallbackQuery: 'hiring+python+AI+LLM', desc: 'Streams Who Is Hiring threads and top stories via hn.algolia.com/api/v1 and firebaseio.com.' },
      { id: 'kaggle_datasets', name: 'Kaggle Datasets & Competitions REST API v1', icon: 'database', endpoint: 'https://www.kaggle.com/api/v1/datasets/list', fallbackQuery: 'Kaggle+dataset+machine+learning+LLM+python', desc: 'Fetches trending CSV/JSON datasets & competitions from kaggle.com/api/v1/datasets/list.' }
    ];

    const TIME_PRESETS = [
      { id: '1h', label: 'Last 1 Hour', icon: 'zap', desc: 'Latest immediate run' },
      { id: '6h', label: 'Morning 6:00 AM', icon: 'sunrise', desc: 'Morning briefing window' },
      { id: '24h', label: 'Last 24 Hours', icon: 'clock', desc: 'Full daily activity' },
      { id: '7d', label: 'Last 7 Days', icon: 'calendar', desc: 'Weekly opportunities' },
      { id: '30d', label: 'Last 30 Days', icon: 'layers', desc: 'Monthly archive' },
      { id: 'all', label: 'All Time', icon: 'database', desc: 'Complete saved memory' }
    ];

    let JOBS_DATA = [
      { id: 'job-hw-1', domain: 'hardware', title: 'RTL Design & Verification Intern', company: 'NVIDIA', location: 'Bengaluru / Pune, India', source: 'Greenhouse', hiringEmail: 'university-recruiting@nvidia.com', url: 'https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite', skills: ['SystemVerilog', 'Verilog', 'RTL', 'ASIC', 'UVM', 'Python'], posted: '1h ago', directApplyReady: true },
      { id: 'job-hw-2', domain: 'hardware', title: 'Embedded Firmware & SoC Intern', company: 'Qualcomm', location: 'Hyderabad / Bengaluru', source: 'Greenhouse', hiringEmail: 'india-university@qualcomm.com', url: 'https://careers.qualcomm.com/careers', skills: ['Embedded C', 'RTOS', 'ARM', 'UART', 'SPI', 'Linux'], posted: '2h ago', directApplyReady: true },
      { id: 'job-hw-3', domain: 'hardware', title: 'Silicon Verification & FPGA Engineer Intern', company: 'AMD', location: 'Bengaluru / Hyderabad', source: 'Greenhouse', hiringEmail: 'careers@amd.com', url: 'https://careers.amd.com/careers-home', skills: ['Verilog', 'SystemVerilog', 'FPGA', 'Vivado', 'RISC-V'], posted: '3h ago', directApplyReady: true },
      { id: 'job-hw-4', domain: 'hardware', title: 'Analog, PCB & Mixed-Signal Hardware Intern', company: 'Texas Instruments', location: 'Bengaluru, India', source: 'Greenhouse', hiringEmail: 'university@ti.com', url: 'https://careers.ti.com/', skills: ['PCB', 'KiCad', 'LTSPICE', 'Embedded C', 'I2C', 'Oscilloscope'], posted: '4h ago', directApplyReady: true },
      { id: 'job-hw-5', domain: 'hardware', title: 'STM32 Firmware & IoT Applications Intern', company: 'STMicroelectronics', location: 'Greater Noida / Bengaluru', source: 'Wellfound', hiringEmail: 'careers.india@st.com', url: 'https://www.st.com/content/st_com/en/about/careers/careers.html', skills: ['STM32', 'FreeRTOS', 'Embedded C', 'CAN', 'SPI', 'Firmware'], posted: '5h ago', directApplyReady: true },
      { id: 'job-1', domain: 'software', title: 'AI Builder & Software Engineering Intern', company: 'Razorpay', location: 'Bengaluru, India', source: 'Ashby', hiringEmail: 'jobs@razorpay.com', url: 'https://razorpay.com/buildathon/', skills: ['Python', 'FastAPI', 'SQL', 'REST APIs', 'Git'], posted: '1h ago', directApplyReady: true },
      { id: 'job-2', title: 'AI Platform & MCP Engineering Intern', company: 'Postman', location: 'Bengaluru / Remote India', source: 'Greenhouse', hiringEmail: 'careers@postman.com', url: 'https://www.postman.com/company/careers/open-positions/', skills: ['Python', 'JavaScript', 'REST APIs', 'MCP', 'React'], posted: '2h ago', directApplyReady: true },
      { id: 'job-3', title: 'Research Engineer Intern (AI Systems & Inference)', company: 'Yotta Labs', location: 'Remote India', source: 'Ashby', hiringEmail: 'careers@yottalabs.ai', url: 'https://jobs.ashbyhq.com/yotta/09821a51-fbe6-42a7-a566-0d2b5d40fae3', skills: ['Python', 'PyTorch', 'REST APIs', 'Linux', 'Git'], posted: '3h ago', directApplyReady: true },
      { id: 'job-4', title: 'Backend Software Engineering Intern (AI Native)', company: 'Enterpret', location: 'Bengaluru, India', source: 'Ashby', hiringEmail: 'talent@enterpret.com', url: 'https://jobs.ashbyhq.com/enterpret', skills: ['Python', 'FastAPI', 'LangGraph', 'SQL', 'TypeScript'], posted: '4h ago', directApplyReady: true },
      { id: 'job-5', title: 'Software Developer Intern (SaaS Platform)', company: 'Zoho Corporation', location: 'Chennai / Coimbatore', source: 'Wellfound', hiringEmail: 'careers@zohocorp.com', url: 'https://www.zoho.com/careers/', skills: ['Python', 'JavaScript', 'SQL', 'React', 'Linux'], posted: '5h ago', directApplyReady: true },
      { id: 'job-6', title: 'AI Engineer Intern (LLM Agents & Evaluators)', company: 'Meraki Labs', location: 'Bengaluru / Remote', source: 'Ashby', hiringEmail: 'apply@merakilabs.com', url: 'https://jobs.ashbyhq.com/Meraki-Labs/93ff65d2-f0cd-4fd1-b76f-b2e350f2d6c8', skills: ['Python', 'LangGraph', 'REST APIs', 'SQL'], posted: '6h ago', directApplyReady: true },
      { id: 'job-7', title: 'Autonomous AI & Data Systems Intern', company: 'Karya', location: 'Bengaluru / Remote India', source: 'Ashby', hiringEmail: 'hiring@karya.in', url: 'https://karya.in/careers', skills: ['Python', 'FastAPI', 'SQLite', 'React', 'Git'], posted: '7h ago', directApplyReady: true },
      { id: 'job-8', title: 'Technical Intern (AI Agents for Enterprise)', company: 'Laminar', location: 'Remote India', source: 'Ashby', hiringEmail: 'team@laminar.dev', url: 'https://jobs.ashbyhq.com/laminar-jobs/b8bf92af-a213-4f50-a22c-4a2413c4ab87', skills: ['Python', 'React', 'REST APIs', 'Git'], posted: '8h ago', directApplyReady: true },
      { id: 'job-9', title: 'Software Engineer Intern (Python / FastAPI)', company: 'AiPrise', location: 'Bengaluru / Remote', source: 'Wellfound', hiringEmail: 'jobs@aiprise.com', url: 'https://www.ycombinator.com/companies/aiprise/jobs', skills: ['Python', 'FastAPI', 'React', 'SQL', 'REST APIs'], posted: '10h ago', directApplyReady: true },
      { id: 'job-10', title: 'Campus Graduate Engineer Trainee', company: 'Juspay', location: 'Bengaluru, India', source: 'Unstop', hiringEmail: 'careers@juspay.in', url: 'https://unstop.com/job-fairs', skills: ['Python', 'SQL', 'Algorithms', 'Git'], posted: '12h ago', directApplyReady: true },
      { id: 'job-11', title: 'Junior AI Systems Engineer', company: 'Stripe', location: 'Bengaluru, India', source: 'Greenhouse', hiringEmail: 'recruiting@stripe.com', url: 'https://stripe.com/jobs/search?office_locations=Asia+Pacific--Bengaluru', skills: ['Python', 'SQL', 'REST APIs', 'Git', 'Linux'], posted: '14h ago', directApplyReady: true },
      { id: 'job-12', title: 'Remote Python & Backend Developer', company: 'Remotive Partner Network', location: 'Remote Worldwide', source: 'Remotive', hiringEmail: 'jobs@remotive.com', url: 'https://remotive.com/remote-jobs/software-dev', skills: ['Python', 'React', 'TypeScript', 'SQL'], posted: '1d ago', directApplyReady: true }
    ];

    let FREE_APIS_DATA = [
      { id: 'api-1', name: 'Google AI Studio (Gemini API)', category: 'LLM & Multimodal', quota: 'Generous Free Tier (1M tokens/min)', features: ['Gemini 2.5 Flash', 'Multimodal Text & Vision', 'Structured JSON Output'], url: 'https://aistudio.google.com/docs/api-key' },
      { id: 'api-2', name: 'Groq Cloud High-Speed Inference', category: 'High-Throughput Inference', quota: 'Free Plan with 30 RPM', features: ['Llama 3.3 70B', 'Fast Inference (~500 t/s)', 'OpenAI-Compatible SDK'], url: 'https://console.groq.com/' },
      { id: 'api-3', name: 'OpenRouter Free Models', category: 'Multi-Model Gateway', quota: '25+ Completely Free Models', features: ['Free Model Router', 'OpenAI SDK Format', 'No Credit Card Needed'], url: 'https://openrouter.ai/models?max_price=0' },
      { id: 'api-4', name: 'Hugging Face Inference Providers', category: 'Model Hub API', quota: 'Free Serverless Community Tier', features: ['Transformers', 'Diffusers', 'Custom Endpoint Routing'], url: 'https://huggingface.co/docs/api-inference/' },
      { id: 'api-5', name: 'Cloudflare Workers AI', category: 'Edge Serverless AI', quota: '10,000 Neurons/Day Free', features: ['Serverless Llama', 'Whisper Speech-to-Text', 'Edge Fast Routing'], url: 'https://developers.cloudflare.com/workers-ai/' },
      { id: 'api-6', name: 'Mistral AI Platform', category: 'Reasoning & Coding', quota: 'Free Tier Enabled by Default', features: ['Codestral for Coding', 'Mistral Small & Nemo', 'Function Calling'], url: 'https://console.mistral.ai/' },
      { id: 'api-7', name: 'GitHub REST & GraphQL API', category: 'Developer Telemetry', quota: '5,000 Requests/Hour with Token', features: ['Repository Analytics', 'Workflow Runs', 'User Profiles'], url: 'https://docs.github.com/en/rest' },
      { id: 'api-8', name: 'Pollinations.ai Free Media API', category: 'Image Generation', quota: 'Completely Free (No Key Required)', features: ['Text-to-Image', 'Image-to-Image', 'OpenAI Format Compatible'], url: 'https://pollinations.ai/' }
    ];

    let TECH_PROJECTS_DATA = [
      { id: 'proj-1', title: 'Autonomous Multi-Agent Career & Job Applier', roleTrack: 'AI Agent Engineer', stack: ['Python', 'FastAPI', 'LangGraph', 'MCP', 'SQLite'], desc: 'Build an autonomous agent that scrapes corporate boards, extracts recruiter inboxes, tailors resumes to JD keywords, and dispatches tracked applications.', url: 'https://github.com/balu-cod/career-agent-system' },
      { id: 'proj-2', title: 'Model Context Protocol (MCP) High-Concurrency Server', roleTrack: 'AI Systems Architect', stack: ['Python', 'FastAPI', 'MCP SDK', 'AsyncIO'], desc: 'Standardized server connecting local SQL databases and APIs to AI coding assistants and agent runtimes.', url: 'https://github.com/modelcontextprotocol/python-sdk' },
      { id: 'proj-3', title: 'Production Inventory & Asset Shelf Tracker', roleTrack: 'Full Stack Python Developer', stack: ['Python', 'FastAPI', 'React', 'SQL', 'Docker'], desc: 'Real-world system digitizing manufacturing workflows, physical barcode lookups, and inventory audits (similar to Aditya Birla TIMS).', url: 'https://github.com/zhanymkanov/fastapi-best-practices' },
      { id: 'proj-4', title: 'High-Throughput Continuous LLM Batching Server', roleTrack: 'Inference Infrastructure Engineer', stack: ['Python', 'CUDA/C++', 'vLLM', 'PyTorch'], desc: 'Optimizing inference speed, KV-cache management, and PagedAttention for production open-source model serving.', url: 'https://github.com/vllm-project/vllm' }
    ];

    let CONTESTS_DATA = [
      { id: 'c-hw-1', title: 'Smart India Hackathon — Hardware & Robotics Edition', platform: 'SIH / MoE', prize: 'INR 1,00,000 + Hardware Grant', deadline: 'Open Now', tags: ['Embedded C', 'STM32', 'PCB', 'IoT'], url: 'https://www.sih.gov.in/' },
      { id: 'c-hw-2', title: 'RISC-V International Silicon & FPGA Design Challenge', platform: 'GitHub / RISC-V', prize: 'Dev Kits + Silicon Internship PPI', deadline: 'Open Globally', tags: ['SystemVerilog', 'RISC-V', 'FPGA', 'RTL'], url: 'https://riscv.org/community/learn/' },
      { id: 'c-1', title: 'Razorpay AI Buildathon — Verification & Autonomous Builders', platform: 'Unstop', prize: 'INR 10,00,000 + 6-12 Mo Internships', deadline: 'Open Now', tags: ['AI Agents', 'Python', 'FastAPI'], url: 'https://razorpay.com/buildathon/' },
      { id: 'c-2', title: 'Unstop India AI & Agentic Engineering Hackathon', platform: 'Unstop', prize: 'INR 5,00,000 + PPIs', deadline: '14 Days Left', tags: ['AI Agents', 'Python', 'FastAPI'], url: 'https://unstop.com/hackathons' },
      { id: 'c-3', title: 'Flipkart GRiD — Software Development Track', platform: 'Unstop', prize: 'INR 6,00,000 + Internship', deadline: 'Open Now', tags: ['Backend', 'Python', 'React'], url: 'https://unstop.com/competitions' },
      { id: 'c-4', title: 'Global MCP & LangGraph Agent Builders Challenge', platform: 'Devpost', prize: 'USD 25,000 Prize Pool', deadline: 'Global Online', tags: ['MCP', 'LangGraph', 'LLMs'], url: 'https://devpost.com/hackathons' },
      { id: 'c-5', title: 'Kaggle Community AI Agents Benchmark Hackathon', platform: 'Kaggle', prize: 'USD 50,000 + Medals', deadline: 'Open Globally', tags: ['Python', 'Evaluation', 'LLMs'], url: 'https://www.kaggle.com/competitions' },
      { id: 'c-6', title: 'LeetCode Weekly Algorithmic Contest', platform: 'LeetCode', prize: 'Global Ranking', deadline: 'Every Sunday 8:00 AM', tags: ['DSA', 'Python', 'Algorithms'], url: 'https://leetcode.com/contest/' },
      { id: 'c-7', title: 'HackerEarth India Product Startup Hiring Challenge', platform: 'HackerEarth', prize: 'Direct Intern & FTE Offers', deadline: 'Remote India', tags: ['Python', 'SQL', 'APIs'], url: 'https://www.hackerearth.com/challenges/' },
      { id: 'c-8', title: 'Juspay Engineering Hiring Challenge', platform: 'Unstop', prize: 'INR 40,000/mo Stipend + PPO', deadline: 'Bengaluru', tags: ['Systems', 'Backend'], url: 'https://unstop.com/job-fairs' }
    ];

    let CERTS_DATA = [
      { id: 'cert-hw-1', title: 'NPTEL Digital System Design with Verilog HDL & FPGA', provider: 'IIT / NPTEL', category: 'ECE, VLSI & RTL', cost: 'Free Audit / Exam Cert', skills: ['Verilog', 'FPGA', 'Digital Logic', 'RTL'], url: 'https://nptel.ac.in/' },
      { id: 'cert-hw-2', title: 'ARM Cortex-M Embedded Systems & FreeRTOS Firmware', provider: 'edX / UT Austin', category: 'Embedded & Hardware', cost: 'Free Audit Track', skills: ['Embedded C', 'ARM', 'FreeRTOS', 'UART'], url: 'https://www.edx.org/' },
      { id: 'cert-1', title: 'Hugging Face AI Agents Course', provider: 'Hugging Face', category: 'AI & LLMs', cost: 'Free Official Certificate', skills: ['AI Agents', 'LangGraph', 'MCP'], url: 'https://huggingface.co/learn/agents-course' },
      { id: 'cert-2', title: 'LangChain Academy: Introduction to LangGraph', provider: 'LangChain', category: 'AI & LLMs', cost: 'Free Official Course', skills: ['LangGraph', 'Stateful Agents'], url: 'https://academy.langchain.com/' },
      { id: 'cert-3', title: 'DeepLearning.AI: Building Systems with the ChatGPT API', provider: 'DeepLearning.AI', category: 'AI & LLMs', cost: 'Free Course', skills: ['LLMs', 'Prompt Engineering', 'Python'], url: 'https://www.deeplearning.ai/short-courses/' },
      { id: 'cert-4', title: 'CS50 Introduction to Programming with Python', provider: 'Harvard / edX', category: 'Python & Backend', cost: 'Free Track', skills: ['Python', 'Testing', 'OOP'], url: 'https://cs50.harvard.edu/python/' },
      { id: 'cert-5', title: 'Scientific Computing & Backend APIs with Python', provider: 'freeCodeCamp', category: 'Python & Backend', cost: 'Free Certification', skills: ['Python', 'APIs'], url: 'https://www.freecodecamp.org/learn/' },
      { id: 'cert-6', title: 'AWS Cloud Practitioner & Bedrock Foundations', provider: 'AWS Skill Builder', category: 'Cloud & DevOps', cost: 'Free Digital Badge', skills: ['AWS', 'Cloud Architecture'], url: 'https://explore.skillbuilder.aws/' },
      { id: 'cert-7', title: 'Google Cloud Generative AI Leader Path', provider: 'Google Cloud', category: 'Cloud & DevOps', cost: 'Free Skill Badge', skills: ['GenAI', 'Vertex AI'], url: 'https://www.cloudskillsboost.google/' },
      { id: 'cert-8', title: 'Full Stack Open — Deep Dive to Modern Web Development', provider: 'University of Helsinki', category: 'Python & Backend', cost: 'Free ECTS Certificate', skills: ['React', 'TypeScript', 'Node.js', 'SQL'], url: 'https://fullstackopen.com/en/' }
    ];

    let AI_NEWS_DATA = [
      { title: 'Model Context Protocol (MCP) Python SDK — Standardized Tool Routing for AI Agents', source: 'GitHub Trending', time: '1h ago', url: 'https://github.com/modelcontextprotocol/python-sdk' },
      { title: 'LangGraph Multi-Agent Orchestration: Stateful Python Workflows', source: 'LangChain Blog', time: '2h ago', url: 'https://blog.langchain.dev/langgraph/' },
      { title: 'Hugging Face Open-Source LLM & Agentic Evaluation Benchmarks', source: 'Hugging Face', time: '3h ago', url: 'https://huggingface.co/blog' },
      { title: 'FastAPI High-Concurrency Async Patterns for Production AI Microservices', source: 'FastAPI', time: '4h ago', url: 'https://fastapi.tiangolo.com/' },
      { title: 'Open-Source AI Autonomous Agents Directory — Frameworks & Tools Breakdown', source: 'GitHub Trending', time: '5h ago', url: 'https://github.com/e2b-dev/awesome-ai-agents' },
      { title: 'System Design Primer: Scalable Distributed Systems Architecture in Python', source: 'GitHub', time: '6h ago', url: 'https://github.com/donnemartin/system-design-primer' },
      { title: 'vLLM & Continuous Batching: High-Throughput Open LLM Serving Architecture', source: 'GitHub Trending', time: '7h ago', url: 'https://github.com/vllm-project/vllm' },
      { title: 'Show HN: Autonomous Coding & Career Discovery Agents in Python', source: 'Hacker News', time: '8h ago', url: 'https://news.ycombinator.com/show' }
    ];

    let YOUTUBE_VIDEOS_DATA = [
      { title: 'MCP & Agentic AI Engineering — Full Architecture Breakdown', channel: 'Fireship', duration: '11:24', url: 'https://www.youtube.com/@Fireship/videos' },
      { title: 'Reasoning LLMs & Autonomous Tool Use: What Changed This Week', channel: 'AI Explained', duration: '18:40', url: 'https://www.youtube.com/@aiexplained-official/videos' },
      { title: 'Production Python Backend Architecture with FastAPI & Clean Design', channel: 'ArjanCodes', duration: '22:15', url: 'https://www.youtube.com/@ArjanCodes/videos' },
      { title: 'Complete LangGraph & Python AI Agents Course', channel: 'freeCodeCamp.org', duration: '3:45:10', url: 'https://www.youtube.com/@freecodecamp/videos' },
      { title: 'Docker, Kubernetes & CI/CD Pipeline Setup for Python Services', channel: 'TechWorld with Nana', duration: '42:18', url: 'https://www.youtube.com/@TechWorldwithNana/videos' },
      { title: 'Why Minimalist Codebases & Fast Systems Win in Production', channel: 'ThePrimeagen', duration: '19:05', url: 'https://www.youtube.com/@ThePrimeagen/videos' },
      { title: 'AI Tools & Open-Source Agent Releases This Week', channel: 'Matt Wolfe', duration: '24:30', url: 'https://www.youtube.com/@mreflow/videos' },
      { title: 'Full Stack Python, FastAPI & React Project Roadmap', channel: 'CodeWithHarry', duration: '54:12', url: 'https://www.youtube.com/@CodeWithHarry/videos' }
    ];

    let MATERIALS_DATA = [
      { id: 'mat-1', title: 'System Design Primer', author: 'Donne Martin', category: 'System Design', tags: ['Architecture', 'Distributed Systems', 'Flashcards'], desc: 'Comprehensive guide to designing large-scale software systems and interview prep with interactive Anki cards.', url: 'https://github.com/donnemartin/system-design-primer' },
      { id: 'mat-2', title: 'FastAPI Production Best Practices', author: 'zhanymkanov', category: 'Backend Architecture', tags: ['FastAPI', 'Pydantic', 'Async', 'Project Layout'], desc: 'Opinionated conventions and battle-tested architecture patterns from production startup backends.', url: 'https://github.com/zhanymkanov/fastapi-best-practices' },
      { id: 'mat-3', title: 'Awesome AI Autonomous Agents', author: 'e2b-dev', category: 'AI & LLMs', tags: ['Agent Frameworks', 'LangGraph', 'MCP', 'Evaluation'], desc: 'Curated directory of autonomous AI agents, multi-agent frameworks, tool protocols, and runtimes.', url: 'https://github.com/e2b-dev/awesome-ai-agents' },
      { id: 'mat-4', title: 'Full Stack Python Architecture Guide', author: 'Matt Makai', category: 'Python & Backend', tags: ['Python', 'WSGI/ASGI', 'Databases', 'Deployment'], desc: 'Comprehensive explanations of web frameworks, database ORMs, caching, and server deployment in Python.', url: 'https://www.fullstackpython.com/' },
      { id: 'mat-5', title: 'NeetCode 150 Coding Interview Roadmap', author: 'NeetCode', category: 'Data Structures & Algorithms', tags: ['DSA', 'Python', 'Blind 75', 'Patterns'], desc: 'Structured algorithmic problem sets grouped by patterns (Two Pointers, Sliding Window, Trees, Graphs, DP).', url: 'https://neetcode.io/practice' },
      { id: 'mat-6', title: 'Model Context Protocol (MCP) Official Documentation', author: 'Anthropic / Open Source', category: 'AI & LLMs', tags: ['MCP', 'Tools', 'Resources', 'Prompts'], desc: 'The open standard for connecting AI models to local files, development tools, and external APIs.', url: 'https://modelcontextprotocol.io/' },
      { id: 'mat-7', title: 'React Official Hands-On Documentation & Patterns', author: 'Meta Open Source', category: 'Frontend', tags: ['React', 'Hooks', 'State Management', 'Components'], desc: 'Modern interactive React guide covering component state, effect cleanup, and reactive data fetching.', url: 'https://react.dev/learn' },
      { id: 'mat-8', title: 'SQL & Database Indexing Internals', author: 'Markus Winand', category: 'Databases', tags: ['SQL', 'B-Tree', 'Indexes', 'Query Optimization'], desc: 'In-depth guide to understanding database indexes, execution plans, and query performance in SQL.', url: 'https://use-the-index-luke.com/' }
    ];

    let TRACKER_ITEMS = [
      { id: 'tr-1', company: 'Razorpay', role: 'AI Builder & Software Engineering Intern', stage: 'Applied', updated: 'Today' },
      { id: 'tr-2', company: 'Postman', role: 'AI Platform & MCP Intern', stage: 'Interviewing', updated: 'Today' },
      { id: 'tr-3', company: 'Enterpret', role: 'Backend Software Engineering Intern', stage: 'Saved', updated: 'Yesterday' },
      { id: 'tr-4', company: 'Zoho Corporation', role: 'Software Developer Intern', stage: 'Applied', updated: '2d ago' },
      { id: 'tr-5', company: 'Aditya Birla Garments Ltd', role: 'Software Developer Intern (Completed — TIMS & Shelf Tracker)', stage: 'Offer', updated: 'Completed' }
    ];

    // RAG VECTORS & SEMANTIC KNOWLEDGE STORE
    let RAG_KNOWLEDGE_CHUNKS = [];


    // MULTI-THEME MANAGEMENT & VISUAL SYSTEM
    // =========================================================================
    const THEME_NAMES = {
      'ece': 'ECE Silicon Workbench',
      'obsidian': 'Obsidian Linear',
      'emerald': 'Emerald Mission Control',
      'nordic': 'Nordic Frost',
      'cyberpunk': 'Cyberpunk Horizon',
      'sapphire': 'Royal Sapphire & Gold'
    };

    function applyTheme(themeKey) {
      if (!THEME_NAMES[themeKey]) themeKey = 'ece';
      
      const themeClasses = ['theme-ece', 'theme-obsidian', 'theme-emerald', 'theme-nordic', 'theme-cyberpunk', 'theme-sapphire'];
      themeClasses.forEach(cls => document.body.classList.remove(cls));

      // Nordic is a light theme; the other 5 are dark themes (including ECE Silicon Workbench)
      if (themeKey === 'nordic') {
        document.documentElement.classList.remove('dark');
        document.body.classList.remove('dark');
      } else {
        document.documentElement.classList.add('dark');
        document.body.classList.add('dark');
      }

      document.body.classList.add('theme-' + themeKey);
      try { localStorage.setItem('cas-theme-v2', themeKey); } catch (e) {}

      // Update badge in header
      const headerLabel = document.getElementById('active-theme-label');
      if (headerLabel) headerLabel.innerText = THEME_NAMES[themeKey];

      // Update active badge in Theme Studio view
      const studioBadge = document.getElementById('active-theme-badge-name');
      if (studioBadge) studioBadge.innerText = THEME_NAMES[themeKey] + ' Active';

      // Update cards highlighting in Theme Studio
      document.querySelectorAll('.theme-showcase-card').forEach(card => {
        const isCurrent = card.id === 'theme-card-' + themeKey;
        card.classList.toggle('active-theme-card', isCurrent);
        const icon = card.querySelector('.active-check-icon');
        if (icon) icon.classList.toggle('hidden', !isCurrent);
      });

      closeThemeGalleryModal();
      logLine(`[Theme Studio] Applied ${THEME_NAMES[themeKey]} visual design system across entire application.`, 'text-purple-400 font-semibold');
      showToast(`Activated ${THEME_NAMES[themeKey]} theme!`, 'success');
      refreshLucideIcons();
    }
    window.applyTheme = applyTheme;

    function openThemeGalleryModal() {
      const modal = document.getElementById('theme-gallery-modal');
      if (modal) modal.classList.remove('hidden');
      refreshLucideIcons();
    }
    window.openThemeGalleryModal = openThemeGalleryModal;

    function closeThemeGalleryModal() {
      const modal = document.getElementById('theme-gallery-modal');
      if (modal) modal.classList.add('hidden');
    }
    window.closeThemeGalleryModal = closeThemeGalleryModal;
