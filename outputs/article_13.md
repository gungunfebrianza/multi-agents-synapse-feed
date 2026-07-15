<!-- source row_id: api-1fabcbbe -->

Title: Context-Firewalled Browser Agents

Thesis:
Browser security primitives must become the execution substrate for LLM agents, not a wrapper around them. A buildable agent should run each web task inside isolated browser contexts, traverse only explicit browsing-context trees, and escalate to human supervision at security boundaries, because prompt injection is a primary agent risk and browser-native isolation already defines the strongest enforceable limits on session, storage, and cross-origin access [MDN WebDriver BiDi browser module; MDN browser.setDownloadBehavior command][MDN WebDriver BiDi browsingContext module][MDN Same-origin policy][OpenAI: Operator System Card][OWASP GenAI Security Project: LLM01:2025 Prompt Injection; OWASP AI Agent Security Cheat Sheet; OpenAI Deployment Safety Hub: ChatGPT Agent Watch Mode].

The System:
Build one agent runtime that binds three layers into a single control loop.

1. **Browser layer: per-task isolation as the default**
   WebDriver BiDi’s browser module exposes user-context isolation, where tabs in the same user context share cookies and session data, and tabs in different user contexts are completely isolated [MDN WebDriver BiDi browser module; MDN browser.setDownloadBehavior command].  
   The agent should place each delegated task in its own user context. That makes “research a vendor site,” “open webmail,” and “access billing” separate session islands by construction. The same module also exposes `setDownloadBehavior`, so downloads can be explicitly directed instead of handled implicitly [MDN WebDriver BiDi browser module; MDN browser.setDownloadBehavior command].

2. **Navigation layer: explicit context-tree control**
   WebDriver BiDi models automation around browsing contexts: top-level contexts are tabs/windows, child contexts are iframes/popups, and the automation stack can enumerate this tree with `browsingContext.getTree` [MDN WebDriver BiDi browsingContext module].  
   The agent should never treat “the page” as a flat surface. It should reason over the actual tree and apply separate trust to top-level documents, iframes, and popups. This matters because prompt injection can arrive from embedded or spawned content just as easily as from the main page [OpenAI: Operator System Card][NIST Technical Blog: Strengthening AI Agent Hijacking Evaluations].

3. **Security layer: trust boundaries mapped to browser boundaries**
   The same-origin policy blocks one origin’s script from freely interacting with another origin’s resources, and origin checks still apply for APIs including `localStorage`, `indexedDB`, `BroadcastChannel`, and `SharedWorker` [MDN Same-origin policy].  
   Chrome storage partitioning changed in Chrome 115 so that when site A embeds site B in an iframe, site B does not get the same storage it would have in a first-party tab [Chrome for Developers: Storage and cookies].  
   COOP can place top-level documents into different browsing context groups, and COEP plus COOP are required for cross-origin isolation [MDN Browsing context glossary; MDN COOP header; MDN COEP header].  
   The agent runtime should use these facts as policy primitives: embedded cross-site content gets less trust than first-party tabs, state is scoped to origin and partition, and cross-origin-isolated or separate browsing-context-group pages are treated as hard execution boundaries, not mere UI variations [MDN Same-origin policy][Chrome for Developers: Storage and cookies][MDN Browsing context glossary; MDN COOP header; MDN COEP header].

4. **Agent layer: capable enough to matter, structured enough to constrain**
   OpenAI’s CUA is already positioned for browser automation workflows like QA and data entry through the Responses API computer use tool [OpenAI: New tools for building agents]. It reported 58.1% on WebArena and 87% on WebVoyager, and newer browser-agent results reached 67.3% on WebArena-Verified and 92.8% on Online-Mind2Web [OpenAI: Computer-Using Agent][OpenAI: Introducing GPT-5.4].  
   These numbers establish that browser agents are operationally capable enough to touch real systems, which means browser-native containment is mandatory rather than optional [OpenAI: Computer-Using Agent][OpenAI: Introducing GPT-5.4].

