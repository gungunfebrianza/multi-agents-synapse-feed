<!-- source row_id: api-f224d5af -->

Title: Permission-Timed Contract Firewall

Thesis:
The right buildable defense is a browser extension that requests site access only at signing time, classifies smart-contract risk from typed-signature and approval semantics, and enforces security by shrinking both extension privilege and contract-authority exposure at the same moment; anything less leaves the browser and the chain as separate attack surfaces instead of one defended system.

The System:
Build a signing firewall as a browser extension whose core action is not constant page surveillance but permission-timed intervention.

First constraint: the browser extension layer cannot rely on old-style omniscient interception. In Chrome MV3, blocking through `chrome.webRequest` is no longer available to normal extensions, and most interception is pushed to `declarativeNetRequest` while host action still requires granted host access [Chrome Extensions docs: chrome.webRequest API; Chrome Extensions docs: chrome.declarativeNetRequest API]. In Firefox, runtime host grants through `optional_host_permissions` control privileged API use such as `webRequest`, `cookies`, and `tabs`, and users can later revoke those grants [MDN: optional_host_permissions; MDN: permissions; MDN: webRequest]. Programmatic injection also requires `activeTab` or host permissions, and MV3 content scripts cannot use host permissions for cross-origin fetches the same way extension pages can [MDN: Content scripts].

Those constraints define the architecture. The extension should stay unprivileged by default, ask for host access only when a wallet flow starts, and use that brief access window to inspect the dapp context and signing request. That directly applies Google’s documented mitigation of limiting extension site access to reduce credential theft and transaction tampering exposure [Google Online Security Blog: Staying Safe with Chrome Extensions]. It also aligns with Chrome’s runtime host-access model [Chrome Extensions docs: chrome.declarativeNetRequest API].

Second constraint: the security model must assume the extension ecosystem itself is hostile. Google documents harmful-extension detection through Safety Check, Safe Browsing, Enhanced Protection, and periodic review of what extensions actually do over time versus their stated objectives [Google Online Security Blog: Staying Safe with Chrome Extensions; Google Chrome Safe Browsing blog; Chrome Browser Strategic Security Layer technical paper]. Google also states that over 70% of malicious or policy-violating extensions blocked from the Chrome Web Store contained obfuscated code, and store policy prohibits obfuscation while requiring MV3 functionality to be discernible from submitted code [Google Online Security Blog: Trustworthy Chrome Extensions, by Default; Chrome Web Store Program Policies]. MV3 submissions must have fully reviewable packaged functionality, remote hosted code used to execute logic is prohibited, and obfuscated code is disallowed [Chrome Web Store Program Policies; Chrome Extensions docs: Deal with remote hosted code violations; EIP-6963].

That means the firewall’s risk engine should be packaged, reviewable, and local-first. It should not depend on hidden server-side logic. If it uses external simulation, it must label that dependency as supplemental, because MetaMask’s estimated balance changes rely on a centralized MetaMask server for simulation [MetaMask Help Center: What are estimated balance changes?]. The extension can still use simulation as an added signal, but never as the sole basis for a safe/unsafe decision.

Third constraint: the smart-contract layer carries risks that ordinary browser security UI does not express. EIP-712 improves structured readability for off-chain messages but does not include replay protection [EIP-712: Typed structured data hashing and signing]. ERC-2612 replaces an on-chain approve with an off-chain signature, reducing one transaction step while creating a signature-risk surface in the browser flow [EIP-2612: Permit Extension for EIP-20 Signed Approvals]. MetaMask states that disconnecting a dapp does not revoke token approvals [MetaMask Help Center: User guide: dapps]. MetaMask Smart Transactions adds safety and MEV protection only on supported networks and flows, leaving gaps elsewhere [MetaMask Help Center: What is 'Smart Transactions'?; MetaMask Help Center: Transactions].

So the extension’s contract firewall should do three concrete things during that temporary permission window:

1. Detect signature class.
   Separate plain transactions, EIP-712 typed messages, and ERC-2612 permit-style approvals, because they create different downstream authority [EIP-712: Typed structured data hashing and signing; EIP-2612: Permit Extension for EIP-20 Signed Approvals].

2. Translate wallet actions into authority persistence.
   If the action grants spending authority, show that disconnection will not revoke it, because MetaMask documents that disconnecting a dapp does not affect token approvals [MetaMask Help Center: User guide: dapps].

3. Bind browser permission to contract risk.
   High-risk pages get host access only for the active signing event, not permanently. This uses extension-site-access minimization as a security control [Google Online Security Blog: Staying Safe with Chrome Extensions] and matches the browser’s actual privilege model [Chrome Extensions docs: chrome.declarativeNetRequest API; MDN: optional_host_permissions].

This recombination is adversarial because it treats the dapp page, the extension store, and the signed payload as one attack chain. A fake wallet extension can capture a recovery phrase through store impersonation [Google Chrome Community thread: Fake Chrome extensions (Jun 11, 2026)]. Malware can exfiltrate data from Chrome and MetaMask [ESET APT Activity Report Q4 2024–Q1 2025]. A typed signature can still be replay-prone if the app’s anti-replay design is weak [EIP-712: Typed structured data hashing and signing]. The system answers all three by reducing standing extension power, exposing contract authority before signature, and making every defense auditable under store policy.

Interdependence proof:
- Remove browser extension: There is no runtime host-permission gate, no page-context inspection at the moment of signing, and no way to apply Google’s site-access minimization guidance as an active control inside the wallet flow [Google Online Security Blog: Staying Safe with Chrome Extensions; Chrome Extensions docs: chrome.declarativeNetRequest API; MDN: optional_host_permissions].
- Remove security: The system collapses into a convenience tool. Without anti-obfuscation, packaged reviewability, and harmful-extension assumptions, the same mechanism becomes a privileged interception point that attackers can imitate or subvert; that risk is documented by Google’s extension-abuse controls and the prevalence of obfuscated malicious extensions [Google Online Security Blog: Trustworthy Chrome Extensions, by Default; Chrome Web Store Program Policies].
- Remove smart contract: The extension can restrict hosts but cannot distinguish harmless site interaction from replay-prone EIP-712 signatures, permit-based authority grants, or approvals that persist after disconnect. Then it fails at the exact place where wallet users lose funds: contract authority, not just page access [EIP-712: Typed structured data hashing and signing; EIP-2612: Permit Extension for EIP-20 Signed Approvals; MetaMask Help Center: User guide: dapps].

Failure mode:
A malicious extension that looks legitimate still bypasses this design if the user installs the attacker’s extension instead of the defender, which matches the documented fake-wallet-store pattern [Google Chrome Community thread: Fake Chrome extensions (Jun 11, 2026)].
Endpoint malware that exfiltrates browser and MetaMask data defeats browser-layer controls entirely, which is already documented in recent operations [ESET APT Activity Report Q4 2024–Q1 2025].

Open question:
How far can a fully packaged, reviewable MV3 extension infer replay risk and persistent approval danger from EIP-712 and ERC-2612 signing flows without relying on centralized simulation services that are incomplete or unavailable on some networks [EIP-712: Typed structured data hashing and signing; EIP-2612: Permit Extension for EIP-20 Signed Approvals; MetaMask Help Center: What are estimated balance changes?; MetaMask Help Center: What is 'Smart Transactions'?; MetaMask Help Center: Transactions]?