5. **Defense layer: prompt-injection handling tied to supervision**
   Prompt injection is a core browser-agent risk; OpenAI reports final-model susceptibility of 23% on a 31-scenario prompt-injection eval, versus 62% with no mitigations and 47% with prompting alone [OpenAI: Operator System Card]. OpenAI also added a prompt-injection monitor with 99% recall and 90% precision on a 77-example red-team set [OpenAI: Operator System Card]. NIST defines agent hijacking as indirect prompt injection via ingested data, and OWASP classifies prompt injection as LLM01:2025 while naming websites, documents, and emails as primary indirect sources [NIST Technical Blog: Strengthening AI Agent Hijacking Evaluations][OWASP GenAI Security Project: LLM01:2025 Prompt Injection; OWASP AI Agent Security Cheat Sheet; OpenAI Deployment Safety Hub: ChatGPT Agent Watch Mode].  
   Therefore the runtime should do three things:
   - run a prompt-injection monitor on every browsed context [OpenAI: Operator System Card];
   - trigger watch-mode-style pauses on sensitive surfaces when the user becomes inactive or leaves the page [OpenAI: Introducing Operator; OpenAI: Operator System Card; OpenAI Deployment Safety Hub: ChatGPT Agent Watch Mode];
   - require takeover mode for credentials and payments [OpenAI: Introducing Operator; OpenAI: Operator System Card; OpenAI Deployment Safety Hub: ChatGPT Agent Watch Mode].

6. **Abuse reduction outside the page**
   OpenAI states ChatGPT agent disables memory at launch and restricts terminal network requests to reduce exfiltration and abuse [OWASP GenAI Security Project: LLM01:2025 Prompt Injection; OWASP AI Agent Security Cheat Sheet; OpenAI Deployment Safety Hub: ChatGPT Agent Watch Mode].  
   That policy fits this architecture: if a browser context is compromised by indirect prompt injection, the blast radius is limited not only by browser context isolation and origin boundaries, but also by reduced long-term memory carryover and constrained terminal egress [MDN WebDriver BiDi browser module; MDN browser.setDownloadBehavior command][MDN Same-origin policy][OWASP GenAI Security Project: LLM01:2025 Prompt Injection; OWASP AI Agent Security Cheat Sheet; OpenAI Deployment Safety Hub: ChatGPT Agent Watch Mode].

7. **Evaluation layer: test on the live web, not only benchmarks**
   BrowserArena introduced live open-web evaluation with user-submitted tasks and step-level human feedback, and WAREX focused on reliability across WebArena, WebVoyager, and REAL [arXiv: BrowserArena: Evaluating LLM Agents on Real-World Web Navigation Tasks; arXiv: WAREX: Web Agent Reliability Evaluation on Existing Benchmarks].  
   This system should be evaluated on both capability and containment: not just whether the agent completes tasks, but whether user-context isolation, browsing-context-tree awareness, and supervision gates prevent task crossover and hijack propagation [MDN WebDriver BiDi browser module; MDN browser.setDownloadBehavior command][MDN WebDriver BiDi browsingContext module][arXiv: BrowserArena: Evaluating LLM Agents on Real-World Web Navigation Tasks; arXiv: WAREX: Web Agent Reliability Evaluation on Existing Benchmarks].

Interdependence proof:
- Remove browser: the system loses enforceable user-context isolation, explicit browsing-context trees, download control, origin-scoped storage rules, and COOP/COEP boundary handling, so “security” collapses into prompts and classifiers without hard execution limits [MDN WebDriver BiDi browser module; MDN browser.setDownloadBehavior command][MDN WebDriver BiDi browsingContext module][MDN Same-origin policy][MDN Browsing context glossary; MDN COOP header; MDN COEP header].
- Remove LLM Agents: the system no longer needs dynamic delegation, web reasoning, or computer-use orchestration; it becomes ordinary browser automation and never faces the central threat of agent hijacking through interpreted web content [OpenAI: New tools for building agents][NIST Technical Blog: Strengthening AI Agent Hijacking Evaluations].
- Remove security: the system becomes an uncontained browser operator despite documented prompt-injection risk, known agent-hijacking pathways, and the need for watch mode, takeover mode, memory limits, and network restrictions [OpenAI: Operator System Card][NIST Technical Blog: Strengthening AI Agent Hijacking Evaluations][OWASP GenAI Security Project: LLM01:2025 Prompt Injection; OWASP AI Agent Security Cheat Sheet; OpenAI Deployment Safety Hub: ChatGPT Agent Watch Mode].

Failure mode:
A malicious instruction inside an iframe or email causes the agent to open a new context that appears task-related, then steers actions before takeover mode triggers.  
If the runtime fails to bind prompt monitoring and supervision to the actual browsing-context tree, isolation exists on paper but the hijack still lands operationally [MDN WebDriver BiDi browsingContext module][OpenAI: Operator System Card].

Open question:
How should a browser agent convert live browsing-context structure, storage partition state, and same-origin boundaries into a real-time trust score that reliably blocks indirect prompt injection without reducing task success on open-web evaluations like BrowserArena and WAREX [MDN WebDriver BiDi browsingContext module][Chrome for Developers: Storage and cookies][MDN Same-origin policy][arXiv: BrowserArena: Evaluating LLM Agents on Real-World Web Navigation Tasks; arXiv: WAREX: Web Agent Reliability Evaluation on Existing Benchmarks]?